"""Blast-radius estimation (``PROJECT.md`` §5.2, §7).

``delete_record(id)`` and ``delete_records(filter="*")`` share a reversibility
class but not a risk. Blast radius is the cardinality of affected entities. We
estimate it structurally from the call arguments, and — when a cheap read-probe
is available — refine it by actually counting matches (a dry run that touches no
state, keeping R0 semantics).

Fail safe: if we cannot bound it, we report ``unbounded`` (treated as high risk),
never a comforting small number (golden rule #2).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from unwind.classify import schema as schema_mod
from unwind.types import BlastRadius, ToolSpec

# Argument keys that select potentially many entities.
_BULK_ARG_KEYS = frozenset(
    {
        "filter",
        "query",
        "where",
        "pattern",
        "glob",
        "prefix",
        "selector",
        "criteria",
        "all",
        "search",
    }
)
_WILDCARDS = frozenset({"*", "%", ".*", "all", "everything", ""})

# A probe counts how many entities an argument set would match, without mutating.
ReadProbe = Callable[[ToolSpec, dict[str, Any]], int]


def estimate_blast_radius(
    spec: ToolSpec,
    args: dict[str, Any],
    *,
    probe: ReadProbe | None = None,
) -> BlastRadius:
    """Estimate how many entities a call to ``spec`` with ``args`` would affect."""
    # 1) A read-probe, if provided, gives a real count (preferred, structural).
    if probe is not None:
        try:
            n = probe(spec, args)
            return BlastRadius(
                count=n, unbounded=False, probed=True, scope=f"probe counted {n} matching entities"
            )
        except Exception:
            return BlastRadius(
                unbounded=True, probed=False, scope="read-probe failed; treating as unbounded"
            )

    # 2) Array of identifiers → exactly that many.
    for key, val in args.items():
        if key.lower() in schema_mod._ID_KEYS and isinstance(val, list):
            return BlastRadius(count=len(val), scope=f"{len(val)} ids in '{key}'")

    # 3) A bulk selector present → potentially unbounded, worse if wildcard-ish.
    for key, val in args.items():
        if key.lower() in _BULK_ARG_KEYS:
            if isinstance(val, str) and val.strip().lower() in _WILDCARDS:
                return BlastRadius(unbounded=True, scope=f"wildcard selector {key}={val!r}")
            return BlastRadius(unbounded=True, scope=f"selector '{key}' may match many")

    # 4) A single identifier present → one entity.
    if any(k.lower() in schema_mod._ID_KEYS for k in args):
        return BlastRadius(count=1, scope="single identifier")

    # 5) The schema *permits* bulk selection even if this call didn't use one,
    #    and no id was given → cannot bound it. Fail safe to unbounded.
    if schema_mod.bulk_signal(spec) or not args:
        return BlastRadius(unbounded=True, scope="no bounding identifier; schema permits bulk")

    return BlastRadius(count=1, scope="no bulk selector; assuming single entity")
