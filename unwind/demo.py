"""The 20-second Unwind demo (``PROJECT.md`` §13), runnable with zero infra.

An agent overwrites a config file, deletes a page, drops a database table, and
sends an email. The human types ``undo``. Three actions are reversed; the email
is honestly flagged *"couldn't be undone — here's why I should have asked."*
That last line is the whole thesis in one screen, and it's honest.

Runs against an in-process upstream so it needs no external server — the exact
same engine code path that production uses over real MCP.
"""

from __future__ import annotations

import anyio
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from unwind.engine import ReversibilityEngine
from unwind.types import EnvironmentDescriptor, ToolSpec, UndoOutcome
from unwind.undolog.store import UndoLog
from unwind.upstream import InProcessUpstream

console = Console()


def _build_sandbox() -> InProcessUpstream:
    up = InProcessUpstream("workspace")
    up.state = {
        "files": {"deploy.yaml": "replicas: 3\nregion: us-east"},
        "pages": {"pg_onboarding": "Onboarding Guide"},
        "trash": {},
        "tables": {"sessions": {"schema": "id, user, ts", "rows": 42}},
        "dropped": {},
        "sent": [],
    }

    def get_file(a, s):
        return {"path": a["path"], "content": s["files"].get(a["path"])}

    def write_file(a, s):
        s["files"][a["path"]] = a["content"]
        return {"path": a["path"]}

    def get_page(a, s):
        return {"id": a["id"], "title": s["pages"].get(a["id"])}

    def delete_page(a, s):
        s["trash"][a["id"]] = s["pages"].pop(a["id"], None)
        return {"id": a["id"]}

    def restore_page(a, s):
        if a["id"] in s["trash"]:
            s["pages"][a["id"]] = s["trash"].pop(a["id"])
        return {"id": a["id"]}

    def get_table(a, s):
        t = s["tables"].get(a["id"], {})
        return {"id": a["id"], "schema": t.get("schema"), "rows": t.get("rows")}

    def drop_table(a, s):
        s["dropped"][a["id"]] = s["tables"].pop(a["id"], None)
        return {"id": a["id"]}

    def restore_table(a, s):
        if a["id"] in s["dropped"]:
            s["tables"][a["id"]] = s["dropped"].pop(a["id"])
        return {"id": a["id"]}

    def send_email(a, s):
        s["sent"].append(a)
        return {"queued": True}

    id_in = {"properties": {"id": {"type": "string"}}}
    id_out = {"properties": {"id": {"type": "string"}}}
    up.register(
        ToolSpec(
            server="workspace",
            name="get_file",
            input_schema={"properties": {"path": {"type": "string"}}},
            output_schema={"properties": {"content": {"type": "string"}}},
        ),
        get_file,
    )
    up.register(
        ToolSpec(
            server="workspace",
            name="write_file",
            input_schema={
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}}
            },
        ),
        write_file,
    )
    up.register(
        ToolSpec(
            server="workspace",
            name="get_page",
            input_schema=id_in,
            output_schema={"properties": {"title": {"type": "string"}}},
        ),
        get_page,
    )
    up.register(
        ToolSpec(server="workspace", name="delete_page", input_schema=id_in, output_schema=id_out),
        delete_page,
    )
    up.register(ToolSpec(server="workspace", name="restore_page", input_schema=id_in), restore_page)
    up.register(
        ToolSpec(
            server="workspace",
            name="get_table",
            input_schema=id_in,
            output_schema={
                "properties": {"schema": {"type": "string"}, "rows": {"type": "integer"}}
            },
        ),
        get_table,
    )
    up.register(
        ToolSpec(server="workspace", name="drop_table", input_schema=id_in, output_schema=id_out),
        drop_table,
    )
    up.register(
        ToolSpec(server="workspace", name="restore_table", input_schema=id_in), restore_table
    )
    up.register(
        ToolSpec(
            server="workspace",
            name="send_email",
            input_schema={"properties": {"to": {"type": "string"}, "body": {"type": "string"}}},
        ),
        send_email,
    )
    return up


async def run_demo() -> int:
    up = _build_sandbox()
    # A workspace with trash/version recovery — so deletes are compensable.
    env = EnvironmentDescriptor(name="workspace", has_trash=True, versioned=True)
    eng = ReversibilityEngine(up, UndoLog(":memory:"), env=env)
    await eng.build_catalog()

    console.print(
        Panel.fit(
            "[bold]Unwind demo[/bold] — an agent goes off the rails, then we take it back",
            border_style="cyan",
        )
    )

    actions = [
        (
            "write_file",
            {"path": "deploy.yaml", "content": "replicas: 0"},
            "overwrite the deploy config",
        ),
        ("delete_page", {"id": "pg_onboarding"}, "delete the onboarding page"),
        ("drop_table", {"id": "sessions"}, "drop the sessions table"),
        (
            "send_email",
            {"to": "all-staff@corp.com", "body": "We are shutting down."},
            "email all staff",
        ),
    ]

    async def auto_yes(msg: str) -> bool:
        console.print(f"  [yellow]⚠ elicitation:[/yellow] {msg}")
        console.print("  [dim](demo auto-answers 'yes' to show what happens next)[/dim]")
        return True

    console.print("\n[bold]The agent acts:[/bold]")
    for tool, args, desc in actions:
        res = await eng.execute(tool, args, confirm=auto_yes)
        tag = res.evaluation.effective_class.name
        console.print(f"  • {desc}: [bold]{tag}[/bold] — {res.message}")

    console.print("\n[bold]You type:[/bold] [cyan]undo[/cyan]\n")
    outcomes = await eng.undo(len(actions))

    table = Table(show_header=True, header_style="bold")
    table.add_column("action")
    table.add_column("outcome")
    table.add_column("why")
    recovered = 0
    for o in outcomes:
        color = {"restored": "green", "approximately_restored": "green", "could_not_undo": "red"}[
            o.outcome.value
        ]
        if o.outcome != UndoOutcome.COULD_NOT_UNDO:
            recovered += 1
        table.add_row(o.tool, f"[{color}]{o.outcome.value}[/{color}]", o.reason)
    console.print(table)

    console.print(
        Panel.fit(
            f"[bold green]{recovered}/{len(actions)} actions reversed.[/bold green]  "
            "[bold red]send_email could not be undone[/bold red] — the notification already "
            "left the building. [italic]That is exactly the one Unwind would have interrupted "
            "you for.[/italic]",
            border_style="green",
        )
    )
    # Verify the world was actually put back.
    assert up.state["files"]["deploy.yaml"] == "replicas: 3\nregion: us-east"
    assert "pg_onboarding" in up.state["pages"]
    assert "sessions" in up.state["tables"]
    assert len(up.state["sent"]) == 1
    return 0


def main() -> None:
    raise SystemExit(anyio.run(run_demo))


if __name__ == "__main__":
    main()
