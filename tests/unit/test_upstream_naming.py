"""Regression tests for server-name inference and clock-robust checkpoints."""

from __future__ import annotations

import anyio
import pytest

from unwind.upstream import _infer_server_name


@pytest.mark.parametrize(
    ("command", "args", "expected"),
    [
        ("npx", ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"], "server-filesystem"),
        ("uvx", ["mcp-server-git", "--repo", "."], "mcp-server-git"),
        ("/usr/local/bin/node", ["build/index.js"], "index.js"),
        ("python", ["-m", "my_mcp_server"], "my_mcp_server"),
        ("my-server", [], "my-server"),
        ("npx", ["@scope/pkg@1.2.3"], "pkg"),
    ],
)
def test_infer_server_name(command: str, args: list[str], expected: str) -> None:
    assert _infer_server_name(command, args) == expected


def test_checkpoint_undo_is_clock_independent(monkeypatch: pytest.MonkeyPatch) -> None:
    """A checkpoint + a same-tick action must still undo, even on a coarse clock.

    Windows' ``time.time()`` resolution (~15ms) previously let an action share a
    timestamp with the checkpoint and be missed by a ``ts >`` comparison. The fix
    keys off entry identity; here we freeze the clock to the worst case.
    """
    import unwind.types as types_mod
    import unwind.undolog.store as store_mod

    monkeypatch.setattr(types_mod, "now_ts", lambda: 1000.0)
    monkeypatch.setattr(store_mod, "now_ts", lambda: 1000.0)

    from unwind.engine import ReversibilityEngine
    from unwind.tools import UnwindTools
    from unwind.types import EnvironmentDescriptor, ToolSpec
    from unwind.undolog.store import UndoLog
    from unwind.upstream import InProcessUpstream

    up = InProcessUpstream("ws")
    up.state = {"pages": {}, "trash": {}}
    up.register(
        ToolSpec(
            server="ws",
            name="get_page",
            input_schema={"properties": {"id": {"type": "string"}}},
            output_schema={"properties": {"id": {"type": "string"}}},
        ),
        lambda a, s: {"id": a["id"], "title": s["pages"].get(a["id"])},
    )
    up.register(
        ToolSpec(
            server="ws",
            name="create_page",
            input_schema={"properties": {"id": {"type": "string"}, "title": {"type": "string"}}},
            output_schema={"properties": {"id": {"type": "string"}}},
        ),
        lambda a, s: (s["pages"].__setitem__(a["id"], a.get("title", "")), {"id": a["id"]})[1],
    )
    up.register(
        ToolSpec(
            server="ws",
            name="delete_page",
            input_schema={"properties": {"id": {"type": "string"}}},
            output_schema={"properties": {"id": {"type": "string"}}},
        ),
        lambda a, s: (
            s["trash"].__setitem__(a["id"], s["pages"].pop(a["id"], None)),
            {"id": a["id"]},
        )[1],
    )

    async def scenario() -> int:
        eng = ReversibilityEngine(
            up, UndoLog(":memory:"), env=EnvironmentDescriptor(has_trash=True, versioned=True)
        )
        await eng.build_catalog()
        tools = UnwindTools(eng)
        cp = (await tools.dispatch("unwind.checkpoint", {}))["structured"]["checkpoint_id"]
        await eng.execute("create_page", {"id": "pg1", "title": "X"})  # same frozen ts
        res = await tools.dispatch("unwind.undo", {"to_checkpoint": cp})
        return len(res["structured"]["undone"])

    n = anyio.run(scenario)
    assert n == 1
    assert "pg1" not in up.state["pages"]
