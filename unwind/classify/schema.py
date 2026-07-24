"""Structural signals from JSON schemas (``PROJECT.md`` §6 Stage 2, W2).

Schema shape is a strong, purely-structural signal — it does not depend on
natural-language descriptions (which "Mind the GAP" shows are insufficient for
safety reasoning). Two things matter most:

1. **Identifier acceptance** — does the tool take an id/selector of an entity?
   A tool that accepts a single ``id`` has bounded blast radius; one that accepts
   a ``filter``/``query``/``where`` (or nothing) may affect many entities.
2. **Bulk indicators** — array-typed selectors, ``recursive``/``force``/``all``
   flags, wildcard-friendly parameters raise both blast radius and risk.
"""

from __future__ import annotations

from typing import Any

from unwind.types import ToolSpec

_ID_KEYS = frozenset(
    {
        "id",
        "ids",
        "uuid",
        "guid",
        "key",
        "name",
        "path",
        "url",
        "handle",
        "slug",
        "record_id",
        "page_id",
        "message_id",
        "file",
        "filename",
        "target",
    }
)
_BULK_KEYS = frozenset(
    {
        "filter",
        "query",
        "where",
        "pattern",
        "glob",
        "prefix",
        "selector",
        "criteria",
        "search",
        "all",
        "every",
    }
)
_DANGER_FLAGS = frozenset(
    {"force", "recursive", "cascade", "permanent", "hard", "purge", "no_trash"}
)


def _properties(spec: ToolSpec) -> dict[str, Any]:
    schema = spec.input_schema or {}
    props = schema.get("properties")
    return props if isinstance(props, dict) else {}


def accepts_identifier(spec: ToolSpec) -> bool:
    """Whether the tool accepts a single-entity identifier (bounded blast radius)."""
    props = _properties(spec)
    for key, meta in props.items():
        if key.lower() in _ID_KEYS:
            # An *array* of ids is still identifier-based but multi-entity.
            t = meta.get("type") if isinstance(meta, dict) else None
            if t != "array":
                return True
    return False


def id_return_key(spec: ToolSpec) -> str | None:
    """The identifier field this tool *returns* (used to bind an inverse call).

    Read from ``output_schema`` when present; otherwise inferred conventionally.
    """
    out = spec.output_schema or {}
    props = out.get("properties") if isinstance(out, dict) else None
    if isinstance(props, dict):
        for key in props:
            if key.lower() in _ID_KEYS:
                return str(key)
    return None


def bulk_signal(spec: ToolSpec) -> bool:
    """Whether the schema suggests the tool can affect many entities at once."""
    props = _properties(spec)
    for key, meta in props.items():
        lk = key.lower()
        if lk in _BULK_KEYS:
            return True
        if isinstance(meta, dict) and meta.get("type") == "array" and lk in _ID_KEYS:
            return True
    return False


def danger_flags(spec: ToolSpec) -> list[str]:
    """Destructive-intent flags present in the schema (force/recursive/permanent...)."""
    props = _properties(spec)
    return sorted({k.lower() for k in props if k.lower() in _DANGER_FLAGS})


def schema_signals(spec: ToolSpec) -> dict[str, Any]:
    """Bundle the structural signals for the ensemble to weigh."""
    return {
        "accepts_identifier": accepts_identifier(spec),
        "id_return_key": id_return_key(spec),
        "bulk": bulk_signal(spec),
        "danger_flags": danger_flags(spec),
    }
