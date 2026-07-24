"""The reversibility engine — Unwind's beating heart (``PROJECT.md`` §2, §6, §7).

Ties the pieces together for one upstream server:

* at ``tools/list`` time → classify every tool + synthesise a compensation plan,
  and cache both (so R0 reads never pay a hot-path cost, golden rule #7);
* at ``tools/call`` time → classify the specific call, estimate blast radius,
  decide (auto-allow / logged / elicit / block), capture pre-state, forward, and
  append a durable undo-log entry;
* on ``undo(n)`` → replay compensations in reverse order (stack unwinding) and
  report each outcome honestly as restored / approximately_restored /
  could_not_undo (§2 session-level output).

The engine is transport-agnostic: it drives any :class:`~unwind.upstream.Upstream`.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from unwind.blast import estimate_blast_radius
from unwind.classify.ensemble import classify_tool
from unwind.classify.llm import LLMClassifier
from unwind.policy.config import PolicyConfig
from unwind.policy.engine import DecisionResult, decide
from unwind.synthesize.plan import effective_class, synthesize_plan
from unwind.types import (
    BlastRadius,
    Classification,
    CompensationPlan,
    Decision,
    EnvironmentDescriptor,
    ReversibilityClass,
    ToolSpec,
    UndoEntry,
    UndoOutcome,
    UndoStatus,
    now_ts,
)
from unwind.undolog.store import UndoLog
from unwind.upstream import Upstream

# A confirmation callback: given a message, return True to proceed. In the proxy
# this is wired to native MCP elicitation; in the CLI/demo it can be a prompt.
ConfirmFn = Callable[[str], Awaitable[bool]]


@dataclass
class CallEvaluation:
    tool: str
    classification: Classification
    blast: BlastRadius
    plan: CompensationPlan | None
    decision: DecisionResult
    effective_class: ReversibilityClass


@dataclass
class CallResult:
    evaluation: CallEvaluation
    executed: bool
    result: dict[str, Any] | None
    undo_id: str | None
    message: str


@dataclass
class UndoResult:
    entry_id: str
    tool: str
    outcome: UndoOutcome
    reason: str
    residue: list[str]


def _extract_id(result: dict[str, Any] | None) -> Any:
    if not result:
        return None
    structured = result.get("structured")
    if isinstance(structured, dict):
        for key in ("id", "uuid", "key", "name", "path", "record_id", "page_id"):
            if key in structured:
                return structured[key]
    return None


class ReversibilityEngine:
    """Stateful engine bound to one upstream server + one durable undo log."""

    def __init__(
        self,
        upstream: Upstream,
        undolog: UndoLog,
        *,
        env: EnvironmentDescriptor | None = None,
        policy: PolicyConfig | None = None,
        llm: LLMClassifier | None = None,
        use_llm: bool = False,
        session_id: str | None = None,
    ) -> None:
        self.upstream = upstream
        self.log = undolog
        self.env = env or EnvironmentDescriptor()
        self.policy = policy or PolicyConfig()
        self.llm = llm
        self.use_llm = use_llm
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.catalog: dict[str, ToolSpec] = {}
        self.plans: dict[str, CompensationPlan] = {}

    # -- catalog (tools/list time) ---------------------------------------
    async def build_catalog(self) -> list[ToolSpec]:
        """Classify + synthesise plans for every upstream tool; cache the result."""
        specs = await self.upstream.list_tools()
        for spec in specs:
            cls = classify_tool(spec, self.env, llm=self.llm, use_llm=self.use_llm)
            spec.rev_class = cls.rev_class
            spec.confidence = cls.confidence
            spec.effect_verb = cls.effect_verb
            spec.entity = cls.entity
            spec.externality = cls.externality
            self.catalog[spec.name] = spec
        # Second pass: synthesise plans now that the full toolset is known.
        toolset = list(self.catalog.values())
        for spec in toolset:
            if spec.rev_class == ReversibilityClass.R0:
                continue
            plan = synthesize_plan(spec, toolset, self.env)
            self.plans[spec.name] = plan
            # Fold the plan's evidence back into the tool's effective class.
            eff = effective_class(plan, spec.rev_class)
            spec.rev_class = eff
            if plan.expiry_s is not None:
                spec.half_life_s = plan.expiry_s
        return toolset

    # -- evaluation (no side effects) ------------------------------------
    def evaluate(self, tool_name: str, args: dict[str, Any]) -> CallEvaluation:
        """Classify + decide for a call without executing it (powers ``unwind.preview``)."""
        spec = self.catalog.get(tool_name)
        if spec is None:
            # Unknown tool → fail safe: treat as irreversible, escalate.
            spec = ToolSpec(
                server=self.upstream.server_name, name=tool_name, rev_class=ReversibilityClass.R4
            )
        cls = classify_tool(spec, self.env, llm=self.llm, use_llm=self.use_llm)
        # Prefer the catalog's plan-informed class if we have one.
        cls = cls.model_copy(update={"rev_class": max(cls.rev_class, spec.rev_class)})
        blast = estimate_blast_radius(spec, args)
        plan = self.plans.get(tool_name)
        eff = effective_class(plan, cls.rev_class) if plan else cls.rev_class
        # A viable, confident compensation is itself evidence of reversibility:
        # fold the plan's confidence into the class confidence the policy sees, so
        # a lexically-ambiguous R1/R2 with a strong undo plan can be auto-allowed
        # rather than needlessly escalated. (Never the reverse: this only applies
        # once the class is already reversible.)
        conf = cls.confidence
        if (
            plan is not None
            and plan.is_viable
            and eff in (ReversibilityClass.R1, ReversibilityClass.R2)
        ):
            conf = max(conf, plan.confidence)
        cls_eff = cls.model_copy(update={"rev_class": eff, "confidence": conf})
        decision = decide(cls_eff, blast, plan, self.policy)
        return CallEvaluation(tool_name, cls_eff, blast, plan, decision, eff)

    # -- execution (the real flow) ---------------------------------------
    async def execute(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        confirm: ConfirmFn | None = None,
    ) -> CallResult:
        """Run the full classify → decide → capture → forward → log flow."""
        ev = self.evaluate(tool_name, args)
        d = ev.decision.decision

        if d == Decision.BLOCK:
            return CallResult(ev, False, None, None, f"BLOCKED: {ev.decision.reason}")

        if d == Decision.ELICIT_CONFIRMATION:
            approved = False
            if confirm is not None:
                approved = await confirm(ev.decision.confirm_message or "Proceed?")
            if not approved:
                return CallResult(ev, False, None, None, f"DECLINED: {ev.decision.reason}")

        # Capture pre-state before mutating (enables R1 self-reversal).
        prestate: dict[str, Any] | None = None
        plan = ev.plan
        if plan and plan.pre_read and plan.pre_read in self.catalog:
            snap = await self.upstream.call_tool(plan.pre_read, _id_args(args))
            prestate = snap.get("structured") or {"raw": snap.get("content")}

        # Forward the (possibly confirmed) call to the upstream server.
        result = await self.upstream.call_tool(tool_name, args)

        # Log it durably unless it was a pure R0 read.
        undo_id: str | None = None
        if ev.effective_class != ReversibilityClass.R0:
            entry = UndoEntry(
                id=uuid.uuid4().hex,
                server=self.upstream.server_name,
                tool=tool_name,
                args=args,
                result=result,
                prestate=prestate,
                plan=plan,
                rev_class=ev.effective_class,
                expires_at=(now_ts() + plan.expiry_s) if (plan and plan.expiry_s) else None,
                status=UndoStatus.ACTIVE,
                session_id=self.session_id,
            )
            self.log.append(entry)
            undo_id = entry.id

        verb = "auto-allowed" if d.startswith("auto_allow") else "executed after confirmation"
        return CallResult(ev, True, result, undo_id, f"{ev.effective_class.name} {verb}")

    # -- undo (reverse order = stack unwinding) --------------------------
    async def undo(self, n: int = 1) -> list[UndoResult]:
        """Reverse the last ``n`` undoable actions of this session, newest first."""
        self.log.expire_due()
        entries = self.log.undoable(session_id=self.session_id)[:n]
        results: list[UndoResult] = []
        for entry in entries:
            results.append(await self._undo_one(entry))
        return results

    async def undo_entry(self, entry_id: str) -> UndoResult:
        entry = self.log.get(entry_id)
        if entry is None:
            raise KeyError(entry_id)
        return await self._undo_one(entry)

    async def _undo_one(self, entry: UndoEntry) -> UndoResult:
        plan = entry.plan
        if entry.is_expired():
            self.log.mark(entry.id, UndoStatus.EXPIRED)
            return UndoResult(
                entry.id,
                entry.tool,
                UndoOutcome.COULD_NOT_UNDO,
                "reversibility half-life elapsed",
                plan.residue if plan else [],
            )

        if plan is None or plan.inverse_tool is None:
            residue = plan.residue if plan else ["no compensation plan"]
            self.log.mark(entry.id, UndoStatus.FAILED)
            return UndoResult(
                entry.id,
                entry.tool,
                UndoOutcome.COULD_NOT_UNDO,
                "no inverse operation exists for this action — I should have asked first",
                residue,
            )

        inverse_args = _bind_inverse_args(plan, entry)
        res = await self.upstream.call_tool(plan.inverse_tool, inverse_args)
        if res.get("isError"):
            self.log.mark(entry.id, UndoStatus.FAILED)
            return UndoResult(
                entry.id,
                entry.tool,
                UndoOutcome.COULD_NOT_UNDO,
                f"inverse '{plan.inverse_tool}' failed: {res.get('content')}",
                plan.residue,
            )

        self.log.mark(entry.id, UndoStatus.UNDONE)
        from unwind.types import FidelityGrade

        # Outcome label reflects how faithfully prior state was restored. Residue
        # (notifications, audit entries, version bumps) is reported alongside and
        # is orthogonal to the label — even an exact restore can leave residue
        # (Garcia-Molina & Salem; §2 reports both).
        if plan.fidelity_grade >= FidelityGrade.EXACT:
            outcome = UndoOutcome.RESTORED
            reason = f"restored via '{plan.inverse_tool}' (fidelity: exact)"
        else:
            outcome = UndoOutcome.APPROXIMATELY_RESTORED
            reason = (
                f"approximately restored via '{plan.inverse_tool}' ({plan.fidelity_grade.label})"
            )
        return UndoResult(entry.id, entry.tool, outcome, reason, plan.residue)

    # -- convenience -----------------------------------------------------
    def history(self, n: int = 20) -> list[UndoEntry]:
        return self.log.recent(n, session_id=self.session_id)


_ID_KEYS = ("id", "ids", "uuid", "key", "name", "path", "record_id", "page_id", "file")


def _id_args(args: dict[str, Any]) -> dict[str, Any]:
    """Extract identifier-ish args to pass to a pre-state reader."""
    return {k: v for k, v in args.items() if k.lower() in _ID_KEYS}


def _bind_inverse_args(plan: CompensationPlan, entry: UndoEntry) -> dict[str, Any]:
    """Bind the inverse call's arguments from pre-state and the forward result."""
    tmpl = dict(plan.inverse_template or {})
    args: dict[str, Any] = {}

    if tmpl.pop("__from_prestate__", False):
        # Self-reversal: carry identifiers from the original call, overlay the
        # captured prior field values so the same tool writes state back.
        args.update(_id_args(entry.args))
        if isinstance(entry.prestate, dict):
            args.update({k: v for k, v in entry.prestate.items() if k != "raw"})
        return args

    if tmpl.pop("__bind_id_from_result__", False):
        rid = _extract_id(entry.result)
        if rid is None:
            # Fall back to any identifier from the original args.
            id_args = _id_args(entry.args)
            return id_args or {}
        return {"id": rid}

    # Static template (already fully specified).
    return tmpl
