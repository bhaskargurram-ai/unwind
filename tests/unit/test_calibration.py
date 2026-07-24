"""Unit tests for confidence calibration (``unwind/calibration/calibrate.py``)."""

from __future__ import annotations

import itertools
import math

from unwind.calibration.calibrate import (
    ConformalRiskController,
    IsotonicCalibrator,
    TemperatureScaler,
    expected_calibration_error,
)


def _nll(scores: list[float], labels: list[int]) -> float:
    eps = 1e-6
    total = 0.0
    for p, y in zip(scores, labels, strict=True):
        p = min(1.0 - eps, max(eps, p))
        total += -(y * math.log(p) + (1 - y) * math.log(1.0 - p))
    return total


class TestTemperatureScaler:
    def test_fit_reduces_nll_on_miscalibrated_set(self) -> None:
        # Overconfident scores: high scores but only ~half are correct.
        scores = [0.95, 0.9, 0.92, 0.88, 0.93, 0.9, 0.91, 0.89]
        labels = [1, 0, 1, 0, 1, 0, 1, 0]
        scaler = TemperatureScaler().fit(scores, labels)
        calibrated = scaler.transform(scores)
        assert _nll(calibrated, labels) < _nll(scores, labels)

    def test_transform_stays_in_open_unit_interval(self) -> None:
        scaler = TemperatureScaler(temperature=2.5)
        for p in (0.01, 0.5, 0.99):
            out = scaler.transform_one(p)
            assert 0.0 < out < 1.0

    def test_transform_batch(self) -> None:
        scaler = TemperatureScaler(temperature=1.0)
        out = scaler.transform([0.2, 0.8])
        assert all(0.0 < x < 1.0 for x in out)

    def test_fit_empty_is_noop(self) -> None:
        scaler = TemperatureScaler(temperature=3.0)
        scaler.fit([], [])
        assert scaler.temperature == 3.0


class TestIsotonicCalibrator:
    def test_monotonic_output(self) -> None:
        scores = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
        labels = [0, 0, 0, 1, 0, 1, 1, 1, 1]
        cal = IsotonicCalibrator().fit(scores, labels)
        xs = [i / 20 for i in range(21)]
        ys = [cal.transform_one(x) for x in xs]
        for a, b in itertools.pairwise(ys):
            assert b >= a - 1e-9  # non-decreasing

    def test_output_in_unit_interval(self) -> None:
        cal = IsotonicCalibrator().fit([0.2, 0.8], [0, 1])
        for x in (0.0, 0.5, 1.0):
            out = cal.transform_one(x)
            assert 0.0 <= out <= 1.0

    def test_empty_fit_is_identity(self) -> None:
        cal = IsotonicCalibrator().fit([], [])
        assert cal.transform_one(0.42) == 0.42


class TestConformalRiskController:
    def test_threshold_holds_target_on_toy_set(self) -> None:
        # A large calibration set where the conformal quantile is meaningful:
        # 40 low-risk good actions, 4 high-risk bad ones.
        risk = [0.02 * i for i in range(40)] + [0.9, 0.92, 0.95, 0.99]
        is_bad = [0] * 40 + [1, 1, 1, 1]
        ctrl = ConformalRiskController().fit(risk, is_bad, target=0.1)
        # At a 10% target, the fraction of the whole calibration sample that is
        # both bad and auto-allowed stays within the target risk budget.
        n = len(risk)
        bad_auto = sum(
            1 for r, b in zip(risk, is_bad, strict=True) if ctrl.auto_allow(r) and b == 1
        )
        assert bad_auto / n <= 0.1 + 1e-9
        # And every genuinely-low-risk good action is auto-allowed.
        assert all(ctrl.auto_allow(r) for r, b in zip(risk, is_bad, strict=True) if b == 0)

    def test_stricter_target_gives_tighter_threshold(self) -> None:
        risk = [0.02 * i for i in range(40)] + [0.9, 0.92, 0.95, 0.99]
        is_bad = [0] * 40 + [1, 1, 1, 1]
        strict = ConformalRiskController().fit(risk, is_bad, target=0.05).threshold
        loose = ConformalRiskController().fit(risk, is_bad, target=0.2).threshold
        # A stricter (smaller) target auto-allows a narrower band of scores.
        assert strict >= loose

    def test_empty_fit_threshold_one(self) -> None:
        ctrl = ConformalRiskController().fit([], [], target=0.01)
        assert ctrl.threshold == 1.0

    def test_auto_allow_boundary(self) -> None:
        ctrl = ConformalRiskController(threshold=0.5)
        assert ctrl.auto_allow(0.5) is True
        assert ctrl.auto_allow(0.51) is False


class TestExpectedCalibrationError:
    def test_perfectly_calibrated_toy_data_is_zero(self) -> None:
        # In each bin, average confidence equals accuracy -> ECE 0.
        # Bin (0.0, 0.1]: score 0.0 label 0. Bin (0.9,1.0]: score 1.0 label 1.
        scores = [0.0, 0.0, 1.0, 1.0]
        labels = [0, 0, 1, 1]
        assert expected_calibration_error(scores, labels, bins=10) == 0.0

    def test_empty_is_zero(self) -> None:
        assert expected_calibration_error([], []) == 0.0

    def test_overconfident_positive_error(self) -> None:
        # All scores 0.9 but accuracy 0.5 -> ECE around 0.4.
        scores = [0.9, 0.9, 0.9, 0.9]
        labels = [1, 0, 1, 0]
        ece = expected_calibration_error(scores, labels, bins=10)
        assert ece > 0.3
