"""Loader for ReversiBench scenario traces (``PROJECT.md`` §8.E).

Reads the committed ``*.json`` scenario files in this directory into typed
:class:`~bench.scenarios.schema.Scenario` objects.
"""

from __future__ import annotations

from pathlib import Path

from .schema import Scenario

__all__ = ["SCENARIO_DIR", "load_all_scenarios", "load_scenario"]

SCENARIO_DIR = Path(__file__).resolve().parent


def load_scenario(path: Path) -> Scenario:
    """Load and validate one scenario JSON file."""
    return Scenario.model_validate_json(path.read_text(encoding="utf-8"))


def load_all_scenarios(directory: Path | None = None) -> list[Scenario]:
    """Load every ``*.json`` scenario in ``directory`` (default: this package).

    Sorted by scenario ``id`` for deterministic ordering in ``make results``.
    """
    directory = directory or SCENARIO_DIR
    scenarios = [load_scenario(p) for p in sorted(directory.glob("*.json"))]
    scenarios.sort(key=lambda s: s.id)
    return scenarios
