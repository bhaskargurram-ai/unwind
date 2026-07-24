"""Unwind — a reversibility layer for agentic tool use.

Unwind sits between any MCP client and any MCP server, works out which actions
can be taken back, quietly takes back the ones that go wrong, and interrupts you
only for the ones that truly can't be undone.

See ``PROJECT.md`` for the full specification and ``CLAUDE.md`` for the golden
rules that govern every design decision in this package.
"""

from __future__ import annotations

__version__ = "0.1.0"

from unwind.types import (
    BlastRadius,
    Classification,
    CompensationPlan,
    Decision,
    EffectVerb,
    EnvironmentDescriptor,
    Externality,
    FidelityGrade,
    ReversibilityClass,
    ToolSpec,
    UndoEntry,
    UndoOutcome,
    UndoStatus,
)

__all__ = [
    "BlastRadius",
    "Classification",
    "CompensationPlan",
    "Decision",
    "EffectVerb",
    "EnvironmentDescriptor",
    "Externality",
    "FidelityGrade",
    "ReversibilityClass",
    "ToolSpec",
    "UndoEntry",
    "UndoOutcome",
    "UndoStatus",
    "__version__",
]
