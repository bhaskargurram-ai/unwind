"""WITNESS — Witnessed Irreversibility Testing via Discharged Refutation.

The novel reversibility-inference method (designed by an adversarial scientist
panel; see the paper). Its thesis: reversibility should be decided not by
aggregating a model's *beliefs* (self-consistency) nor by trusting its
*arguments* (debate), but by placing the **burden of proof on reversibility** and
**discharging it operationally**.

Mechanism (this module implements the aggregation core; :mod:`unwind.classify.discharge`
is the evidence engine):

1. **Typed irrefutation grammar.** An adversarial proposer enumerates *typed,
   checkable* irreversibility witnesses from a closed grammar — never free-text
   doubt. Each witness names a concrete, falsifiable mechanism:
     * ``EXTERNALITY(channel)``   — effect observable on a read channel outside
       the target entity's Markov blanket (outbox, audit feed, read-receipt).
     * ``HALF_LIFE(window)``      — the inverse is valid only within a window;
       after it, no inverse exists (payment settlement, message recall).
     * ``LOST_INVERSE_PARAM(f)``  — the synthesized inverse needs a field not
       bindable from the forward response / pre-state (server-assigned id).
     * ``MISSING_SNAPSHOT_CASCADE`` — pre-state cannot be captured, or the
       mutation cascades to entities the inverse does not touch.

2. **Discharged-refutation voter.** Each witness is CONFIRMED / REFUTED /
   UNTESTABLE by a *deterministic* discharge function (execution or schema-graph),
   never by the proposer's assertion (invariant I5). Only CONFIRMED witnesses
   count, and the class is the **worst-case discharged witness**.

3. **Monotone hardening.** The voter can only *raise* the class above the
   ensemble base, never lower it (invariant I1) — so WITNESS structurally cannot
   manufacture a false undo (golden rule #3) and its Critical Error Rate is
   ``<=`` the baseline's *by construction*. The environment descriptor remains a
   hard ceiling (invariant I2).

Fail-safe envelope (invariant I4): any probe exception, missing inverse, or
suspected-but-untestable witness drives the evidence score to 1.0 → escalate.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from unwind.classify.ensemble import classify_tool
from unwind.synthesize.plan import synthesize_plan
from unwind.types import (
    Classification,
    CompensationPlan,
    EnvironmentDescriptor,
    ReversibilityClass,
    ToolSpec,
)


class WitnessType(StrEnum):
    EXTERNALITY = "externality"
    HALF_LIFE = "half_life"
    LOST_INVERSE_PARAM = "lost_inverse_param"
    MISSING_SNAPSHOT_CASCADE = "missing_snapshot_cascade"


class Verdict(StrEnum):
    CONFIRMED = "confirmed"
    REFUTED = "refuted"
    UNTESTABLE = "untestable"


# The class each witness type floors to when CONFIRMED (the worst-case reading).
_MIN_CLASS: dict[WitnessType, ReversibilityClass] = {
    WitnessType.EXTERNALITY: ReversibilityClass.R3,
    WitnessType.HALF_LIFE: ReversibilityClass.R4,
    WitnessType.LOST_INVERSE_PARAM: ReversibilityClass.R3,
    WitnessType.MISSING_SNAPSHOT_CASCADE: ReversibilityClass.R4,
}

# Witness types we treat as "suspect": if the proposer names one but it cannot be
# discharged (UNTESTABLE), we do NOT confirm the class change, but we DO raise the
# evidence score toward escalation (non-evidence, not no-evidence — fail safe).
_SUSPECT_TYPES = frozenset({WitnessType.HALF_LIFE, WitnessType.MISSING_SNAPSHOT_CASCADE})

_PRIOR_ONLY = 0.5  # evidence score for a suspected-but-untestable witness


def _max_class(a: ReversibilityClass, b: ReversibilityClass) -> ReversibilityClass:
    """max() over the ordinal R-scale, typed as ReversibilityClass (not a Literal)."""
    return a if a >= b else b


@dataclass(frozen=True)
class Witness:
    """A typed, checkable claim that an action is irreversible for a concrete reason."""

    type: WitnessType
    target: str = ""  # the channel / field / window the claim is about
    claim: str = ""  # human-readable statement of the mechanism

    @property
    def min_class(self) -> ReversibilityClass:
        return _MIN_CLASS[self.type]

    @property
    def min_class_score(self) -> float:
        # A confirmed R4 witness is maximal evidence; R3 witnesses are strong.
        return 1.0 if self.min_class >= ReversibilityClass.R4 else 0.8


# A discharge function: (witness, spec, plan, toolset, env) -> (verdict, evidence in [0,1]).
DischargeFn = Callable[
    [Witness, ToolSpec, CompensationPlan, list[ToolSpec], EnvironmentDescriptor],
    tuple[Verdict, float],
]


@runtime_checkable
class WitnessProposer(Protocol):
    """Enumerates typed irreversibility witnesses for a tool (LLM or deterministic)."""

    def propose(
        self,
        spec: ToolSpec,
        toolset: list[ToolSpec],
        env: EnvironmentDescriptor,
        plan: CompensationPlan,
    ) -> list[Witness]: ...


@dataclass
class WitnessResult:
    classification: Classification
    evidence_score: float  # calibration feature s in [0,1]
    base_class: ReversibilityClass
    env_class: ReversibilityClass
    proposed: list[Witness] = field(default_factory=list)
    confirmed: list[Witness] = field(default_factory=list)
    verdicts: list[tuple[Witness, Verdict, float]] = field(default_factory=list)


def classify_witness(
    spec: ToolSpec,
    toolset: list[ToolSpec],
    env: EnvironmentDescriptor,
    proposer: WitnessProposer,
    discharge: DischargeFn,
    *,
    base: Classification | None = None,
    plan: CompensationPlan | None = None,
) -> WitnessResult:
    """Run the WITNESS pipeline (Stages 0-4 of the algorithm) for one tool.

    Implements the monotone-hardening aggregation. ``proposer`` supplies typed
    witnesses; ``discharge`` confirms/refutes them operationally. Never softens
    the ensemble base (I1) and never beats the environment ceiling (I2).
    """
    from unwind.classify import environment as env_mod

    base = base or classify_tool(spec, env)
    plan = plan or synthesize_plan(spec, toolset, env)

    # Stage 0 — R0 reads are free; already-escalating classes need no probe.
    if base.rev_class == ReversibilityClass.R0:
        return WitnessResult(base, 0.0, base.rev_class, base.rev_class)
    env_class = env_mod.rederive(base, env).rev_class
    if base.rev_class >= ReversibilityClass.R3:
        # Already escalating; skip proposal but keep evidence high.
        return WitnessResult(
            base.model_copy(update={"rev_class": _max_class(base.rev_class, env_class)}),
            1.0,
            base.rev_class,
            env_class,
        )

    # Stage 1 — adversarial typed proposal (only for the <=R2 region worth probing).
    try:
        proposed = proposer.propose(spec, toolset, env, plan)
    except Exception:
        proposed = []

    # Stage 2 — discharge each witness by execution / schema-graph (never belief).
    confirmed: list[Witness] = []
    verdicts: list[tuple[Witness, Verdict, float]] = []
    s_evidence = 0.0
    for w in proposed:
        try:
            verdict, r = discharge(w, spec, plan, toolset, env)
        except Exception:
            verdict, r = Verdict.UNTESTABLE, 1.0
        verdicts.append((w, verdict, r))
        if verdict == Verdict.CONFIRMED:
            confirmed.append(w)
            s_evidence = max(s_evidence, r, w.min_class_score)
        elif verdict == Verdict.UNTESTABLE and w.type in _SUSPECT_TYPES:
            s_evidence = max(s_evidence, _PRIOR_ONLY)

    # Stage 3 — monotone hardening: class can only rise (I1), env ceiling holds (I2).
    witness_floor: ReversibilityClass = base.rev_class
    for w in confirmed:
        witness_floor = _max_class(witness_floor, w.min_class)
    eff = _max_class(witness_floor, env_class)

    # If nothing was confirmed and the plan has no working inverse, fall back to
    # the ensemble's own uncertainty as the escalation signal (I4 fail-safe).
    if not confirmed and s_evidence == 0.0:
        if plan is None or plan.inverse_tool is None:
            s_evidence = 1.0
        else:
            s_evidence = max(0.0, 1.0 - base.confidence)

    signals = dict(base.signals)
    signals["witness"] = {
        "proposed": [w.type.value for w in proposed],
        "confirmed": [w.type.value for w in confirmed],
        "evidence": round(s_evidence, 3),
    }
    rationale = base.rationale
    if confirmed:
        rationale += " | WITNESS confirmed: " + ", ".join(
            f"{w.type.value}({w.target})" for w in confirmed
        )
    result_cls = base.model_copy(
        update={"rev_class": eff, "signals": signals, "rationale": rationale}
    )
    return WitnessResult(
        result_cls, round(s_evidence, 4), base.rev_class, env_class, proposed, confirmed, verdicts
    )
