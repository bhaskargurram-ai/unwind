"""Validation tests for the destructive scenario traces (§8.E)."""

from __future__ import annotations

from bench.scenarios.loader import SCENARIO_DIR, load_all_scenarios, load_scenario
from unwind.types import Decision, ReversibilityClass


def test_all_scenarios_load_and_validate() -> None:
    scenarios = load_all_scenarios()
    ids = {s.id for s in scenarios}
    # The three committed scenarios must be present.
    assert {"demo-destructive", "bulk-email-deletion", "permission-grant-revoke"} <= ids


def test_demo_scenario_shape() -> None:
    demo = load_scenario(SCENARIO_DIR / "demo_destructive.json")
    assert demo.id == "demo-destructive"
    assert len(demo.steps) == 4
    # Exactly one step is the interruption (the external send_email).
    interrupts = [s for s in demo.steps if s.expected_decision == Decision.ELICIT_CONFIRMATION]
    assert len(interrupts) == 1
    assert interrupts[0].tool == "send_email"
    # Honest undo contract: 3 compensable steps are undoable, the email is not.
    assert demo.expect_undoable_count == 3


def test_destructive_steps_are_never_auto_allowed_silently() -> None:
    # Fail-safe invariant (golden rule #2): a truly irreversible (R4) step must
    # never carry a plain auto_allow / auto_allow_logged decision in ground truth.
    for scenario in load_all_scenarios():
        for step in scenario.steps:
            if step.expected_rev_class == ReversibilityClass.R4:
                assert step.expected_decision in {
                    Decision.ELICIT_CONFIRMATION,
                    Decision.BLOCK,
                }, f"{scenario.id}/{step.tool} R4 must escalate"


def test_bulk_delete_blast_radius_escalates_despite_compensable_class() -> None:
    scen = load_scenario(SCENARIO_DIR / "bulk_email_deletion.json")
    bulk = next(s for s in scen.steps if s.tool == "bulk_delete_messages")
    # Class is compensable (R2) but the step still escalates on blast radius.
    assert bulk.expected_rev_class == ReversibilityClass.R2
    assert bulk.expected_decision == Decision.ELICIT_CONFIRMATION
    assert bulk.is_destructive


def test_environment_relativity_across_scenarios() -> None:
    # delete_bucket / drop_table is R2 in the versioned demo env but R4 in the
    # versionless cloud env — validates §5.2 environment-relativity in the corpus.
    demo = load_scenario(SCENARIO_DIR / "demo_destructive.json")
    perm = load_scenario(SCENARIO_DIR / "permission_grant_revoke.json")
    drop = next(s for s in demo.steps if s.tool == "drop_table")
    delete_bucket = next(s for s in perm.steps if s.tool == "delete_bucket")
    assert demo.environment.versioned is True
    assert perm.environment.versioned is False
    assert drop.expected_rev_class == ReversibilityClass.R2
    assert delete_bucket.expected_rev_class == ReversibilityClass.R4


def test_destructive_steps_helper() -> None:
    perm = load_scenario(SCENARIO_DIR / "permission_grant_revoke.json")
    assert len(perm.destructive_steps) == 2
