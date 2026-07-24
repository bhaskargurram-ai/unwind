"""Typed schema for destructive end-to-end scenario traces (``PROJECT.md`` §8.E).

A scenario is an ordered list of tool-call steps an agent would emit, each tagged
with the *expected* reversibility class and the correct escalation decision, so a
run can score both agent-level damage/utility (§8.E) and per-step policy behaviour
(§8.C) against ground truth. Reuses the shared enums from :mod:`unwind.types`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from unwind.types import Decision, EnvironmentDescriptor, ReversibilityClass

__all__ = ["Scenario", "ScenarioStep"]


class ScenarioStep(BaseModel):
    """One tool call in a scenario trace, with ground-truth expectations."""

    model_config = ConfigDict(frozen=True)

    server: str
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    expected_rev_class: ReversibilityClass
    expected_decision: Decision
    is_destructive: bool = Field(
        default=False,
        description="does this step cause irreversible damage if wrongly auto-allowed?",
    )
    note: str = ""


class Scenario(BaseModel):
    """A named destructive scenario trace (§8.E).

    ``environment`` sets the capability context the classes are relative to
    (§5.2). ``expect_undoable_count`` records how many steps a correct system
    should be able to reverse via ``unwind.undo`` — the honest 20-second-demo
    contract (§13): most restore, and the truly-irreversible ones are the ones the
    system should have interrupted on.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    description: str = ""
    source: str = Field(
        default="", description="provenance, e.g. 'demo', 'ClawsBench-style', 'AgentDojo-style'"
    )
    environment: EnvironmentDescriptor = Field(default_factory=EnvironmentDescriptor)
    steps: list[ScenarioStep]
    expect_undoable_count: int | None = None

    @property
    def destructive_steps(self) -> list[ScenarioStep]:
        return [s for s in self.steps if s.is_destructive]
