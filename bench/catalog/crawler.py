"""Tool-catalog crawler for ReversiBench (``PROJECT.md`` §8 "Corpus").

Given an MCP server launched over **stdio**, connect with the official ``mcp``
SDK client, call ``tools/list``, and emit one :class:`~unwind.types.ToolSpec` row
per tool as JSONL. Reversibility fields are left at their (fail-safe) defaults —
the crawler captures *only* the raw schema surface (name / description / input
schema / output schema); classification and labelling happen downstream so the
corpus stays a faithful record of what servers actually declare (§1: 96.1% of
tool descriptions carry no consequence warning — we record that ground truth).

Data hygiene (``CLAUDE.md`` git conventions / ``PROJECT.md`` §12): crawl outputs
are written under ``bench/catalog/data/`` (gitignored). Commit the crawler and a
content-hash manifest (:func:`hash_catalog`) only — never the crawled data.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from unwind.types import ToolSpec

__all__ = [
    "DATA_DIR",
    "crawl_stdio_server",
    "hash_catalog",
    "read_jsonl",
    "toolspec_from_mcp_tool",
    "write_jsonl",
]

# All crawl artefacts live here; the directory is gitignored (see .gitignore).
DATA_DIR = Path(__file__).resolve().parent / "data"


def toolspec_from_mcp_tool(server: str, tool: object) -> ToolSpec:
    """Convert one MCP-SDK ``Tool`` object into a raw :class:`ToolSpec`.

    Accepts either an ``mcp.types.Tool`` (attribute access) or a plain dict
    (``{"name", "description", "inputSchema", "outputSchema"}``), so the function
    is testable without a live server. Reversibility-derived fields keep their
    fail-safe defaults; the crawler does not classify.
    """
    if isinstance(tool, dict):
        name = tool.get("name", "")
        description = tool.get("description") or ""
        input_schema = tool.get("inputSchema") or tool.get("input_schema") or {}
        output_schema = tool.get("outputSchema") or tool.get("output_schema")
    else:
        name = getattr(tool, "name", "")
        description = getattr(tool, "description", None) or ""
        input_schema = getattr(tool, "inputSchema", None) or {}
        output_schema = getattr(tool, "outputSchema", None)
    return ToolSpec(
        server=server,
        name=name,
        description=description,
        input_schema=dict(input_schema) if input_schema else {},
        output_schema=dict(output_schema) if output_schema else None,
    )


def write_jsonl(specs: list[ToolSpec], path: Path) -> Path:
    """Write tool specs as one JSON object per line. Creates parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for spec in specs:
            fh.write(spec.model_dump_json())
            fh.write("\n")
    return path


def read_jsonl(path: Path) -> list[ToolSpec]:
    """Read a JSONL catalog back into :class:`ToolSpec` rows."""
    out: list[ToolSpec] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(ToolSpec.model_validate_json(line))
    return out


def hash_catalog(specs: list[ToolSpec]) -> str:
    """Content hash of a catalog for the committed ``hashes.json`` manifest.

    Deterministic SHA-256 over the *raw declared surface* of each tool (server,
    name, description, input/output schema), independent of row order. This lets
    us commit an integrity hash of a crawl without committing the crawl itself
    (§12): a reviewer re-runs the crawl and checks the hash matches.
    """
    digest = hashlib.sha256()
    rows = sorted(
        json.dumps(
            {
                "server": s.server,
                "name": s.name,
                "description": s.description,
                "input_schema": s.input_schema,
                "output_schema": s.output_schema,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        for s in specs
    )
    for row in rows:
        digest.update(row.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


async def crawl_stdio_server(
    server_id: str,
    command: str,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> list[ToolSpec]:
    """Connect to a stdio MCP server, list its tools, return raw :class:`ToolSpec`\\ s.

    Uses the official SDK exactly as ``CLAUDE.md`` specifies::

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

    The import is deferred so the module (and the pure helpers above) load without
    a live ``mcp`` runtime, keeping the unit tests dependency-light.
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=command, args=list(args or []), env=env)
    specs: list[ToolSpec] = []
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        listed = await session.list_tools()
        for tool in listed.tools:
            specs.append(toolspec_from_mcp_tool(server_id, tool))
    return specs
