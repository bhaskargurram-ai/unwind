"""Confidence calibration on risk scores (``PROJECT.md`` §8.C, W5).

Raw classifier confidences are not probabilities. Before the escalation policy
can honour a *target damage rate*, the risk scores must be calibrated so that
"0.9" means "wrong ~10% of the time". This reuses the selective-prediction
machinery from the wider research identity (VerifyDoc's abstention layer).

Implemented in pure Python (no hard ``numpy`` dependency) so calibration works in
the default install; the ``[metrics]`` extra is only needed for the eval plots.
Three standard methods:

* :class:`TemperatureScaler` — one scalar temperature on the logit (Guo et al.).
* :class:`IsotonicCalibrator` — non-parametric monotone fit via PAVA.
* :class:`ConformalRiskController` — distribution-free threshold for a target risk.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass, field


def _clip(p: float, eps: float = 1e-6) -> float:
    return min(1.0 - eps, max(eps, p))


def _logit(p: float) -> float:
    p = _clip(p)
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


@dataclass
class TemperatureScaler:
    """Single-parameter temperature scaling of probabilistic scores."""

    temperature: float = 1.0

    def fit(self, scores: list[float], labels: list[int], *, iters: int = 200) -> TemperatureScaler:
        """Fit ``T`` minimising negative log-likelihood via 1-D ternary search."""
        if not scores:
            return self
        logits = [_logit(s) for s in scores]

        def nll(t: float) -> float:
            total = 0.0
            for z, y in zip(logits, labels, strict=True):
                p = _clip(_sigmoid(z / t))
                total += -(y * math.log(p) + (1 - y) * math.log(1.0 - p))
            return total

        lo, hi = 0.05, 10.0
        for _ in range(iters):
            m1 = lo + (hi - lo) / 3.0
            m2 = hi - (hi - lo) / 3.0
            if nll(m1) < nll(m2):
                hi = m2
            else:
                lo = m1
        self.temperature = (lo + hi) / 2.0
        return self

    def transform(self, scores: list[float]) -> list[float]:
        return [_sigmoid(_logit(s) / self.temperature) for s in scores]

    def transform_one(self, score: float) -> float:
        return _sigmoid(_logit(score) / self.temperature)


@dataclass
class IsotonicCalibrator:
    """Non-parametric monotone calibration via pool-adjacent-violators (PAVA)."""

    _x: list[float] = field(default_factory=list)
    _y: list[float] = field(default_factory=list)

    def fit(self, scores: list[float], labels: list[int]) -> IsotonicCalibrator:
        if not scores:
            return self
        order = sorted(range(len(scores)), key=lambda i: scores[i])
        xs = [scores[i] for i in order]
        ys = [float(labels[i]) for i in order]
        # PAVA: merge adjacent blocks that violate monotonicity.
        weights = [1.0] * len(ys)
        values = ys[:]
        i = 0
        while i < len(values) - 1:
            if values[i] > values[i + 1]:
                new_w = weights[i] + weights[i + 1]
                new_v = (values[i] * weights[i] + values[i + 1] * weights[i + 1]) / new_w
                values[i] = new_v
                weights[i] = new_w
                del values[i + 1]
                del weights[i + 1]
                del xs[i + 1]
                if i > 0:
                    i -= 1
            else:
                i += 1
        self._x = xs
        self._y = values
        return self

    def transform_one(self, score: float) -> float:
        if not self._x:
            return score
        idx = bisect_left(self._x, score)
        if idx <= 0:
            return _clip(self._y[0])
        if idx >= len(self._x):
            return _clip(self._y[-1])
        return _clip(self._y[idx - 1])

    def transform(self, scores: list[float]) -> list[float]:
        return [self.transform_one(s) for s in scores]


@dataclass
class ConformalRiskController:
    """Distribution-free threshold for a target risk (split-conformal style).

    Given calibration risk scores for items whose true outcome (here: was the
    action actually irreversible / did the undo fail) is known, pick the score
    threshold that holds the miss rate at/below ``target`` with the conformal
    finite-sample correction.
    """

    threshold: float = 1.0

    def fit(
        self, risk_scores: list[float], is_bad: list[int], *, target: float = 0.01
    ) -> ConformalRiskController:
        """Fit a threshold so that auto-allowing below it misses ≤ ``target`` bad actions."""
        pairs = sorted(zip(risk_scores, is_bad, strict=True), key=lambda p: p[0])
        n = len(pairs)
        if n == 0:
            self.threshold = 1.0
            return self
        # Conformal quantile level with finite-sample correction.
        level = min(1.0, math.ceil((n + 1) * (1 - target)) / n)
        idx = min(n - 1, max(0, math.ceil(level * n) - 1))
        self.threshold = pairs[idx][0]
        return self

    def auto_allow(self, risk_score: float) -> bool:
        """Whether an action with this risk is safe to auto-allow under the target."""
        return risk_score <= self.threshold


def expected_calibration_error(scores: list[float], labels: list[int], *, bins: int = 10) -> float:
    """ECE (``PROJECT.md`` §8.C): |confidence − accuracy| averaged over bins."""
    if not scores:
        return 0.0
    n = len(scores)
    total = 0.0
    for b in range(bins):
        lo = b / bins
        hi = (b + 1) / bins
        members = [
            (s, y)
            for s, y in zip(scores, labels, strict=True)
            if (lo < s <= hi) or (b == 0 and s == 0)
        ]
        if not members:
            continue
        conf = sum(s for s, _ in members) / len(members)
        acc = sum(y for _, y in members) / len(members)
        total += (len(members) / n) * abs(conf - acc)
    return total
