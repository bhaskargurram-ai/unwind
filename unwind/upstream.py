"""Upstream abstraction — the boundary between Unwind and a real MCP server.

Two implementations behind one Protocol so the *same* engine logic
(classify → capture → forward → log → undo) runs in production and in the
hermetic demo/tests:

* :class:`McpUpstream` — a real MCP server spawned over stdio via the official
  ``mcp`` client SDK.
* :class:`InProcessUpstream` — a dict of Python-callable "tools" over a mutable
  state store, used by ``scripts/demo.py`` and the unit tests. It models
  pre-state semantics (create/delete/write) so undo can be exercised end-to-end
  with no external process.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from typing import Any, Protocol, runtime_checkable

from unwind.types import ToolSpec


@runtime_checkable
class Upstream(Protocol):
    """Everything the engine needs from an upstream MCP server."""

    server_name: str

    async def list_tools(self) -> list[ToolSpec]: ...

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Real MCP upstream (stdio transport)
# ---------------------------------------------------------------------------
class McpUpstream:
    """Wraps a real MCP server subprocess via ``mcp`` ClientSession over stdio."""

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        *,
        name: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.command = command
        self.args = args or []
        self.env = env
        self.server_name = name or command.rsplit("/", 1)[-1]
        self._stack: AsyncExitStack | None = None
        self._session: Any = None

    async def __aenter__(self) -> McpUpstream:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        self._stack = AsyncExitStack()
        params = StdioServerParameters(command=self.command, args=self.args, env=self.env)
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._session = None

    async def list_tools(self) -> list[ToolSpec]:
        assert self._session is not None, "McpUpstream must be entered as an async context"
        result = await self._session.list_tools()
        specs: list[ToolSpec] = []
        for tool in result.tools:
            specs.append(
                ToolSpec(
                    server=self.server_name,
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=getattr(tool, "inputSchema", None) or {},
                    output_schema=getattr(tool, "outputSchema", None),
                )
            )
        return specs

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        assert self._session is not None, "McpUpstream must be entered as an async context"
        result = await self._session.call_tool(name, arguments=args)
        content: list[Any] = []
        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            content.append(text if text is not None else block.model_dump())
        return {
            "content": content,
            "structured": getattr(result, "structuredContent", None),
            "isError": bool(getattr(result, "isError", False)),
        }


# ---------------------------------------------------------------------------
# In-process upstream (demo + tests)
# ---------------------------------------------------------------------------
ToolFn = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
"""A tool: ``(args, state) -> result``; may mutate ``state`` in place."""


class InProcessUpstream:
    """A fully in-memory upstream that models real tool semantics for the demo."""

    def __init__(self, server_name: str = "sandbox") -> None:
        self.server_name = server_name
        self.state: dict[str, Any] = {}
        self._specs: dict[str, ToolSpec] = {}
        self._fns: dict[str, ToolFn] = {}

    def register(self, spec: ToolSpec, fn: ToolFn) -> None:
        spec = spec.model_copy(update={"server": self.server_name})
        self._specs[spec.name] = spec
        self._fns[spec.name] = fn

    def snapshot(self) -> dict[str, Any]:
        """Deep-ish copy of observable state, for fidelity diffing."""
        import copy

        return copy.deepcopy(self.state)

    async def list_tools(self) -> list[ToolSpec]:
        return list(self._specs.values())

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name not in self._fns:
            return {"content": [f"unknown tool {name}"], "isError": True}
        try:
            out = self._fns[name](args, self.state)
            return {"content": [out], "structured": out, "isError": False}
        except Exception as exc:
            return {"content": [f"{type(exc).__name__}: {exc}"], "isError": True}


# Awaitable alias used by callers that accept either sync or async factories.
UpstreamFactory = Callable[[], Awaitable[Upstream]]
