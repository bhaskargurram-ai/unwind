"""The label record model for ReversiBench (``PROJECT.md`` §5, §8 "Labelling").

Each row is one *(tool, environment)* judgement by one annotator. Reversibility is
a function of (tool, environment) (§5.2), so the environment descriptor is part of
the primary key — the same tool re-labelled under a different environment is a
distinct record. Reuses the shared enums from :mod:`unwind.types` (never
redefined).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from unwind.types import EffectVerb, EnvironmentDescriptor, Externality, ReversibilityClass

__all__ = ["AdjudicatedLabel", "LabelRecord"]


class LabelRecord(BaseModel):
    """One annotator's judgement of one tool under one environment (§8 Labelling).

    The annotator assigns the R-class and the orthogonal dimensions (§5.2): blast
    radius, externality, and reversibility half-life. ``environment`` is mandatory
    because class assignment is environment-relative.
    """

    model_config = ConfigDict(frozen=True)

    # Identity of the labelled unit.
    server: str = Field(description="source MCP server id (e.g. 'filesystem')")
    tool: str = Field(description="tool name as listed by tools/list")
    environment: EnvironmentDescriptor = Field(
        default_factory=EnvironmentDescriptor,
        description="capability flags the class is relative to (§5.2)",
    )

    # The judgement.
    annotator_id: str = Field(description="stable pseudonymous annotator id")
    rev_class: ReversibilityClass = Field(description="assigned R-class R0..R4")
    effect_verb: EffectVerb = EffectVerb.UNKNOWN
    entity: str | None = Field(default=None, description="target entity noun, if any")
    externality: Externality = Externality.UNKNOWN
    blast_radius: int | None = Field(
        default=None, description="cardinality of affected entities; None = unbounded"
    )
    blast_radius_unbounded: bool = False
    half_life_s: float | None = Field(
        default=None, description="reversibility window in seconds; None = no known decay"
    )
    rationale: str = ""

    @property
    def unit_key(self) -> str:
        """Primary key for a labelled unit: (server, tool, environment)."""
        return f"{self.server}:{self.tool}@{self.environment.capability_key()}"


class AdjudicatedLabel(BaseModel):
    """The gold label after adjudicating annotator disagreements (§8 Labelling).

    Records the final class and whether adjudication was needed, so the
    disagreement rate can be reported (§8 "Adjudicate disagreements and report the
    rate").
    """

    model_config = ConfigDict(frozen=True)

    server: str
    tool: str
    environment: EnvironmentDescriptor = Field(default_factory=EnvironmentDescriptor)
    gold_rev_class: ReversibilityClass
    gold_externality: Externality = Externality.UNKNOWN
    gold_half_life_s: float | None = None
    n_annotators: int = 0
    was_disagreement: bool = False
    adjudicator_note: str = ""

    @property
    def unit_key(self) -> str:
        return f"{self.server}:{self.tool}@{self.environment.capability_key()}"
