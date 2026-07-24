"""LLM classifier with self-consistency (``PROJECT.md`` §6 Stage 1, W5).

The LLM is *pluggable* and optional: Unwind must run with zero credentials, so
the default :class:`HeuristicLLM` is a deterministic offline stand-in that mimics
the shape of an LLM voter (a class + a confidence from sampled agreement). Real
backends (OpenAI/Anthropic) plug in behind the :class:`LLMClassifier` protocol
and are only used when explicitly configured.

Self-consistency: sample ``k`` judgements; the modal class is the vote and the
agreement fraction is the confidence signal (§6 Stage 6). Disagreement lowers
confidence, which makes the policy escalate rather than auto-allow.
"""

from __future__ import annotations

from collections import Counter
from typing import Protocol, runtime_checkable

from unwind.classify.lexical import classify_lexical
from unwind.types import Classification, ReversibilityClass, ToolSpec

CLASSIFY_SYSTEM_PROMPT = """\
You classify the reversibility of an AI-agent tool on this ordinal scale:
R0 nullipotent (no state change; read/list/search)
R1 self-reversible (the same tool restores exact prior state given a snapshot)
R2 compensable (a different tool semantically undoes it; approximate restore)
R3 mitigable only (no true inverse; a third party may already have observed it)
R4 irreversible (no inverse and no meaningful mitigation)
Answer with only the class token (R0..R4) and a one-line reason. When uncertain,
choose the MORE irreversible class — a false "it's undoable" is worse than a
needless confirmation.
"""


@runtime_checkable
class LLMClassifier(Protocol):
    """Any backend that returns a single R-class judgement for a tool."""

    def judge(self, spec: ToolSpec, *, seed: int) -> ReversibilityClass: ...


class HeuristicLLM:
    """Deterministic offline stand-in (default; no network, no credentials).

    Derives its judgement from the lexical rules but perturbs it slightly by seed
    for the ambiguous middle classes, so self-consistency produces a realistic
    (non-degenerate) confidence signal for R1/R2 while staying stable for R0/R4.
    """

    def judge(self, spec: ToolSpec, *, seed: int) -> ReversibilityClass:
        base = classify_lexical(spec).rev_class
        # Stable at the extremes; jitter the ambiguous middle deterministically.
        if base in (ReversibilityClass.R1, ReversibilityClass.R2):
            # Cheap deterministic hash of (name, seed) → occasional neighbour vote.
            h = (hash((spec.name, seed)) >> 3) % 5
            if h == 0:
                return ReversibilityClass(min(int(base) + 1, int(ReversibilityClass.R4)))
        return base


def classify_llm(
    spec: ToolSpec,
    backend: LLMClassifier | None = None,
    *,
    k: int = 5,
) -> Classification:
    """Self-consistency vote over ``k`` samples from the LLM backend."""
    llm = backend or HeuristicLLM()
    votes = [llm.judge(spec, seed=i) for i in range(max(1, k))]
    counts = Counter(votes)
    modal, n = counts.most_common(1)[0]
    confidence = n / len(votes)
    return Classification(
        rev_class=modal,
        confidence=confidence,
        effect_verb=classify_lexical(spec).effect_verb,
        signals={
            "llm_backend": type(llm).__name__,
            "llm_votes": {c.name: cnt for c, cnt in counts.items()},
            "llm_k": len(votes),
        },
        rationale=f"LLM self-consistency {n}/{len(votes)} → {modal.name}",
    )
