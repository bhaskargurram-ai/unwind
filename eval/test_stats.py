"""Regression tests for the bootstrap / permutation machinery (§8 "Statistics").

Seeded bootstrap intervals are pinned to exact numbers so ``make results`` and CI
reproduce them byte-for-byte. If numpy's default_rng stream ever changes these
will (correctly) fail and force a re-pin.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pytest

from eval.stats import (
    bootstrap_ci,
    paired_bootstrap,
    paired_permutation_test,
)


def _mean(xs: Sequence[float]) -> float:
    return float(np.mean(xs)) if xs else 0.0


def test_bootstrap_ci_point_is_exact_statistic() -> None:
    sample = [1.0, 2.0, 3.0, 4.0, 5.0]
    ci = bootstrap_ci(sample, _mean, seed=0, n_resamples=2000)
    assert ci.point == pytest.approx(3.0)  # mean of 1..5
    assert ci.low <= ci.point <= ci.high
    assert ci.level == 0.95
    assert ci.n_resamples == 2000


def test_bootstrap_ci_is_deterministic_across_calls() -> None:
    sample = [1.0, 2.0, 3.0, 4.0, 5.0]
    a = bootstrap_ci(sample, _mean, seed=42, n_resamples=1000)
    b = bootstrap_ci(sample, _mean, seed=42, n_resamples=1000)
    assert a.as_tuple() == b.as_tuple()


def test_bootstrap_ci_pinned_interval() -> None:
    # Pinned regression: identical seed/resamples MUST reproduce this interval.
    sample = [10.0, 12.0, 23.0, 23.0, 16.0, 23.0, 21.0, 16.0]
    ci = bootstrap_ci(sample, _mean, seed=7, n_resamples=5000)
    # Recompute reference independently with the same algorithm to pin it.
    rng = np.random.default_rng(7)
    idx = np.arange(len(sample))
    reps = np.array(
        [
            np.mean([sample[j] for j in rng.choice(idx, size=len(sample), replace=True)])
            for _ in range(5000)
        ]
    )
    assert ci.low == pytest.approx(float(np.percentile(reps, 2.5)))
    assert ci.high == pytest.approx(float(np.percentile(reps, 97.5)))


def test_paired_bootstrap_difference_zero_when_identical() -> None:
    a = [1.0, 2.0, 3.0, 4.0]
    ci = paired_bootstrap(a, list(a), _mean, seed=0, n_resamples=500)
    assert ci.point == pytest.approx(0.0)
    assert ci.low <= 0.0 <= ci.high


def test_paired_bootstrap_detects_shift() -> None:
    a = [5.0, 6.0, 7.0, 8.0]
    b = [1.0, 2.0, 3.0, 4.0]  # a is exactly 4 higher, elementwise
    ci = paired_bootstrap(a, b, _mean, seed=1, n_resamples=1000)
    assert ci.point == pytest.approx(4.0)
    # Constant per-pair difference -> every resample yields diff 4.
    assert ci.low == pytest.approx(4.0)
    assert ci.high == pytest.approx(4.0)


def test_paired_permutation_identical_is_nonsignificant() -> None:
    a = [1.0, 2.0, 3.0, 4.0, 5.0]
    p = paired_permutation_test(a, list(a), n_permutations=1000, seed=0)
    # All differences zero -> every permutation ties -> p = 1.0.
    assert p == pytest.approx(1.0)


def test_paired_permutation_strong_effect_is_significant() -> None:
    a = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    b = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]  # a uniformly 9 higher (constant diff)
    p = paired_permutation_test(a, b, n_permutations=2000, seed=0)
    # Diffs are constant (all 9), so |mean(signs*9)| >= 9 iff all signs agree
    # (all + or all -) -> two extreme sign vectors out of 2^6. For seed 0 the
    # draw hits an all-same-sign vector 58 times; +1 for the observed -> p =
    # 59/2001. Pinned exactly (deterministic given the seed).
    assert p == pytest.approx(59.0 / 2001.0)
    assert p < 0.05  # still clearly significant


def test_paired_permutation_is_deterministic() -> None:
    a = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0]
    b = [2.0, 6.0, 5.0, 3.0, 5.0, 8.0]
    p1 = paired_permutation_test(a, b, n_permutations=1000, seed=123)
    p2 = paired_permutation_test(a, b, n_permutations=1000, seed=123)
    assert p1 == p2


def test_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError):
        bootstrap_ci([], _mean)
    with pytest.raises(ValueError):
        paired_bootstrap([1.0], [1.0, 2.0], _mean)
    with pytest.raises(ValueError):
        paired_permutation_test([1.0], [1.0, 2.0])
