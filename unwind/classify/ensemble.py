"""Ensemble classifier (``PROJECT.md`` §6, W2/W5).

Combines the lexical rule voter, structural schema signals, and the (optional)
LLM self-consistency voter into a single calibrated :class:`Classification`, then
re-derives it against the :class:`EnvironmentDescriptor`.

Two invariants hold throughout (golden rules #2, #3):

* **Fail safe.** On disagreement or low confidence the *more irreversible* class
  wins — never the more convenient one.
* **Structural signals can only harden**, never soften: a bulk/danger schema
  raises the class; it is not allowed to talk us into "this is reversible".
"""

from __future__ import annotations

from unwind.classify import environment as env_mod
from unwind.classify import schema as schema_mod
from unwind.classify.lexical import classify_lexical
from unwind.classify.llm import LLMClassifier, classify_llm
from unwind.types import (
    Classification,
    EnvironmentDescriptor,
    ReversibilityClass,
    ToolSpec,
)

_DEFAULT_ENV = EnvironmentDescriptor()


def classify_tool(
    spec: ToolSpec,
    env: EnvironmentDescriptor | None = None,
    *,
    llm: LLMClassifier | None = None,
    use_llm: bool = False,
    k: int = 5,
) -> Classification:
    """Produce the final per-tool classification for ``spec`` in ``env``.

    ``use_llm`` gates the (optional) model voter; with it off the ensemble is
    lexical + schema only and fully offline.
    """
    env = env or _DEFAULT_ENV
    lex = classify_lexical(spec)
    sig = schema_mod.schema_signals(spec)

    # Start from the lexical class + confidence.
    rclass = lex.rev_class
    confidence = lex.confidence
    signals: dict[str, object] = {"lexical": lex.signals, "schema": sig}
    rationale = lex.rationale

    # --- structural hardening (never softening) ---
    if sig["danger_flags"]:
        rclass = max(rclass, ReversibilityClass.R4)
        confidence = max(confidence, 0.8)
        rationale += f" | danger flags {sig['danger_flags']} → hardened to R4"
    if sig["bulk"] and rclass >= ReversibilityClass.R2:
        # Bulk mutation is not more reversible; nudge confidence up for escalation.
        confidence = min(1.0, confidence + 0.1)
        rationale += " | bulk selector present"

    # --- optional LLM voter (self-consistency) ---
    if use_llm:
        llm_cls = classify_llm(spec, llm, k=k)
        signals["llm"] = llm_cls.signals
        # Fail-safe fusion: take the MORE irreversible of the two class votes,
        # and average confidence weighted toward agreement.
        fused = max(rclass, llm_cls.rev_class)
        agree = rclass == llm_cls.rev_class
        confidence = (
            (confidence + llm_cls.confidence) / 2
            if agree
            else min(confidence, llm_cls.confidence) * 0.9
        )
        rclass = fused
        rationale += f" | llm {llm_cls.rev_class.name}@{llm_cls.confidence:.2f}"

    fused_cls = Classification(
        rev_class=rclass,
        confidence=round(confidence, 4),
        effect_verb=lex.effect_verb,
        entity=lex.entity,
        externality=lex.externality,
        signals=signals,
        rationale=rationale,
    )

    # --- environment re-derivation (§5.2) ---
    return env_mod.rederive(fused_cls, env)
