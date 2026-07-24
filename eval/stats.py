"""Bootstrap confidence intervals and paired significance tests (``PROJECT.md`` §8).

The experimental protocol (§8, "Statistics") requires **bootstrap 95% CIs on
every headline number** and **paired tests for system comparisons**. Everything
here is deterministic given a seed so ``make results`` reproduces byte-identical
intervals and CI regression tests can pin exact numbers.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

import numpy as np

__all__ = [
    "ConfidenceInterval",
    "bootstrap_ci",
    "paired_bootstrap",
    "paired_permutation_test",
]

T = TypeVar("T")


@dataclass(frozen=True)
class ConfidenceInterval:
    """A point estimate with a two-sided bootstrap interval.

    Attributes
    ----------
    point:
        The statistic evaluated on the full sample.
    low, high:
        The ``(1 - level)/2`` and ``1 - (1 - level)/2`` percentiles of the
        bootstrap distribution.
    level:
        Nominal coverage (0.95 by default).
    n_resamples:
        Number of bootstrap resamples drawn.
    """

    point: float
    low: float
    high: float
    level: float
    n_resamples: int

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.point, self.low, self.high)


def _percentile_bounds(level: float) -> tuple[float, float]:
    alpha = 1.0 - level
    return (100.0 * alpha / 2.0, 100.0 * (1.0 - alpha / 2.0))


def bootstrap_ci(
    sample: Sequence[T],
    statistic: Callable[[Sequence[T]], float],
    *,
    level: float = 0.95,
    n_resamples: int = 10_000,
    seed: int = 0,
) -> ConfidenceInterval:
    """Percentile bootstrap 95% CI for an arbitrary statistic (§8 "Statistics").

    Draws ``n_resamples`` case-resamples (sampling rows with replacement),
    evaluates ``statistic`` on each, and returns the ``level`` percentile
    interval. Seeded via :class:`numpy.random.default_rng` so the interval is
    deterministic and reproducible for ``make results`` and regression tests.

    Parameters
    ----------
    sample:
        The observed data as a sequence of rows; resampled by index.
    statistic:
        A function mapping a resampled sub-sequence to a scalar. Must accept a
        list of the same element type as ``sample``.
    level:
        Nominal two-sided coverage (default 0.95 per the protocol).
    n_resamples:
        Bootstrap replicate count (default 10 000).
    seed:
        RNG seed; identical seeds reproduce identical intervals.
    """
    if not sample:
        raise ValueError("bootstrap_ci requires a non-empty sample")
    if not 0.0 < level < 1.0:
        raise ValueError("level must be in (0, 1)")
    rng = np.random.default_rng(seed)
    n = len(sample)
    idx = np.arange(n)
    point = float(statistic(list(sample)))
    replicates = np.empty(n_resamples, dtype=float)
    for i in range(n_resamples):
        draw = rng.choice(idx, size=n, replace=True)
        replicates[i] = statistic([sample[j] for j in draw])
    lo_pct, hi_pct = _percentile_bounds(level)
    low = float(np.percentile(replicates, lo_pct))
    high = float(np.percentile(replicates, hi_pct))
    return ConfidenceInterval(point=point, low=low, high=high, level=level, n_resamples=n_resamples)


def paired_bootstrap(
    sample_a: Sequence[T],
    sample_b: Sequence[T],
    statistic: Callable[[Sequence[T]], float],
    *,
    level: float = 0.95,
    n_resamples: int = 10_000,
    seed: int = 0,
) -> ConfidenceInterval:
    """Paired bootstrap CI on the *difference* ``stat(A) - stat(B)`` (§8).

    Used for **system comparisons**: the two samples must be paired row-for-row
    (e.g. system A vs. system B on the same items), and the *same* resample
    indices are applied to both so the pairing is preserved. A CI that excludes
    0 indicates a significant difference at ``level``.
    """
    if len(sample_a) != len(sample_b):
        raise ValueError("paired_bootstrap requires equal-length paired samples")
    if not sample_a:
        raise ValueError("paired_bootstrap requires a non-empty sample")
    rng = np.random.default_rng(seed)
    n = len(sample_a)
    idx = np.arange(n)
    point = float(statistic(list(sample_a)) - statistic(list(sample_b)))
    replicates = np.empty(n_resamples, dtype=float)
    for i in range(n_resamples):
        draw = rng.choice(idx, size=n, replace=True)
        ra = statistic([sample_a[j] for j in draw])
        rb = statistic([sample_b[j] for j in draw])
        replicates[i] = ra - rb
    lo_pct, hi_pct = _percentile_bounds(level)
    return ConfidenceInterval(
        point=point,
        low=float(np.percentile(replicates, lo_pct)),
        high=float(np.percentile(replicates, hi_pct)),
        level=level,
        n_resamples=n_resamples,
    )


def paired_permutation_test(
    values_a: Sequence[float],
    values_b: Sequence[float],
    *,
    n_permutations: int = 10_000,
    seed: int = 0,
    two_sided: bool = True,
) -> float:
    """Paired permutation test on the mean per-item difference (§8 "paired tests").

    Under H0 the sign of each paired difference ``a_i - b_i`` is exchangeable.
    We randomly flip signs ``n_permutations`` times and report the fraction of
    permutations whose absolute mean difference is at least the observed one
    (two-sided). Deterministic given ``seed``.

    Returns
    -------
    float
        A p-value in ``[0, 1]``. The observed assignment is always counted, so
        the minimum achievable p-value is ``1 / (n_permutations + 1)``.
    """
    if len(values_a) != len(values_b):
        raise ValueError("paired_permutation_test requires equal-length samples")
    diffs = np.asarray(values_a, dtype=float) - np.asarray(values_b, dtype=float)
    n = diffs.size
    if n == 0:
        raise ValueError("paired_permutation_test requires a non-empty sample")
    observed = float(np.mean(diffs))
    rng = np.random.default_rng(seed)
    count = 1  # count the observed (identity) assignment, per convention
    for _ in range(n_permutations):
        signs = rng.choice(np.array([-1.0, 1.0]), size=n)
        stat = float(np.mean(signs * diffs))
        if two_sided:
            if abs(stat) >= abs(observed) - 1e-12:
                count += 1
        elif stat >= observed - 1e-12:
            count += 1
    return count / (n_permutations + 1)
