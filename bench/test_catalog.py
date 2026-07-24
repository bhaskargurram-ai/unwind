"""Tests for the catalog crawler helpers (§8 "Corpus").

These cover the pure, dependency-light surface (spec extraction, JSONL round-trip,
content hashing). The live stdio crawl is exercised in the integration/sandbox
suite, not here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bench.catalog.crawler import (
    hash_catalog,
    read_jsonl,
    toolspec_from_mcp_tool,
    write_jsonl,
)
from unwind.types import ReversibilityClass

CATALOG_DIR = Path(__file__).resolve().parent / "catalog"


def test_toolspec_from_dict() -> None:
    tool = {
        "name": "delete_file",
        "description": "Delete a file at the given path.",
        "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}},
    }
    spec = toolspec_from_mcp_tool("filesystem", tool)
    assert spec.server == "filesystem"
    assert spec.name == "delete_file"
    assert spec.description.startswith("Delete")
    assert spec.input_schema["properties"]["path"]["type"] == "string"
    # Crawler does NOT classify: rev_class stays at the fail-safe default (R4).
    assert spec.rev_class == ReversibilityClass.R4
    assert spec.confidence == 0.0


def test_toolspec_from_object() -> None:
    class FakeTool:
        def __init__(self) -> None:
            self.name = "read_file"
            self.description = "Read a file."
            self.inputSchema = {"type": "object"}
            self.outputSchema = None

    spec = toolspec_from_mcp_tool("filesystem", FakeTool())
    assert spec.name == "read_file"
    assert spec.output_schema is None


def test_jsonl_round_trip(tmp_path: Path) -> None:
    tools = [
        toolspec_from_mcp_tool("s1", {"name": "a", "description": "d1"}),
        toolspec_from_mcp_tool("s1", {"name": "b", "description": "d2"}),
    ]
    path = tmp_path / "catalog.jsonl"
    write_jsonl(tools, path)
    back = read_jsonl(path)
    assert [t.qualified_name for t in back] == ["s1:a", "s1:b"]
    assert back[0].description == "d1"


def test_hash_is_order_independent_and_stable() -> None:
    a = toolspec_from_mcp_tool("s", {"name": "x", "description": "dx"})
    b = toolspec_from_mcp_tool("s", {"name": "y", "description": "dy"})
    h1 = hash_catalog([a, b])
    h2 = hash_catalog([b, a])  # reversed order -> same hash
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


def test_hash_changes_on_content_change() -> None:
    a = toolspec_from_mcp_tool("s", {"name": "x", "description": "dx"})
    a2 = toolspec_from_mcp_tool("s", {"name": "x", "description": "CHANGED"})
    assert hash_catalog([a]) != hash_catalog([a2])


def test_sources_yaml_is_valid_and_stratified() -> None:
    data = yaml.safe_load((CATALOG_DIR / "sources.yaml").read_text())
    strata = set(data["strata"])
    # PROJECT.md §8: stratify by these domains.
    assert {
        "files",
        "vcs",
        "db",
        "comms",
        "payments",
        "crm",
        "cloud",
        "calendar",
    } <= strata
    server_domains = {s["domain"] for s in data["servers"]}
    # Every declared server domain is a known stratum.
    assert server_domains <= strata
    # The in-repo mocks are wired to be crawlable.
    mock_ids = {s["id"] for s in data["servers"] if s["id"].startswith("mock-")}
    assert {"mock-comms", "mock-payments"} <= mock_ids


def test_data_dir_is_gitignored_location() -> None:
    # The crawler must write under bench/catalog/data/ (gitignored) — assert the
    # path resolves inside the catalog package as documented.
    from bench.catalog.crawler import DATA_DIR

    assert DATA_DIR.name == "data"
    assert DATA_DIR.parent == CATALOG_DIR


def test_empty_hash_is_defined() -> None:
    # Hashing an empty catalog is well-defined (used before a real crawl exists).
    assert isinstance(hash_catalog([]), str)
    with pytest.raises(FileNotFoundError):
        read_jsonl(Path("/nonexistent/catalog.jsonl"))
