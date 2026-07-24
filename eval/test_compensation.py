"""Hand-computed numeric regression tests for §8.B compensation metrics."""

from __future__ import annotations

import pytest

from eval.compensation import (
    compensation_coverage,
    compensation_validity,
    half_life_accuracy,
    residue_rate,
    rollback_fidelity_distribution,
)
from unwind.types import CompensationPlan, FidelityGrade, ReversibilityClass, ToolSpec


def _tool(name: str, cls: ReversibilityClass) -> ToolSpec:
    return ToolSpec(server="s", name=name, rev_class=cls)


def test_compensation_coverage_hand_computed() -> None:
    tools = [
        _tool("read_file", ReversibilityClass.R0),  # not mutating -> excluded
        _tool("create_page", ReversibilityClass.R2),  # viable plan
        _tool("update_rec", ReversibilityClass.R1),  # viable via pre_read
        _tool("send_email", ReversibilityClass.R3),  # no viable plan
        _tool("charge", ReversibilityClass.R4),  # None plan
    ]
    plans: list[CompensationPlan | None] = [
        CompensationPlan(forward="read_file"),  # ignored (R0)
        CompensationPlan(forward="create_page", inverse_tool="delete_page"),  # viable
        CompensationPlan(forward="update_rec", pre_read="get_rec"),  # viable
        CompensationPlan(forward="send_email"),  # not viable (no inverse/pre_read)
        None,  # no candidate
    ]
    # Mutating tools = 4 (R2, R1, R3, R4). Viable = 2 (create, update). 2/4 = 0.5
    assert compensation_coverage(tools, plans) == pytest.approx(0.5)


def test_compensation_coverage_no_mutating_returns_zero() -> None:
    tools = [_tool("read", ReversibilityClass.R0)]
    plans: list[CompensationPlan | None] = [None]
    assert compensation_coverage(tools, plans) == 0.0


def test_compensation_validity_hand_computed() -> None:
    # 3 of 4 executed cleanly.
    assert compensation_validity([True, True, False, True]) == pytest.approx(0.75)


def test_rollback_fidelity_distribution_hand_computed() -> None:
    grades = [
        FidelityGrade.EXACT,
        FidelityGrade.EXACT,
        FidelityGrade.SEMANTIC,
        FidelityGrade.ACCEPTABLE_APPROXIMATION,
        FidelityGrade.FAILED,
    ]
    dist = rollback_fidelity_distribution(grades)
    assert dist[FidelityGrade.EXACT] == pytest.approx(2 / 5)
    assert dist[FidelityGrade.SEMANTIC] == pytest.approx(1 / 5)
    assert dist[FidelityGrade.ACCEPTABLE_APPROXIMATION] == pytest.approx(1 / 5)
    assert dist[FidelityGrade.FAILED] == pytest.approx(1 / 5)
    # Every grade present as a key even at 0; distribution sums to 1.
    assert set(dist.keys()) == set(FidelityGrade)
    assert sum(dist.values()) == pytest.approx(1.0)


def test_rollback_fidelity_never_collapses_to_scalar() -> None:
    dist = rollback_fidelity_distribution([FidelityGrade.EXACT])
    assert isinstance(dist, dict)
    assert len(dist) == len(FidelityGrade)


def test_residue_rate_hand_computed() -> None:
    residues = [[], ["notification fired"], [], ["audit entry", "version bump"]]
    # 2 of 4 undos left residue -> 0.5
    assert residue_rate(residues) == pytest.approx(0.5)


def test_half_life_accuracy_hand_computed() -> None:
    predicted = [30.0, 100.0, 5.0]
    actual = [28.0, 90.0, 5.0]
    # abs err: 2, 10, 0 -> MAE = 12/3 = 4.0
    res = half_life_accuracy(predicted, actual, tolerance_s=5.0)
    assert res.mae_seconds == pytest.approx(4.0)
    # within tolerance (<=5): 2<=5 yes, 10<=5 no, 0<=5 yes -> 2/3
    assert res.within_tolerance_rate == pytest.approx(2 / 3)
    assert res.n == 3


def test_empty_inputs_raise() -> None:
    with pytest.raises(ValueError):
        compensation_validity([])
    with pytest.raises(ValueError):
        rollback_fidelity_distribution([])
    with pytest.raises(ValueError):
        residue_rate([])
    with pytest.raises(ValueError):
        half_life_accuracy([], [])
