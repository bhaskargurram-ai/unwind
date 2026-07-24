"""Stage 3 — pre-state capture planning (``PROJECT.md`` §6).

Identify the read tool that snapshots the target entity *before* a mutation, so
an R1 self-reversal (write back the captured prior state) is possible. Without a
viable snapshot, R1 is unreachable and the class degrades (handled in the plan).
"""

from __future__ import annotations

from unwind.classify.lexical import classify_lexical, tokenize
from unwind.synthesize.effect_typing import effect_type
from unwind.types import EffectVerb, ReversibilityClass, ToolSpec


def find_prestate_reader(target: ToolSpec, toolset: list[ToolSpec]) -> ToolSpec | None:
    """Find a ``get_<entity>`` / ``read_<entity>`` tool matching the target entity."""
    _, entity = effect_type(target)
    best: tuple[int, ToolSpec] | None = None
    for cand in toolset:
        cls = classify_lexical(cand)
        if cls.rev_class != ReversibilityClass.R0 or cls.effect_verb != EffectVerb.READ:
            continue
        cand_tokens = set(tokenize(cand.name))
        score = 0
        if entity and entity in cand_tokens:
            score += 2
        # Prefer a single-entity reader (get) over a list reader.
        if "get" in cand_tokens or "read" in cand_tokens or "describe" in cand_tokens:
            score += 1
        if "list" in cand_tokens or "search" in cand_tokens:
            score -= 1
        if score <= 0:
            continue
        if best is None or score > best[0]:
            best = (score, cand)
    return best[1] if best else None
