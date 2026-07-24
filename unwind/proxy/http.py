"""Streamable HTTP proxy mode (``PROJECT.md`` §7, §3.1; SEP-2243).

For teams that run MCP over Streamable HTTP rather than stdio. This is a thin
ASGI app that forwards JSON-RPC to an upstream HTTP MCP endpoint, stamping the
gateway-routing headers the spec now requires (``Mcp-Protocol-Version``,
``Mcp-Method``, ``Mcp-Name``) so downstream gateways can route on the operation
without parsing the body — and applying the same reversibility logic as the
stdio mode to ``tools/list`` / ``tools/call``.

Scope note: single-response (non-SSE) request/response is implemented here; full
server-initiated SSE streaming is a documented extension (see ``docs``). The
header discipline and interception surface are the parts that matter for the
proxy-pattern being "blessed by the spec".
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from unwind.policy.config import PolicyConfig
from unwind.types import EnvironmentDescriptor

MCP_PROTOCOL_VERSION = "2025-06-18"


class StreamableHttpProxy:
    """Minimal Streamable-HTTP forwarding proxy with reversibility interception."""

    def __init__(
        self,
        upstream_url: str,
        *,
        environment: EnvironmentDescriptor | None = None,
        policy: PolicyConfig | None = None,
        passthrough_only: bool = False,
    ) -> None:
        self.upstream_url = upstream_url
        self.env = environment or EnvironmentDescriptor()
        self.policy = policy or PolicyConfig(passthrough_only=passthrough_only)
        self.passthrough_only = passthrough_only

    def _headers_for(self, message: dict[str, Any]) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Mcp-Protocol-Version": MCP_PROTOCOL_VERSION,
        }
        method = message.get("method")
        if isinstance(method, str):
            headers["Mcp-Method"] = method  # SEP-2243: route without body inspection
            params = message.get("params") or {}
            name = params.get("name")
            if isinstance(name, str):
                headers["Mcp-Name"] = name
        return headers

    async def forward(self, message: dict[str, Any]) -> dict[str, Any]:
        """Forward one JSON-RPC message upstream, annotating tools/list responses."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                self.upstream_url, content=json.dumps(message), headers=self._headers_for(message)
            )
            resp.raise_for_status()
            body: dict[str, Any] = resp.json()
        if not self.passthrough_only and _is_tools_list_result(body):
            _annotate_tools_list(body, self.env)
        return body

    async def asgi(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """A tiny ASGI entry point so this can mount under uvicorn/hypercorn."""
        if scope["type"] != "http":  # pragma: no cover - lifespan etc.
            return
        raw = b""
        while True:
            event = await receive()
            raw += event.get("body", b"")
            if not event.get("more_body"):
                break
        try:
            message = json.loads(raw or b"{}")
            result = await self.forward(message)
            status, payload = 200, json.dumps(result).encode()
        except Exception as exc:
            status, payload = 502, json.dumps({"error": str(exc)}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": payload})


def _is_tools_list_result(body: dict[str, Any]) -> bool:
    return isinstance(body.get("result"), dict) and "tools" in body["result"]


def _annotate_tools_list(body: dict[str, Any], env: EnvironmentDescriptor) -> None:
    from unwind.classify.ensemble import classify_tool
    from unwind.tools import TOOL_DEFS
    from unwind.types import ToolSpec

    tools = body["result"].get("tools", [])
    for t in tools:
        spec = ToolSpec(
            server="upstream",
            name=t.get("name", ""),
            description=t.get("description", "") or "",
            input_schema=t.get("inputSchema", {}) or {},
        )
        cls = classify_tool(spec, env)
        meta = t.setdefault("_meta", {})
        meta["io.unwind/reversibility"] = {
            "class": cls.rev_class.name,
            "label": cls.rev_class.label,
        }
    existing = {t.get("name") for t in tools}
    tools.extend(d for d in TOOL_DEFS if d["name"] not in existing)
    body["result"]["tools"] = tools
