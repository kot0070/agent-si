"""K13 ExecutionRun state-machine tests (Manifest sections 14, 14A).

Covers: 15-step creation transaction + gate (no execution before step 13),
ALLOWED table + TERMINAL set, CAS, RUN_STATUS_TERMINATION_COMPATIBILITY,
pre-run failure disposition per cause, and the audit disposition map.
Shared names come ONLY from iface.frozen_manifest.manifest (M1a-owned).
"""

from dataclasses import FrozenInstanceError
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from agent_si.state_machines import run_machine
from iface.frozen_manifest import manifest


def _skeleton(**overrides):
    args = dict(
        run_id="run-1",
        project_id="P1",
        task_id="T1",
        contract_hash="h-active",
        run_sequence=1,
    )
    args.update(overrides)
    return run_machine.create_run(**args)


def _drive(run, *edges):
    for to_status, reason in edges:
        run = run_machine.transition_run(
            run,
            expected_status=run.status,
            expected_version=0,
            to_status=to_status,
            termination_reason=reason,
            at="t",
        )
    return run


def _run_at(status, reason, run_id="run-x"):
    name = status if isinstance(status, str) else status.value
    prefix = {
        "RUNNING": [],
        "VERIFYING": [("RUNNING", "NONE")],
        "AUDITING": [("RUNNING", "NONE"), ("VERIFYING", "NONE")],
        "REWORK_REQUIRED": [
            ("RUNNING", "NONE"),
            ("VERIFYING", "NONE"),
            ("AUDITING", "NONE"),
        ],
        "SUCCEEDED": [
            ("RUNNING", "NONE"),
            ("VERIFYING", "NONE"),
            ("AUDITING", "NONE"),
        ],
        "FAILED": [("RUNNING", "NONE")],
        "CANCELLED": [],
        "SUPERSEDED": [],
    }[name]
    return _drive(_drive(_skeleton(run_id=run_id), *prefix), (name, reason))


def test_manifest_pin_and_shared_names():
    assert manifest.MANIFEST_SHA256 == "f256bab4d31be3cd9e86c22a1bdcef90b08ad62500a8eca2051705cc0a9b0690"
    assert manifest.verify_manifest(ROOT / "RECORDS" / "day0" / "K13_MANIFEST.md") is True
    assert run_machine.manifest is manifest
    assert run_machine.TERMINAL is manifest.RUN_TERMINAL
    assert run_machine.ALLOWED is manifest.RUN_ALLOWED
    assert set(run_machine.TERMINAL) == {
        manifest.ExecutionRunStatus.SUCCEEDED,
        manifest.ExecutionRunStatus.FAILED,
        manifest.ExecutionRunStatus.CANCELLED,
        manifest.ExecutionRunStatus.SUPERSEDED,
    }


def test_skeleton_defaults_created_none_nulls():
    run = _skeleton()
    assert run.status == manifest.ExecutionRunStatus.CREATED
    assert run.termination_reason == manifest.RunTerminationReason.NONE
    assert run.contract_hash == "h-active"
    assert run.routing_decision_ref is None
    assert run.route is None
    assert run.started_at is None
    assert run.ended_at is None
    assert run.revision_no == 0
    assert not hasattr(run, "state_version")


def test_run_frozen_one_hash_per_life():
    run = _skeleton()
    with pytest.raises(FrozenInstanceError):
        run.status = manifest.ExecutionRunStatus.RUNNING
    with pytest.raises(FrozenInstanceError):
        run.contract_hash = "h-other"
    moved = run_machine.transition_run(
        run,
        expected_status="CREATED",
        expected_version=0,
        to_status="RUNNING",
        termination_reason="NONE",
        at="t1",
    )
    assert moved.contract_hash == run.contract_hash == "h-active"
    assert moved.started_at == "t1"
    assert run.status == manifest.ExecutionRunStatus.CREATED


def test_run_sequence_unique_atomic():
    first = _skeleton(run_id="run-1", run_sequence=1)
    assert first.run_sequence == 1
    assert run_machine.allocate_run_sequence([1, 2, 3]) == 4
    assert run_machine.allocate_run_sequence([]) == 1
    with pytest.raises(run_machine.DuplicateRunSequenceError):
        _skeleton(run_id="run-2", run_sequence=1, existing_sequences=[1])
    with pytest.raises(run_machine.DuplicateRunSequenceError):
        run_machine.create_run(
            run_id="run-3",
            project_id="P1",
            task_id="T1",
            contract_hash="h-active",
            run_sequence=2,
            existing_sequences=[1, 2],
        )
    with pytest.raises(ValueError):
        run_machine.create_run(
            run_id="run-4",
            project_id="P1",
            task_id="T1",
            contract_hash="",
            run_sequence=9,
        )


def test_revision_no_correction_only():
    assert run_machine.derive_revision_no("INITIAL_EXECUTION", 0) == 0
    assert run_machine.derive_revision_no("VERIFICATION_REWORK", 2) == 3
    assert run_machine.derive_revision_no("AUDIT_REWORK", 2) == 3
    assert run_machine.derive_revision_no("AMENDMENT_RESTART", 2) == 2
    assert run_machine.derive_revision_no("FALLBACK_REROUTE", 2) == 2
    with pytest.raises(ValueError):
        run_machine.derive_revision_no("NOPE", 0)
    src = _skeleton(run_sequence=1)
    rework = _skeleton(
        run_id="run-2",
        run_sequence=2,
        existing_sequences=[1],
        creation_reason="VERIFICATION_REWORK",
        source_run=src,
    )
    assert rework.revision_no == 1
    reroute = _skeleton(
        run_id="run-3",
        run_sequence=3,
        existing_sequences=[1, 2],
        creation_reason="FALLBACK_REROUTE",
        source_run=rework,
    )
    assert reroute.revision_no == 1
    with pytest.raises(ValueError):
        _skeleton(run_id="run-x", run_sequence=9, creation_reason="AUDIT_REWORK")


def test_creation_steps_frozen_order_and_gate():
    assert len(run_machine.CREATION_STEPS) == 15
    assert run_machine.CREATION_STEPS[12] == "ATTEMPT_EXECUTION_GATE"
    assert run_machine.CREATION_STEPS[13] == "START_RUNNING"
    assert run_machine.CREATION_STEPS[14] == "PRE_RUN_FAILURE_DISPOSITION"
    state = run_machine.CreationState()
    with pytest.raises(run_machine.ExecutionBeforeGateError):
        run_machine.note_execution(state)
    with pytest.raises(run_machine.CreationOrderError):
        run_machine.advance_creation(state, "START_RUNNING")
    for step in run_machine.CREATION_STEPS[:13]:
        state = run_machine.advance_creation(state, step)
    with pytest.raises(run_machine.ExecutionBeforeGateError):
        run_machine.note_execution(state)
    gated = run_machine.pass_attempt_gate(state)
    assert gated.gate_passed is True
    noted = run_machine.note_execution(gated)
    assert noted.execution_noted is True
    with pytest.raises(run_machine.GateNotPassedError):
        run_machine.pass_attempt_gate(run_machine.CreationState())
    with pytest.raises(run_machine.CreationOrderError):
        run_machine.advance_creation(gated, "ATTEMPT_EXECUTION_GATE")


def test_no_execution_before_gate_on_start():
    run = _skeleton()
    state = run_machine.CreationState()
    with pytest.raises(run_machine.GateNotPassedError):
        run_machine.start_run(run, state, expected_version=0, started_at="t1")
    for step in run_machine.CREATION_STEPS[:13]:
        state = run_machine.advance_creation(state, step)
    state = run_machine.pass_attempt_gate(state)
    started = run_machine.start_run(run, state, expected_version=0, started_at="t1")
    assert started.status == manifest.ExecutionRunStatus.RUNNING
    assert started.started_at == "t1"
    assert run.status == manifest.ExecutionRunStatus.CREATED


def test_allowed_table_and_terminal_have_no_outgoing():
    for src, targets in manifest.RUN_ALLOWED.items():
        for dst in targets:
            assert manifest.is_run_transition_allowed(src, dst) is True
    assert manifest.is_run_transition_allowed("REWORK_REQUIRED", "RUNNING") is False
    assert manifest.is_run_transition_allowed("CREATED", "SUCCEEDED") is False
    assert manifest.is_run_transition_allowed("VERIFYING", "SUCCEEDED") is False
    assert manifest.is_run_transition_allowed("AUDITING", "RUNNING") is False
    assert manifest.is_run_transition_allowed("NOPE", "RUNNING") is False
    for terminal in manifest.RUN_TERMINAL:
        assert manifest.RUN_ALLOWED[terminal] == frozenset()
        run = _run_at(
            terminal,
            "COMPLETED"
            if terminal == manifest.ExecutionRunStatus.SUCCEEDED
            else "AUDIT_FAIL"
            if terminal == manifest.ExecutionRunStatus.FAILED
            else "CANCELLED_BY_USER"
            if terminal == manifest.ExecutionRunStatus.CANCELLED
            else "SUPERSEDED_BY_REWORK",
            run_id="run-t",
        )
        with pytest.raises(run_machine.IllegalRunTransitionError):
            run_machine.transition_run(
                run,
                expected_status=terminal,
                expected_version=0,
                to_status="RUNNING",
                termination_reason="NONE",
            )


def test_failed_never_to_superseded():
    run = _run_at("FAILED", "EXECUTION_FAILED", run_id="run-f")
    with pytest.raises(run_machine.IllegalRunTransitionError):
        run_machine.transition_run(
            run,
            expected_status="FAILED",
            expected_version=0,
            to_status="SUPERSEDED",
            termination_reason="SUPERSEDED_BY_REWORK",
        )


def test_transition_enforces_allowed_and_returns_new_run():
    run = _skeleton()
    running = run_machine.transition_run(
        run,
        expected_status="CREATED",
        expected_version=0,
        to_status="RUNNING",
        termination_reason="NONE",
        at="t1",
    )
    assert running.status == manifest.ExecutionRunStatus.RUNNING
    assert running.started_at == "t1"
    verifying = run_machine.transition_run(
        running,
        expected_status="RUNNING",
        expected_version=0,
        to_status="VERIFYING",
        termination_reason="NONE",
        at="t2",
    )
    assert verifying.status == manifest.ExecutionRunStatus.VERIFYING
    assert verifying.ended_at is None
    done = run_machine.transition_run(
        verifying,
        expected_status="VERIFYING",
        expected_version=0,
        to_status="AUDITING",
        termination_reason="NONE",
    )
    terminal = run_machine.transition_run(
        done,
        expected_status="AUDITING",
        expected_version=0,
        to_status="SUCCEEDED",
        termination_reason="COMPLETED",
        at="t9",
    )
    assert terminal.ended_at == "t9"


def test_cas_rejects_stale_state_and_bad_version_token():
    run = _skeleton()
    with pytest.raises(run_machine.StaleRunStateError):
        run_machine.transition_run(
            run,
            expected_status="RUNNING",
            expected_version=0,
            to_status="VERIFYING",
            termination_reason="NONE",
        )
    for bad_token in (-1, "0", None, True):
        with pytest.raises(run_machine.StaleRunStateError):
            run_machine.transition_run(
                run,
                expected_status="CREATED",
                expected_version=bad_token,
                to_status="RUNNING",
                termination_reason="NONE",
            )
    moved = run_machine.transition_run(
        run,
        expected_status="CREATED",
        expected_version=0,
        to_status="RUNNING",
        termination_reason="NONE",
    )
    assert moved.status == manifest.ExecutionRunStatus.RUNNING
    with pytest.raises(run_machine.StaleRunStateError):
        run_machine.transition_run(
            moved,
            expected_status="CREATED",
            expected_version=0,
            to_status="VERIFYING",
            termination_reason="NONE",
        )


def test_compatibility_map_enforced():
    good = [
        ("SUCCEEDED", "COMPLETED"),
        ("FAILED", "EXECUTION_FAILED"),
        ("FAILED", "VERIFICATION_FAILED"),
        ("FAILED", "AUDIT_FAIL"),
        ("FAILED", "POLICY_BLOCK"),
        ("FAILED", "RESOURCE_FAILURE"),
        ("FAILED", "ROUTING_NO_ELIGIBLE_CANDIDATE"),
        ("FAILED", "CAPABILITY_UNAVAILABLE"),
        ("FAILED", "BUDGET_BLOCKED"),
        ("CANCELLED", "CANCELLED_BY_USER"),
        ("CANCELLED", "CANCELLED_BY_AMENDMENT"),
        ("SUPERSEDED", "SUPERSEDED_BY_FALLBACK"),
        ("SUPERSEDED", "SUPERSEDED_BY_REWORK"),
        ("CREATED", "NONE"),
        ("RUNNING", "NONE"),
        ("VERIFYING", "NONE"),
        ("AUDITING", "NONE"),
        ("REWORK_REQUIRED", "NONE"),
    ]
    for status, reason in good:
        assert run_machine.is_termination_compatible(status, reason) is True
    bad = [
        ("SUCCEEDED", "EXECUTION_FAILED"),
        ("SUCCEEDED", "NONE"),
        ("FAILED", "COMPLETED"),
        ("FAILED", "NONE"),
        ("CANCELLED", "COMPLETED"),
        ("CANCELLED", "POLICY_BLOCK"),
        ("SUPERSEDED", "COMPLETED"),
        ("RUNNING", "COMPLETED"),
        ("CREATED", "COMPLETED"),
        ("AUDITING", "AUDIT_FAIL"),
        ("REWORK_REQUIRED", "SUPERSEDED_BY_REWORK"),
        ("SUCCEEDED", "NOPE"),
        ("NOPE", "NONE"),
    ]
    for status, reason in bad:
        assert run_machine.is_termination_compatible(status, reason) is False
    run = _skeleton()
    with pytest.raises(run_machine.IncompatibleTerminationError):
        run_machine.transition_run(
            run,
            expected_status="CREATED",
            expected_version=0,
            to_status="RUNNING",
            termination_reason="COMPLETED",
        )


@pytest.mark.parametrize(
    "cause,task",
    [
        ("ROUTING_NO_ELIGIBLE_CANDIDATE", "ESCALATED"),
        ("CAPABILITY_UNAVAILABLE", "ESCALATED"),
    ],
)
def test_pre_run_disposition_escalating_causes(cause, task):
    run = _skeleton()
    disp = run_machine.apply_pre_run_disposition(run, cause)
    assert disp.run_to_status == manifest.ExecutionRunStatus.FAILED
    assert disp.run_to_reason == manifest.RunTerminationReason(cause)
    assert disp.task_to_state == manifest.TaskState(task)
    assert disp.release_reservations is True
    assert disp.replacement_run_id is None
    applied = run_machine.transition_run(
        run,
        expected_status="CREATED",
        expected_version=0,
        to_status=disp.run_to_status,
        termination_reason=disp.run_to_reason,
    )
    assert applied.status == manifest.ExecutionRunStatus.FAILED


@pytest.mark.parametrize("cause", ["RESOURCE_FAILURE", "BUDGET_BLOCKED"])
def test_pre_run_disposition_recoverable_blocked_else_escalated(cause):
    run = _skeleton()
    assert (
        run_machine.apply_pre_run_disposition(run, cause, recoverable=True).task_to_state
        == manifest.TaskState.BLOCKED
    )
    assert (
        run_machine.apply_pre_run_disposition(run, cause, recoverable=False).task_to_state
        == manifest.TaskState.ESCALATED
    )


def test_pre_run_disposition_policy_block_three_way():
    run = _skeleton()
    assert (
        run_machine.apply_pre_run_disposition(run, "POLICY_BLOCK").task_to_state
        == manifest.TaskState.BLOCKED
    )
    assert (
        run_machine.apply_pre_run_disposition(
            run, "POLICY_BLOCK", conflict=True
        ).task_to_state
        == manifest.TaskState.ESCALATED
    )
    failed = run_machine.apply_pre_run_disposition(
        run, "POLICY_BLOCK", terminally_unsatisfiable=True
    )
    assert failed.task_to_state == manifest.TaskState.FAILED
    assert failed.run_to_reason == manifest.RunTerminationReason.POLICY_BLOCK


def test_pre_run_disposition_replacement_before_terminalization():
    run = _skeleton()
    disp = run_machine.apply_pre_run_disposition(
        run, "RESOURCE_FAILURE", replacement_run_id="run-2"
    )
    assert disp.run_to_status == manifest.ExecutionRunStatus.SUPERSEDED
    assert disp.run_to_reason == manifest.RunTerminationReason.SUPERSEDED_BY_FALLBACK
    assert disp.task_to_state is None
    assert disp.replacement_run_id == "run-2"
    applied = run_machine.transition_run(
        run,
        expected_status="CREATED",
        expected_version=0,
        to_status=disp.run_to_status,
        termination_reason=disp.run_to_reason,
    )
    assert applied.status == manifest.ExecutionRunStatus.SUPERSEDED


def test_pre_run_disposition_only_from_created_and_known_causes():
    running = _run_at("RUNNING", "NONE", run_id="run-r")
    with pytest.raises(run_machine.PreRunDispositionError):
        run_machine.apply_pre_run_disposition(running, "BUDGET_BLOCKED")
    with pytest.raises(run_machine.PreRunDispositionError):
        run_machine.apply_pre_run_disposition(_skeleton(), "COMPLETED")
    staged = run_machine.apply_pre_run_disposition(
        _skeleton(), "BUDGET_BLOCKED", correction_staging=True
    )
    assert staged.run_to_reason == manifest.RunTerminationReason.BUDGET_BLOCKED


def _auditing_run(run_id="run-a"):
    return _run_at("AUDITING", "NONE", run_id=run_id)


def test_audit_disposition_map_matches_manifest():
    assert run_machine.AUDIT_DISPOSITION[manifest.AuditResult.PASS].task_to_state == (
        manifest.TaskState.COMPLETED
    )
    for result, task_state in manifest.AUDIT_RESULT_TRANSITION_MAP.items():
        assert run_machine.AUDIT_DISPOSITION[result].task_to_state == task_state


def test_audit_pass_and_fail_terminalize_run():
    passed = run_machine.apply_audit_disposition(_auditing_run(), "PASS")
    assert passed.run_to_status == manifest.ExecutionRunStatus.SUCCEEDED
    assert passed.run_to_reason == manifest.RunTerminationReason.COMPLETED
    assert passed.task_to_state == manifest.TaskState.COMPLETED
    assert passed.run_mutated is True
    assert passed.requires_replacement_run is False
    failed = run_machine.apply_audit_disposition(_auditing_run(), "FAIL")
    assert failed.run_to_status == manifest.ExecutionRunStatus.FAILED
    assert failed.run_to_reason == manifest.RunTerminationReason.AUDIT_FAIL
    assert failed.task_to_state == manifest.TaskState.FAILED
    auditing = _auditing_run(run_id="run-a2")
    applied = run_machine.transition_run(
        auditing,
        expected_status="AUDITING",
        expected_version=0,
        to_status=failed.run_to_status,
        termination_reason=failed.run_to_reason,
    )
    assert applied.status == manifest.ExecutionRunStatus.FAILED


def test_audit_rework_requires_replacement_and_supersedes_prior():
    disp = run_machine.apply_audit_disposition(_auditing_run(), "REWORK")
    assert disp.run_to_status == manifest.ExecutionRunStatus.REWORK_REQUIRED
    assert disp.run_to_reason == manifest.RunTerminationReason.NONE
    assert disp.task_to_state == manifest.TaskState.REWORK_PENDING
    assert disp.requires_replacement_run is True
    assert (
        disp.supersede_reason_after_replacement
        == manifest.RunTerminationReason.SUPERSEDED_BY_REWORK
    )
    auditing = _auditing_run(run_id="run-a3")
    held = run_machine.transition_run(
        auditing,
        expected_status="AUDITING",
        expected_version=0,
        to_status=disp.run_to_status,
        termination_reason=disp.run_to_reason,
    )
    closed = run_machine.transition_run(
        held,
        expected_status="REWORK_REQUIRED",
        expected_version=0,
        to_status="SUPERSEDED",
        termination_reason=disp.supersede_reason_after_replacement,
    )
    assert closed.status == manifest.ExecutionRunStatus.SUPERSEDED
    with pytest.raises(run_machine.IllegalRunTransitionError):
        run_machine.transition_run(
            held,
            expected_status="REWORK_REQUIRED",
            expected_version=0,
            to_status="RUNNING",
            termination_reason="NONE",
        )


@pytest.mark.parametrize("result", ["BLOCKED", "ESCALATE"])
def test_audit_suspension_holds_run_without_mutation(result):
    disp = run_machine.apply_audit_disposition(_auditing_run(), result)
    assert disp.run_to_status == manifest.ExecutionRunStatus.AUDITING
    assert disp.run_to_reason == manifest.RunTerminationReason.NONE
    assert disp.run_mutated is False
    assert disp.run_to_status not in manifest.RUN_TERMINAL
    assert disp.task_to_state == manifest.AUDIT_RESULT_TRANSITION_MAP[
        manifest.AuditResult(result)
    ]


def test_audit_disposition_only_from_auditing():
    with pytest.raises(run_machine.AuditDispositionError):
        run_machine.apply_audit_disposition(_skeleton(), "PASS")
    with pytest.raises(run_machine.AuditDispositionError):
        run_machine.apply_audit_disposition(_run_at("RUNNING", "NONE", run_id="r"), "FAIL")
    with pytest.raises(run_machine.AuditDispositionError):
        run_machine.apply_audit_disposition(_auditing_run(), "COMPLETED")


_SEC14_SELECTION_FIELDS = [
    "run_id",
    "project_id",
    "task_id",
    "contract_hash",
    "run_sequence",
    "revision_no",
    "creation_reason",
    "source_run_id",
    "routing_decision_ref",
    "routing_decision_refs",
    "route",
    "split_strategy",
    "primary_provider",
    "primary_provider_instance",
    "primary_model",
    "implementer_provider_ids",
    "implementer_model_ids",
    "status",
    "termination_reason",
    "started_at",
    "ended_at",
    "created_at",
]


def test_execution_run_full_sec14_selection_set_no_state_version():
    from dataclasses import fields as _dc_fields

    names = [f.name for f in _dc_fields(run_machine.ExecutionRun)]
    assert set(names) == set(_SEC14_SELECTION_FIELDS)
    assert "state_version" not in names
    run = _skeleton()
    assert run.routing_decision_refs == ()
    assert run.split_strategy is None
    assert run.primary_provider is None
    assert run.primary_provider_instance is None
    assert run.primary_model is None
    assert run.implementer_provider_ids == ()
    assert run.implementer_model_ids == ()


def test_bind_selection_fields_step9():
    run = run_machine.bind_selection_fields(
        _skeleton(),
        routing_decision_refs=["rd-1", "rd-2"],
        split_strategy="SPLIT",
        primary_provider="prov-a",
        primary_provider_instance="prov-a-1",
        primary_model="model-x",
        implementer_provider_ids=["prov-a", "prov-b"],
        implementer_model_ids=["model-x", "model-y"],
    )
    assert run.routing_decision_refs == ("rd-1", "rd-2")
    assert run.split_strategy == "SPLIT"
    assert run.primary_provider == "prov-a"
    assert run.primary_provider_instance == "prov-a-1"
    assert run.primary_model == "model-x"
    assert run.implementer_provider_ids == ("prov-a", "prov-b")
    assert run.implementer_model_ids == ("model-x", "model-y")
    assert run.status == manifest.ExecutionRunStatus.CREATED
    running = _run_at("RUNNING", "NONE", run_id="run-sel")
    with pytest.raises(run_machine.CreationOrderError):
        run_machine.bind_selection_fields(running, split_strategy="SPLIT")
