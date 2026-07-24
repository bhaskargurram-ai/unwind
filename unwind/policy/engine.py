"""Escalation decision engine (``PROJECT.md`` §2, §7, §8.C).

Maps ``(classification, blast_radius, compensation_plan, config)`` to a
:class:`Decision`. The whole point of the project lives here: **auto-allow the
reversible majority** (with a real undo log behind it) and **reserve interruption
for the irreversible minority** — so the approval signal means something again.

Two hard invariants (golden rules #2, #3):

* **Never auto-allow on uncertainty.** Unknown class, low confidence, failed
  classification, or missing compensation → escalate, never auto-allow.
* **Never rely on a compensation we don't trust.** A reversible verdict only
  earns ``auto_allow_logged`` if there is a viable, sufficiently-confident plan.
"""

from __future__ import annotations

from dataclasses import dataclass

from unwind.policy.config import PolicyConfig
from unwind.types import (
    BlastRadius,
    Classification,
    CompensationPlan,
    Decision,
    ReversibilityClass,
)


@dataclass(frozen=True)
class DecisionResult:
    decision: Decision
    reason: str
    confirm_message: str | None = None  # populated when eliciting

    @property
    def intervenes(self) -> bool:
        return self.decision in (Decision.ELICIT_CONFIRMATION, Decision.BLOCK)


def _confirm_message(cls: Classification, blast: BlastRadius, plan: CompensationPlan | None) -> str:
    scope = blast.scope or ("unbounded" if blast.unbounded else "1 entity")
    line = (
        f"'{cls.effect_verb.value}' action classified {cls.rev_class.name} "
        f"({cls.rev_class.label}); blast radius: {scope}."
    )
    if plan is not None and plan.inverse_tool:
        line += (
            f" If it goes wrong I can undo it via '{plan.inverse_tool}' "
            f"(fidelity: {plan.fidelity_grade.label})."
        )
    else:
        line += " I have no reliable way to undo this."
    if plan and plan.residue:
        line += f" Residue undo cannot remove: {'; '.join(plan.residue)}."
    return line + " Proceed?"


def decide(
    classification: Classification,
    blast: BlastRadius,
    plan: CompensationPlan | None,
    config: PolicyConfig | None = None,
) -> DecisionResult:
    """Decide how to handle a single ``tools/call``."""
    cfg = config or PolicyConfig()
    cls = classification
    rc = cls.rev_class

    # Panic switch: pure proxy, never intervene (golden rule #1 escape hatch).
    if cfg.passthrough_only:
        return DecisionResult(Decision.AUTO_ALLOW, "passthrough-only mode")

    # R0 reads are nullipotent: never touch the hot path (golden rule #7).
    if rc == ReversibilityClass.R0:
        return DecisionResult(Decision.AUTO_ALLOW, "R0 nullipotent read")

    # Hard block: irreversible with unbounded blast radius is never auto-run.
    if cfg.block_unbounded_irreversible and rc >= ReversibilityClass.R4 and blast.unbounded:
        return DecisionResult(
            Decision.BLOCK,
            "R4 with unbounded blast radius — refusing to auto-execute",
            _confirm_message(cls, blast, plan),
        )

    # Always confirm at/above the configured class, or for explicitly-fixed classes.
    if rc >= cfg.always_confirm_at or rc in cfg.fixed_confirm_classes:
        decision = (
            Decision.ELICIT_CONFIRMATION
            if cfg.client_supports_elicitation
            else Decision.BLOCK  # fail safe: can't ask → don't silently proceed
        )
        reason = f"{rc.name} needs confirmation"
        if not cfg.client_supports_elicitation:
            reason += " but client has no elicitation channel → blocking (fail safe)"
        return DecisionResult(decision, reason, _confirm_message(cls, blast, plan))

    # Low confidence on a supposedly-reversible action → escalate, don't auto-allow.
    if cls.confidence < cfg.min_confidence_auto_allow:
        return DecisionResult(
            Decision.ELICIT_CONFIRMATION if cfg.client_supports_elicitation else Decision.BLOCK,
            f"low confidence ({cls.confidence:.2f} < {cfg.min_confidence_auto_allow})",
            _confirm_message(cls, blast, plan),
        )

    # Reversible (R1/R2) but large blast radius → confirm even though undoable.
    if blast.is_high and (
        blast.unbounded
        or (blast.count is not None and blast.count > cfg.blast_radius_confirm_threshold)
    ):
        return DecisionResult(
            Decision.ELICIT_CONFIRMATION if cfg.client_supports_elicitation else Decision.BLOCK,
            f"reversible but high blast radius ({blast.scope})",
            _confirm_message(cls, blast, plan),
        )

    # Reversible + confident + bounded: auto-allow, but only *logged* if we truly
    # have a viable compensation. Otherwise escalate (never over-promise undo).
    if plan is not None and plan.is_viable and plan.confidence >= 0.4:
        return DecisionResult(
            Decision.AUTO_ALLOW_LOGGED,
            f"{rc.name} auto-allowed with undo plan via "
            f"{plan.inverse_tool or plan.forward} ({plan.fidelity_grade.label})",
        )

    return DecisionResult(
        Decision.ELICIT_CONFIRMATION if cfg.client_supports_elicitation else Decision.BLOCK,
        f"{rc.name} but no viable compensation to back an auto-allow",
        _confirm_message(cls, blast, plan),
    )
