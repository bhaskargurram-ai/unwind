"""Stage 2 — inverse-candidate retrieval (``PROJECT.md`` §6).

Given a mutating tool ``T`` and the full toolset ``S`` of its server, find the
tool that most plausibly *undoes* ``T``, scoring three purely-structural signals:

1. **Verb-antonym match** — create↔delete, add↔remove, enable↔disable,
   grant↔revoke, archive↔restore, attach↔detach, ...
2. **Entity-noun agreement** — ``create_page`` ↔ ``delete_page`` (same noun).
3. **Parameter-schema compatibility** — does the candidate *accept* an identifier
   of the type ``T`` *returns*? This is the strongest, and it is structural
   (independent of prose), exactly as §6 stresses.
"""

from __future__ import annotations

from dataclasses import dataclass

from unwind.classify import schema as schema_mod
from unwind.synthesize.effect_typing import effect_type
from unwind.types import EffectVerb, ToolSpec

# Directed verb antonyms: a forward verb -> the verbs that undo it.
_ANTONYMS: dict[EffectVerb, frozenset[str]] = {
    EffectVerb.CREATE: frozenset({"delete", "remove", "destroy", "drop", "archive", "trash"}),
    EffectVerb.DELETE: frozenset({"create", "add", "restore", "insert", "recreate", "undelete"}),
    EffectVerb.GRANT: frozenset({"revoke", "remove", "deny", "unshare", "unassign"}),
    EffectVerb.REVOKE: frozenset({"grant", "add", "allow", "share", "assign"}),
    EffectVerb.UPDATE: frozenset({"update", "set", "restore", "revert"}),  # self via prestate
    EffectVerb.MOVE: frozenset({"move", "restore"}),
    EffectVerb.SEND: frozenset({"delete", "retract", "recall", "unsend", "revoke"}),
}


@dataclass(frozen=True)
class InverseCandidate:
    tool: ToolSpec
    score: float
    signals: dict[str, object]


def _entity_agreement(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return a == b or a in b or b in a


def score_candidate(target: ToolSpec, candidate: ToolSpec) -> InverseCandidate | None:
    """Score one candidate as an inverse of ``target``; ``None`` if implausible."""
    if candidate.name == target.name:
        # Self-reversible (update/set): only valid when the same tool can write
        # back captured pre-state.
        t_verb, _ = effect_type(target)
        if t_verb in (EffectVerb.UPDATE,):
            return InverseCandidate(candidate, 0.6, {"self_reversible": True})
        return None

    t_verb, t_entity = effect_type(target)
    c_verb, c_entity = effect_type(candidate)

    antonyms = _ANTONYMS.get(t_verb, frozenset())
    verb_match = c_verb.value in antonyms or _candidate_name_has_antonym(candidate, antonyms)
    if not verb_match:
        return None

    signals: dict[str, object] = {"antonym_verb": c_verb.value}
    entity_ok = _entity_agreement(t_entity, c_entity)
    returned = schema_mod.id_return_key(target)
    schema_ok = bool(returned) and schema_mod.accepts_identifier(candidate)

    # An antonym verb ALONE is not enough — that would match `delete_page` as the
    # "inverse" of `send_email`. Require concrete evidence the candidate acts on
    # the SAME entity: either entity-noun agreement or the strong structural
    # signal that the target returns an id the candidate accepts. (Golden rule #3:
    # never invent a compensation we can't justify.)
    if not (entity_ok or schema_ok):
        return None

    score = 0.4  # base for an antonym verb
    if entity_ok:
        score += 0.3
        signals["entity_agreement"] = f"{t_entity}~{c_entity}"
    if schema_ok:
        score += 0.3
        signals["schema_compat"] = f"returns:{returned} accepted-by-candidate"

    return InverseCandidate(candidate, min(score, 1.0), signals)


def _candidate_name_has_antonym(candidate: ToolSpec, antonyms: frozenset[str]) -> bool:
    from unwind.classify.lexical import tokenize

    return bool(set(tokenize(candidate.name)) & antonyms)


def find_inverse(target: ToolSpec, toolset: list[ToolSpec]) -> InverseCandidate | None:
    """Return the highest-scoring inverse candidate for ``target`` in ``toolset``."""
    scored = [c for c in (score_candidate(target, cand) for cand in toolset) if c is not None]
    if not scored:
        return None
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[0]
