"""Invariant + behaviour tests for WITNESS (the discharged-refutation method).

Pins the safety invariants I1–I5 from the algorithm: monotone hardening, the
environment ceiling, measured-not-asserted fidelity, fail-safe on probe errors,
and discharge-not-assertion. A regression on any of these breaks the method's
central guarantee (CER <= baseline by construction), so they gate CI.
"""

from __future__ import annotations

import pytest

from unwind.classify.discharge import (
    DeterministicProposer,
    discharge_schema_graph,
    make_executable_discharge,
)
from unwind.classify.witness import (
    Verdict,
    Witness,
    WitnessType,
    classify_witness,
)
from unwind.synthesize.plan import synthesize_plan
from unwind.types import EnvironmentDescriptor, ReversibilityClass, ToolSpec

_ID_IN = {"properties": {"id": {"type": "string"}}}
_ID_OUT = {"properties": {"id": {"type": "string"}}}


def _spec(name: str, ins: dict | None = None, outs: dict | None = None) -> ToolSpec:
    return ToolSpec(server="s", name=name, input_schema=ins or {}, output_schema=outs)


PROP = DeterministicProposer()


def _classify(spec, toolset, env):
    return classify_witness(spec, toolset, env, PROP, discharge_schema_graph)


class TestMonotoneHardening:
    """I1: the witness voter can only raise the class, never lower it."""

    @pytest.mark.parametrize(
        "name",
        ["write_file", "create_page", "update_record", "send_email", "delete_row", "post_message"],
    )
    def test_never_softens(self, name: str) -> None:
        specs = [
            _spec(name, _ID_IN, _ID_OUT),
            _spec("get_thing", _ID_IN, _ID_OUT),
            _spec("delete_thing", _ID_IN),
        ]
        for env in (
            EnvironmentDescriptor(),
            EnvironmentDescriptor(versioned=True),
            EnvironmentDescriptor(has_trash=True),
            EnvironmentDescriptor(external_side_effects=True),
        ):
            r = _classify(specs[0], specs, env)
            assert r.classification.rev_class >= r.base_class, "I1: witness softened the class"


class TestEnvCeiling:
    """I2: the environment descriptor is a hard ceiling the witness cannot beat."""

    def test_env_r4_is_a_floor(self) -> None:
        # delete on a versionless store is R4 by env; witness cannot demote it.
        spec = _spec("delete_record", _ID_IN)
        r = _classify(spec, [spec], EnvironmentDescriptor(versioned=False, has_trash=False))
        assert r.classification.rev_class >= r.env_class
        assert r.classification.rev_class == ReversibilityClass.R4


class TestDischargeFunctions:
    """The deterministic schema-graph discharge confirms/refutes correctly."""

    def test_externality_confirmed_on_external_env(self) -> None:
        spec = _spec("create_ticket", _ID_IN, _ID_OUT)
        plan = synthesize_plan(
            spec, [spec, _spec("delete_ticket", _ID_IN)], EnvironmentDescriptor()
        )
        v, r = discharge_schema_graph(
            Witness(WitnessType.EXTERNALITY),
            spec,
            plan,
            [spec],
            EnvironmentDescriptor(external_side_effects=True),
        )
        assert v == Verdict.CONFIRMED and r > 0

    def test_externality_refuted_when_internal(self) -> None:
        spec = _spec("update_record", _ID_IN, _ID_OUT)
        plan = synthesize_plan(spec, [spec], EnvironmentDescriptor())
        v, _ = discharge_schema_graph(
            Witness(WitnessType.EXTERNALITY), spec, plan, [spec], EnvironmentDescriptor()
        )
        assert v == Verdict.REFUTED

    def test_half_life_confirmed_on_window_description(self) -> None:
        spec = _spec("hold_inventory", _ID_IN)
        spec.description = "Places a hold; the hold expires after a retention window."
        plan = synthesize_plan(spec, [spec], EnvironmentDescriptor())
        v, r = discharge_schema_graph(
            Witness(WitnessType.HALF_LIFE), spec, plan, [spec], EnvironmentDescriptor()
        )
        assert v == Verdict.CONFIRMED and r > 0


class TestConfirmedWitnessesFloorClass:
    def test_witness_hardens_r2_via_discovered_observation_channel(self) -> None:
        # A create (base R2, ordinary env) whose effect is observable via a
        # co-located audit/activity feed the ensemble+env descriptor cannot see.
        # WITNESS discovers the channel and hardens R2 -> R3 — signal beyond the
        # environment descriptor, which is the whole point of the method.
        spec = _spec("create_ticket", _ID_IN, _ID_OUT)
        toolset = [
            spec,
            _spec("delete_ticket", _ID_IN),
            _spec("get_activity_feed", {}, {"properties": {"events": {"type": "array"}}}),
        ]
        env = EnvironmentDescriptor()  # NO external_side_effects flag set
        r = classify_witness(spec, toolset, env, PROP, discharge_schema_graph)
        assert r.base_class == ReversibilityClass.R2  # env did NOT already escalate it
        assert any(w.type == WitnessType.EXTERNALITY for w in r.confirmed)
        assert r.classification.rev_class >= ReversibilityClass.R3

    def test_r0_is_never_probed(self) -> None:
        spec = _spec("read_file", {"properties": {"path": {"type": "string"}}})
        r = _classify(spec, [spec], EnvironmentDescriptor())
        assert r.classification.rev_class == ReversibilityClass.R0
        assert r.evidence_score == 0.0
        assert r.proposed == []


class TestFailSafe:
    """I4: a broken proposer or a probe exception must not crash and must escalate."""

    def test_broken_proposer_does_not_crash(self) -> None:
        class Boom:
            def propose(self, *a, **k):  # type: ignore[no-untyped-def]
                raise RuntimeError("boom")

        spec = _spec("mutate_thing", _ID_IN)
        r = classify_witness(spec, [spec], EnvironmentDescriptor(), Boom(), discharge_schema_graph)
        # no witnesses proposed → falls back to fail-safe escalation signal
        assert r.classification.rev_class >= r.base_class

    def test_probe_exception_fails_safe(self) -> None:
        def boom_discharge(*a, **k):  # type: ignore[no-untyped-def]
            raise RuntimeError("probe blew up")

        spec = _spec("create_thing", _ID_IN)
        r = classify_witness(
            spec,
            [spec, _spec("delete_thing", _ID_IN)],
            EnvironmentDescriptor(),
            PROP,
            boom_discharge,
        )
        # exceptions are caught → treated as UNTESTABLE → evidence stays high
        assert r.classification.rev_class >= r.base_class
        assert r.evidence_score >= 0.5


class TestExecutableDischarge:
    """The env-differential probe confirms MISSING_SNAPSHOT only where it's real."""

    def test_differential_confirms_irreversible_on_versionless(self) -> None:
        # Model a delete: versionless backend loses the row; versioned restores it.
        vl_state = {"row": "data"}
        ver_state = {"row": "data"}

        def vl_exec(tool, args):
            if tool == "delete_row":
                vl_state.pop("row", None)
            return {}

        def ver_exec(tool, args):
            if tool == "delete_row":
                ver_state["_bak"] = ver_state.get("row")
                ver_state.pop("row", None)
            elif tool == "restore_row":
                ver_state["row"] = ver_state.pop("_bak", None)
            return {}

        # versionless has no restore; give the plan a (broken-on-vl) inverse.
        spec = _spec("delete_row", _ID_IN)
        plan = synthesize_plan(spec, [spec, _spec("restore_row", _ID_IN)], EnvironmentDescriptor())
        disc = make_executable_discharge(
            real=(vl_exec, lambda: dict(vl_state)),
            paired=(ver_exec, lambda: {k: v for k, v in ver_state.items() if k != "_bak"}),
        )
        v, r = disc(
            Witness(WitnessType.MISSING_SNAPSHOT_CASCADE),
            spec,
            plan,
            [spec],
            EnvironmentDescriptor(),
        )
        assert v == Verdict.CONFIRMED and r == 1.0
