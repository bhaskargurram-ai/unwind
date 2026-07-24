"""Escalation-policy configuration (``PROJECT.md`` §2, §8.C).

The policy trades **interruptions per session** against **irreversible-damage
rate**. It is tuned to a target damage rate (e.g. ≤1% of truly-R4 actions
executed without confirmation) — a selective-prediction problem with asymmetric
loss.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from unwind.types import ReversibilityClass


class PolicyConfig(BaseModel):
    """Thresholds governing the auto-allow / elicit / block decision."""

    # The class at/above which we always confirm regardless of confidence.
    always_confirm_at: ReversibilityClass = ReversibilityClass.R3

    # Minimum classifier confidence to trust a *reversible* verdict. Below this we
    # escalate rather than auto-allow (fail safe).
    min_confidence_auto_allow: float = 0.6

    # Confirm reversible (R1/R2) actions when blast radius exceeds this, even
    # though they are individually undoable (a 10k-row update is worth a pause).
    blast_radius_confirm_threshold: int = 50

    # Target irreversible-damage rate the calibrated threshold solver aims for.
    target_damage_rate: float = 0.01

    # Hard blocklist / panic behaviour.
    passthrough_only: bool = False  # panic switch: never intervene, pure proxy
    block_unbounded_irreversible: bool = True  # block R4 with unbounded blast radius

    # Whether the client advertised elicitation support (observed at initialize).
    client_supports_elicitation: bool = True

    model_config = {"frozen": False}

    fixed_confirm_classes: set[ReversibilityClass] = Field(default_factory=set)
