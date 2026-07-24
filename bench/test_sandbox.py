"""Tests for the live-validation sandbox: mock backends + fidelity grading (§6, §8)."""

from __future__ import annotations

import pytest

from bench.sandbox.harness import BackendCaller, grade_fidelity, run_forward_inverse
from bench.sandbox.mock_servers.comms_server import RECALL_HALF_LIFE_S, CommsBackend
from bench.sandbox.mock_servers.payments_server import (
    DEFAULT_VOID_WINDOW_S,
    PROCESSING_FEE_CENTS,
    PaymentsBackend,
)
from unwind.types import FidelityGrade


# --------------------------------------------------------------------------
# Fidelity grading ladder (§6 Stage 5) — hand-constructed pre/post states.
# --------------------------------------------------------------------------
def test_grade_exact() -> None:
    r = grade_fidelity(
        {"balance_cents": 100},
        {"balance_cents": 100},
        key_fields=["balance_cents"],
        residue=[],
        inverse_ok=True,
    )
    assert r.grade == FidelityGrade.EXACT
    assert r.changed_fields == []


def test_grade_semantic_when_nonkey_field_drifts() -> None:
    # key field restored, no residue, but a non-key field (updated_at) changed.
    r = grade_fidelity(
        {"balance_cents": 100, "updated_at": 1},
        {"balance_cents": 100, "updated_at": 2},
        key_fields=["balance_cents"],
        residue=[],
        inverse_ok=True,
    )
    assert r.grade == FidelityGrade.SEMANTIC


def test_grade_acceptable_approximation_when_residue_present() -> None:
    r = grade_fidelity(
        {"balance_cents": 100},
        {"balance_cents": 100},
        key_fields=["balance_cents"],
        residue=["processing_fee_not_returned"],
        inverse_ok=True,
    )
    assert r.grade == FidelityGrade.ACCEPTABLE_APPROXIMATION


def test_grade_failed_when_key_field_differs() -> None:
    r = grade_fidelity(
        {"balance_cents": 100},
        {"balance_cents": 40},
        key_fields=["balance_cents"],
        residue=[],
        inverse_ok=True,
    )
    assert r.grade == FidelityGrade.FAILED


def test_grade_failed_when_inverse_errored() -> None:
    r = grade_fidelity(
        {"balance_cents": 100},
        {"balance_cents": 100},
        key_fields=["balance_cents"],
        residue=[],
        inverse_ok=False,
    )
    assert r.grade == FidelityGrade.FAILED


def test_grade_ordinal_ladder_is_monotone() -> None:
    # exact > semantic > acceptable-approximation > failed (IntEnum ordinality).
    assert (
        FidelityGrade.EXACT
        > FidelityGrade.SEMANTIC
        > FidelityGrade.ACCEPTABLE_APPROXIMATION
        > FidelityGrade.FAILED
    )


# --------------------------------------------------------------------------
# Payments: charge -> void (clean inverse, pre-settlement) = semantic restore.
# --------------------------------------------------------------------------
def test_payments_void_within_window_restores_balance() -> None:
    clock = [1000.0]
    be = PaymentsBackend(clock=lambda: clock[0])
    caller = BackendCaller(be)
    report = run_forward_inverse(
        caller,
        pre_read="get_balance",
        pre_read_args={"account": "a"},
        forward="charge",
        forward_args={"account": "a", "amount_cents": 500},
        inverse="void",
        inverse_args_fn=lambda pre, fwd: {"charge_id": fwd["id"]},
        key_fields=["balance_cents"],
    )
    # Balance restored; void leaves an authorization-hold notification residue ->
    # capped at acceptable-approximation.
    assert report.executed_ok is True
    assert report.grade == FidelityGrade.ACCEPTABLE_APPROXIMATION
    assert be.get_balance("a")["balance_cents"] == 0


def test_payments_void_after_settlement_fails() -> None:
    clock = [1000.0]
    be = PaymentsBackend(clock=lambda: clock[0])
    caller = BackendCaller(be)

    def advance_then_void(pre, fwd):  # type: ignore[no-untyped-def]
        clock[0] += DEFAULT_VOID_WINDOW_S + 1.0  # settle before the void runs
        return {"charge_id": fwd["id"]}

    report = run_forward_inverse(
        caller,
        pre_read="get_balance",
        pre_read_args={"account": "a"},
        forward="charge",
        forward_args={"account": "a", "amount_cents": 500},
        inverse="void",
        inverse_args_fn=advance_then_void,
        key_fields=["balance_cents"],
    )
    # Void fails post-settlement -> balance NOT restored -> failed.
    assert report.executed_ok is False
    assert report.grade == FidelityGrade.FAILED
    assert be.get_balance("a")["balance_cents"] == -500


def test_payments_refund_is_partial_compensation_with_residue() -> None:
    clock = [1000.0]
    be = PaymentsBackend(clock=lambda: clock[0])
    res = be.charge("a", 500)
    refund = be.refund(res["id"])
    assert refund["refunded"] is True
    # Balance restored, but the fee is retained and notifications fired -> residue.
    assert be.get_balance("a")["balance_cents"] == 0
    assert refund["fee_retained_cents"] == PROCESSING_FEE_CENTS
    assert "processing_fee_not_returned" in refund["residue"]


# --------------------------------------------------------------------------
# Comms: retract within / outside the half-life; read closes the window.
# --------------------------------------------------------------------------
def test_comms_retract_within_half_life_succeeds() -> None:
    clock = [0.0]
    be = CommsBackend(clock=lambda: clock[0])
    sent = be.send_email("x@y.com", "hi")
    clock[0] += RECALL_HALF_LIFE_S - 1.0  # still inside the window
    out = be.retract_message(sent["id"])
    assert out["retracted"] is True
    # Even a successful retraction leaves a delivery-notification residue.
    assert "delivery_notification_fired" in out["residue"]


def test_comms_retract_after_half_life_fails() -> None:
    clock = [0.0]
    be = CommsBackend(clock=lambda: clock[0])
    sent = be.send_email("x@y.com", "hi")
    clock[0] += RECALL_HALF_LIFE_S + 1.0  # window elapsed
    out = be.retract_message(sent["id"])
    assert out["retracted"] is False
    assert out["reason"] == "recall_window_elapsed"


def test_comms_retract_after_read_fails_with_extra_residue() -> None:
    clock = [0.0]
    be = CommsBackend(clock=lambda: clock[0])
    sent = be.send_email("x@y.com", "hi")
    be.mark_read(sent["id"])  # recipient read it -> irreversible-ish
    out = be.retract_message(sent["id"])
    assert out["retracted"] is False
    assert "recipient_already_read" in out["residue"]


def test_comms_send_reports_half_life() -> None:
    be = CommsBackend(clock=lambda: 0.0)
    assert be.send_email("x@y.com", "hi")["recall_half_life_s"] == RECALL_HALF_LIFE_S


def test_backend_caller_wraps_nonmapping_results() -> None:
    be = CommsBackend(clock=lambda: 0.0)
    caller = BackendCaller(be)
    out = caller.call("list_messages")
    # list_messages returns a list -> wrapped under "result".
    assert "result" in out


def test_seed_labels_are_illustrative_and_well_formed() -> None:
    # The seed labels file must parse as LabelRecord rows and be clearly marked
    # illustrative (not claimed corpus results).
    from pathlib import Path

    from bench.labeling.schema import LabelRecord

    path = Path(__file__).resolve().parent / "labeling" / "seed_labels.jsonl"
    rows = [
        LabelRecord.model_validate_json(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]
    assert len(rows) >= 25  # ~30 illustrative seed labels
    assert all("ILLUSTRATIVE SEED" in r.rationale for r in rows)
    # Spans multiple domains/servers.
    assert len({r.server for r in rows}) >= 6
    # Includes the environment-relativity pair (same tool, different class).
    write_file_rows = [r for r in rows if r.tool == "write_file"]
    assert {int(r.rev_class) for r in write_file_rows} == {1, 4}


def test_grade_failed_takes_priority_over_residue() -> None:
    # A key-field mismatch is FAILED even if residue is also present.
    r = grade_fidelity(
        {"balance_cents": 100},
        {"balance_cents": 40},
        key_fields=["balance_cents"],
        residue=["something"],
        inverse_ok=True,
    )
    assert r.grade == FidelityGrade.FAILED


def test_void_window_is_positive() -> None:
    assert DEFAULT_VOID_WINDOW_S > 0
    with pytest.raises(KeyError):
        # get_charge on an unknown id raises (fail-safe: no silent success).
        PaymentsBackend(clock=lambda: 0.0).get_charge("missing")
