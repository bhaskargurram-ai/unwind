"""§8.C — Escalation-policy metrics: selective prediction with asymmetric loss.

Structurally identical to VerifyDoc's abstention layer (§2, §8), applied to
*actions* instead of extracted fields. The escalation policy thresholds an
**irreversibility risk score** ``s ∈ [0, 1]``: above the threshold we interrupt
the human (elicit confirmation), below we auto-allow.

Two rates trade off over the threshold (§8.C):
* **interruption rate** — fraction of actions we interrupt (the fatigue cost).
* **irreversible-damage rate** — fraction of truly-irreversible actions we let
  through *unconfirmed* (the safety cost).

The headline product number is :func:`interruptions_at_damage` at a 1% damage
target: how rarely we interrupt while leaking ≤1% of irreversible actions.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from unwind.types import ReversibilityClass

__all__ = [
    "ECEResult",
    "InterruptionDamagePoint",
    "adaptive_ece",
    "damage_at_autoapprove_budget",
    "e_aurc",
    "ece",
    "fpr_at_tpr",
    "interruption_damage_curve",
    "interruptions_at_damage",
]


def _irreversible_mask(
    y_true: Sequence[ReversibilityClass],
    irreversible_at: ReversibilityClass,
) -> np.ndarray:
    return np.array([1 if t >= irreversible_at else 0 for t in y_true], dtype=int)


def _validate(scores: Sequence[float], y_true: Sequence[ReversibilityClass]) -> None:
    if len(scores) != len(y_true):
        raise ValueError("scores and y_true must have equal length")
    if not scores:
        raise ValueError("escalation metrics require a non-empty sample")


@dataclass(frozen=True)
class InterruptionDamagePoint:
    """One point on the interruption-damage curve.

    Attributes
    ----------
    threshold:
        Actions with ``score >= threshold`` are interrupted.
    interruption_rate:
        Fraction of *all* actions interrupted (per-session interruption load).
    damage_rate:
        Fraction of truly-irreversible actions auto-allowed (unconfirmed).
    """

    threshold: float
    interruption_rate: float
    damage_rate: float


def interruption_damage_curve(
    scores: Sequence[float],
    y_true: Sequence[ReversibilityClass],
    *,
    irreversible_at: ReversibilityClass = ReversibilityClass.R4,
) -> list[InterruptionDamagePoint]:
    """Interruption-damage curve — the risk-coverage analogue (§8.C).

    Sweeps the decision threshold over every distinct score (plus the two
    endpoints that interrupt-none / interrupt-all), and at each threshold reports
    ``interruption_rate`` vs ``damage_rate``. "Damage" = a truly-irreversible
    action (``rev_class >= irreversible_at``, default R4) with ``score <
    threshold`` (auto-allowed unconfirmed).

    The curve is monotone: raising the threshold interrupts fewer actions
    (interruption_rate ↓) but leaks more irreversible ones (damage_rate ↑). Sorted
    by ascending threshold (so ascending interruption... no: ascending threshold ⇒
    descending interruption_rate). Feeds :func:`e_aurc` and
    :func:`interruptions_at_damage`.
    """
    _validate(scores, y_true)
    s = np.asarray(scores, dtype=float)
    irr = _irreversible_mask(y_true, irreversible_at)
    n_irr = int(irr.sum())
    # Candidate thresholds: just above each distinct score covers "interrupt all
    # at/above this score"; we add +inf (interrupt none) and -inf (interrupt all).
    uniq = np.unique(s)
    thresholds = np.concatenate(([-np.inf], uniq, [np.inf]))
    points: list[InterruptionDamagePoint] = []
    for thr in thresholds:
        interrupted = s >= thr
        interruption_rate = float(np.mean(interrupted))
        if n_irr == 0:
            damage_rate = 0.0
        else:
            # irreversible AND auto-allowed (not interrupted)
            leaked = int(np.sum((irr == 1) & (~interrupted)))
            damage_rate = leaked / n_irr
        if np.isfinite(thr):
            thr_val = float(thr)
        elif thr > 0:
            thr_val = float(uniq.max()) + 1.0
        else:
            thr_val = float(uniq.min()) - 1.0
        points.append(
            InterruptionDamagePoint(
                threshold=thr_val,
                interruption_rate=interruption_rate,
                damage_rate=damage_rate,
            )
        )
    points.sort(key=lambda p: p.threshold)
    return points


def e_aurc(
    scores: Sequence[float],
    y_true: Sequence[ReversibilityClass],
    *,
    irreversible_at: ReversibilityClass = ReversibilityClass.R4,
) -> float:
    """E-AURC — area under the interruption-damage curve (§8.C).

    Unitless and comparable across systems (§8.C). Computed as the trapezoidal
    area of ``interruption_rate`` (y) against ``damage_rate`` (x) over the curve,
    with both axes in ``[0, 1]``. **Lower is better**: a perfect policy interrupts
    exactly the irreversible actions and nothing else, so it hugs the axes and its
    area → 0; a policy that must interrupt heavily to suppress damage sweeps out a
    large area.
    """
    points = interruption_damage_curve(scores, y_true, irreversible_at=irreversible_at)
    # Order by damage_rate ascending for integration over x = damage.
    pts = sorted(points, key=lambda p: (p.damage_rate, p.interruption_rate))
    x = np.array([p.damage_rate for p in pts], dtype=float)
    y = np.array([p.interruption_rate for p in pts], dtype=float)
    # Deduplicate identical x by keeping the max interruption (upper envelope).
    order = np.argsort(x, kind="stable")
    x, y = x[order], y[order]
    return float(np.trapezoid(y, x))


def interruptions_at_damage(
    scores: Sequence[float],
    y_true: Sequence[ReversibilityClass],
    *,
    target: float = 0.01,
    irreversible_at: ReversibilityClass = ReversibilityClass.R4,
) -> float:
    """Interruptions@1% damage — THE headline product number (§8.C).

    The minimum achievable **interruption rate** subject to holding the
    irreversible-damage rate at or below ``target`` (default 0.01 = 1%, per §2's
    success contract). Answers: "how rarely can we interrupt while letting through
    ≤1% of truly-irreversible actions unconfirmed?"

    Scans the curve for feasible operating points (``damage_rate <= target``) and
    returns the smallest interruption rate among them. Returns 1.0 if no operating
    point satisfies the target (must interrupt everything to stay safe).
    """
    points = interruption_damage_curve(scores, y_true, irreversible_at=irreversible_at)
    feasible = [p.interruption_rate for p in points if p.damage_rate <= target + 1e-12]
    if not feasible:
        return 1.0
    return float(min(feasible))


def damage_at_autoapprove_budget(
    scores: Sequence[float],
    y_true: Sequence[ReversibilityClass],
    k: float,
    *,
    irreversible_at: ReversibilityClass = ReversibilityClass.R4,
) -> float:
    """Damage@AutoApprove(k) — leakage under a fixed auto-approve budget (§8.C).

    ``k`` is the auto-approve budget as a fraction of all actions (e.g. 0.9 = we
    are willing to auto-approve 90% of actions, interrupting the riskiest 10%).
    The policy interrupts the top ``(1 - k)`` fraction by score; this function
    returns the resulting irreversible-damage rate (fraction of truly-irreversible
    actions that fall inside the auto-approved majority).

    We interrupt exactly the ``n_interrupt = round((1 - k)·N)`` highest-scoring
    actions by rank (stable tie-break), the boundary action included, then return
    the irreversible-damage rate among the auto-approved remainder.

    DECISION: budget is spent by *rank*, not by a score threshold — so an action
    at the cutoff rank is interrupted even if a lower-ranked action shares its
    score. This makes the auto-approved set exactly the bottom ``k·N`` by rank,
    matching "auto-approve budget of k" literally, rather than under-spending it
    when scores tie at the boundary.
    """
    if not 0.0 <= k <= 1.0:
        raise ValueError("k (auto-approve budget) must be in [0, 1]")
    _validate(scores, y_true)
    s = np.asarray(scores, dtype=float)
    irr = _irreversible_mask(y_true, irreversible_at)
    n = s.size
    n_irr = int(irr.sum())
    if n_irr == 0:
        return 0.0
    n_interrupt = round((1.0 - k) * n)
    if n_interrupt <= 0:
        return 1.0  # interrupt nothing -> every irreversible action leaks
    # Interrupt the top n_interrupt by rank (stable); boundary rank included.
    order = np.argsort(-s, kind="stable")
    interrupted = np.zeros(n, dtype=bool)
    interrupted[order[:n_interrupt]] = True
    # Auto-approved irreversible actions = leaked damage.
    leaked = int(np.sum((irr == 1) & (~interrupted)))
    return leaked / n_irr


@dataclass(frozen=True)
class ECEResult:
    """Calibration result with reliability-diagram data (§8.C).

    Attributes
    ----------
    ece:
        Expected Calibration Error (bin-count-weighted |confidence - accuracy|).
    bin_confidence, bin_accuracy, bin_count:
        Per-bin mean predicted score, empirical positive rate, and population —
        the three arrays needed to draw a reliability diagram.
    """

    ece: float
    bin_confidence: list[float]
    bin_accuracy: list[float]
    bin_count: list[int]


def _binary_positives(
    y_true: Sequence[ReversibilityClass], irreversible_at: ReversibilityClass
) -> np.ndarray:
    return _irreversible_mask(y_true, irreversible_at)


def ece(
    scores: Sequence[float],
    y_true: Sequence[ReversibilityClass],
    *,
    n_bins: int = 10,
    irreversible_at: ReversibilityClass = ReversibilityClass.R4,
) -> ECEResult:
    """Expected Calibration Error on the irreversibility risk score (§8.C).

    Equal-width binning of the score into ``n_bins`` bins on ``[0, 1]``. For each
    bin, ``confidence`` = mean score, ``accuracy`` = empirical fraction of truly
    irreversible actions; ECE = ``Σ_b (n_b / N) · |conf_b - acc_b|``. Also returns
    per-bin arrays for the reliability diagram (§8.C "with a reliability diagram").

    DECISION: bins are ``[edge_i, edge_{i+1})`` half-open except the last, which
    is closed on the right so score == 1.0 lands in the top bin.
    """
    _validate(scores, y_true)
    s = np.asarray(scores, dtype=float)
    pos = _binary_positives(y_true, irreversible_at).astype(float)
    n = s.size
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    conf_out: list[float] = []
    acc_out: list[float] = []
    cnt_out: list[int] = []
    total_ece = 0.0
    for b in range(n_bins):
        lo, hi = edges[b], edges[b + 1]
        # Last bin is closed on the right so score == 1.0 lands in the top bin.
        mask = (s >= lo) & (s <= hi) if b == n_bins - 1 else (s >= lo) & (s < hi)
        count = int(mask.sum())
        if count == 0:
            conf_out.append(0.0)
            acc_out.append(0.0)
            cnt_out.append(0)
            continue
        conf = float(s[mask].mean())
        acc = float(pos[mask].mean())
        conf_out.append(conf)
        acc_out.append(acc)
        cnt_out.append(count)
        total_ece += (count / n) * abs(conf - acc)
    return ECEResult(
        ece=total_ece, bin_confidence=conf_out, bin_accuracy=acc_out, bin_count=cnt_out
    )


def adaptive_ece(
    scores: Sequence[float],
    y_true: Sequence[ReversibilityClass],
    *,
    n_bins: int = 10,
    irreversible_at: ReversibilityClass = ReversibilityClass.R4,
) -> ECEResult:
    """Adaptive ECE — equal-*mass* binning variant (§8.C "ECE / Adaptive ECE").

    Identical to :func:`ece` but bins are chosen so each holds (approximately) the
    same *number* of samples (quantile edges), which removes the sensitivity of
    fixed-width ECE to sparsely-populated score regions. Ties may make bins
    unequal; empty bins are skipped.
    """
    _validate(scores, y_true)
    s = np.asarray(scores, dtype=float)
    pos = _binary_positives(y_true, irreversible_at).astype(float)
    n = s.size
    order = np.argsort(s, kind="stable")
    s_sorted = s[order]
    pos_sorted = pos[order]
    # Split indices into n_bins near-equal contiguous chunks.
    splits = np.array_split(np.arange(n), min(n_bins, n))
    conf_out: list[float] = []
    acc_out: list[float] = []
    cnt_out: list[int] = []
    total_ece = 0.0
    for chunk in splits:
        if chunk.size == 0:
            continue
        conf = float(s_sorted[chunk].mean())
        acc = float(pos_sorted[chunk].mean())
        count = int(chunk.size)
        conf_out.append(conf)
        acc_out.append(acc)
        cnt_out.append(count)
        total_ece += (count / n) * abs(conf - acc)
    return ECEResult(
        ece=total_ece, bin_confidence=conf_out, bin_accuracy=acc_out, bin_count=cnt_out
    )


def fpr_at_tpr(
    scores: Sequence[float],
    y_true: Sequence[ReversibilityClass],
    *,
    tpr_target: float = 0.95,
    irreversible_at: ReversibilityClass = ReversibilityClass.R4,
) -> float:
    """FPR@95%TPR — needless interruptions at 95% irreversible-catch (§8.C).

    A direct fatigue proxy: with the threshold set so we interrupt at least
    ``tpr_target`` (default 95%) of truly-irreversible actions (TPR = recall on
    the positive class), what fraction of *reversible* actions do we needlessly
    interrupt (FPR)? Lower is better.

    Scans thresholds from most to least permissive and returns the FPR at the
    first threshold reaching the target TPR. Returns 1.0 if the target TPR is
    unreachable, and 0.0 if there are no negatives.
    """
    _validate(scores, y_true)
    s = np.asarray(scores, dtype=float)
    pos = _binary_positives(y_true, irreversible_at)
    n_pos = int(pos.sum())
    n_neg = int((pos == 0).sum())
    if n_pos == 0:
        return 0.0
    if n_neg == 0:
        return 0.0
    # Candidate thresholds: each distinct score. interrupted = score >= thr.
    best_fpr = 1.0
    found = False
    for thr in np.unique(s):
        interrupted = s >= thr
        tp = int(np.sum((pos == 1) & interrupted))
        fp = int(np.sum((pos == 0) & interrupted))
        tpr = tp / n_pos
        fpr = fp / n_neg
        if tpr >= tpr_target - 1e-12:
            # Among thresholds meeting the TPR floor, we want the smallest FPR.
            found = True
            best_fpr = min(best_fpr, fpr)
    return best_fpr if found else 1.0
