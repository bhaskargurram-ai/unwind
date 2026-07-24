"""Unit tests for blast-radius estimation (``unwind/blast.py``)."""

from __future__ import annotations

from typing import Any

from unwind.blast import estimate_blast_radius
from unwind.types import ToolSpec


def _spec(input_schema: dict | None = None) -> ToolSpec:
    return ToolSpec(server="s", name="delete_thing", input_schema=input_schema or {})


class TestArgumentBasedEstimation:
    def test_single_id_is_count_one(self) -> None:
        br = estimate_blast_radius(_spec({"properties": {"id": {"type": "string"}}}), {"id": "abc"})
        assert br.count == 1
        assert br.unbounded is False

    def test_array_of_ids_is_len(self) -> None:
        br = estimate_blast_radius(_spec(), {"ids": ["a", "b", "c"]})
        assert br.count == 3
        assert br.unbounded is False

    def test_wildcard_filter_unbounded(self) -> None:
        br = estimate_blast_radius(_spec(), {"filter": "*"})
        assert br.unbounded is True

    def test_nonwildcard_filter_still_unbounded(self) -> None:
        br = estimate_blast_radius(_spec(), {"filter": "status=open"})
        assert br.unbounded is True

    def test_no_args_bulk_capable_schema_unbounded(self) -> None:
        # Schema permits bulk (filter) and no id given -> cannot bound -> unbounded.
        spec = _spec({"properties": {"filter": {"type": "string"}}})
        br = estimate_blast_radius(spec, {})
        assert br.unbounded is True

    def test_empty_args_unbounded_fail_safe(self) -> None:
        br = estimate_blast_radius(_spec({"properties": {"id": {"type": "string"}}}), {})
        assert br.unbounded is True

    def test_non_bulk_non_id_args_assume_single(self) -> None:
        spec = _spec({"properties": {"content": {"type": "string"}}})
        br = estimate_blast_radius(spec, {"content": "hello"})
        assert br.count == 1
        assert br.unbounded is False


class TestProbe:
    def test_probe_returns_probed_count(self) -> None:
        def probe(spec: ToolSpec, args: dict[str, Any]) -> int:
            return 7

        br = estimate_blast_radius(_spec(), {"filter": "*"}, probe=probe)
        assert br.count == 7
        assert br.probed is True
        assert br.unbounded is False

    def test_probe_raising_is_unbounded_fail_safe(self) -> None:
        def probe(spec: ToolSpec, args: dict[str, Any]) -> int:
            raise RuntimeError("probe failed")

        br = estimate_blast_radius(_spec(), {"id": "abc"}, probe=probe)
        assert br.unbounded is True
        assert br.probed is False
