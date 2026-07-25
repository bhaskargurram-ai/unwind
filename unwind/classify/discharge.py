"""Discharge engine for WITNESS — confirm/refute typed witnesses operationally.

A witness is admitted only if a **deterministic** procedure confirms it (invariant
I5), never by the proposer's assertion. Two discharge modes:

* :func:`discharge_schema_graph` — a deterministic checker over the ToolSpec +
  toolset (no model, no execution). Available for *every* tool, including the
  ~31k-tool ecosystem with no sandbox analog. This is the coverage backstop.
* :func:`make_executable_discharge` — builds a discharge fn that actually runs
  ``forward + synthesized-inverse`` against a real backend (and a capability-
  paired counterfactual), reads an observation channel, and advances the
  reversibility-half-life clock. Used where a sandbox analog exists; this is the
  non-circular ground truth for the environment-relativity result.

:class:`DeterministicProposer` is an offline proposer that enumerates the typed
witnesses worth checking, so WITNESS runs with zero credentials; the LLM proposer
(experiments) names concrete channels/fields but is discharged by the same
functions.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from unwind.classify.lexical import classify_lexical, tokenize
from unwind.classify.schema import accepts_identifier, id_return_key
from unwind.classify.witness import (
    DischargeFn,
    Verdict,
    Witness,
    WitnessProposer,
    WitnessType,
)
from unwind.synthesize.prestate import find_prestate_reader
from unwind.types import (
    CompensationPlan,
    EffectVerb,
    EnvironmentDescriptor,
    ReversibilityClass,
    ToolSpec,
)

# Lexical anchors for the schema-graph checks.
_EXTERNAL_VERB_WORDS = frozenset(
    {
        "send",
        "post",
        "publish",
        "email",
        "message",
        "notify",
        "broadcast",
        "tweet",
        "announce",
        "dispatch",
        "comment",
        "reply",
        "share",
        "invite",
        "sms",
    }
)
# STRONG, unambiguous time-window terms only. Weak words like "within", "pending",
# "grace", "timeout", "window" are common English (e.g. "within the allowed
# directories") and cause false HALF_LIFE positives on ordinary writes, so they
# are excluded. Matched as WHOLE WORDS, never substrings.
_HALF_LIFE_WORDS = frozenset(
    {
        "expire",
        "expires",
        "expiry",
        "settle",
        "settled",
        "settlement",
        "recall",
        "unsend",
        "retract",
        "voidable",
        "chargeback",
    }
)
_OBSERVATION_WORDS = frozenset(
    {
        "outbox",
        "sent",
        "activity",
        "audit",
        "feed",
        "receipt",
        "notification",
        "notifications",
        "delivery",
        "log",
        "event",
        "history",
        "inbox",
        "timeline",
    }
)


# --------------------------------------------------------------------------
# Deterministic schema-graph discharge (always available)
# --------------------------------------------------------------------------
def _entity(spec: ToolSpec) -> str | None:
    return classify_lexical(spec).entity


def _has_observation_channel(toolset: list[ToolSpec], entity: str | None) -> ToolSpec | None:
    """A co-located R0 read tool that a third party would read from (not the target)."""
    for cand in toolset:
        cls = classify_lexical(cand)
        if cls.rev_class != ReversibilityClass.R0:
            continue
        toks = set(tokenize(cand.name))
        if toks & _OBSERVATION_WORDS:
            return cand
    return None


def discharge_schema_graph(
    w: Witness,
    spec: ToolSpec,
    plan: CompensationPlan,
    toolset: list[ToolSpec],
    env: EnvironmentDescriptor,
) -> tuple[Verdict, float]:
    """Confirm/refute a witness from schema + toolset facts alone (deterministic)."""
    cls = classify_lexical(spec)
    verb = cls.effect_verb
    name_toks = set(tokenize(spec.name))

    if w.type == WitnessType.EXTERNALITY:
        # Confirmed if the tool's own effect is external, the environment leaks,
        # or a third-party observation channel exists in the server.
        if (
            verb == EffectVerb.SEND
            or (name_toks & _EXTERNAL_VERB_WORDS)
            or env.external_side_effects
        ):
            return Verdict.CONFIRMED, 0.9
        if _has_observation_channel(toolset, _entity(spec)) is not None:
            return Verdict.CONFIRMED, 0.8
        return Verdict.REFUTED, 0.0

    if w.type == WitnessType.HALF_LIFE:
        # A half-life implies a time-bounded, typically external/transactional
        # action — confirmed by an explicit retention window on the environment,
        # or a STRONG whole-word window term in the tool text. A plain local
        # mutation (file write) has no half-life regardless of prose.
        text_tokens = set(tokenize(f"{spec.name} {spec.description}"))
        if env.retention_window_s is not None or (text_tokens & _HALF_LIFE_WORDS):
            return Verdict.CONFIRMED, 0.85
        return Verdict.REFUTED, 0.0

    if w.type == WitnessType.LOST_INVERSE_PARAM:
        # The plan claims an inverse but the forward tool does not return the id
        # the inverse must bind → the compensation cannot actually run.
        if plan is None or plan.inverse_tool is None:
            return Verdict.REFUTED, 0.0  # no inverse claimed; nothing to lose
        inverse_spec = _find(toolset, plan.inverse_tool)
        needs_id = accepts_identifier(inverse_spec) if inverse_spec is not None else True
        returns_id = id_return_key(spec) is not None
        if needs_id and not returns_id and verb in (EffectVerb.CREATE,):
            return Verdict.CONFIRMED, 0.8
        return Verdict.REFUTED, 0.0

    if w.type == WitnessType.MISSING_SNAPSHOT_CASCADE:
        reader = find_prestate_reader(spec, toolset)
        mutating = verb in (
            EffectVerb.DELETE,
            EffectVerb.UPDATE,
            EffectVerb.CREATE,
            EffectVerb.MOVE,
            EffectVerb.EXECUTE,
        )
        has_env_recovery = env.versioned or env.has_trash or env.soft_delete
        no_inverse = plan is None or plan.inverse_tool is None
        # A mutation with NO available inverse tool AND no environmental recovery
        # cannot be reversed — whether it is a delete whose pre-state cannot be
        # captured or a create with no sibling delete in the server. This is the
        # panel's "missing-inverse" case; without it a create_table with no
        # drop_table stays optimistically R2. (Golden rule #3: no inverse → no
        # undo promise.)
        if mutating and no_inverse and not has_env_recovery:
            return Verdict.CONFIRMED, 0.9
        # A destructive overwrite/delete whose prior state cannot be snapshotted.
        if (
            verb in (EffectVerb.DELETE, EffectVerb.UPDATE)
            and reader is None
            and not env.supports_snapshot
            and not has_env_recovery
        ):
            return Verdict.CONFIRMED, 0.85
        return Verdict.REFUTED, 0.0

    return Verdict.UNTESTABLE, 0.0


def _find(toolset: list[ToolSpec], name: str) -> ToolSpec | None:
    return next((t for t in toolset if t.name == name), None)


# --------------------------------------------------------------------------
# Executable discharge (where a sandbox analog exists) — the non-circular ground
# truth for environment-relativity, externality, and half-life.
# --------------------------------------------------------------------------
# An executor runs a tool against a concrete backend and returns observable state.
Executor = Callable[[str, dict[str, Any]], dict[str, Any]]
Snapshot = Callable[[], dict[str, Any]]


def make_executable_discharge(
    *,
    real: tuple[Executor, Snapshot],
    paired: tuple[Executor, Snapshot] | None = None,
    forward_args: dict[str, Any] | None = None,
    inverse_args: dict[str, Any] | None = None,
    observe: Snapshot | None = None,
    advance_clock: Callable[[], None] | None = None,
    schema_fallback: bool = True,
) -> DischargeFn:
    """Build a discharge fn that confirms witnesses by *executing* probes.

    * MISSING_SNAPSHOT_CASCADE / differential env-relativity: run forward+inverse
      on ``real`` and (if given) ``paired``; CONFIRMED when core state is not
      restored on the environment the call actually runs in.
    * EXTERNALITY: snapshot ``observe`` before/after; CONFIRMED when a T-induced
      footprint survives the inverse.
    * HALF_LIFE: ``advance_clock`` past the window and re-run the inverse;
      CONFIRMED when it no longer round-trips.

    Falls back to :func:`discharge_schema_graph` for witness types with no probe.
    """
    from unwind.synthesize.validate import state_diff

    real_exec, real_snap = real
    fargs = forward_args or {}
    iargs = inverse_args or {}

    def _discharge(w, spec, plan, toolset, env):  # type: ignore[no-untyped-def]
        if plan is None or plan.inverse_tool is None:
            return Verdict.CONFIRMED, 1.0  # no inverse to run → irreversible

        if w.type == WitnessType.MISSING_SNAPSHOT_CASCADE:
            s0 = real_snap()
            real_exec(plan.forward, fargs)
            real_exec(plan.inverse_tool, iargs)
            s2 = real_snap()
            resid = len(state_diff(s0, s2))
            if paired is not None:
                p_exec, p_snap = paired
                p0 = p_snap()
                p_exec(plan.forward, fargs)
                p_exec(plan.inverse_tool, iargs)
                p2 = p_snap()
                presid = len(state_diff(p0, p2))
                # Differential: irreversible here but reversible on the paired env.
                if resid > 0 and presid == 0:
                    return Verdict.CONFIRMED, 1.0
                if resid == 0:
                    return Verdict.REFUTED, 0.0
            return (Verdict.CONFIRMED, 1.0) if resid > 0 else (Verdict.REFUTED, 0.0)

        if w.type == WitnessType.EXTERNALITY and observe is not None:
            o0 = observe()
            real_exec(plan.forward, fargs)
            real_exec(plan.inverse_tool, iargs)
            o2 = observe()
            footprint = state_diff(o0, o2)
            return (Verdict.CONFIRMED, 0.95) if footprint else (Verdict.REFUTED, 0.0)

        if w.type == WitnessType.HALF_LIFE and advance_clock is not None:
            real_exec(plan.forward, fargs)
            advance_clock()
            res = real_exec(plan.inverse_tool, iargs)
            failed = (
                bool(res.get("isError"))
                or bool(res.get("expired"))
                or "elapsed" in str(res).lower()
            )
            return (Verdict.CONFIRMED, 1.0) if failed else (Verdict.REFUTED, 0.0)

        if schema_fallback:
            return discharge_schema_graph(w, spec, plan, toolset, env)
        return Verdict.UNTESTABLE, 0.0

    return _discharge


# --------------------------------------------------------------------------
# Deterministic proposer — enumerates the typed witnesses worth discharging.
# --------------------------------------------------------------------------
class DeterministicProposer(WitnessProposer):
    """Offline proposer: names every plausibly-relevant witness for discharge.

    It is deliberately *generous* (proposes candidates) because the discharge
    functions — not the proposer — decide truth (invariant I5). This makes WITNESS
    runnable with no model, as a strong offline baseline arm.
    """

    def propose(self, spec, toolset, env, plan):  # type: ignore[no-untyped-def]
        cls = classify_lexical(spec)
        out: list[Witness] = []
        entity = cls.entity or ""
        # Only propose for mutating tools worth probing.
        if cls.rev_class == ReversibilityClass.R0:
            return out
        out.append(Witness(WitnessType.EXTERNALITY, entity, "effect may be externally observable"))
        out.append(Witness(WitnessType.HALF_LIFE, entity, "inverse may be time-bounded"))
        if cls.effect_verb == EffectVerb.CREATE:
            out.append(
                Witness(
                    WitnessType.LOST_INVERSE_PARAM, entity, "inverse may need a server-assigned id"
                )
            )
        out.append(
            Witness(WitnessType.MISSING_SNAPSHOT_CASCADE, entity, "pre-state may be uncapturable")
        )
        return out
