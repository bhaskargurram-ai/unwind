"""Stage 4 — plan emission + Stage 6 confidence/fallback (``PROJECT.md`` §6).

Combines the effect type, the best inverse candidate, and the pre-state reader
into a :class:`CompensationPlan`. Crucially it implements the fallback rule
(golden rule #3): **never over-promise reversibility**. When the structural
evidence is weak, the plan's fidelity is graded down and the effective class is
degraded (R2→R3) so the policy escalates rather than promising a broken undo.
"""

from __future__ import annotations

from unwind.synthesize.effect_typing import effect_type
from unwind.synthesize.inverse_search import find_inverse
from unwind.synthesize.prestate import find_prestate_reader
from unwind.types import (
    CompensationPlan,
    EffectVerb,
    EnvironmentDescriptor,
    FidelityGrade,
    ReversibilityClass,
    ToolSpec,
)

# Default reversibility half-lives (seconds) by verb, when the tool doesn't
# declare one. The novel "reversibility half-life" dimension (§5.2).
_DEFAULT_HALF_LIFE: dict[EffectVerb, float] = {
    EffectVerb.SEND: 30.0,  # email recall / message unsend window
}


def _residue_for(verb: EffectVerb, external: bool) -> list[str]:
    residue: list[str] = []
    if verb == EffectVerb.SEND or external:
        residue.append("notification/read-receipt may already have fired")
    if verb in (EffectVerb.CREATE, EffectVerb.DELETE, EffectVerb.UPDATE):
        residue.append("audit-log entry and version bump are not removable by undo")
    return residue


def synthesize_plan(
    target: ToolSpec,
    toolset: list[ToolSpec],
    env: EnvironmentDescriptor | None = None,
) -> CompensationPlan:
    """Emit a :class:`CompensationPlan` for ``target`` against its ``toolset``."""
    env = env or EnvironmentDescriptor()
    verb, _entity = effect_type(target)

    reader = find_prestate_reader(target, toolset)
    candidate = find_inverse(target, toolset)
    half_life = target.half_life_s or _DEFAULT_HALF_LIFE.get(verb)
    external = target.externality.value == "external"
    residue = _residue_for(verb, external)

    # --- Case A: self-reversible (R1) — same tool writes back captured pre-state
    if verb in (EffectVerb.UPDATE,) and reader is not None and env.supports_snapshot:
        return CompensationPlan(
            pre_read=reader.name,
            forward=target.name,
            inverse_tool=target.name,
            inverse_template={"__from_prestate__": True},
            expiry_s=half_life,
            fidelity_grade=FidelityGrade.EXACT,
            confidence=0.8,
            residue=residue,
            rationale=f"self-reversible: {reader.name} snapshots, {target.name} restores",
        )

    # --- Case B: compensable (R2) — a sibling inverse tool exists
    if candidate is not None and candidate.score >= 0.5:
        # Fidelity depends on how strong the structural match is.
        if candidate.score >= 0.85:
            fidelity = FidelityGrade.SEMANTIC
            confidence = candidate.score
        else:
            # Weak match: acceptable approximation at best, and low confidence
            # must NOT masquerade as a firm undo → caller degrades the class.
            fidelity = FidelityGrade.ACCEPTABLE_APPROXIMATION
            confidence = candidate.score * 0.8
        return CompensationPlan(
            pre_read=reader.name if reader else None,
            forward=target.name,
            inverse_tool=candidate.tool.name,
            inverse_template={"__bind_id_from_result__": True},
            expiry_s=half_life,
            fidelity_grade=fidelity,
            confidence=round(confidence, 3),
            residue=residue,
            rationale=(
                f"compensable via {candidate.tool.name} "
                f"(score={candidate.score:.2f}, {candidate.signals})"
            ),
        )

    # --- Case C: no viable inverse → not compensable; declare it honestly
    return CompensationPlan(
        pre_read=reader.name if reader else None,
        forward=target.name,
        inverse_tool=None,
        expiry_s=half_life,
        fidelity_grade=FidelityGrade.FAILED,
        confidence=0.0,
        residue=residue or ["no inverse available"],
        rationale="no inverse candidate met the threshold; not compensable",
    )


def effective_class(plan: CompensationPlan, base: ReversibilityClass) -> ReversibilityClass:
    """Map a plan + base class to the class Unwind will actually *act on*.

    Enforces the never-over-promise rule: a plan is only allowed to *promote* a
    delete/irreversible base toward reversibility to the extent its fidelity and
    confidence support; otherwise the base (more irreversible) class stands.
    """
    if plan.inverse_tool is None:
        # No inverse: cannot be better than R3 (mitigable) and never R0–R2.
        return max(base, ReversibilityClass.R3)

    if plan.fidelity_grade >= FidelityGrade.SEMANTIC and plan.confidence >= 0.7:
        if plan.inverse_tool == plan.forward:
            return ReversibilityClass.R1
        return ReversibilityClass.R2

    if plan.fidelity_grade >= FidelityGrade.ACCEPTABLE_APPROXIMATION and plan.confidence >= 0.4:
        # Weak compensation: degrade R2→R3 and escalate (golden rule #3).
        return max(base, ReversibilityClass.R3)

    return max(base, ReversibilityClass.R3)
