"""Micro-benchmarks for the hot path (``PROJECT.md`` §8.D).

The project's success contract requires that **R0 (read) calls stay ~free** — the
proxy must not add latency to reads. These pytest-benchmark cases track the
classification cost so a regression shows up in CI (``benchmark.yml``).

Run just these with:  pytest -m benchmark --benchmark-only
(They are also plain tests, so they run in the normal suite as correctness checks.)
"""

from __future__ import annotations

import pytest

from unwind.classify.ensemble import classify_tool
from unwind.types import ReversibilityClass, ToolSpec

pytestmark = pytest.mark.benchmark

_R0 = ToolSpec(
    server="s", name="get_record", input_schema={"properties": {"id": {"type": "string"}}}
)
_R4 = ToolSpec(
    server="s", name="delete_record", input_schema={"properties": {"id": {"type": "string"}}}
)


def test_classify_r0_latency(benchmark: pytest.FixtureRequest) -> None:
    result = benchmark(classify_tool, _R0)
    assert result.rev_class == ReversibilityClass.R0


def test_classify_r4_latency(benchmark: pytest.FixtureRequest) -> None:
    result = benchmark(classify_tool, _R4)
    assert result.rev_class >= ReversibilityClass.R3
