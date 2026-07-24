"""Hand-computed numeric regression tests for §8.D system metrics."""

from __future__ import annotations

import pytest

from eval.agent_level import (
    FrontierPoint,
    damage_prevented,
    safety_utility_frontier,
    task_completion_preserved,
)
from eval.system import (
    compatibility_rate,
    end_to_end_undo,
    latency_summary,
)
from unwind.types import ReversibilityClass as RC


def test_latency_summary_split_hand_computed() -> None:
    # R0 latencies: 1.0, 3.0 -> p50 = 2.0 (linear interp of [1,3]).
    # mutating latencies: 10, 20, 30 -> p50 = 20.0.
    added = [1.0, 3.0, 10.0, 20.0, 30.0]
    classes = [RC.R0, RC.R0, RC.R2, RC.R3, RC.R4]
    summ = latency_summary(added, classes)
    assert summ.r0.p50_ms == pytest.approx(2.0)
    assert summ.r0.n == 2
    assert summ.mutating.p50_ms == pytest.approx(20.0)
    assert summ.mutating.n == 3
    assert summ.overall.n == 5


def test_end_to_end_undo_hand_computed() -> None:
    lat = [40.0, 60.0, 50.0, 100.0]
    ok = [True, True, False, True]
    res = end_to_end_undo(lat, ok)
    assert res.success_rate == pytest.approx(0.75)
    # p50 of [40,50,60,100] = mean(50,60)=55.0
    assert res.p50_ms == pytest.approx(55.0)
    assert res.n == 4


def test_compatibility_rate_hand_computed() -> None:
    # 7 of 8 client x server pairs unmodified-compatible.
    pairs = [True] * 7 + [False]
    assert compatibility_rate(pairs) == pytest.approx(7 / 8)


def test_damage_prevented_hand_computed() -> None:
    # baseline damaged 4 scenarios; guarded damaged 1 -> (4-1)/4 = 0.75
    base = [True, True, True, True, False]
    guarded = [False, False, True, False, False]
    assert damage_prevented(base, guarded) == pytest.approx(0.75)


def test_damage_prevented_no_baseline_damage() -> None:
    assert damage_prevented([False, False], [False, False]) == 0.0


def test_task_completion_preserved_hand_computed() -> None:
    # baseline completed 4; still completed with guard = 3 -> 0.75
    base = [True, True, True, True, False]
    guarded = [True, True, False, True, True]
    assert task_completion_preserved(base, guarded) == pytest.approx(0.75)


def test_safety_utility_frontier_drops_dominated() -> None:
    pts = [
        FrontierPoint("block-all", 1.0, 0.0),  # trivially safe, useless
        FrontierPoint("t=0.5", 0.8, 0.9),
        FrontierPoint("t=0.7", 0.6, 0.95),
        FrontierPoint("dominated", 0.5, 0.5),  # dominated by t=0.5 and t=0.7
        FrontierPoint("no-guard", 0.0, 1.0),
    ]
    front = safety_utility_frontier(pts)
    labels = {p.label for p in front}
    assert "dominated" not in labels
    # block-all, t=0.5, t=0.7, no-guard are all Pareto-optimal.
    assert labels == {"block-all", "t=0.5", "t=0.7", "no-guard"}
    # Sorted ascending by damage_prevented.
    dp = [p.damage_prevented for p in front]
    assert dp == sorted(dp)


def test_frontier_exposes_block_all_as_worthless() -> None:
    # The "block everything" corner survives on the frontier but with 0 utility,
    # which is exactly the honest signal §8.E wants.
    front = safety_utility_frontier([FrontierPoint("block-all", 1.0, 0.0)])
    assert front[0].task_completion_preserved == 0.0
