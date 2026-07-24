"""Native MCP elicitation for confirmations (``PROJECT.md`` §3.1, §7; SEP-2322).

Confirmations ride the protocol's own elicitation channel — never a bespoke UI —
so they work in every compliant client (golden rule #8). The spec's canonical
example is literally ``{"type":"elicitation","message":"Delete 3 files?",
"schema":{"type":"boolean"}}``.

This module builds the elicitation request frame and interprets the client's
reply. The request/response *routing* (matching the reply to the pending
confirmation without leaking the frame to the upstream) lives in
:mod:`unwind.proxy.stdio`, which owns both byte streams.
"""

from __future__ import annotations

from typing import Any

# Reserved JSON-RPC id prefix for proxy-originated requests, so responses can be
# demultiplexed from client/server traffic and never forwarded onward.
UNWIND_ID_PREFIX = "unwind:"


def build_elicitation_request(request_id: str, message: str) -> dict[str, Any]:
    """A boolean confirmation elicitation, per the spec example."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "elicitation/create",
        "params": {
            "message": message,
            "requestedSchema": {
                "type": "object",
                "properties": {
                    "approve": {
                        "type": "boolean",
                        "description": "Approve this irreversible/low-confidence action?",
                    }
                },
                "required": ["approve"],
            },
        },
    }


def interpret_elicitation_reply(reply: dict[str, Any]) -> bool:
    """Interpret a client's elicitation reply as approve / decline.

    Fail safe (golden rule #2): anything that is not an explicit accept+approve
    is treated as a decline.
    """
    result = reply.get("result")
    if not isinstance(result, dict):
        return False
    action = result.get("action")
    if action is not None and action != "accept":
        return False  # declined or cancelled
    content = result.get("content")
    if isinstance(content, dict):
        return bool(content.get("approve", False))
    # Some clients return the boolean directly.
    return bool(result.get("approve", False))


def is_unwind_request_id(frame_id: Any) -> bool:
    return isinstance(frame_id, str) and frame_id.startswith(UNWIND_ID_PREFIX)
