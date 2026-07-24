"""A minimal, dependency-free MCP-ish stdio server for conformance testing.

It is deliberately hand-rolled JSON-RPC (no SDK) so the conformance suite proves
the *proxy* forwards faithfully rather than testing the SDK. It supports just
enough: ``initialize``, ``tools/list``, ``tools/call`` (echo), and a deliberately
unusual method ``x/custom`` used to prove byte-faithful passthrough of methods
Unwind does not understand.
"""

from __future__ import annotations

import json
import sys

TOOLS = [
    {
        "name": "read_note",
        "description": "Read a note by id.",
        "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}},
    },
    {
        "name": "delete_note",
        "description": "Permanently delete a note.",
        "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}},
    },
]


def handle(msg: dict) -> dict | None:
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "result": {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake", "version": "0"},
            },
        }
    if method == "notifications/initialized":
        return None  # notification, no reply
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params", {})
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "result": {
                "content": [{"type": "text", "text": f"called {params.get('name')}"}],
                "structuredContent": {"id": params.get("arguments", {}).get("id", "n/a")},
                "isError": False,
            },
        }
    if method == "x/custom":
        # Unknown method: echo the params back verbatim to prove passthrough.
        return {"jsonrpc": "2.0", "id": mid, "result": {"echo": msg.get("params")}}
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        reply = handle(msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
