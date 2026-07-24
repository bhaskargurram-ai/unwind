"""Protocol-conformance suite (MANDATORY CI gate, ``CLAUDE.md`` golden rule #1).

A proxy that breaks a client is worthless. These tests spawn the real
``unwind run`` proxy in front of a hand-rolled JSON-RPC server (``fake_server``)
and assert, over actual pipes, that:

* unknown methods are forwarded **byte-faithfully** (``x/custom``);
* ``initialize`` and ordinary ``tools/call`` reads pass through untouched;
* ``tools/list`` is augmented **non-destructively** (upstream tools preserved,
  ``unwind.*`` tools injected, reversibility annotations added under ``_meta``);
* the ``unwind.*`` agentic surface is handled locally, never forwarded;
* ``--passthrough-only`` is a true panic switch — zero modification.
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

# The stdio proxy uses asyncio pipe transports on the process's own stdin/stdout,
# which the Windows Proactor loop does not implement (connect_read_pipe). The
# core library is cross-platform; only the *stdio transport* is POSIX-only for
# now (Windows stdio support is tracked as future work). Skip the subprocess
# conformance run on Windows rather than fail CI on a documented limitation.
pytestmark = [
    pytest.mark.protocol,
    pytest.mark.skipif(
        sys.platform == "win32", reason="stdio proxy transport is POSIX-only for now"
    ),
]

FAKE = str(Path(__file__).parent / "fake_server.py")


class ProxyClient:
    """Drives the proxy subprocess as if it were an MCP client."""

    def __init__(self, *, passthrough_only: bool = False) -> None:
        cmd = [sys.executable, "-m", "unwind", "run", "--db", ":memory:"]
        if passthrough_only:
            cmd.append("--passthrough-only")
        cmd += ["--", sys.executable, FAKE]
        self.p = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.q: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self) -> None:
        assert self.p.stdout
        for line in self.p.stdout:
            self.q.put(line.strip())

    def send(self, obj: dict) -> None:
        assert self.p.stdin
        self.p.stdin.write(json.dumps(obj) + "\n")
        self.p.stdin.flush()

    def recv(self, want_id: int, timeout: float = 10.0) -> dict:
        end = time.time() + timeout
        while time.time() < end:
            try:
                line = self.q.get(timeout=max(0.01, end - time.time()))
            except queue.Empty:
                break
            if not line:
                continue
            msg = json.loads(line)
            if msg.get("id") == want_id:
                return msg
        raise TimeoutError(f"no response for id {want_id}")

    def close(self) -> None:
        try:
            if self.p.stdin:
                self.p.stdin.close()
        finally:
            self.p.terminate()
            try:
                self.p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.p.kill()


@pytest.fixture
def client():
    c = ProxyClient()
    c.send(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"capabilities": {"elicitation": {}}},
        }
    )
    c.recv(1)
    yield c
    c.close()


def test_initialize_passes_through(client: ProxyClient) -> None:
    client.send(
        {"jsonrpc": "2.0", "id": 10, "method": "initialize", "params": {"capabilities": {}}}
    )
    r = client.recv(10)
    assert r["result"]["serverInfo"]["name"] == "fake"


def test_unknown_method_byte_faithful(client: ProxyClient) -> None:
    payload = {"nested": {"a": [1, 2, 3]}, "unicode": "café"}
    client.send({"jsonrpc": "2.0", "id": 11, "method": "x/custom", "params": payload})
    r = client.recv(11)
    assert r["result"]["echo"] == payload  # forwarded and returned untouched


def test_tools_list_augmented_non_destructively(client: ProxyClient) -> None:
    client.send({"jsonrpc": "2.0", "id": 12, "method": "tools/list"})
    tools = client.recv(12)["result"]["tools"]
    names = {t["name"] for t in tools}
    # Upstream tools preserved.
    assert {"read_note", "delete_note"} <= names
    # unwind.* injected.
    assert "unwind.undo" in names and "unwind.preview" in names
    # Reversibility annotation added under _meta, delete_note is R4.
    dn = next(t for t in tools if t["name"] == "delete_note")
    assert dn["_meta"]["io.unwind/reversibility"]["class"] == "R4"


def test_read_call_passes_through(client: ProxyClient) -> None:
    client.send(
        {
            "jsonrpc": "2.0",
            "id": 13,
            "method": "tools/call",
            "params": {"name": "read_note", "arguments": {"id": "n1"}},
        }
    )
    r = client.recv(13)
    assert "called read_note" in r["result"]["content"][0]["text"]


def test_unwind_tool_handled_locally(client: ProxyClient) -> None:
    client.send(
        {
            "jsonrpc": "2.0",
            "id": 14,
            "method": "tools/call",
            "params": {
                "name": "unwind.preview",
                "arguments": {"tool": "delete_note", "args": {"id": "x"}},
            },
        }
    )
    r = client.recv(14)
    assert r["result"]["structuredContent"]["reversibility_class"] == "R4"


def test_passthrough_only_does_not_augment() -> None:
    c = ProxyClient(passthrough_only=True)
    try:
        c.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"capabilities": {}}})
        c.recv(1)
        c.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = c.recv(2)["result"]["tools"]
        names = {t["name"] for t in tools}
        # Panic switch: pure proxy — NO unwind.* injection, NO _meta annotation.
        assert names == {"read_note", "delete_note"}
        assert all("_meta" not in t for t in tools)
    finally:
        c.close()
