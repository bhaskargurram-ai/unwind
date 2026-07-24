"""Unit tests for the reversibility engine (``unwind/engine.py``)."""

from __future__ import annotations

import pytest

from unwind.engine import ConfirmFn, ReversibilityEngine
from unwind.types import Decision, ReversibilityClass, UndoOutcome, UndoStatus


class TestBuildCatalog:
    async def test_classifies_every_tool(self, engine: ReversibilityEngine) -> None:
        specs = await engine.build_catalog()
        by_name = {s.name: s for s in specs}
        assert by_name["get_file"].rev_class == ReversibilityClass.R0
        # write_file is R1 (self-reversible via get_file prestate).
        assert by_name["write_file"].rev_class == ReversibilityClass.R1
        # delete_page in a trash/versioned env is compensable/recoverable.
        assert by_name["delete_page"].rev_class <= ReversibilityClass.R2
        # send_email stays R3 (no inverse).
        assert by_name["send_email"].rev_class == ReversibilityClass.R3
        assert "get_file" in engine.catalog
        # R0 reads get no plan.
        assert "get_file" not in engine.plans


class TestWriteFileFlow:
    async def test_write_auto_allows_logs_and_undo_restores(
        self, engine: ReversibilityEngine
    ) -> None:
        await engine.build_catalog()
        original = engine.upstream.state["files"]["deploy.yaml"]  # type: ignore[attr-defined]

        res = await engine.execute("write_file", {"path": "deploy.yaml", "content": "replicas: 0"})
        assert res.executed is True
        assert res.evaluation.decision.decision == Decision.AUTO_ALLOW_LOGGED
        assert res.undo_id is not None
        assert engine.upstream.state["files"]["deploy.yaml"] == "replicas: 0"  # type: ignore[attr-defined]

        outcomes = await engine.undo(1)
        assert len(outcomes) == 1
        assert outcomes[0].outcome == UndoOutcome.RESTORED
        assert engine.upstream.state["files"]["deploy.yaml"] == original  # type: ignore[attr-defined]


class TestCreatePageFlow:
    async def test_create_then_undo_removes_it(
        self, engine: ReversibilityEngine, confirm_yes: ConfirmFn
    ) -> None:
        await engine.build_catalog()
        res = await engine.execute(
            "create_page", {"id": "pg_new", "title": "New Page"}, confirm=confirm_yes
        )
        assert res.executed is True
        assert "pg_new" in engine.upstream.state["pages"]  # type: ignore[attr-defined]

        outcomes = await engine.undo(1)
        assert outcomes[0].outcome in (UndoOutcome.RESTORED, UndoOutcome.APPROXIMATELY_RESTORED)
        assert "pg_new" not in engine.upstream.state["pages"]  # type: ignore[attr-defined]


class TestSendEmailCannotUndo:
    async def test_send_confirmed_then_undo_could_not_undo(
        self, engine: ReversibilityEngine, confirm_yes: ConfirmFn
    ) -> None:
        await engine.build_catalog()
        res = await engine.execute(
            "send_email", {"to": "all@corp.com", "body": "hi"}, confirm=confirm_yes
        )
        assert res.executed is True
        assert len(engine.upstream.state["sent"]) == 1  # type: ignore[attr-defined]

        outcomes = await engine.undo(1)
        assert outcomes[0].outcome == UndoOutcome.COULD_NOT_UNDO
        # The email stays sent — undo cannot un-send it.
        assert len(engine.upstream.state["sent"]) == 1  # type: ignore[attr-defined]


class TestDeclinedAndBlockedDoNotMutate:
    async def test_declined_send_does_not_mutate_or_log(
        self, engine: ReversibilityEngine, confirm_no: ConfirmFn
    ) -> None:
        await engine.build_catalog()
        res = await engine.execute(
            "send_email", {"to": "all@corp.com", "body": "hi"}, confirm=confirm_no
        )
        assert res.executed is False
        assert res.result is None
        assert res.undo_id is None
        assert "DECLINED" in res.message
        assert engine.upstream.state["sent"] == []  # type: ignore[attr-defined]
        # Nothing logged.
        assert engine.history() == []

    async def test_send_with_no_confirm_callback_declines(
        self, engine: ReversibilityEngine
    ) -> None:
        await engine.build_catalog()
        # ELICIT decision but no confirm fn -> treated as not approved.
        res = await engine.execute("send_email", {"to": "x@y.com", "body": "hi"})
        assert res.executed is False
        assert engine.upstream.state["sent"] == []  # type: ignore[attr-defined]


class TestUndoEntryAndHistory:
    async def test_history_lists_logged_actions(self, engine: ReversibilityEngine) -> None:
        await engine.build_catalog()
        await engine.execute("write_file", {"path": "deploy.yaml", "content": "x"})
        hist = engine.history()
        assert len(hist) == 1
        assert hist[0].tool == "write_file"
        assert hist[0].status == UndoStatus.ACTIVE

    async def test_undo_entry_marks_undone(self, engine: ReversibilityEngine) -> None:
        await engine.build_catalog()
        res = await engine.execute("write_file", {"path": "deploy.yaml", "content": "x"})
        assert res.undo_id is not None
        out = await engine.undo_entry(res.undo_id)
        assert out.outcome == UndoOutcome.RESTORED
        assert engine.log.get(res.undo_id).status == UndoStatus.UNDONE  # type: ignore[union-attr]

    async def test_undo_entry_missing_raises(self, engine: ReversibilityEngine) -> None:
        await engine.build_catalog()
        with pytest.raises(KeyError):
            await engine.undo_entry("nonexistent")


class TestEvaluateUnknownTool:
    async def test_unknown_tool_fails_safe_to_r4(self, engine: ReversibilityEngine) -> None:
        await engine.build_catalog()
        ev = engine.evaluate("totally_unknown_tool", {})
        assert ev.effective_class >= ReversibilityClass.R3
