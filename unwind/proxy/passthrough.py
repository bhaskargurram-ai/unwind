"""Raw JSON-RPC stdio pump — the transparency substrate (``PROJECT.md`` §7, W1).

Golden rule #1: *transparency is sacred*. Unwind must be invisible when idle —
any method it does not understand is forwarded **byte-faithfully**. The correct
architecture for that guarantee is a raw newline-delimited JSON-RPC pump that
spawns the upstream server as a subprocess and shuttles frames between the
client's stdio and the child's stdio, applying logic only to the handful of
methods we understand.

This module is deliberately dependency-light (stdlib ``asyncio`` only): the
fewer moving parts between the two byte streams, the stronger the transparency
guarantee. A malformed or unknown frame is *never* dropped — it is forwarded
verbatim and, at worst, logged to stderr.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

Json = dict[str, Any]

# A hook decides what to do with a parsed frame. It returns:
#   * a dict   -> forward THIS (possibly modified) frame onward
#   * None     -> drop the frame (do not forward)
# Hooks may have side effects (logging, sending frames on the reverse channel).
Hook = Callable[[Json], Awaitable["HookResult"]]


@dataclass
class HookResult:
    forward: Json | None  # frame to send onward (None = drop)
    handled_reply: Json | None = None  # a frame to send back on the SOURCE channel


def _identity_hook_factory() -> Hook:
    async def _hook(frame: Json) -> HookResult:
        return HookResult(forward=frame)

    return _hook


def eprint(*args: object) -> None:
    """Log to stderr (stdout is the sacred protocol channel — never write there)."""
    print("[unwind]", *args, file=sys.stderr, flush=True)


class StdioProxy:
    """Spawns an upstream MCP server and pumps JSON-RPC both ways through hooks."""

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        *,
        env: dict[str, str] | None = None,
        on_client: Hook | None = None,  # client -> server frames
        on_server: Hook | None = None,  # server -> client frames
        passthrough_only: bool = False,
    ) -> None:
        self.command = command
        self.args = args or []
        self.env = env
        self.passthrough_only = passthrough_only
        self.on_client = (
            _identity_hook_factory() if (passthrough_only or on_client is None) else on_client
        )
        self.on_server = (
            _identity_hook_factory() if (passthrough_only or on_server is None) else on_server
        )
        self._proc: asyncio.subprocess.Process | None = None
        self._client_writer: asyncio.StreamWriter | None = None

    async def run(
        self,
        client_reader: asyncio.StreamReader | None = None,
        client_writer: asyncio.StreamWriter | None = None,
    ) -> int:
        """Run until the upstream exits. Uses process stdio if streams not given."""
        if client_reader is None or client_writer is None:
            client_reader, client_writer = await _stdio_streams()
        self._client_writer = client_writer

        self._proc = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=None,  # inherit: upstream logs go straight to our stderr
            env={**_os_environ(), **(self.env or {})} if self.env else None,
        )
        assert self._proc.stdin and self._proc.stdout

        if self.passthrough_only:
            eprint("passthrough-only mode: pure proxy, no interception")

        c2s = asyncio.create_task(
            self._forward(client_reader, self._proc.stdin, self.on_client, client_writer, "C→S")
        )
        s2c = asyncio.create_task(
            self._forward(self._proc.stdout, client_writer, self.on_server, self._proc.stdin, "S→C")
        )
        await asyncio.wait({c2s, s2c}, return_when=asyncio.FIRST_COMPLETED)
        for t in (c2s, s2c):
            t.cancel()
        rc = await self._proc.wait()
        return rc

    async def send_to_client(self, frame: Json) -> None:
        """Inject a server→client frame (used for elicitation requests)."""
        if self._client_writer is not None:
            await _write_frame(self._client_writer, frame)

    async def send_to_server(self, frame: Json) -> None:
        if self._proc and self._proc.stdin:
            await _write_frame(self._proc.stdin, frame)

    async def _forward(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        hook: Hook,
        back_writer: asyncio.StreamWriter,
        label: str,
    ) -> None:
        while True:
            line = await reader.readline()
            if not line:
                break
            raw = line.rstrip(b"\n")
            if not raw.strip():
                continue
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                # Not JSON we can parse — forward verbatim (transparency).
                writer.write(line)
                await writer.drain()
                continue
            try:
                result = await hook(frame)
            except Exception as exc:
                eprint(f"{label} hook error ({type(exc).__name__}: {exc}); forwarding raw")
                writer.write(line)
                await writer.drain()
                continue
            if result.handled_reply is not None:
                await _write_frame(back_writer, result.handled_reply)
            if result.forward is not None:
                await _write_frame(writer, result.forward)


async def _write_frame(writer: asyncio.StreamWriter, frame: Json) -> None:
    writer.write(json.dumps(frame, separators=(",", ":")).encode() + b"\n")
    await writer.drain()


async def _stdio_streams() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Wrap process stdin/stdout as asyncio streams.

    DECISION: this uses ``connect_read_pipe``/``connect_write_pipe``, which the
    Windows Proactor event loop does not implement for arbitrary pipes. The core
    library is cross-platform; only the *stdio transport* is POSIX-only for now.
    Windows users can run under WSL, or use the HTTP mode. A thread-backed reader
    for native Windows stdio is tracked as future work.
    """
    if sys.platform == "win32":  # pragma: no cover - platform-specific guard
        raise RuntimeError(
            "The Unwind stdio proxy transport is not yet supported natively on "
            "Windows (asyncio pipe limitation). Run under WSL, or use the HTTP "
            "proxy mode. See docs/faq for details."
        )
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    w_transport, w_protocol = await loop.connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    writer = asyncio.StreamWriter(w_transport, w_protocol, reader, loop)
    return reader, writer


def _os_environ() -> dict[str, str]:
    import os

    return dict(os.environ)
