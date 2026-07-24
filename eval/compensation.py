"""§8.B — Compensation-synthesis metrics (``PROJECT.md`` §8).

Fidelity is **never** reported as a single "undo worked" number (golden rule #4 /
§8.B): :func:`rollback_fidelity_distribution` always returns the full histogram
over :class:`~unwind.types.FidelityGrade`. Residue (side-effects undo cannot
remove) is a first-class metric, per Garcia-Molina & Salem.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from unwind.types import CompensationPlan, FidelityGrade, ReversibilityClass, ToolSpec

__all__ = [
    "HalfLifeAccuracy",
    "compensation_coverage",
    "compensation_validity",
    "half_life_accuracy",
    "residue_rate",
    "rollback_fidelity_distribution",
]


def compensation_coverage(
    tools: Sequence[ToolSpec],
    plans: Sequence[CompensationPlan | None],
) -> float:
    """Compensation coverage — % of mutating tools receiving a candidate inverse (§8.B).

    Denominator is the set of **mutating** tools (``rev_class != R0``; R0 reads
    need no inverse). Numerator counts those whose paired plan is *viable*
    (:pyattr:`CompensationPlan.is_viable` — names an inverse tool or a pre-read
    for self-reversal). ``plans[i]`` is the synthesiser's output for ``tools[i]``
    (``None`` = no candidate produced).

    Returns a fraction in ``[0, 1]``; 0.0 if there are no mutating tools.
    """
    if len(tools) != len(plans):
        raise ValueError("tools and plans must be aligned and equal-length")
    mutating = [
        (t, p) for t, p in zip(tools, plans, strict=True) if t.rev_class != ReversibilityClass.R0
    ]
    if not mutating:
        return 0.0
    covered = sum(1 for _, p in mutating if p is not None and p.is_viable)
    return covered / len(mutating)


def compensation_validity(execution_ok: Sequence[bool]) -> float:
    """Compensation validity — % of synthesised inverses that execute w/o error (§8.B).

    ``execution_ok[i]`` is ``True`` iff the i-th synthesised inverse ran against
    the live sandbox without raising / returning a protocol error (independent of
    whether it *restored* state — that is fidelity, below). Fraction in ``[0, 1]``.
    """
    if not execution_ok:
        raise ValueError("compensation_validity requires a non-empty sample")
    return sum(1 for ok in execution_ok if ok) / len(execution_ok)


def rollback_fidelity_distribution(
    grades: Sequence[FidelityGrade],
) -> dict[FidelityGrade, float]:
    """Rollback fidelity distribution — histogram over grades, NEVER a scalar (§8.B).

    Returns the *proportion* of undos at each :class:`FidelityGrade`
    (failed / acceptable-approximation / semantic / exact). Every grade appears
    as a key even at proportion 0.0. Reporting the full distribution is
    mandatory (golden rule #4): a single "undo worked" number would hide the
    approximation that compensation inherently is (Garcia-Molina & Salem).
    """
    if not grades:
        raise ValueError("rollback_fidelity_distribution requires a non-empty sample")
    n = len(grades)
    return {g: sum(1 for x in grades if x == g) / n for g in FidelityGrade}


def residue_rate(residues: Sequence[Sequence[str]]) -> float:
    """Residue rate — % of undos leaving detectable side-effects (§8.B).

    ``residues[i]`` is the list of residual side-effects observed after the i-th
    undo (notifications fired, audit entries, version bumps — things undo cannot
    remove). An undo "leaves residue" iff that list is non-empty. Fraction in
    ``[0, 1]``.
    """
    if not residues:
        raise ValueError("residue_rate requires a non-empty sample")
    return sum(1 for r in residues if len(r) > 0) / len(residues)


@dataclass(frozen=True)
class HalfLifeAccuracy:
    """Result of :func:`half_life_accuracy`.

    Attributes
    ----------
    mae_seconds:
        Mean absolute error between predicted and actual reversibility windows.
    within_tolerance_rate:
        Fraction of predictions within ``tolerance_s`` of the actual window.
    n:
        Number of (predicted, actual) pairs scored.
    """

    mae_seconds: float
    within_tolerance_rate: float
    n: int


def half_life_accuracy(
    predicted_s: Sequence[float],
    actual_s: Sequence[float],
    *,
    tolerance_s: float = 5.0,
) -> HalfLifeAccuracy:
    """Half-life accuracy — predicted vs. actual reversibility window (§8.B).

    Reports MAE (in seconds) **and** a within-tolerance rate, per §8.B
    ("predicted vs actual window; report MAE + within-tolerance rate"). The
    reversibility half-life (§5.2, novel contribution) is the window in which an
    action stays reversible (email recall ~30 s, payment void-before-settlement,
    trash retention). ``tolerance_s`` is the absolute slack allowed when counting
    a prediction "correct".
    """
    if len(predicted_s) != len(actual_s):
        raise ValueError("predicted_s and actual_s must have equal length")
    if not predicted_s:
        raise ValueError("half_life_accuracy requires a non-empty sample")
    pred = np.asarray(predicted_s, dtype=float)
    act = np.asarray(actual_s, dtype=float)
    abs_err = np.abs(pred - act)
    mae = float(np.mean(abs_err))
    within = float(np.mean(abs_err <= tolerance_s))
    return HalfLifeAccuracy(mae_seconds=mae, within_tolerance_rate=within, n=len(predicted_s))
