"""Unit tests for sandbox validation + fidelity grading (``unwind/synthesize/validate.py``)."""

from __future__ import annotations

from typing import Any

from unwind.synthesize.validate import state_diff, validate_plan
from unwind.types import CompensationPlan, FidelityGrade


def _make_env() -> tuple[dict[str, Any], Any, Any]:
    """A tiny in-memory world with an executor and snapshot closure."""
    state: dict[str, Any] = {"name": "original", "value": 1}

    def executor(tool: str, args: dict[str, Any]) -> dict[str, Any]:
        if tool == "set_name":
            state["name"] = args["name"]
        elif tool == "restore_name":
            state["name"] = args["name"]
        elif tool == "set_and_bump_version":
            state["name"] = args["name"]
            state["version"] = state.get("version", 0) + 1
        elif tool == "restore_name_bump_version":
            state["name"] = args["name"]
            state["version"] = state.get("version", 0) + 1
        elif tool == "boom":
            raise RuntimeError("executor exploded")
        elif tool == "leave_broken":
            state["name"] = args["name"]  # never restored to original
        return {}

    def snapshot() -> dict[str, Any]:
        return dict(state)

    return state, executor, snapshot


class TestStateDiff:
    def test_no_diff(self) -> None:
        assert state_diff({"a": 1}, {"a": 1}) == {}

    def test_changed_key(self) -> None:
        assert state_diff({"a": 1}, {"a": 2}) == {"a": (1, 2)}

    def test_added_and_removed(self) -> None:
        d = state_diff({"a": 1}, {"b": 2})
        assert d == {"a": (1, None), "b": (None, 2)}


class TestValidatePlan:
    def test_exact_when_forward_and_inverse_restore(self) -> None:
        _, ex, snap = _make_env()
        plan = CompensationPlan(forward="set_name", inverse_tool="restore_name")
        res = validate_plan(plan, {"name": "changed"}, {"name": "original"}, ex, snap)
        assert res.fidelity_grade == FidelityGrade.EXACT
        assert res.diff == {}

    def test_semantic_when_only_residue_key_differs(self) -> None:
        _, ex, snap = _make_env()
        plan = CompensationPlan(
            forward="set_and_bump_version", inverse_tool="restore_name_bump_version"
        )
        # name is restored; only "version" (a residue key) differs -> SEMANTIC.
        res = validate_plan(plan, {"name": "changed"}, {"name": "original"}, ex, snap)
        assert res.fidelity_grade == FidelityGrade.SEMANTIC
        assert "version" in res.diff

    def test_failed_when_executor_raises(self) -> None:
        _, ex, snap = _make_env()
        plan = CompensationPlan(forward="boom", inverse_tool="restore_name")
        res = validate_plan(plan, {}, {"name": "original"}, ex, snap)
        assert res.fidelity_grade == FidelityGrade.FAILED
        assert res.error is not None

    def test_failed_when_no_inverse_tool(self) -> None:
        _, ex, snap = _make_env()
        plan = CompensationPlan(forward="set_name", inverse_tool=None)
        res = validate_plan(plan, {"name": "x"}, {}, ex, snap)
        assert res.fidelity_grade == FidelityGrade.FAILED
        assert res.error == "no inverse tool in plan"

    def test_acceptable_approximation_when_core_left_changed(self) -> None:
        _, ex, snap = _make_env()
        # forward changes name, "inverse" leaves it broken (different value).
        plan = CompensationPlan(forward="set_name", inverse_tool="leave_broken")
        res = validate_plan(plan, {"name": "changed"}, {"name": "still-wrong"}, ex, snap)
        # Non-residue "name" differs -> not EXACT/SEMANTIC.
        assert res.fidelity_grade == FidelityGrade.FAILED
        assert "name" in res.diff
