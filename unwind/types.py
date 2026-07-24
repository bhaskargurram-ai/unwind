"""Core typed protocol objects for Unwind.

These are defined *first* (per ``CLAUDE.md``) because every other module depends
on them. All types are ``pydantic`` models or ordinal enums; comparisons on
:class:`ReversibilityClass` are meaningful (``R0 < R4``), which the metrics in
``eval/`` rely on (ordinal MAE, critical-error-rate).

References
----------
* R-scale taxonomy: ``PROJECT.md`` §5.1
* Orthogonal dimensions (blast radius, externality, half-life, environment): §5.2
* Compensation synthesis outputs: §6
* Decision space / escalation policy: §2, §8.C
"""

from __future__ import annotations

import time
from enum import IntEnum, StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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
    "now_ts",
]


def now_ts() -> float:
    """Wall-clock seconds since the epoch. Isolated so tests can monkeypatch it."""
    return time.time()


class ReversibilityClass(IntEnum):
    """The ordinal R-scale (``PROJECT.md`` §5.1).

    Ordinal with **asymmetric loss**: misclassifying R4 as R1 is catastrophic,
    the reverse merely annoys. ``IntEnum`` so ``R4 > R2`` etc. are meaningful and
    ordinal-distance metrics work directly.
    """

    R0 = 0  # Nullipotent — no state change, safe to repeat (get/list/search/read)
    R1 = 1  # Self-reversible — same tool restores exact prior state given pre-state
    R2 = 2  # Compensable — a different tool semantically undoes it (approximation)
    R3 = 3  # Mitigable only — no true inverse; third parties may have observed it
    R4 = 4  # Irreversible — no inverse, no meaningful mitigation

    @property
    def label(self) -> str:
        return {
            0: "nullipotent",
            1: "self-reversible",
            2: "compensable",
            3: "mitigable-only",
            4: "irreversible",
        }[int(self)]

    @property
    def is_mutating(self) -> bool:
        """R0 is the only non-mutating class; it must stay ~free on the hot path."""
        return self is not ReversibilityClass.R0

    @property
    def needs_confirmation_by_default(self) -> bool:
        """R3/R4 are never auto-allowed without an explicit budgeted policy."""
        return self >= ReversibilityClass.R3

    @classmethod
    def parse(cls, value: str | int | ReversibilityClass) -> ReversibilityClass:
        if isinstance(value, ReversibilityClass):
            return value
        if isinstance(value, int):
            return cls(value)
        s = value.strip().upper()
        if s.startswith("R") and s[1:].isdigit():
            return cls(int(s[1:]))
        for member in cls:
            if member.label == value.strip().lower():
                return member
        raise ValueError(f"cannot parse ReversibilityClass from {value!r}")


class EffectVerb(StrEnum):
    """Canonical effect verbs (compensation synthesis Stage 1, §6)."""

    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    SEND = "send"
    EXECUTE = "execute"
    GRANT = "grant"
    REVOKE = "revoke"
    MOVE = "move"
    UNKNOWN = "unknown"


class Externality(StrEnum):
    """Does the effect become visible to third parties? Drives the R2/R3 boundary."""

    INTERNAL = "internal"  # effect stays inside the controlled system
    EXTERNAL = "external"  # a third party may already have observed it
    UNKNOWN = "unknown"


class FidelityGrade(IntEnum):
    """Graded rollback fidelity (Garcia-Molina & Salem; §6 Stage 5).

    Never a boolean — a compensation restores "an acceptable approximation", not
    necessarily exact prior state. Ordinal so ``EXACT > FAILED``.
    """

    FAILED = 0
    ACCEPTABLE_APPROXIMATION = 1
    SEMANTIC = 2
    EXACT = 3

    @property
    def label(self) -> str:
        return {
            0: "failed",
            1: "acceptable-approximation",
            2: "semantic",
            3: "exact",
        }[int(self)]


class UndoStatus(StrEnum):
    """Lifecycle of an undo-log entry."""

    ACTIVE = "active"  # forward action logged; undo still possible
    UNDONE = "undone"  # successfully compensated
    EXPIRED = "expired"  # reversibility half-life elapsed
    FAILED = "failed"  # undo was attempted and failed
    SUPERSEDED = "superseded"  # a later action makes this entry moot


class UndoOutcome(StrEnum):
    """Per-action result of ``unwind(n)`` (§2 session-level output)."""

    RESTORED = "restored"
    APPROXIMATELY_RESTORED = "approximately_restored"
    COULD_NOT_UNDO = "could_not_undo"


class Decision(StrEnum):
    """Escalation-policy output (§2, §8.C).

    ``fail_safe`` is *not* auto-allow: on uncertainty we escalate, never
    auto-allow (golden rule #2).
    """

    AUTO_ALLOW = "auto_allow"  # R0 reads — never touch the hot path
    AUTO_ALLOW_LOGGED = "auto_allow_logged"  # reversible; logged with a compensation
    ELICIT_CONFIRMATION = "elicit_confirmation"  # ask the human via native elicitation
    BLOCK = "block"  # refuse outright (policy or panic)


class EnvironmentDescriptor(BaseModel):
    """Declarative capability flags for an environment (§5.2 environment-relativity).

    Reversibility is a function of *(tool, environment)*, never tool alone: the
    same ``write_file`` is R1 on a git-backed tree and R4 on a versionless one.
    Classes are re-derived per environment from these flags.
    """

    model_config = ConfigDict(frozen=True)

    name: str = "default"
    versioned: bool = False  # git-backed / object-versioning present
    has_trash: bool = False  # soft-delete / recycle bin
    soft_delete: bool = False  # tombstoning rather than hard delete
    retention_window_s: float | None = None  # how long deletes are recoverable
    supports_snapshot: bool = True  # can we read pre-state before mutating?
    external_side_effects: bool = False  # actions leak to third parties by nature
    notes: str = ""

    def capability_key(self) -> str:
        """Stable key for caching class re-derivation per environment."""
        return (
            f"v={int(self.versioned)}|t={int(self.has_trash)}|s={int(self.soft_delete)}"
            f"|r={self.retention_window_s}|snap={int(self.supports_snapshot)}"
            f"|ext={int(self.external_side_effects)}"
        )


class ToolSpec(BaseModel):
    """Everything Unwind knows about one upstream tool (classified at ``tools/list``)."""

    server: str
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] | None = None

    # Derived by the classifier / synthesiser (populated lazily, cached).
    effect_verb: EffectVerb = EffectVerb.UNKNOWN
    entity: str | None = None
    rev_class: ReversibilityClass = ReversibilityClass.R4  # fail safe default
    confidence: float = 0.0
    externality: Externality = Externality.UNKNOWN
    blast_radius_hint: int | None = None
    half_life_s: float | None = None  # reversibility window; None = no known decay

    @property
    def qualified_name(self) -> str:
        return f"{self.server}:{self.name}"


class CompensationPlan(BaseModel):
    """A concrete recipe for undoing a mutating call (§6 Stage 4).

    ``inverse_template`` binds arguments from captured pre-state and the forward
    call's response. Fidelity is always graded, never boolean (golden rule #4).
    """

    pre_read: str | None = None  # tool that snapshots the target entity, if any
    forward: str  # the mutating tool this plan compensates
    inverse_tool: str | None = None  # the tool that performs the inverse
    inverse_template: dict[str, Any] = Field(default_factory=dict)
    expiry_s: float | None = None  # reversibility half-life for this plan
    fidelity_grade: FidelityGrade = FidelityGrade.FAILED
    confidence: float = 0.0
    residue: list[str] = Field(default_factory=list)  # side-effects undo cannot remove
    rationale: str = ""

    @property
    def is_viable(self) -> bool:
        """A plan is viable only if it names an inverse or is self-reversible."""
        return self.inverse_tool is not None or self.pre_read is not None


class Classification(BaseModel):
    """The per-call classifier output with a calibrated confidence."""

    rev_class: ReversibilityClass
    confidence: float
    effect_verb: EffectVerb = EffectVerb.UNKNOWN
    entity: str | None = None
    externality: Externality = Externality.UNKNOWN
    signals: dict[str, Any] = Field(default_factory=dict)  # per-classifier votes
    rationale: str = ""

    def degraded(self, reason: str) -> Classification:
        """Degrade one step toward irreversible and escalate (golden rule #3).

        Never over-promise: a low-confidence R2 becomes R3 rather than a broken
        undo guarantee.
        """
        worse = ReversibilityClass(min(int(self.rev_class) + 1, int(ReversibilityClass.R4)))
        return self.model_copy(
            update={
                "rev_class": worse,
                "rationale": f"{self.rationale} | degraded: {reason}".strip(" |"),
            }
        )


class BlastRadius(BaseModel):
    """Predicted count/scope of affected entities (§5.2)."""

    count: int | None = None  # None = unknown/unbounded → treat as high
    unbounded: bool = False
    scope: str = ""  # human-readable, e.g. "all rows matching filter='*'"
    probed: bool = False  # did we run a read-probe, or is this a heuristic?

    @property
    def is_high(self) -> bool:
        return self.unbounded or (self.count is not None and self.count > 1)


class UndoEntry(BaseModel):
    """A durable, cross-server, expiry-aware undo-log record (§9 ``undolog/``)."""

    id: str
    ts: float = Field(default_factory=now_ts)
    server: str
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    prestate: dict[str, Any] | None = None
    plan: CompensationPlan | None = None
    rev_class: ReversibilityClass = ReversibilityClass.R4
    expires_at: float | None = None
    status: UndoStatus = UndoStatus.ACTIVE
    session_id: str | None = None

    def is_expired(self, at: float | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (at if at is not None else now_ts()) >= self.expires_at
