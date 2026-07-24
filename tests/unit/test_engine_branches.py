"""Extra engine branch coverage: approximate restore, expired undo, failed inverse."""

from __future__ import annotations

from typing import Any

from unwind.engine import ConfirmFn, ReversibilityEngine
from unwind.types import (
    EnvironmentDescriptor,
    ToolSpec,
    UndoOutcome,
    UndoStatus,
    now_ts,
)
from unwind.undolog.store import UndoLog
from unwind.upstream import InProcessUpstream


class TestApproximateRestore:
    async def test_create_undo_is_approximate(
        self, engine: ReversibilityEngine, confirm_yes: ConfirmFn
    ) -> None:
        # A compensable create has SEMANTIC (not EXACT) fidelity -> the undo is
        # reported as approximately_restored, not restored.
        await engine.build_catalog()
        res = await engine.execute("create_page", {"id": "pg_x", "title": "X"}, confirm=confirm_yes)
        assert res.executed
        outcomes = await engine.undo(1)
        assert outcomes[0].outcome == UndoOutcome.APPROXIMATELY_RESTORED
        assert "approximately restored" in outcomes[0].reason


class TestExpiredUndo:
    async def test_undo_entry_expired_reports_could_not_undo(
        self, engine: ReversibilityEngine
    ) -> None:
        await engine.build_catalog()
        res = await engine.execute("write_file", {"path": "deploy.yaml", "content": "x"})
        assert res.undo_id is not None
        # Force the entry to be expired, then undo it directly (bypasses the
        # undoable() filter so we exercise the expired branch of _undo_one).
        entry = engine.log.get(res.undo_id)
        assert entry is not None
        entry.expires_at = now_ts() - 1.0
        engine.log.append(entry)  # INSERT OR REPLACE overwrites

        out = await engine.undo_entry(res.undo_id)
        assert out.outcome == UndoOutcome.COULD_NOT_UNDO
        assert "half-life" in out.reason
        assert engine.log.get(res.undo_id).status == UndoStatus.EXPIRED  # type: ignore[union-attr]


def _build_failing_inverse_upstream() -> InProcessUpstream:
    up = InProcessUpstream("workspace")
    up.state = {"pages": {}}

    def get_page(a: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
        return {"id": a["id"], "title": s["pages"].get(a["id"])}

    def create_page(a: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
        s["pages"][a["id"]] = a.get("title", "")
        return {"id": a["id"]}

    def delete_page(a: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("delete backend is down")

    id_in = {"properties": {"id": {"type": "string"}}}
    id_out = {"properties": {"id": {"type": "string"}}}
    up.register(
        ToolSpec(server="workspace", name="get_page", input_schema=id_in, output_schema=id_out),
        get_page,
    )
    up.register(
        ToolSpec(
            server="workspace",
            name="create_page",
            input_schema={"properties": {"id": {"type": "string"}, "title": {"type": "string"}}},
            output_schema=id_out,
        ),
        create_page,
    )
    up.register(
        ToolSpec(server="workspace", name="delete_page", input_schema=id_in, output_schema=id_out),
        delete_page,
    )
    return up


class TestFailedInverse:
    async def test_inverse_error_marks_failed(self, confirm_yes: ConfirmFn) -> None:
        up = _build_failing_inverse_upstream()
        eng = ReversibilityEngine(
            up,
            UndoLog(":memory:"),
            env=EnvironmentDescriptor(has_trash=True, versioned=True),
        )
        await eng.build_catalog()
        res = await eng.execute("create_page", {"id": "pg_x", "title": "X"}, confirm=confirm_yes)
        assert res.undo_id is not None
        outcomes = await eng.undo(1)
        # The inverse (delete_page) raises -> isError -> COULD_NOT_UNDO / FAILED.
        assert outcomes[0].outcome == UndoOutcome.COULD_NOT_UNDO
        assert "failed" in outcomes[0].reason.lower()
        assert eng.log.get(res.undo_id).status == UndoStatus.FAILED  # type: ignore[union-attr]


class TestBlockedPath:
    async def test_blocked_r4_unbounded_does_not_execute(self, confirm_yes: ConfirmFn) -> None:
        # A drop-style tool with a bulk selector in a versionless env is R4 with
        # unbounded blast radius -> BLOCK, no mutation, no log.
        up = InProcessUpstream("db")
        up.state = {"tables": {"t1": 1}}

        def drop_tables(a: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
            s["tables"].clear()
            return {"ok": True}

        up.register(
            ToolSpec(
                server="db",
                name="drop_tables",
                input_schema={"properties": {"filter": {"type": "string"}}},
            ),
            drop_tables,
        )
        eng = ReversibilityEngine(
            up,
            UndoLog(":memory:"),
            env=EnvironmentDescriptor(versioned=False),
        )
        await eng.build_catalog()
        res = await eng.execute("drop_tables", {"filter": "*"}, confirm=confirm_yes)
        assert res.executed is False
        assert "BLOCKED" in res.message
        assert up.state["tables"] == {"t1": 1}
        assert eng.history() == []
