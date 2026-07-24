"""Unit tests for structural schema signals (``unwind/classify/schema.py``)."""

from __future__ import annotations

from unwind.classify.schema import (
    accepts_identifier,
    bulk_signal,
    danger_flags,
    id_return_key,
    schema_signals,
)
from unwind.types import ToolSpec


def _spec(input_schema: dict, output_schema: dict | None = None) -> ToolSpec:
    return ToolSpec(server="s", name="t", input_schema=input_schema, output_schema=output_schema)


class TestAcceptsIdentifier:
    def test_single_id(self) -> None:
        spec = _spec({"properties": {"id": {"type": "string"}}})
        assert accepts_identifier(spec) is True

    def test_path_identifier(self) -> None:
        spec = _spec({"properties": {"path": {"type": "string"}}})
        assert accepts_identifier(spec) is True

    def test_array_of_ids_is_not_single(self) -> None:
        spec = _spec({"properties": {"ids": {"type": "array"}}})
        assert accepts_identifier(spec) is False

    def test_no_identifier(self) -> None:
        spec = _spec({"properties": {"filter": {"type": "string"}}})
        assert accepts_identifier(spec) is False

    def test_empty_schema(self) -> None:
        assert accepts_identifier(_spec({})) is False


class TestIdReturnKey:
    def test_reads_from_output_schema(self) -> None:
        spec = _spec({}, {"properties": {"id": {"type": "string"}}})
        assert id_return_key(spec) == "id"

    def test_page_id_key(self) -> None:
        spec = _spec({}, {"properties": {"page_id": {"type": "string"}}})
        assert id_return_key(spec) == "page_id"

    def test_none_when_no_id_field(self) -> None:
        spec = _spec({}, {"properties": {"title": {"type": "string"}}})
        assert id_return_key(spec) is None

    def test_none_when_no_output_schema(self) -> None:
        assert id_return_key(_spec({})) is None


class TestBulkSignal:
    def test_filter_key_is_bulk(self) -> None:
        assert bulk_signal(_spec({"properties": {"filter": {"type": "string"}}})) is True

    def test_query_key_is_bulk(self) -> None:
        assert bulk_signal(_spec({"properties": {"query": {"type": "string"}}})) is True

    def test_array_of_ids_is_bulk(self) -> None:
        assert bulk_signal(_spec({"properties": {"ids": {"type": "array"}}})) is True

    def test_single_id_not_bulk(self) -> None:
        assert bulk_signal(_spec({"properties": {"id": {"type": "string"}}})) is False


class TestDangerFlags:
    def test_detects_force_recursive(self) -> None:
        spec = _spec(
            {"properties": {"force": {"type": "boolean"}, "recursive": {"type": "boolean"}}}
        )
        assert danger_flags(spec) == ["force", "recursive"]

    def test_permanent_and_cascade(self) -> None:
        spec = _spec(
            {"properties": {"permanent": {"type": "boolean"}, "cascade": {"type": "boolean"}}}
        )
        assert set(danger_flags(spec)) == {"cascade", "permanent"}

    def test_no_danger_flags(self) -> None:
        assert danger_flags(_spec({"properties": {"id": {"type": "string"}}})) == []


class TestSchemaSignalsBundle:
    def test_bundle_shape(self) -> None:
        spec = _spec(
            {"properties": {"id": {"type": "string"}, "force": {"type": "boolean"}}},
            {"properties": {"id": {"type": "string"}}},
        )
        sig = schema_signals(spec)
        assert sig["accepts_identifier"] is True
        assert sig["id_return_key"] == "id"
        assert sig["bulk"] is False
        assert sig["danger_flags"] == ["force"]
