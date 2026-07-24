"""The Unwind agentic surface (``PROJECT.md`` §4, §7, W3).

Unwind is itself an MCP server exposing tools the *agent* can call to reason
about and reverse **its own** actions. This is what makes Unwind agentic rather
than a filter:

* ``unwind.preview``      — classify a prospective call without executing it
* ``unwind.undo``         — reverse the last *n* actions (or to a checkpoint)
* ``unwind.explain_risk`` — a human-readable risk explanation for a call
* ``unwind.history``      — the durable, cross-server undo log
* ``unwind.checkpoint``   — mark a point the agent can later roll back to

The definitions are transport-agnostic: the stdio proxy injects them into
``tools/list`` and dispatches them locally; a standalone deployment can expose
the same surface via ``FastMCP`` (see :func:`build_fastmcp`).
"""

from __future__ import annotations

import uuid
from typing import Any

from unwind.engine import ReversibilityEngine
from unwind.types import now_ts

UNWIND_TOOL_PREFIX = "unwind."

# Tool definitions in MCP ``tools/list`` shape (name/description/inputSchema).
TOOL_DEFS: list[dict[str, Any]] = [
    {
        "name": "unwind.preview",
        "description": (
            "Classify what WOULD happen if a tool were called — its reversibility "
            "class (R0–R4), blast radius, whether Unwind can undo it and at what "
            "fidelity — without executing it. Call this before any risky action."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool": {"type": "string", "description": "The upstream tool name."},
                "args": {"type": "object", "description": "The arguments you intend to pass."},
            },
            "required": ["tool"],
        },
    },
    {
        "name": "unwind.undo",
        "description": (
            "Reverse the last N actions in this session (default 1), newest first, "
            "like unwinding a stack. Reports each as restored / approximately_restored "
            "/ could_not_undo with the reason and any residue."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "minimum": 1, "default": 1},
                "to_checkpoint": {
                    "type": "string",
                    "description": "Undo back to this checkpoint id.",
                },
            },
        },
    },
    {
        "name": "unwind.explain_risk",
        "description": "Explain in plain language why a tool call has a given reversibility risk.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool": {"type": "string"},
                "args": {"type": "object"},
            },
            "required": ["tool"],
        },
    },
    {
        "name": "unwind.history",
        "description": "List recent logged actions and their undo status from the durable log.",
        "inputSchema": {
            "type": "object",
            "properties": {"n": {"type": "integer", "minimum": 1, "default": 20}},
        },
    },
    {
        "name": "unwind.checkpoint",
        "description": "Mark the current point so you can later `unwind.undo` back to it.",
        "inputSchema": {
            "type": "object",
            "properties": {"label": {"type": "string"}},
        },
    },
]

TOOL_NAMES = frozenset(t["name"] for t in TOOL_DEFS)


class UnwindTools:
    """Dispatcher for the ``unwind.*`` tools over a :class:`ReversibilityEngine`."""

    def __init__(self, engine: ReversibilityEngine) -> None:
        self.engine = engine
        self._checkpoints: dict[str, dict[str, Any]] = {}

    @staticmethod
    def is_unwind_tool(name: str) -> bool:
        return name in TOOL_NAMES

    async def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        args = args or {}
        if name == "unwind.preview":
            return await self._preview(args)
        if name == "unwind.explain_risk":
            return await self._explain(args)
        if name == "unwind.undo":
            return await self._undo(args)
        if name == "unwind.history":
            return self._history(args)
        if name == "unwind.checkpoint":
            return self._checkpoint(args)
        return {"isError": True, "content": [f"unknown unwind tool {name}"]}

    async def _preview(self, args: dict[str, Any]) -> dict[str, Any]:
        ev = self.engine.evaluate(args["tool"], args.get("args", {}))
        payload = {
            "tool": ev.tool,
            "reversibility_class": ev.effective_class.name,
            "class_label": ev.effective_class.label,
            "confidence": round(ev.classification.confidence, 3),
            "blast_radius": ev.blast.scope,
            "decision": ev.decision.decision.value,
            "reason": ev.decision.reason,
            "can_undo": bool(ev.plan and ev.plan.inverse_tool),
            "undo_via": ev.plan.inverse_tool if ev.plan else None,
            "fidelity": ev.plan.fidelity_grade.label if ev.plan else None,
            "residue": ev.plan.residue if ev.plan else [],
        }
        return {"isError": False, "structured": payload, "content": [payload]}

    async def _explain(self, args: dict[str, Any]) -> dict[str, Any]:
        ev = self.engine.evaluate(args["tool"], args.get("args", {}))
        lines = [
            f"'{ev.tool}' is class {ev.effective_class.name} ({ev.effective_class.label}).",
            f"Effect: {ev.classification.effect_verb.value}; blast radius: {ev.blast.scope}.",
            ev.classification.rationale,
        ]
        if ev.plan and ev.plan.inverse_tool:
            lines.append(
                f"If it goes wrong, Unwind can undo via '{ev.plan.inverse_tool}' "
                f"(fidelity: {ev.plan.fidelity_grade.label})."
            )
        else:
            lines.append(
                "Unwind has NO reliable way to undo this — you should confirm before acting."
            )
        if ev.plan and ev.plan.residue:
            lines.append("Residue undo cannot remove: " + "; ".join(ev.plan.residue))
        text = "\n".join(lines)
        return {"isError": False, "content": [text], "structured": {"explanation": text}}

    async def _undo(self, args: dict[str, Any]) -> dict[str, Any]:
        cp = args.get("to_checkpoint")
        if cp is not None and cp in self._checkpoints:
            # Undo everything logged after the checkpoint head.
            head_ts = self._checkpoints[cp]["ts"]
            entries = [
                e
                for e in self.engine.log.undoable(session_id=self.engine.session_id)
                if e.ts > head_ts
            ]
            outcomes = [await self.engine.undo_entry(e.id) for e in entries]
        else:
            outcomes = await self.engine.undo(int(args.get("n", 1)))
        payload = [
            {"tool": o.tool, "outcome": o.outcome.value, "reason": o.reason, "residue": o.residue}
            for o in outcomes
        ]
        return {"isError": False, "structured": {"undone": payload}, "content": payload}

    def _history(self, args: dict[str, Any]) -> dict[str, Any]:
        entries = self.engine.history(int(args.get("n", 20)))
        payload = [
            {
                "ts": e.ts,
                "server": e.server,
                "tool": e.tool,
                "class": e.rev_class.name,
                "status": e.status.value,
                "expires_at": e.expires_at,
            }
            for e in entries
        ]
        return {"isError": False, "structured": {"history": payload}, "content": payload}

    def _checkpoint(self, args: dict[str, Any]) -> dict[str, Any]:
        cp_id = "cp_" + uuid.uuid4().hex[:8]
        head = self.engine.log.undoable(session_id=self.engine.session_id)
        marker = {
            "checkpoint_id": cp_id,
            "label": args.get("label", cp_id),
            "ts": now_ts(),
            "head_entry_id": head[0].id if head else None,
        }
        self._checkpoints[cp_id] = marker
        return {"isError": False, "structured": marker, "content": [marker]}


def build_fastmcp(engine: ReversibilityEngine) -> Any:
    """Expose the ``unwind.*`` surface as a standalone MCP server via FastMCP."""
    from mcp.server.fastmcp import FastMCP

    tools = UnwindTools(engine)
    server = FastMCP("unwind")

    @server.tool(name="unwind.preview")
    async def preview(tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        return await tools.dispatch("unwind.preview", {"tool": tool, "args": args or {}})

    @server.tool(name="unwind.undo")
    async def undo(n: int = 1) -> dict[str, Any]:
        return await tools.dispatch("unwind.undo", {"n": n})

    @server.tool(name="unwind.explain_risk")
    async def explain_risk(tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        return await tools.dispatch("unwind.explain_risk", {"tool": tool, "args": args or {}})

    @server.tool(name="unwind.history")
    async def history(n: int = 20) -> dict[str, Any]:
        return await tools.dispatch("unwind.history", {"n": n})

    @server.tool(name="unwind.checkpoint")
    async def checkpoint(label: str = "") -> dict[str, Any]:
        return await tools.dispatch("unwind.checkpoint", {"label": label})

    return server
