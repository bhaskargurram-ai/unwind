"""Lexical reversibility rules (``PROJECT.md`` §6 Stage 1, classifier v1, W2).

Fast, dependency-free, deterministic verb/noun rules that map a tool's *name*
(and, weakly, its description) to an effect verb and a base :class:`ReversibilityClass`.
This is one voter in the ensemble; on its own it deliberately **fails safe**:
anything it cannot recognise as clearly reversible defaults toward R4.
"""

from __future__ import annotations

import re

from unwind.types import (
    Classification,
    EffectVerb,
    Externality,
    ReversibilityClass,
    ToolSpec,
)

# Verb prefix/keyword -> (effect verb, base reversibility class).
# Order matters: the first matching group wins, most-specific first.
_VERB_RULES: list[tuple[frozenset[str], EffectVerb, ReversibilityClass]] = [
    # R0 — nullipotent reads
    (
        frozenset(
            {
                "get",
                "list",
                "search",
                "read",
                "fetch",
                "find",
                "query",
                "describe",
                "show",
                "view",
                "count",
                "check",
                "lookup",
                "peek",
                "head",
                "stat",
                "preview",
                "inspect",
                "download",
                "export",
                "ls",
                "cat",
                "grep",
            }
        ),
        EffectVerb.READ,
        ReversibilityClass.R0,
    ),
    # R1 — self-reversible mutations (same tool restores, given pre-state)
    (
        frozenset(
            {
                "update",
                "set",
                "edit",
                "modify",
                "write",
                "put",
                "patch",
                "rename",
                "replace",
                "configure",
                "toggle",
                "assign",
                "label",
                "tag",
                "annotate",
            }
        ),
        EffectVerb.UPDATE,
        ReversibilityClass.R1,
    ),
    # R2 — compensable via a sibling inverse (create<->delete, add<->remove...)
    (
        frozenset(
            {
                "create",
                "add",
                "insert",
                "new",
                "make",
                "register",
                "enable",
                "attach",
                "upload",
                "import",
                "copy",
                "duplicate",
                "clone",
                "provision",
                "archive",
                "star",
                "subscribe",
                "follow",
                "mkdir",
                "touch",
            }
        ),
        EffectVerb.CREATE,
        ReversibilityClass.R2,
    ),
    (
        frozenset({"grant", "allow", "authorize", "share", "invite"}),
        EffectVerb.GRANT,
        ReversibilityClass.R2,
    ),
    (
        frozenset(
            {
                "revoke",
                "deny",
                "disable",
                "unshare",
                "unassign",
                "unsubscribe",
                "detach",
                "remove",
                "unregister",
            }
        ),
        EffectVerb.REVOKE,
        ReversibilityClass.R2,
    ),
    (
        frozenset({"move", "transfer", "migrate", "reorder"}),
        EffectVerb.MOVE,
        ReversibilityClass.R2,
    ),
    # R3 — mitigable only; externally observable communications
    (
        frozenset(
            {
                "send",
                "post",
                "publish",
                "email",
                "message",
                "notify",
                "broadcast",
                "comment",
                "reply",
                "tweet",
                "announce",
                "dispatch",
                "emit",
                "mention",
            }
        ),
        EffectVerb.SEND,
        ReversibilityClass.R3,
    ),
    # R4 — irreversible / destructive (checked before generic delete so 'purge' etc. win)
    (
        frozenset(
            {
                "delete",
                "drop",
                "destroy",
                "purge",
                "wipe",
                "erase",
                "truncate",
                "terminate",
                "kill",
                "revert",
                "reset",
                "format",
                "shred",
                "obliterate",
            }
        ),
        EffectVerb.DELETE,
        ReversibilityClass.R4,  # default destructive to R4; env/inverse can promote it
    ),
    (
        frozenset(
            {
                "pay",
                "charge",
                "capture",
                "settle",
                "transfer_funds",
                "withdraw",
                "purchase",
                "checkout",
                "refund",
                "payout",
                "wire",
                "bill",
                "invoice",
            }
        ),
        EffectVerb.EXECUTE,
        ReversibilityClass.R4,
    ),
    (
        frozenset(
            {
                "execute",
                "run",
                "exec",
                "invoke",
                "trigger",
                "deploy",
                "apply",
                "launch",
                "start",
                "stop",
                "restart",
                "rollout",
                "call",
            }
        ),
        EffectVerb.EXECUTE,
        ReversibilityClass.R4,
    ),
]

_EXTERNAL_HINTS = frozenset(
    {
        "email",
        "send",
        "post",
        "publish",
        "tweet",
        "sms",
        "slack",
        "notify",
        "webhook",
        "broadcast",
        "message",
        "announce",
        "comment",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(name: str) -> list[str]:
    """Split a tool name into lowercase word tokens (snake/camel/kebab aware)."""
    # camelCase -> camel Case
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    return _TOKEN_RE.findall(spaced.lower())


def _match_verb(tokens: list[str]) -> tuple[EffectVerb, ReversibilityClass] | None:
    token_set = set(tokens)
    # Mutation verbs win over R0 read verbs when both appear: `write_query`,
    # `update_and_get`, `create_or_replace` are mutations, not reads. So we test
    # the non-R0 (mutating) rules first and only fall back to R0 (nullipotent)
    # when no mutation verb is present. This is also the fail-safe order (golden
    # rule #2: don't assume an action is nullipotent).
    for keywords, verb, rclass in _VERB_RULES:
        if rclass == ReversibilityClass.R0:
            continue
        if token_set & keywords:
            return verb, rclass
    for keywords, verb, rclass in _VERB_RULES:
        if rclass == ReversibilityClass.R0 and token_set & keywords:
            return verb, rclass
    return None


def guess_entity(tokens: list[str], verb: EffectVerb) -> str | None:
    """The noun the verb acts on — used for inverse-candidate entity agreement."""
    verb_words = {v.value for v in EffectVerb}
    nouns = [t for t in tokens if t not in verb_words and len(t) > 1]
    # Common convention: entity is the last noun token (delete_user -> user).
    return nouns[-1] if nouns else None


def classify_lexical(spec: ToolSpec) -> Classification:
    """Classify a tool from its name/description using lexical rules alone.

    Fail-safe: unrecognised → R4 with low confidence, so the ensemble/policy
    escalates rather than auto-allowing (golden rule #2).
    """
    tokens = tokenize(spec.name)
    match = _match_verb(tokens)

    if match is None:
        # Unknown verb: also scan the description for a strong destructive hint.
        desc_tokens = tokenize(spec.description)
        match = _match_verb(desc_tokens)
        tokens = tokens or desc_tokens

    if match is None:
        return Classification(
            rev_class=ReversibilityClass.R4,
            confidence=0.15,
            effect_verb=EffectVerb.UNKNOWN,
            entity=guess_entity(tokens, EffectVerb.UNKNOWN),
            externality=Externality.UNKNOWN,
            signals={"lexical": "no-verb-match"},
            rationale="no recognised effect verb; failing safe to R4",
        )

    verb, rclass = match
    entity = guess_entity(tokens, verb)
    external = bool(set(tokens) & _EXTERNAL_HINTS)

    # Confidence: reads are unambiguous; destructive verbs are clear; the middle
    # (create/update) is genuinely ambiguous without structural evidence.
    confidence = {
        ReversibilityClass.R0: 0.9,
        ReversibilityClass.R1: 0.5,
        ReversibilityClass.R2: 0.55,
        ReversibilityClass.R3: 0.7,
        ReversibilityClass.R4: 0.75,
    }[rclass]

    return Classification(
        rev_class=rclass,
        confidence=confidence,
        effect_verb=verb,
        entity=entity,
        externality=Externality.EXTERNAL if external else Externality.INTERNAL,
        signals={"lexical": verb.value, "tokens": tokens},
        rationale=f"lexical verb '{verb.value}' → {rclass.name}",
    )
