"""Unit tests for the Unwind agentic surface (``unwind/tools.py``)."""

from __future__ import annotations

import pytest

from unwind.engine import ReversibilityEngine
from unwind.tools import UnwindTools


@pytest.fixture
async def tools(engine: ReversibilityEngine) -> UnwindTools:
    await engine.build_catalog()
    return UnwindTools(engine)


class TestIsUnwindTool:
    def test_recognises_prefix_tools(self) -> None:
        assert UnwindTools.is_unwind_tool("unwind.preview") is True
        assert UnwindTools.is_unwind_tool("unwind.undo") is True
        assert UnwindTools.is_unwind_tool("unwind.history") is True
        assert UnwindTools.is_unwind_tool("unwind.checkpoint") is True
        assert UnwindTools.is_unwind_tool("unwind.explain_risk") is True

    def test_rejects_upstream_tools(self) -> None:
        assert UnwindTools.is_unwind_tool("write_file") is False
        assert UnwindTools.is_unwind_tool("unwind.nonexistent") is False


class TestPreview:
    async def test_preview_read(self, tools: UnwindTools) -> None:
        out = await tools.dispatch(
            "unwind.preview", {"tool": "get_file", "args": {"path": "deploy.yaml"}}
        )
        assert out["isError"] is False
        p = out["structured"]
        assert p["tool"] == "get_file"
        assert p["reversibility_class"] == "R0"
        assert p["decision"] == "auto_allow"

    async def test_preview_send_cannot_undo(self, tools: UnwindTools) -> None:
        out = await tools.dispatch(
            "unwind.preview", {"tool": "send_email", "args": {"to": "x@y.com"}}
        )
        p = out["structured"]
        assert p["reversibility_class"] == "R3"
        assert p["can_undo"] is False


class TestExplainRisk:
    async def test_explain_send_has_no_undo_line(self, tools: UnwindTools) -> None:
        out = await tools.dispatch(
            "unwind.explain_risk", {"tool": "send_email", "args": {"to": "x@y.com"}}
        )
        assert out["isError"] is False
        text = out["structured"]["explanation"]
        assert "R3" in text
        assert "NO reliable way to undo" in text

    async def test_explain_write_has_undo_line(self, tools: UnwindTools) -> None:
        out = await tools.dispatch(
            "unwind.explain_risk", {"tool": "write_file", "args": {"path": "deploy.yaml"}}
        )
        text = out["structured"]["explanation"]
        assert "can undo" in text.lower()


class TestHistory:
    async def test_history_reflects_executed_actions(
        self, engine: ReversibilityEngine, tools: UnwindTools
    ) -> None:
        await engine.execute("write_file", {"path": "deploy.yaml", "content": "x"})
        out = tools._history({"n": 20})  # exercise the sync helper directly
        hist = out["structured"]["history"]
        assert len(hist) == 1
        assert hist[0]["tool"] == "write_file"
        assert hist[0]["status"] == "active"

    async def test_history_via_dispatch(
        self, engine: ReversibilityEngine, tools: UnwindTools
    ) -> None:
        await engine.execute("write_file", {"path": "deploy.yaml", "content": "x"})
        out = await tools.dispatch("unwind.history", {})
        assert len(out["structured"]["history"]) == 1


class TestCheckpointAndUndo:
    async def test_checkpoint_then_undo_to_checkpoint(
        self, engine: ReversibilityEngine, tools: UnwindTools
    ) -> None:
        # Checkpoint, then act, then undo back to the checkpoint.
        cp = await tools.dispatch("unwind.checkpoint", {"label": "before"})
        cp_id = cp["structured"]["checkpoint_id"]
        assert cp_id.startswith("cp_")

        await engine.execute("write_file", {"path": "deploy.yaml", "content": "replicas: 0"})
        assert engine.upstream.state["files"]["deploy.yaml"] == "replicas: 0"  # type: ignore[attr-defined]

        out = await tools.dispatch("unwind.undo", {"to_checkpoint": cp_id})
        undone = out["structured"]["undone"]
        assert len(undone) == 1
        assert undone[0]["outcome"] == "restored"
        assert engine.upstream.state["files"]["deploy.yaml"] == "replicas: 3\nregion: us-east"  # type: ignore[attr-defined]

    async def test_undo_n_via_dispatch(
        self, engine: ReversibilityEngine, tools: UnwindTools
    ) -> None:
        await engine.execute("write_file", {"path": "deploy.yaml", "content": "x"})
        out = await tools.dispatch("unwind.undo", {"n": 1})
        assert out["structured"]["undone"][0]["outcome"] == "restored"

    async def test_undo_missing_checkpoint_falls_back_to_n(
        self, engine: ReversibilityEngine, tools: UnwindTools
    ) -> None:
        # An unknown checkpoint id falls through to the plain undo(n) path.
        await engine.execute("write_file", {"path": "deploy.yaml", "content": "x"})
        out = await tools.dispatch("unwind.undo", {"to_checkpoint": "cp_does_not_exist"})
        assert out["structured"]["undone"][0]["outcome"] == "restored"

    async def test_checkpoint_with_existing_head(
        self, engine: ReversibilityEngine, tools: UnwindTools
    ) -> None:
        # Log an action first so the checkpoint records a head entry id.
        await engine.execute("write_file", {"path": "deploy.yaml", "content": "x"})
        cp = tools._checkpoint({"label": "mid"})
        assert cp["structured"]["head_entry_id"] is not None


class TestUnknownTool:
    async def test_dispatch_unknown_returns_error(self, tools: UnwindTools) -> None:
        out = await tools.dispatch("unwind.bogus", {})
        assert out["isError"] is True

    async def test_dispatch_none_args_ok(self, tools: UnwindTools) -> None:
        out = await tools.dispatch("unwind.history", None)  # type: ignore[arg-type]
        assert out["isError"] is False


class TestBuildFastmcp:
    async def test_build_fastmcp_exposes_unwind_surface(self, engine: ReversibilityEngine) -> None:
        from unwind.tools import build_fastmcp

        await engine.build_catalog()
        server = build_fastmcp(engine)
        listed = await server.list_tools()
        names = {t.name for t in listed}
        assert {
            "unwind.preview",
            "unwind.undo",
            "unwind.explain_risk",
            "unwind.history",
            "unwind.checkpoint",
        } <= names
