"""Stage 1 — effect typing (``PROJECT.md`` §6).

Classify a mutating tool's effect verb and target entity noun. Thin, so the
synthesiser and classifier agree on one source of truth for verb/entity.
"""

from __future__ import annotations

from unwind.classify.lexical import classify_lexical, guess_entity, tokenize
from unwind.types import EffectVerb, ToolSpec


def effect_type(spec: ToolSpec) -> tuple[EffectVerb, str | None]:
    """Return the ``(effect_verb, entity)`` for a tool."""
    cls = classify_lexical(spec)
    entity = cls.entity or guess_entity(tokenize(spec.name), cls.effect_verb)
    return cls.effect_verb, entity
