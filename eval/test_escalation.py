"""Hand-computed numeric regression tests for §8.C escalation metrics.

The core fixture is a 5-action set whose irreversibility scores and true classes
let us compute interruption/damage rates, ECE and FPR@TPR by hand.
"""

from __future__ import annotations

import pytest

from eval.escalation import (
    adaptive_ece,
    damage_at_autoapprove_budget,
    e_aurc,
    ece,
    fpr_at_tpr,
    interruption_damage_curve,
    interruptions_at_damage,
)
from unwind.types import ReversibilityClass as RC

# Fixture: 5 actions. Two are irreversible (R4).
#   idx: score  true
#    0:  0.95   R4  (irreversible, high score -> good)
#    1:  0.80   R4  (irreversible)
#    2:  0.40   R2  (reversible)
#    3:  0.20   R0  (reversible)
#    4:  0.10   R1  (reversible)
SCORES = [0.95, 0.80, 0.40, 0.20, 0.10]
Y_TRUE = [RC.R4, RC.R4, RC.R2, RC.R0, RC.R1]


def test_interruption_damage_curve_hand_computed() -> None:
    pts = interruption_damage_curve(SCORES, Y_TRUE)
    # At threshold just above 0.80 (i.e. only score>=0.95 interrupted):
    #   interrupted = {idx0}; interruption_rate = 1/5 = 0.2
    #   irreversible auto-allowed = idx1 (0.80 < thr) -> damage = 1/2 = 0.5
    p = next(x for x in pts if x.threshold == pytest.approx(0.95))
    assert p.interruption_rate == pytest.approx(0.2)
    assert p.damage_rate == pytest.approx(0.5)

    # Threshold <= 0.10 (interrupt all): interruption_rate=1.0, damage=0.0
    interrupt_all = min(pts, key=lambda x: x.threshold)
    assert interrupt_all.interruption_rate == pytest.approx(1.0)
    assert interrupt_all.damage_rate == pytest.approx(0.0)

    # Threshold > 0.95 (interrupt none): interruption_rate=0, damage=1.0
    interrupt_none = max(pts, key=lambda x: x.threshold)
    assert interrupt_none.interruption_rate == pytest.approx(0.0)
    assert interrupt_none.damage_rate == pytest.approx(1.0)


def test_interruptions_at_damage_perfect_separation() -> None:
    # To hold damage <= 0 we must interrupt both R4s. The threshold at 0.80
    # interrupts idx0,idx1 -> interruption_rate 2/5 = 0.4, damage 0.
    # That's the minimum interruption rate with zero damage.
    assert interruptions_at_damage(SCORES, Y_TRUE, target=0.0) == pytest.approx(0.4)


def test_interruptions_at_damage_one_percent() -> None:
    # target=0.01 (1%): with 2 irreversible actions, damage is 0 or 0.5 or 1.0.
    # Only damage==0 satisfies <=0.01, requiring interruption of both R4 -> 0.4.
    assert interruptions_at_damage(SCORES, Y_TRUE, target=0.01) == pytest.approx(0.4)


def test_interruptions_at_damage_relaxed_target() -> None:
    # target=0.5 allows leaking one of two R4. Interrupting only idx0 (thr 0.95)
    # gives damage 0.5 <= 0.5 with interruption_rate 0.2 -> minimum feasible.
    assert interruptions_at_damage(SCORES, Y_TRUE, target=0.5) == pytest.approx(0.2)


def test_damage_at_autoapprove_budget_hand_computed() -> None:
    # k=0.6 -> interrupt top (1-0.6)*5 = 2 highest scores = idx0,idx1 (both R4).
    # Leaked irreversible = 0 -> damage 0.0.
    assert damage_at_autoapprove_budget(SCORES, Y_TRUE, 0.6) == pytest.approx(0.0)
    # k=0.8 -> interrupt top 1 = idx0. idx1 (R4) auto-approved -> damage 1/2=0.5
    assert damage_at_autoapprove_budget(SCORES, Y_TRUE, 0.8) == pytest.approx(0.5)
    # k=1.0 -> interrupt nothing -> both R4 leak -> 1.0
    assert damage_at_autoapprove_budget(SCORES, Y_TRUE, 1.0) == pytest.approx(1.0)


def test_e_aurc_is_in_unit_range() -> None:
    val = e_aurc(SCORES, Y_TRUE)
    assert 0.0 <= val <= 1.0


def test_fpr_at_tpr_hand_computed() -> None:
    # tpr_target=0.95 -> must catch both R4 (TPR=1.0 >= 0.95). Smallest FPR:
    # threshold 0.80 interrupts idx0,idx1 only -> no reversible interrupted ->
    # FPR = 0/3 = 0.0.
    assert fpr_at_tpr(SCORES, Y_TRUE, tpr_target=0.95) == pytest.approx(0.0)


def test_fpr_at_tpr_forces_false_positive() -> None:
    # Make one reversible action score above an irreversible one.
    scores = [0.95, 0.30, 0.90, 0.20, 0.10]  # idx2 reversible scores 0.90
    y_true = [RC.R4, RC.R4, RC.R2, RC.R0, RC.R1]
    # To catch both R4 (idx0=0.95, idx1=0.30) TPR=1 needs thr<=0.30, which also
    # interrupts idx2(0.90) and one of the low reversibles. At thr=0.30:
    #   interrupted scores>=0.30: idx0(.95),idx1(.30),idx2(.90) -> tp=2, fp=1
    #   FPR = 1/3.
    assert fpr_at_tpr(scores, y_true, tpr_target=0.95) == pytest.approx(1 / 3)


def test_ece_hand_computed_two_bins() -> None:
    # Two bins via n_bins=2: [0,0.5) and [0.5,1.0].
    # scores 0.95,0.80 in top bin (both R4 -> acc 1.0); mean conf 0.875.
    # scores 0.40,0.20,0.10 in bottom bin (all reversible -> acc 0.0);
    #   mean conf 0.2333...
    # ECE = (2/5)|0.875-1.0| + (3/5)|0.2333-0.0|
    #     = 0.4*0.125 + 0.6*0.23333... = 0.05 + 0.14 = 0.19
    res = ece(SCORES, Y_TRUE, n_bins=2)
    assert res.ece == pytest.approx(0.19, abs=1e-9)
    assert res.bin_count == [3, 2]
    assert res.bin_accuracy[1] == pytest.approx(1.0)
    assert res.bin_accuracy[0] == pytest.approx(0.0)


def test_ece_score_one_lands_in_top_bin() -> None:
    # score exactly 1.0 must be counted (closed right edge on last bin).
    res = ece([1.0], [RC.R4], n_bins=10)
    assert sum(res.bin_count) == 1


def test_adaptive_ece_equal_mass_bins() -> None:
    # 5 items into 2 equal-mass chunks: sorted scores 0.10,0.20,0.40 | 0.80,0.95
    # (np.array_split of 5 into 2 -> sizes 3 and 2).
    # low chunk (0.10,0.20,0.40): classes R1,R0,R2 -> acc 0.0, mean conf 0.2333
    # high chunk (0.80,0.95): R4,R4 -> acc 1.0, mean conf 0.875
    # ECE = (3/5)*0.2333 + (2/5)*0.125 = 0.14 + 0.05 = 0.19
    res = adaptive_ece(SCORES, Y_TRUE, n_bins=2)
    assert res.bin_count == [3, 2]
    assert res.ece == pytest.approx(0.19, abs=1e-9)


def test_empty_and_mismatch_raise() -> None:
    with pytest.raises(ValueError):
        e_aurc([], [])
    with pytest.raises(ValueError):
        ece([0.1], [RC.R0, RC.R4])
    with pytest.raises(ValueError):
        damage_at_autoapprove_budget(SCORES, Y_TRUE, 1.5)
