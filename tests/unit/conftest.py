"""Shared fixtures for unit tests: an in-process sandbox upstream + engine."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from unwind.engine import ConfirmFn, ReversibilityEngine
from unwind.types import EnvironmentDescriptor, ToolSpec
from unwind.undolog.store import UndoLog
from unwind.upstream import InProcessUpstream


def build_sandbox() -> InProcessUpstream:
    """A workspace upstream mirroring ``unwind/demo.py`` (files/pages/email)."""
    up = InProcessUpstream("workspace")
    up.state = {
        "files": {"deploy.yaml": "replicas: 3\nregion: us-east"},
        "pages": {},
        "trash": {},
        "sent": [],
    }

    def get_file(a: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
        return {"path": a["path"], "content": s["files"].get(a["path"])}

    def write_file(a: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
        s["files"][a["path"]] = a["content"]
        return {"path": a["path"]}

    def get_page(a: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
        return {"id": a["id"], "title": s["pages"].get(a["id"])}

    def create_page(a: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
        s["pages"][a["id"]] = a.get("title", "")
        return {"id": a["id"]}

    def delete_page(a: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
        s["trash"][a["id"]] = s["pages"].pop(a["id"], None)
        return {"id": a["id"]}

    def send_email(a: dict[str, Any], s: dict[str, Any]) -> dict[str, Any]:
        s["sent"].append(a)
        return {"queued": True}

    id_in = {"properties": {"id": {"type": "string"}}}
    id_out = {"properties": {"id": {"type": "string"}}}
    up.register(
        ToolSpec(
            server="workspace",
            name="get_file",
            input_schema={"properties": {"path": {"type": "string"}}},
            output_schema={
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}}
            },
        ),
        get_file,
    )
    up.register(
        ToolSpec(
            server="workspace",
            name="write_file",
            input_schema={
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}}
            },
            output_schema={"properties": {"path": {"type": "string"}}},
        ),
        write_file,
    )
    up.register(
        ToolSpec(
            server="workspace",
            name="get_page",
            input_schema=id_in,
            output_schema={"properties": {"id": {"type": "string"}, "title": {"type": "string"}}},
        ),
        get_page,
    )
    up.register(
        ToolSpec(
            server="workspace",
            name="create_page",
            input_schema={"properties": {"id": {"type": "string"}, "title": {"type": "string"}}},
            output_schema=id_out,
        ),
        create_page,
    )
    up.register(
        ToolSpec(server="workspace", name="delete_page", input_schema=id_in, output_schema=id_out),
        delete_page,
    )
    up.register(
        ToolSpec(
            server="workspace",
            name="send_email",
            input_schema={"properties": {"to": {"type": "string"}, "body": {"type": "string"}}},
        ),
        send_email,
    )
    return up


@pytest.fixture
def sandbox() -> InProcessUpstream:
    return build_sandbox()


@pytest.fixture
def workspace_env() -> EnvironmentDescriptor:
    # Trash + versioned so deletes are compensable, like the demo.
    return EnvironmentDescriptor(name="workspace", has_trash=True, versioned=True)


@pytest.fixture
def engine(sandbox: InProcessUpstream, workspace_env: EnvironmentDescriptor) -> ReversibilityEngine:
    return ReversibilityEngine(sandbox, UndoLog(":memory:"), env=workspace_env)


@pytest.fixture
def confirm_yes() -> ConfirmFn:
    """A confirmation callback that always approves."""

    async def _yes(_msg: str) -> bool:
        return True

    return _yes


@pytest.fixture
def confirm_no() -> ConfirmFn:
    """A confirmation callback that always declines."""

    async def _no(_msg: str) -> bool:
        return False

    return _no


@pytest.fixture
def sandbox_factory() -> Callable[[], InProcessUpstream]:
    """Expose the sandbox builder for tests that need a fresh upstream."""
    return build_sandbox
