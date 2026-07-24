"""End-to-end integration against the REAL ``@modelcontextprotocol/server-filesystem``.

This is the proof that Unwind works with a real third-party MCP server (not just
the in-process demo): the proxy transparently wraps the filesystem server,
injects the ``unwind.*`` surface, the agent overwrites a file (R1, auto-logged
with pre-state capture), and ``unwind.undo`` restores exact prior content.

Marked ``integration`` (skipped by the default unit run) and auto-skips when
``npx`` / Node is unavailable, so it never breaks CI on machines without Node.
"""

from __future__ import annotations

import json
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("npx") is None, reason="npx/Node not available"),
    pytest.mark.skipif(sys.platform == "win32", reason="stdio proxy transport is POSIX-only"),
]

SERVER = ["npx", "-y", "@modelcontextprotocol/server-filesystem"]


class _Proxy:
    def __init__(self, workdir: Path, db: Path) -> None:
        cmd = [
            sys.executable,
            "-m",
            "unwind",
            "run",
            "--db",
            str(db),
            "--versioned-env",
            "--",
            *SERVER,
            str(workdir),
        ]
        self.p = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
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

    def recv(self, want_id: int, timeout: float = 45.0) -> dict:
        end = time.time() + timeout
        while time.time() < end:
            try:
                line = self.q.get(timeout=max(0.01, end - time.time()))
            except queue.Empty:
                break
            if line:
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


@pytest.mark.slow
def test_real_write_then_undo_restores(tmp_path: Path) -> None:
    note = tmp_path / "notes.txt"
    note.write_text("ORIGINAL CONTENT\n")
    proxy = _Proxy(tmp_path, tmp_path / "undo.db")
    try:
        proxy.send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "capabilities": {"elicitation": {}},
                    "protocolVersion": "2025-06-18",
                    "clientInfo": {"name": "t", "version": "0"},
                },
            }
        )
        proxy.recv(1)
        proxy.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        proxy.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = {t["name"] for t in proxy.recv(2)["result"]["tools"]}
        assert "write_file" in tools  # real server tools present
        assert "unwind.undo" in tools  # agentic surface injected

        # Agent overwrites the file (R1 self-reversible in a versioned env).
        proxy.send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "write_file",
                    "arguments": {"path": str(note), "content": "CORRUPTED BY AGENT"},
                },
            }
        )
        proxy.recv(3)
        assert note.read_text().strip() == "CORRUPTED BY AGENT"

        # Agent undoes its own action via the injected unwind.undo tool.
        proxy.send(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "unwind.undo", "arguments": {"n": 1}},
            }
        )
        undone = proxy.recv(4)["result"]["structuredContent"]["undone"]
        assert undone and undone[0]["outcome"] == "restored"
        time.sleep(0.5)
        assert note.read_text().strip() == "ORIGINAL CONTENT"
    finally:
        proxy.close()
