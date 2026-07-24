"""Environment-relative re-derivation of reversibility (``PROJECT.md`` §5.2, W2).

Following *Beyond Attack-Success Rate* (arXiv:2607.07474): reversibility is
environment-determined. The same ``delete_file`` is R4 on a versionless drive and
R1/R2 on a git-backed or trash-enabled one. Classification is a function of
*(tool, environment)*, never tool alone — so we re-derive the base class against
an :class:`EnvironmentDescriptor`.

This can only ever *soften* a class when the environment provides a recovery
mechanism, and *harden* it when the environment removes one. It never invents a
recovery path that the environment cannot back (golden rule #3).
"""

from __future__ import annotations

from unwind.types import (
    Classification,
    EffectVerb,
    EnvironmentDescriptor,
    Externality,
    ReversibilityClass,
)


def rederive(classification: Classification, env: EnvironmentDescriptor) -> Classification:
    """Adjust a base classification for a concrete environment.

    Returns a new :class:`Classification`; the original is untouched.
    """
    base = classification.rev_class
    verb = classification.effect_verb
    new = base
    notes: list[str] = []

    is_destructive = verb in (EffectVerb.DELETE,) or base >= ReversibilityClass.R3

    if is_destructive:
        # A versioned / trash-backed / soft-delete environment makes a delete
        # recoverable: promote toward compensable/self-reversible.
        if env.versioned:
            new = min(new, ReversibilityClass.R1)
            notes.append("versioned env → delete recoverable from history (R1)")
        elif env.soft_delete:
            new = min(new, ReversibilityClass.R2)
            notes.append("soft-delete env → tombstone restorable (R2)")
        elif env.has_trash:
            new = min(new, ReversibilityClass.R2)
            notes.append("trash/retention env → restore-from-trash (R2)")
        else:
            # No recovery mechanism at all: a delete is genuinely irreversible.
            if verb == EffectVerb.DELETE:
                new = max(new, ReversibilityClass.R4)
                notes.append("versionless, no trash → delete is R4")

    # If we cannot snapshot pre-state, R1 (self-reversible-from-prestate) is
    # unreachable; degrade to at best R2 (needs a sibling inverse).
    if not env.supports_snapshot and new == ReversibilityClass.R1:
        new = ReversibilityClass.R2
        notes.append("no snapshot capability → R1 unreachable, degraded to R2")

    # Environments whose actions inherently leak to third parties push R2→R3.
    if env.external_side_effects and new == ReversibilityClass.R2:
        new = ReversibilityClass.R3
        notes.append("external side effects → R2 degraded to R3")
        classification = classification.model_copy(update={"externality": Externality.EXTERNAL})

    if new == base and not notes:
        return classification

    rationale = classification.rationale
    if notes:
        rationale = f"{rationale} | env[{env.name}]: {'; '.join(notes)}".strip(" |")

    signals = dict(classification.signals)
    signals["environment"] = env.capability_key()

    return classification.model_copy(
        update={"rev_class": new, "rationale": rationale, "signals": signals}
    )
