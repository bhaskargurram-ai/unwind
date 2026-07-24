"""The Unwind stdio proxy — default deployment mode (``PROJECT.md`` §7, W1/W3).

One line in ``mcp.json`` puts Unwind transparently in front of any stdio MCP
server. This orchestrator composes:

* :class:`~unwind.proxy.passthrough.StdioProxy` — the byte-faithful pump;
* the :class:`~unwind.engine.ReversibilityEngine` — classify / decide / log / undo;
* the :class:`~unwind.tools.UnwindTools` surface — injected into ``tools/list``;
* native elicitation (:mod:`unwind.proxy.elicit`) for confirmations.

Design notes that keep transparency + correctness intact:

* Unknown methods and R0 reads flow straight through untouched.
* Unwind speaks to the upstream *on the same pipe* by injecting requests with a
  reserved ``unwind:`` id prefix; their responses are demultiplexed and never
  leaked to the client.
* A ``tools/call`` that needs a human is handled in a background task so the
  read loop stays free to receive the client's elicitation reply (no deadlock).
"""

from __future__ import annotations

import asyncio
import itertools
import json
from typing import Any

from unwind.engine import ReversibilityEngine
from unwind.policy.config import PolicyConfig
from unwind.proxy.elicit import (
    build_elicitation_request,
    interpret_elicitation_reply,
    is_unwind_request_id,
)
from unwind.proxy.passthrough import HookResult, StdioProxy, eprint
from unwind.tools import TOOL_DEFS, UnwindTools
from unwind.types import (
    Decision,
    EnvironmentDescriptor,
    ReversibilityClass,
    UndoEntry,
    UndoStatus,
    now_ts,
)
from unwind.undolog.store import UndoLog

Json = dict[str, Any]


class ProxyUpstream:
    """An :class:`Upstream` whose calls are injected onto the proxy's shared pipe."""

    def __init__(self, proxy: UnwindStdioProxy) -> None:
        self._proxy = proxy
        self.server_name = proxy.server_name

    async def list_tools(self):  # type: ignore[no-untyped-def]
        from unwind.types import ToolSpec

        reply = await self._proxy._inject("tools/list", {})
        raw = (reply.get("result") or {}).get("tools", [])
        specs = []
        for t in raw:
            name = t.get("name", "")
            if name.startswith("unwind."):  # never re-ingest our own tools
                continue
            specs.append(
                ToolSpec(
                    server=self.server_name,
                    name=name,
                    description=t.get("description", "") or "",
                    input_schema=t.get("inputSchema", {}) or {},
                    output_schema=t.get("outputSchema"),
                )
            )
        return specs

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        return await self._proxy.call_upstream(name, args)


class UnwindStdioProxy:
    """Transparent, reversibility-aware stdio proxy for one upstream server."""

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        *,
        env: dict[str, str] | None = None,
        db_path: str = "unwind.db",
        environment: EnvironmentDescriptor | None = None,
        policy: PolicyConfig | None = None,
        passthrough_only: bool = False,
        use_llm: bool = False,
    ) -> None:
        self.server_name = command.rsplit("/", 1)[-1]
        self.passthrough_only = passthrough_only
        self.log = UndoLog(db_path)
        self.engine = ReversibilityEngine(
            ProxyUpstream(self),
            self.log,
            env=environment,
            policy=policy or PolicyConfig(passthrough_only=passthrough_only),
            use_llm=use_llm,
        )
        self.tools = UnwindTools(self.engine)
        self._pump = StdioProxy(
            command,
            args,
            env=env,
            on_client=self._on_client,
            on_server=self._on_server,
            passthrough_only=passthrough_only,
        )
        self._pending: dict[str, asyncio.Future[Json]] = {}
        self._ids = itertools.count(1)
        self._catalog_ready = False
        self._tracked_calls: dict[Any, dict[str, Any]] = (
            {}
        )  # client-call id -> {tool,args,plan,prestate}
        self._client_supports_elicitation = True
        self._bg_tasks: set[asyncio.Task[None]] = set()  # keep strong refs to bg tasks

    async def run(self) -> int:
        return await self._pump.run()

    # -- injected upstream calls (reserved id, demultiplexed) ------------
    async def _inject(self, method: str, params: dict[str, Any]) -> Json:
        """Send a proxy-originated request to the upstream and await its reply.

        The reply carries our reserved ``unwind:`` id, so the S→C hook routes it
        back to us and never leaks it to the client.
        """
        rid = f"unwind:req:{next(self._ids)}"
        fut: asyncio.Future[Json] = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        await self._pump.send_to_server(
            {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
        )
        try:
            return await asyncio.wait_for(fut, timeout=30.0)
        except TimeoutError:
            self._pending.pop(rid, None)
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [], "isError": True}}

    async def call_upstream(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        reply = await self._inject("tools/call", {"name": tool, "arguments": args})
        return _result_to_dict(reply)

    async def _elicit(self, message: str) -> bool:
        rid = f"unwind:elicit:{next(self._ids)}"
        fut: asyncio.Future[Json] = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        await self._pump.send_to_client(build_elicitation_request(rid, message))
        try:
            reply = await asyncio.wait_for(fut, timeout=300.0)
        except TimeoutError:
            self._pending.pop(rid, None)
            return False  # fail safe: no answer → decline
        return interpret_elicitation_reply(reply)

    # -- client -> server hook ------------------------------------------
    async def _on_client(self, frame: Json) -> HookResult:
        fid = frame.get("id")
        # Is this the client's reply to one of our elicitation requests?
        if is_unwind_request_id(fid) and fid in self._pending:
            self._resolve(fid, frame)
            return HookResult(forward=None)

        method = frame.get("method")
        if method == "initialize":
            self._observe_client_caps(frame)
            return HookResult(forward=frame)

        if method != "tools/call":
            return HookResult(forward=frame)  # everything else: pass through

        params = frame.get("params") or {}
        name = params.get("name", "")
        call_args = params.get("arguments", {}) or {}

        # Our own tools: handle locally, reply to the client, do not forward.
        if UnwindTools.is_unwind_tool(name):
            out = await self.tools.dispatch(name, call_args)
            return HookResult(forward=None, handled_reply=_reply_frame(fid, out))

        if self.passthrough_only:
            return HookResult(forward=frame)

        # Upstream mutating tool: decide.
        await self._ensure_catalog()
        ev = self.engine.evaluate(name, call_args)
        decision = ev.decision.decision

        if decision == Decision.BLOCK:
            eprint(f"BLOCK {name}: {ev.decision.reason}")
            return HookResult(forward=None, handled_reply=_error_frame(fid, ev.decision.reason))

        if decision == Decision.ELICIT_CONFIRMATION:
            # Handle in the background so the read loop can receive the reply.
            task = asyncio.create_task(
                self._elicit_then_forward(frame, ev.decision.confirm_message or "Proceed?")
            )
            self._bg_tasks.add(task)
            task.add_done_callback(self._bg_tasks.discard)
            return HookResult(forward=None)

        # AUTO_ALLOW / AUTO_ALLOW_LOGGED: capture pre-state, track for logging, forward.
        await self._prepare_tracking(fid, name, call_args, ev)
        return HookResult(forward=frame)

    async def _elicit_then_forward(self, frame: Json, message: str) -> None:
        fid = frame.get("id")
        approved = await self._elicit(message) if self._client_supports_elicitation else False
        if not approved:
            await self._pump.send_to_client(
                _error_frame(fid, "declined by human (Unwind elicitation)")
            )
            return
        params = frame.get("params") or {}
        ev = self.engine.evaluate(params.get("name", ""), params.get("arguments", {}) or {})
        await self._prepare_tracking(
            fid, params.get("name", ""), params.get("arguments", {}) or {}, ev
        )
        await self._pump.send_to_server(frame)

    async def _prepare_tracking(
        self, fid: Any, name: str, call_args: dict[str, Any], ev: Any
    ) -> None:
        prestate = None
        plan = ev.plan
        if plan and plan.pre_read and plan.pre_read in self.engine.catalog:
            snap = await self.call_upstream(plan.pre_read, _id_args(call_args))
            prestate = snap.get("structured") or {"raw": snap.get("content")}
        if ev.effective_class != ReversibilityClass.R0:
            self._tracked_calls[fid] = {
                "tool": name,
                "args": call_args,
                "plan": plan,
                "prestate": prestate,
                "rev_class": ev.effective_class,
            }

    # -- server -> client hook ------------------------------------------
    async def _on_server(self, frame: Json) -> HookResult:
        fid = frame.get("id")
        # Response to one of Unwind's injected requests → capture, do not leak.
        if is_unwind_request_id(fid) and fid in self._pending:
            self._resolve(fid, frame)
            return HookResult(forward=None)

        # A tools/list result → classify, cache, and augment with unwind.* tools.
        if "result" in frame and isinstance(frame["result"], dict) and "tools" in frame["result"]:
            await self._ingest_and_augment(frame)
            return HookResult(forward=frame)

        # Response to a tracked client tools/call → log it durably.
        if fid in self._tracked_calls and "result" in frame:
            self._log_tracked(fid, frame)

        return HookResult(forward=frame)

    async def _ingest_and_augment(self, frame: Json) -> None:
        result = frame["result"]
        raw_tools = result.get("tools", [])
        if not self.passthrough_only:
            # Build/refresh the classified catalog from what the server reported.
            from unwind.classify.ensemble import classify_tool
            from unwind.synthesize.plan import effective_class, synthesize_plan
            from unwind.types import ToolSpec

            specs = [
                ToolSpec(
                    server=self.server_name,
                    name=t.get("name", ""),
                    description=t.get("description", "") or "",
                    input_schema=t.get("inputSchema", {}) or {},
                    output_schema=t.get("outputSchema"),
                )
                for t in raw_tools
            ]
            for spec in specs:
                cls = classify_tool(spec, self.engine.env)
                spec.rev_class = cls.rev_class
                spec.effect_verb = cls.effect_verb
                spec.entity = cls.entity
                spec.externality = cls.externality
                self.engine.catalog[spec.name] = spec
            for spec in specs:
                if spec.rev_class == ReversibilityClass.R0:
                    continue
                plan = synthesize_plan(spec, specs, self.engine.env)
                self.engine.plans[spec.name] = plan
                spec.rev_class = effective_class(plan, spec.rev_class)
            self._catalog_ready = True

            # Non-destructive annotation of upstream tools with a reversibility hint.
            for t in raw_tools:
                cspec = self.engine.catalog.get(t.get("name", ""))
                if cspec is None:
                    continue
                meta = t.setdefault("_meta", {})
                meta["io.unwind/reversibility"] = {
                    "class": cspec.rev_class.name,
                    "label": cspec.rev_class.label,
                    "can_undo": bool(
                        self.engine.plans.get(cspec.name, None)
                        and self.engine.plans[cspec.name].inverse_tool
                    ),
                }
            # Inject the unwind.* agentic surface.
            existing = {t.get("name") for t in raw_tools}
            for d in TOOL_DEFS:
                if d["name"] not in existing:
                    raw_tools.append(d)
        result["tools"] = raw_tools

    def _log_tracked(self, fid: Any, frame: Json) -> None:
        info = self._tracked_calls.pop(fid, None)
        if info is None:
            return
        import uuid

        plan = info["plan"]
        entry = UndoEntry(
            id=uuid.uuid4().hex,
            server=self.server_name,
            tool=info["tool"],
            args=info["args"],
            result=_result_to_dict(frame),
            prestate=info["prestate"],
            plan=plan,
            rev_class=info["rev_class"],
            expires_at=(now_ts() + plan.expiry_s) if (plan and plan.expiry_s) else None,
            status=UndoStatus.ACTIVE,
            session_id=self.engine.session_id,
        )
        self.log.append(entry)

    # -- helpers ---------------------------------------------------------
    def _resolve(self, rid: str, frame: Json) -> None:
        fut = self._pending.pop(rid, None)
        if fut is not None and not fut.done():
            fut.set_result(frame)

    def _observe_client_caps(self, frame: Json) -> None:
        caps = (frame.get("params") or {}).get("capabilities") or {}
        # If the client declares no elicitation capability, we cannot ask → the
        # policy must fail safe (block instead of silently proceeding).
        self._client_supports_elicitation = "elicitation" in caps
        self.engine.policy.client_supports_elicitation = self._client_supports_elicitation

    async def _ensure_catalog(self) -> None:
        if self._catalog_ready or self.engine.catalog:
            return
        # The client hasn't listed tools yet; fetch them ourselves so decisions
        # aren't made blind. Fail open to passthrough only if this errors.
        try:
            await self.engine.build_catalog()
            self._catalog_ready = True
        except Exception as exc:
            eprint(f"catalog build failed ({exc}); decisions may be conservative")


def _reply_frame(fid: Any, out: dict[str, Any]) -> Json:
    content = out.get("content", [])
    blocks = [{"type": "text", "text": c if isinstance(c, str) else json.dumps(c)} for c in content]
    result: Json = {"content": blocks, "isError": bool(out.get("isError", False))}
    if out.get("structured") is not None:
        result["structuredContent"] = out["structured"]
    return {"jsonrpc": "2.0", "id": fid, "result": result}


def _error_frame(fid: Any, message: str) -> Json:
    return {
        "jsonrpc": "2.0",
        "id": fid,
        "result": {"content": [{"type": "text", "text": f"Unwind: {message}"}], "isError": True},
    }


def _result_to_dict(frame: Json) -> dict[str, Any]:
    result = frame.get("result")
    if not isinstance(result, dict):
        return {"content": [], "isError": True}
    content = []
    for block in result.get("content", []) or []:
        content.append(block.get("text") if isinstance(block, dict) else block)
    return {
        "content": content,
        "structured": result.get("structuredContent"),
        "isError": bool(result.get("isError", False)),
    }


_ID_KEYS = ("id", "ids", "uuid", "key", "name", "path", "record_id", "page_id", "file")


def _id_args(args: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in args.items() if k.lower() in _ID_KEYS}
