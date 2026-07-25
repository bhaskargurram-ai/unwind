"""Unit tests for environment-relative re-derivation (``unwind/classify/environment.py``)."""

from __future__ import annotations

from unwind.classify.environment import rederive
from unwind.types import (
    Classification,
    EffectVerb,
    EnvironmentDescriptor,
    Externality,
    ReversibilityClass,
)


def _delete_cls(rc: ReversibilityClass = ReversibilityClass.R4) -> Classification:
    return Classification(
        rev_class=rc, confidence=0.75, effect_verb=EffectVerb.DELETE, entity="file"
    )


class TestDeleteRederivation:
    def test_delete_r4_on_versionless_stays_r4(self) -> None:
        env = EnvironmentDescriptor(versioned=False, has_trash=False, soft_delete=False)
        out = rederive(_delete_cls(), env)
        assert out.rev_class == ReversibilityClass.R4

    def test_delete_versioned_becomes_r1(self) -> None:
        env = EnvironmentDescriptor(versioned=True)
        out = rederive(_delete_cls(), env)
        assert out.rev_class == ReversibilityClass.R1

    def test_delete_has_trash_becomes_r2(self) -> None:
        env = EnvironmentDescriptor(has_trash=True)
        out = rederive(_delete_cls(), env)
        assert out.rev_class == ReversibilityClass.R2

    def test_delete_soft_delete_becomes_r2(self) -> None:
        env = EnvironmentDescriptor(soft_delete=True)
        out = rederive(_delete_cls(), env)
        assert out.rev_class == ReversibilityClass.R2


class TestSnapshotDegradation:
    def test_no_snapshot_no_recovery_hardens_update_to_r4(self) -> None:
        # A destructive overwrite with no capturable pre-state AND no version
        # history / trash has no more inverse than a hard delete → R4 (the
        # independent env-rule contribution; closes the write_file-versionless miss).
        cls = Classification(
            rev_class=ReversibilityClass.R1, confidence=0.5, effect_verb=EffectVerb.UPDATE
        )
        env = EnvironmentDescriptor(supports_snapshot=False)
        assert rederive(cls, env).rev_class == ReversibilityClass.R4

    def test_no_snapshot_with_trash_degrades_r1_to_r2(self) -> None:
        # With trash recovery present, the R4 hardening does NOT fire; the missing
        # snapshot only blocks R1, degrading to R2.
        cls = Classification(
            rev_class=ReversibilityClass.R1, confidence=0.5, effect_verb=EffectVerb.UPDATE
        )
        env = EnvironmentDescriptor(supports_snapshot=False, has_trash=True)
        assert rederive(cls, env).rev_class == ReversibilityClass.R2

    def test_snapshot_ok_keeps_r1(self) -> None:
        cls = Classification(
            rev_class=ReversibilityClass.R1, confidence=0.5, effect_verb=EffectVerb.UPDATE
        )
        env = EnvironmentDescriptor(supports_snapshot=True)
        out = rederive(cls, env)
        assert out.rev_class == ReversibilityClass.R1


class TestExternalSideEffects:
    def test_external_side_effects_degrade_r2_to_r3(self) -> None:
        cls = Classification(
            rev_class=ReversibilityClass.R2, confidence=0.55, effect_verb=EffectVerb.CREATE
        )
        env = EnvironmentDescriptor(external_side_effects=True)
        out = rederive(cls, env)
        assert out.rev_class == ReversibilityClass.R3
        assert out.externality == Externality.EXTERNAL

    def test_external_side_effects_does_not_touch_r1(self) -> None:
        cls = Classification(
            rev_class=ReversibilityClass.R1, confidence=0.5, effect_verb=EffectVerb.UPDATE
        )
        env = EnvironmentDescriptor(external_side_effects=True)
        out = rederive(cls, env)
        assert out.rev_class == ReversibilityClass.R1


class TestNoOp:
    def test_default_env_r0_unchanged(self) -> None:
        cls = Classification(
            rev_class=ReversibilityClass.R0, confidence=0.9, effect_verb=EffectVerb.READ
        )
        out = rederive(cls, EnvironmentDescriptor())
        # No notes, no change -> same object returned.
        assert out is cls

    def test_rationale_records_env_note(self) -> None:
        out = rederive(_delete_cls(), EnvironmentDescriptor(versioned=True))
        assert "versioned" in out.rationale
        assert "environment" in out.signals
