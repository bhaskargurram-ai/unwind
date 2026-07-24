"""Unit tests for the core typed protocol objects (``unwind/types.py``)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from unwind.types import (
    Classification,
    EffectVerb,
    EnvironmentDescriptor,
    FidelityGrade,
    ReversibilityClass,
    UndoEntry,
    UndoStatus,
)


class TestReversibilityClass:
    def test_ordinal_ordering(self) -> None:
        assert ReversibilityClass.R0 < ReversibilityClass.R4
        assert ReversibilityClass.R2 < ReversibilityClass.R3
        assert ReversibilityClass.R4 > ReversibilityClass.R1
        # IntEnum members compare as their int values.
        assert int(ReversibilityClass.R3) == 3

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("R3", ReversibilityClass.R3),
            ("r0", ReversibilityClass.R0),
            (3, ReversibilityClass.R3),
            ("irreversible", ReversibilityClass.R4),
            ("nullipotent", ReversibilityClass.R0),
            ("self-reversible", ReversibilityClass.R1),
            ("compensable", ReversibilityClass.R2),
            ("mitigable-only", ReversibilityClass.R3),
            (ReversibilityClass.R2, ReversibilityClass.R2),
        ],
    )
    def test_parse(self, value: object, expected: ReversibilityClass) -> None:
        assert ReversibilityClass.parse(value) is expected  # type: ignore[arg-type]

    def test_parse_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            ReversibilityClass.parse("not-a-class")

    def test_labels(self) -> None:
        assert ReversibilityClass.R0.label == "nullipotent"
        assert ReversibilityClass.R4.label == "irreversible"

    def test_is_mutating(self) -> None:
        assert ReversibilityClass.R0.is_mutating is False
        for rc in (
            ReversibilityClass.R1,
            ReversibilityClass.R2,
            ReversibilityClass.R3,
            ReversibilityClass.R4,
        ):
            assert rc.is_mutating is True

    def test_needs_confirmation_by_default(self) -> None:
        assert ReversibilityClass.R0.needs_confirmation_by_default is False
        assert ReversibilityClass.R2.needs_confirmation_by_default is False
        assert ReversibilityClass.R3.needs_confirmation_by_default is True
        assert ReversibilityClass.R4.needs_confirmation_by_default is True


class TestFidelityGrade:
    def test_ordering(self) -> None:
        assert FidelityGrade.EXACT > FidelityGrade.FAILED
        assert FidelityGrade.SEMANTIC > FidelityGrade.ACCEPTABLE_APPROXIMATION
        assert FidelityGrade.ACCEPTABLE_APPROXIMATION > FidelityGrade.FAILED

    def test_labels(self) -> None:
        assert FidelityGrade.EXACT.label == "exact"
        assert FidelityGrade.FAILED.label == "failed"
        assert FidelityGrade.ACCEPTABLE_APPROXIMATION.label == "acceptable-approximation"
        assert FidelityGrade.SEMANTIC.label == "semantic"


class TestClassificationDegraded:
    def test_degrade_bumps_one_step(self) -> None:
        c = Classification(rev_class=ReversibilityClass.R2, confidence=0.5)
        d = c.degraded("weak evidence")
        assert d.rev_class == ReversibilityClass.R3
        assert "degraded: weak evidence" in d.rationale
        # Original is untouched (model_copy).
        assert c.rev_class == ReversibilityClass.R2

    def test_degrade_caps_at_r4(self) -> None:
        c = Classification(rev_class=ReversibilityClass.R4, confidence=0.9)
        d = c.degraded("already max")
        assert d.rev_class == ReversibilityClass.R4

    def test_degrade_r3_to_r4(self) -> None:
        c = Classification(rev_class=ReversibilityClass.R3, confidence=0.7)
        assert c.degraded("x").rev_class == ReversibilityClass.R4


class TestEnvironmentDescriptor:
    def test_capability_key_is_stable_and_distinguishes(self) -> None:
        a = EnvironmentDescriptor(versioned=True)
        b = EnvironmentDescriptor(versioned=True)
        c = EnvironmentDescriptor(versioned=False)
        assert a.capability_key() == b.capability_key()
        assert a.capability_key() != c.capability_key()

    def test_capability_key_encodes_all_flags(self) -> None:
        env = EnvironmentDescriptor(
            versioned=True,
            has_trash=True,
            soft_delete=False,
            retention_window_s=3600.0,
            supports_snapshot=False,
            external_side_effects=True,
        )
        key = env.capability_key()
        assert "v=1" in key
        assert "t=1" in key
        assert "s=0" in key
        assert "r=3600.0" in key
        assert "snap=0" in key
        assert "ext=1" in key

    def test_frozen(self) -> None:
        env = EnvironmentDescriptor()
        with pytest.raises(ValidationError):
            env.versioned = True  # type: ignore[misc]


class TestUndoEntry:
    def test_is_expired_no_expiry(self) -> None:
        entry = UndoEntry(id="a", server="s", tool="t", expires_at=None)
        assert entry.is_expired(at=10_000.0) is False

    def test_is_expired_at_boundary_and_past(self) -> None:
        entry = UndoEntry(id="a", server="s", tool="t", expires_at=100.0)
        assert entry.is_expired(at=99.0) is False
        assert entry.is_expired(at=100.0) is True  # >= boundary is expired
        assert entry.is_expired(at=200.0) is True

    def test_defaults(self) -> None:
        entry = UndoEntry(id="a", server="s", tool="t")
        assert entry.status == UndoStatus.ACTIVE
        assert entry.rev_class == ReversibilityClass.R4  # fail-safe default
        assert isinstance(entry.ts, float)
        assert entry.args == {}

    def test_effect_verb_enum_values(self) -> None:
        assert EffectVerb.DELETE.value == "delete"
