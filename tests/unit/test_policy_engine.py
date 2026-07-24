"""Unit tests for the escalation decision engine (``unwind/policy/engine.py``)."""

from __future__ import annotations

from unwind.policy.config import PolicyConfig
from unwind.policy.engine import decide
from unwind.types import (
    BlastRadius,
    Classification,
    CompensationPlan,
    Decision,
    FidelityGrade,
    ReversibilityClass,
)


def _cls(rc: ReversibilityClass, conf: float = 0.9) -> Classification:
    return Classification(rev_class=rc, confidence=conf)


def _viable_plan(conf: float = 0.9) -> CompensationPlan:
    return CompensationPlan(
        forward="create_x",
        inverse_tool="delete_x",
        fidelity_grade=FidelityGrade.SEMANTIC,
        confidence=conf,
    )


class TestBaseDecisions:
    def test_r0_auto_allow(self) -> None:
        d = decide(_cls(ReversibilityClass.R0), BlastRadius(count=1), None)
        assert d.decision == Decision.AUTO_ALLOW

    def test_passthrough_only_auto_allow(self) -> None:
        cfg = PolicyConfig(passthrough_only=True)
        # Even an R4 unbounded call is auto-allowed in panic mode.
        d = decide(_cls(ReversibilityClass.R4), BlastRadius(unbounded=True), None, cfg)
        assert d.decision == Decision.AUTO_ALLOW

    def test_r4_unbounded_blocks(self) -> None:
        d = decide(_cls(ReversibilityClass.R4), BlastRadius(unbounded=True), None)
        assert d.decision == Decision.BLOCK


class TestElicitation:
    def test_r3_elicits(self) -> None:
        d = decide(_cls(ReversibilityClass.R3), BlastRadius(count=1), _viable_plan())
        assert d.decision == Decision.ELICIT_CONFIRMATION
        assert d.confirm_message is not None

    def test_r3_blocks_when_no_elicitation_channel(self) -> None:
        cfg = PolicyConfig(client_supports_elicitation=False)
        d = decide(_cls(ReversibilityClass.R3), BlastRadius(count=1), _viable_plan(), cfg)
        # Fail safe: cannot ask -> block, never silently proceed.
        assert d.decision == Decision.BLOCK

    def test_low_confidence_reversible_elicits(self) -> None:
        d = decide(_cls(ReversibilityClass.R2, conf=0.3), BlastRadius(count=1), _viable_plan())
        assert d.decision == Decision.ELICIT_CONFIRMATION
        assert "low confidence" in d.reason

    def test_high_blast_reversible_elicits(self) -> None:
        # R2, confident, viable plan, but blast radius exceeds threshold.
        blast = BlastRadius(count=1000, unbounded=False, scope="1000 rows")
        d = decide(_cls(ReversibilityClass.R2), blast, _viable_plan())
        assert d.decision == Decision.ELICIT_CONFIRMATION
        assert "blast radius" in d.reason

    def test_unbounded_reversible_elicits(self) -> None:
        blast = BlastRadius(unbounded=True, scope="unbounded")
        d = decide(_cls(ReversibilityClass.R2), blast, _viable_plan())
        assert d.decision == Decision.ELICIT_CONFIRMATION


class TestAutoAllowLogged:
    def test_reversible_viable_confident_auto_allow_logged(self) -> None:
        d = decide(_cls(ReversibilityClass.R2), BlastRadius(count=1), _viable_plan())
        assert d.decision == Decision.AUTO_ALLOW_LOGGED

    def test_r1_viable_auto_allow_logged(self) -> None:
        plan = CompensationPlan(
            forward="update_x",
            inverse_tool="update_x",
            pre_read="get_x",
            fidelity_grade=FidelityGrade.EXACT,
            confidence=0.8,
        )
        d = decide(_cls(ReversibilityClass.R1), BlastRadius(count=1), plan)
        assert d.decision == Decision.AUTO_ALLOW_LOGGED

    def test_reversible_no_viable_plan_escalates(self) -> None:
        # Confident, bounded, but no viable compensation -> escalate (never
        # over-promise undo).
        no_plan = CompensationPlan(
            forward="create_x",
            inverse_tool=None,
            fidelity_grade=FidelityGrade.FAILED,
            confidence=0.0,
        )
        d = decide(_cls(ReversibilityClass.R2), BlastRadius(count=1), no_plan)
        assert d.decision == Decision.ELICIT_CONFIRMATION

    def test_low_plan_confidence_escalates(self) -> None:
        weak = CompensationPlan(
            forward="create_x",
            inverse_tool="delete_x",
            fidelity_grade=FidelityGrade.ACCEPTABLE_APPROXIMATION,
            confidence=0.2,
        )
        d = decide(_cls(ReversibilityClass.R2), BlastRadius(count=1), weak)
        assert d.decision == Decision.ELICIT_CONFIRMATION


class TestDecisionResultProps:
    def test_intervenes(self) -> None:
        elicit = decide(_cls(ReversibilityClass.R3), BlastRadius(count=1), None)
        assert elicit.intervenes is True
        allow = decide(_cls(ReversibilityClass.R0), BlastRadius(count=1), None)
        assert allow.intervenes is False
