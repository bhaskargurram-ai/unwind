"""``unwind`` command-line interface (``PROJECT.md`` §7, §11).

Subcommands:

* ``unwind run -- <upstream cmd>``      → start the transparent stdio proxy
* ``unwind classify -- <upstream cmd>`` → print the R-scale table for a server
* ``unwind index -- <upstream cmd>``    → emit the reversibility index (json/md)
* ``unwind history``                    → show the durable undo log
* ``unwind undo [N] -- <upstream cmd>`` → reverse the last N actions
* ``unwind demo``                       → run the hermetic end-to-end demo
* ``unwind version``
"""

from __future__ import annotations

import anyio
import typer
from rich.console import Console
from rich.table import Table

from unwind import __version__

app = typer.Typer(
    add_completion=False,
    help="Unwind — a reversibility layer for agentic tool use.",
    no_args_is_help=True,
)
console = Console()
err = Console(stderr=True)

_RCLASS_STYLE = {
    "R0": "green",
    "R1": "cyan",
    "R2": "blue",
    "R3": "yellow",
    "R4": "bold red",
}


def _split_cmd(argv: list[str]) -> tuple[str, list[str]]:
    """Split ``["--", "npx", "-y", "server"]`` → ("npx", ["-y","server"])."""
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    if not argv:
        raise typer.BadParameter("provide the upstream command after `--`")
    return argv[0], argv[1:]


_EXTRA = {"allow_extra_args": True, "ignore_unknown_options": True}


@app.command(context_settings=_EXTRA)
def run(
    ctx: typer.Context,
    passthrough_only: bool = typer.Option(
        False, "--passthrough-only", help="Panic switch: pure proxy, no interception."
    ),
    db: str = typer.Option("unwind.db", help="Path to the durable undo-log database."),
    use_llm: bool = typer.Option(
        False, "--llm", help="Enable the (optional) LLM classifier voter."
    ),
    versioned: bool = typer.Option(
        False, "--versioned-env", help="Upstream storage is version-controlled (git-backed)."
    ),
    trash: bool = typer.Option(
        False, "--trash-env", help="Upstream has trash/soft-delete recovery."
    ),
) -> None:
    """Run the transparent stdio proxy in front of an upstream MCP server."""
    from unwind.policy.config import PolicyConfig
    from unwind.proxy.stdio import UnwindStdioProxy
    from unwind.types import EnvironmentDescriptor

    command, args = _split_cmd(list(ctx.args))
    env = EnvironmentDescriptor(versioned=versioned, has_trash=trash)
    proxy = UnwindStdioProxy(
        command,
        args,
        db_path=db,
        environment=env,
        policy=PolicyConfig(passthrough_only=passthrough_only),
        passthrough_only=passthrough_only,
        use_llm=use_llm,
    )
    err.print(
        f"[dim]unwind proxying → {command} {' '.join(args)} "
        f"({'passthrough-only' if passthrough_only else 'reversibility-aware'})[/dim]"
    )
    rc = anyio.run(proxy.run)
    raise typer.Exit(rc)


@app.command(context_settings=_EXTRA)
def classify(
    ctx: typer.Context,
    use_llm: bool = typer.Option(False, "--llm"),
    witness: bool = typer.Option(
        False, "--witness", help="Apply WITNESS discharged-refutation hardening (offline)."
    ),
) -> None:
    """Classify every tool a server exposes and print the R0–R4 table."""
    command, args = _split_cmd(ctx.args)
    specs = anyio.run(_classify_server, command, args, use_llm, witness)
    table = Table(title=f"Reversibility of {command} {' '.join(args)}")
    table.add_column("Tool")
    table.add_column("Class")
    table.add_column("Verb")
    table.add_column("Conf", justify="right")
    table.add_column("Undo via")
    if witness:
        table.add_column("WITNESS")
    for spec, plan, wit in specs:
        style = _RCLASS_STYLE.get(spec.rev_class.name, "white")
        row = [
            spec.name,
            f"[{style}]{spec.rev_class.name} {spec.rev_class.label}[/{style}]",
            spec.effect_verb.value,
            f"{spec.confidence:.2f}",
            (plan.inverse_tool or "—") if plan else "—",
        ]
        if witness:
            row.append(", ".join(wit) if wit else "—")
        table.add_row(*row)
    console.print(table)


@app.command(context_settings=_EXTRA)
def index(
    ctx: typer.Context,
    fmt: str = typer.Option("md", "--format", help="Output format: md | json"),
) -> None:
    """Emit the public reversibility index for a server (feeds the docs page)."""
    import json

    command, args = _split_cmd(ctx.args)
    specs = anyio.run(_classify_server, command, args, False)
    rows = [
        {
            "server": spec.server,
            "tool": spec.name,
            "class": spec.rev_class.name,
            "label": spec.rev_class.label,
            "verb": spec.effect_verb.value,
            "can_undo": bool(plan and plan.inverse_tool),
            "fidelity": plan.fidelity_grade.label if plan else None,
            "half_life_s": spec.half_life_s,
        }
        for spec, plan in specs
    ]
    if fmt == "json":
        console.print_json(json.dumps(rows))
    else:
        console.print("| tool | class | verb | can undo | fidelity |")
        console.print("|---|---|---|---|---|")
        for r in rows:
            console.print(
                f"| {r['tool']} | {r['class']} | {r['verb']} | "
                f"{'yes' if r['can_undo'] else 'no'} | {r['fidelity'] or '—'} |"
            )


@app.command()
def history(db: str = typer.Option("unwind.db"), n: int = typer.Option(20)) -> None:
    """Show recent actions from the durable undo log."""
    from unwind.undolog.store import UndoLog

    log = UndoLog(db)
    entries = log.recent(n)
    if not entries:
        console.print("[dim]no logged actions yet[/dim]")
        raise typer.Exit()
    table = Table(title="Unwind history")
    for col in ("when", "server", "tool", "class", "status"):
        table.add_column(col)
    import datetime

    for e in entries:
        table.add_row(
            datetime.datetime.fromtimestamp(e.ts).strftime("%H:%M:%S"),
            e.server,
            e.tool,
            e.rev_class.name,
            e.status.value,
        )
    console.print(table)


@app.command(context_settings=_EXTRA)
def undo(
    ctx: typer.Context,
    n: int = typer.Argument(1),
    db: str = typer.Option("unwind.db"),
) -> None:
    """Reverse the last N actions by reconnecting to the upstream server."""
    command, args = _split_cmd(ctx.args)
    outcomes = anyio.run(_undo_against, command, args, db, n)
    for o in outcomes:
        color = {
            "restored": "green",
            "approximately_restored": "yellow",
            "could_not_undo": "red",
        }.get(o.outcome.value, "white")
        console.print(f"[{color}]{o.outcome.value}[/{color}] {o.tool}: {o.reason}")
        for r in o.residue:
            console.print(f"    [dim]residue: {r}[/dim]")


undo.__dict__["_typer_allow_extra_args"] = True


@app.command()
def demo() -> None:
    """Run the hermetic end-to-end demo (no external server required)."""
    from unwind.demo import run_demo

    anyio.run(run_demo)


@app.command()
def version() -> None:
    """Print the installed Unwind version."""
    console.print(f"unwind {__version__}")


# -- async helpers -------------------------------------------------------
async def _classify_server(command: str, args: list[str], use_llm: bool, witness: bool = False):  # type: ignore[no-untyped-def]
    from unwind.engine import ReversibilityEngine
    from unwind.undolog.store import UndoLog
    from unwind.upstream import McpUpstream

    async with McpUpstream(command, args) as up:
        eng = ReversibilityEngine(up, UndoLog(":memory:"), use_llm=use_llm)
        specs = await eng.build_catalog()

    if not witness:
        return [(s, eng.plans.get(s.name), []) for s in specs]

    # Apply WITNESS discharged-refutation hardening over the crawled toolset.
    from unwind.classify.discharge import DeterministicProposer, discharge_schema_graph
    from unwind.classify.witness import classify_witness

    proposer = DeterministicProposer()
    out = []
    for s in specs:
        plan = eng.plans.get(s.name)
        wr = classify_witness(s, specs, eng.env, proposer, discharge_schema_graph, plan=plan)
        hardened = s.model_copy(update={"rev_class": wr.classification.rev_class})
        out.append((hardened, plan, [w.type.value for w in wr.confirmed]))
    return out


async def _undo_against(command: str, args: list[str], db: str, n: int):  # type: ignore[no-untyped-def]
    from unwind.engine import ReversibilityEngine
    from unwind.undolog.store import UndoLog
    from unwind.upstream import McpUpstream

    log = UndoLog(db)
    async with McpUpstream(command, args) as up:
        eng = ReversibilityEngine(up, log)
        await eng.build_catalog()
        # Undo across the whole log (all sessions) for the CLI.
        entries = list(log.undoable())[:n]
        return [await eng.undo_entry(e.id) for e in entries]


def main() -> None:  # console-script entry point
    app()


if __name__ == "__main__":
    main()
