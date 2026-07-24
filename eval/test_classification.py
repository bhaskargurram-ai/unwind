"""Hand-computed numeric regression tests for §8.A classification metrics.

Every assertion pins a number derivable by hand from the fixture (golden rule
#10). The confusion set below is small enough to compute macro-F1, ordinal MAE
and CER on paper.
"""

from __future__ import annotations

import math

import pytest

from eval.classification import (
    binary_aupr,
    binary_auroc,
    critical_error_rate,
    environment_sensitivity,
    macro_f1,
    ordinal_mae,
    per_class_f1,
)
from unwind.types import ReversibilityClass as RC


def test_per_class_and_macro_f1_hand_computed() -> None:
    # Fixture (6 items). true -> pred:
    #   R0->R0, R0->R0, R1->R1, R2->R3, R4->R4, R4->R2
    y_true = [RC.R0, RC.R0, RC.R1, RC.R2, RC.R4, RC.R4]
    y_pred = [RC.R0, RC.R0, RC.R1, RC.R3, RC.R4, RC.R2]

    f1 = per_class_f1(y_true, y_pred)
    # R0: TP=2, FP=0, FN=0 -> F1 = 4/4 = 1.0
    assert f1[RC.R0] == pytest.approx(1.0)
    # R1: TP=1, FP=0, FN=0 -> 1.0
    assert f1[RC.R1] == pytest.approx(1.0)
    # R2: TP=0 (true R2 predicted R3), FP=1 (true R4 predicted R2), FN=1 -> 0.0
    assert f1[RC.R2] == pytest.approx(0.0)
    # R3: TP=0, FP=1 (true R2 predicted R3), FN=0 -> 0.0
    assert f1[RC.R3] == pytest.approx(0.0)
    # R4: TP=1, FP=0, FN=1 (true R4 predicted R2) -> 2*1/(2+0+1) = 2/3
    assert f1[RC.R4] == pytest.approx(2.0 / 3.0)

    # macro = mean of [1, 1, 0, 0, 2/3] = (2 + 2/3)/5 = (8/3)/5 = 8/15
    assert macro_f1(y_true, y_pred) == pytest.approx(8.0 / 15.0)


def test_ordinal_mae_hand_computed() -> None:
    y_true = [RC.R0, RC.R0, RC.R1, RC.R2, RC.R4, RC.R4]
    y_pred = [RC.R0, RC.R0, RC.R1, RC.R3, RC.R4, RC.R2]
    # abs diffs: 0,0,0,1,0,2 -> sum 3 over 6 -> 0.5
    assert ordinal_mae(y_true, y_pred) == pytest.approx(0.5)


def test_critical_error_rate_hand_computed() -> None:
    # true R4 count = 2; one predicted R2 (<=R2 -> critical), one predicted R4.
    y_true = [RC.R0, RC.R0, RC.R1, RC.R2, RC.R4, RC.R4]
    y_pred = [RC.R0, RC.R0, RC.R1, RC.R3, RC.R4, RC.R2]
    # 1 critical / 2 true-R4 = 0.5
    assert critical_error_rate(y_true, y_pred) == pytest.approx(0.5)


def test_critical_error_rate_boundary_r2_is_critical() -> None:
    # R2 counts as "<=R2" -> critical (over-promising).
    assert critical_error_rate([RC.R4], [RC.R2]) == pytest.approx(1.0)
    # R3 is NOT critical (still escalates, no false reversibility promise).
    assert critical_error_rate([RC.R4], [RC.R3]) == pytest.approx(0.0)


def test_critical_error_rate_no_r4_is_zero() -> None:
    assert critical_error_rate([RC.R0, RC.R1], [RC.R4, RC.R4]) == 0.0


def test_binary_auroc_hand_computed() -> None:
    # Positives (R4) scores {0.9, 0.6}; negatives (<R4) scores {0.4, 0.2, 0.5}.
    # Every positive outscores every negative -> perfect AUROC = 1.0.
    y_true = [RC.R4, RC.R4, RC.R1, RC.R0, RC.R2]
    scores = [0.9, 0.6, 0.4, 0.2, 0.5]
    assert binary_auroc(y_true, scores) == pytest.approx(1.0)


def test_binary_auroc_with_tie() -> None:
    # One positive (0.5), one negative (0.5) tie, one negative (0.1) below.
    # Pairs: pos vs neg1 (tie -> 0.5), pos vs neg2 (0.5>0.1 -> 1). Mean=1.5/2=0.75.
    y_true = [RC.R4, RC.R1, RC.R0]
    scores = [0.5, 0.5, 0.1]
    assert binary_auroc(y_true, scores) == pytest.approx(0.75)


def test_binary_auroc_single_class_returns_half() -> None:
    assert binary_auroc([RC.R0, RC.R1], [0.3, 0.7]) == pytest.approx(0.5)


def test_binary_aupr_perfect() -> None:
    # Positives strictly outscore negatives -> AP = 1.0.
    y_true = [RC.R4, RC.R4, RC.R0, RC.R1]
    scores = [0.9, 0.8, 0.2, 0.1]
    assert binary_aupr(y_true, scores) == pytest.approx(1.0)


def test_binary_aupr_hand_computed_interleaved() -> None:
    # Descending score order: P(0.9), N(0.8), P(0.7).  n_pos=2.
    # step1 P: tp=1,fp=0 -> P=1.0, R=0.5 -> +(0.5-0)*1.0 = 0.5
    # step2 N: tp=1,fp=1 -> P=0.5, R=0.5 -> +(0.5-0.5)*0.5 = 0
    # step3 P: tp=2,fp=1 -> P=2/3, R=1.0 -> +(1.0-0.5)*(2/3) = 1/3
    # AP = 0.5 + 1/3 = 5/6
    y_true = [RC.R4, RC.R0, RC.R4]
    scores = [0.9, 0.8, 0.7]
    assert binary_aupr(y_true, scores) == pytest.approx(5.0 / 6.0)


def test_environment_sensitivity_hand_computed() -> None:
    # write_file: R1 (git) -> R4 (versionless); delete: R2 -> R4; read: R0 -> R0.
    env_a = [RC.R1, RC.R2, RC.R0, RC.R0]
    env_b = [RC.R4, RC.R4, RC.R0, RC.R0]
    # 2 of 4 changed -> 0.5
    assert environment_sensitivity(env_a, env_b) == pytest.approx(0.5)


def test_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        macro_f1([RC.R0], [RC.R0, RC.R1])
    with pytest.raises(ValueError):
        ordinal_mae([], [])


def test_ordinal_mae_is_nonnegative_and_finite() -> None:
    val = ordinal_mae([RC.R4, RC.R0], [RC.R0, RC.R4])
    assert math.isfinite(val)
    assert val == pytest.approx(4.0)  # |0-4| + |4-0| = 8 over 2
