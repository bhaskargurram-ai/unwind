"""Unit tests for compensation-plan synthesis (``unwind/synthesize/plan.py``)."""

from __future__ import annotations

from unwind.synthesize.plan import effective_class, synthesize_plan
from unwind.types import (
    CompensationPlan,
    EnvironmentDescriptor,
    FidelityGrade,
    ReversibilityClass,
    ToolSpec,
)

_ID_IN = {"properties": {"id": {"type": "string"}}}
_ID_OUT = {"properties": {"id": {"type": "string"}}}


def _tool(
    name: str, input_schema: dict | None = None, output_schema: dict | None = None
) -> ToolSpec:
    return ToolSpec(
        server="s", name=name, input_schema=input_schema or {}, output_schema=output_schema
    )


class TestSynthesizePlan:
    def test_update_with_reader_is_r1_self_reversal(self) -> None:
        update = _tool("update_record", _ID_IN, _ID_OUT)
        reader = _tool("get_record", _ID_IN, _ID_OUT)
        plan = synthesize_plan(update, [update, reader], EnvironmentDescriptor())
        assert plan.inverse_tool == "update_record"  # self-reversal
        assert plan.pre_read == "get_record"
        assert plan.inverse_template.get("__from_prestate__") is True
        assert plan.fidelity_grade == FidelityGrade.EXACT
        # Self-reversal maps to R1.
        assert effective_class(plan, ReversibilityClass.R1) == ReversibilityClass.R1

    def test_compensable_create_is_r2(self) -> None:
        create = _tool("create_page", _ID_IN, _ID_OUT)
        delete = _tool("delete_page", _ID_IN)
        plan = synthesize_plan(create, [create, delete], EnvironmentDescriptor())
        assert plan.inverse_tool == "delete_page"
        assert plan.inverse_template.get("__bind_id_from_result__") is True
        # Fidelity is PROVISIONAL until executed: a lexical antonym match is
        # evidence an inverse EXISTS, not that it RESTORES state, so an unexecuted
        # plan is capped at ACCEPTABLE_APPROXIMATION (never a false SEMANTIC).
        assert plan.fidelity_grade == FidelityGrade.ACCEPTABLE_APPROXIMATION
        # But a confident structural match still yields the R2 (compensable) class.
        from unwind.synthesize.plan import effective_class

        assert effective_class(plan, ReversibilityClass.R4) == ReversibilityClass.R2
        assert effective_class(plan, ReversibilityClass.R2) == ReversibilityClass.R2

    def test_send_has_no_inverse_failed_plan(self) -> None:
        send = _tool("send_email", {"properties": {"to": {"type": "string"}}})
        plan = synthesize_plan(send, [send], EnvironmentDescriptor())
        assert plan.inverse_tool is None
        assert plan.fidelity_grade == FidelityGrade.FAILED
        # A SEND default half-life is applied.
        assert plan.expiry_s == 30.0

    def test_no_snapshot_update_falls_out_of_r1(self) -> None:
        update = _tool("update_record", _ID_IN, _ID_OUT)
        reader = _tool("get_record", _ID_IN, _ID_OUT)
        env = EnvironmentDescriptor(supports_snapshot=False)
        plan = synthesize_plan(update, [update, reader], env)
        # Case A requires supports_snapshot; without it, self-reversal is not used.
        assert plan.inverse_template.get("__from_prestate__") is not True


class TestEffectiveClass:
    def test_no_inverse_never_below_r3(self) -> None:
        plan = CompensationPlan(
            forward="send_email",
            inverse_tool=None,
            fidelity_grade=FidelityGrade.FAILED,
            confidence=0.0,
        )
        assert effective_class(plan, ReversibilityClass.R3) == ReversibilityClass.R3
        # Even if a base tried to claim R1, no-inverse floors at R3.
        assert effective_class(plan, ReversibilityClass.R1) == ReversibilityClass.R3
        # An R4 base is preserved (max).
        assert effective_class(plan, ReversibilityClass.R4) == ReversibilityClass.R4

    def test_strong_self_reversal_is_r1(self) -> None:
        plan = CompensationPlan(
            forward="update_x",
            inverse_tool="update_x",
            fidelity_grade=FidelityGrade.EXACT,
            confidence=0.8,
        )
        assert effective_class(plan, ReversibilityClass.R1) == ReversibilityClass.R1

    def test_strong_sibling_inverse_is_r2(self) -> None:
        plan = CompensationPlan(
            forward="create_x",
            inverse_tool="delete_x",
            fidelity_grade=FidelityGrade.SEMANTIC,
            confidence=0.9,
        )
        assert effective_class(plan, ReversibilityClass.R2) == ReversibilityClass.R2

    def test_weak_compensation_degrades_to_r3(self) -> None:
        # Acceptable-approximation + moderate confidence -> escalate to R3.
        plan = CompensationPlan(
            forward="create_x",
            inverse_tool="delete_x",
            fidelity_grade=FidelityGrade.ACCEPTABLE_APPROXIMATION,
            confidence=0.5,
        )
        assert effective_class(plan, ReversibilityClass.R2) == ReversibilityClass.R3
