"""Unit tests for the ensemble classifier (``unwind/classify/ensemble.py``)."""

from __future__ import annotations

from unwind.classify.ensemble import classify_tool
from unwind.types import EnvironmentDescriptor, ReversibilityClass, ToolSpec


def _spec(
    name: str, input_schema: dict | None = None, output_schema: dict | None = None
) -> ToolSpec:
    return ToolSpec(
        server="s", name=name, input_schema=input_schema or {}, output_schema=output_schema
    )


class TestRepresentativeTools:
    def test_read_is_r0(self) -> None:
        cls = classify_tool(_spec("get_file", {"properties": {"path": {"type": "string"}}}))
        assert cls.rev_class == ReversibilityClass.R0

    def test_create_is_r2_default_env(self) -> None:
        cls = classify_tool(_spec("create_page", {"properties": {"title": {"type": "string"}}}))
        assert cls.rev_class == ReversibilityClass.R2

    def test_send_is_r3(self) -> None:
        cls = classify_tool(_spec("send_email"))
        assert cls.rev_class == ReversibilityClass.R3


class TestDangerFlagHardening:
    def test_force_flag_hardens_to_r4(self) -> None:
        # A create with a "force"/"purge" flag is hardened up to R4 by schema.
        spec = _spec(
            "create_thing",
            {"properties": {"name": {"type": "string"}, "purge": {"type": "boolean"}}},
        )
        cls = classify_tool(spec)
        assert cls.rev_class == ReversibilityClass.R4
        assert cls.confidence >= 0.8

    def test_update_with_force_hardened(self) -> None:
        spec = _spec(
            "update_record",
            {"properties": {"id": {"type": "string"}, "force": {"type": "boolean"}}},
        )
        cls = classify_tool(spec)
        assert cls.rev_class == ReversibilityClass.R4


class TestBulkNudging:
    def test_bulk_selector_raises_confidence(self) -> None:
        plain = classify_tool(_spec("delete_records", {"properties": {"id": {"type": "string"}}}))
        bulk = classify_tool(
            _spec("delete_records", {"properties": {"filter": {"type": "string"}}})
        )
        # Bulk present on an R2+ tool nudges confidence upward for escalation.
        assert bulk.confidence >= plain.confidence


class TestEnvironmentRelativity:
    def test_delete_r4_versionless(self) -> None:
        spec = _spec("delete_file", {"properties": {"path": {"type": "string"}}})
        env = EnvironmentDescriptor(versioned=False, has_trash=False)
        assert classify_tool(spec, env).rev_class == ReversibilityClass.R4

    def test_delete_r1_versioned(self) -> None:
        spec = _spec("delete_file", {"properties": {"path": {"type": "string"}}})
        env = EnvironmentDescriptor(versioned=True)
        assert classify_tool(spec, env).rev_class == ReversibilityClass.R1


class TestWithLlm:
    def test_use_llm_deterministic_and_consistent(self) -> None:
        spec = _spec("get_file", {"properties": {"path": {"type": "string"}}})
        a = classify_tool(spec, use_llm=True)
        b = classify_tool(spec, use_llm=True)
        assert a.rev_class == b.rev_class == ReversibilityClass.R0
        assert a.confidence == b.confidence

    def test_use_llm_fail_safe_takes_more_irreversible(self) -> None:
        # LLM fusion takes the MORE irreversible of the two votes; it may only
        # raise (or hold) the class, never lower a read below R0.
        spec = _spec("delete_page", {"properties": {"id": {"type": "string"}}})
        lex_only = classify_tool(spec)
        with_llm = classify_tool(spec, use_llm=True)
        assert with_llm.rev_class >= lex_only.rev_class

    def test_use_llm_signals_present(self) -> None:
        cls = classify_tool(_spec("create_page"), use_llm=True)
        assert "llm" in cls.signals
