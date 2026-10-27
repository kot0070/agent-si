"""M1b Task state machine + suspension records (Manifest section 12).

Written test-first (RED) before src/agent_si/state_machines/ existed.
Section 12 rules covered: allowed edges, forbidden edges, AUDITING
disposition map, TERMINAL set, ESCALATED non-terminal, restart/reroute,
CAS atomicity, resume invariants, suspension quarantine, reconciliation.
"""

from dataclasses import fields as dc_fields
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from agent_si.state_machines import suspension as susp
from agent_si.state_machines import task_machine as tm
from iface.frozen_manifest import manifest


def test_manifest_verified_first():
    assert manifest.MANIFEST_SHA256 == "f256bab4d31be3cd9e86c22a1bdcef90b08ad62500a8eca2051705cc0a9b0690"
    assert manifest.verify_manifest(ROOT / "RECORDS" / "day0" / "K13_MANIFEST.md") is True


def _machine(state=manifest.TaskState.CREATED, task_id="T1"):
    return tm.TaskMachine(task_id=task_id, project_id="P1", initial_state=state)


def _hop(machine, to, **kw):
    kw.setdefault("actor", "director")
    kw.setdefault("reason", "test-hop")
    return machine.transition(
        to,
        expected_from_state=machine.current_state,
        expected_state_version=machine.state_version,
        **kw,
    )


def _drive(machine, *states):
    for state in states:
        _hop(machine, state, **_edge_kwargs(machine.current_state, state))
    return machine


_AUDIT_FOR_TARGET = {
    manifest.TaskState.COMPLETED: manifest.AuditResult.PASS,
    manifest.TaskState.REWORK_PENDING: manifest.AuditResult.REWORK,
    manifest.TaskState.BLOCKED: manifest.AuditResult.BLOCKED,
    manifest.TaskState.ESCALATED: manifest.AuditResult.ESCALATE,
    manifest.TaskState.FAILED: manifest.AuditResult.FAIL,
}


def _edge_kwargs(source, target):
    kw = {}
    if target in (manifest.TaskState.BLOCKED, manifest.TaskState.ESCALATED):
        kw["resume_target_state"] = manifest.TaskState.EXECUTING
    if source == manifest.TaskState.AUDITING and target in _AUDIT_FOR_TARGET:
        kw["audit_result"] = _AUDIT_FOR_TARGET[target]
    if source == manifest.TaskState.REWORK_PENDING and target == manifest.TaskState.EXECUTING:
        kw["run_id"] = "run-next"
    return kw


def _override(source, original_result=None, **kw):
    base = dict(
        override_id="ovr-1",
        project_id="P1",
        task_id="T1",
        authorized_by="user",
        authorization_ref="auth-1",
        completion_disposition=manifest.CompletionDisposition.ACCEPTED_RISK,
        original_result=original_result,
        override_source_state=source,
        override_reason="accepted risk",
        override_action="complete",
        accepted_risks=("risk-1",),
    )
    base.update(kw)
    return tm.OverrideRecord(**base)


def test_transition_record_fields_match_manifest_order():
    names = [f.name for f in dc_fields(tm.TaskTransition)]
    assert names == list(manifest.TRANSITION_FIELDS)


def test_every_allowed_edge_passes():
    for source, targets in manifest.TASK_ALLOWED.items():
        for target in sorted(targets, key=lambda s: s.value):
            machine = _machine(source)
            record = _hop(machine, target, **_edge_kwargs(source, target))
            assert machine.current_state == target
            assert getattr(record, "from") == source
            assert getattr(record, "to") == target
            assert record.transition_sequence == 1
            assert record.new_state_version == 1
            assert record.expected_from_state == source
            assert record.expected_state_version == 0


def test_forbidden_executing_verifying_to_completed_refused():
    for source in (manifest.TaskState.EXECUTING, manifest.TaskState.VERIFYING):
        machine = _drive(_machine(), *{
            manifest.TaskState.EXECUTING: (
                manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
                manifest.TaskState.PLANNING, manifest.TaskState.EXECUTING,
            ),
            manifest.TaskState.VERIFYING: (
                manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
                manifest.TaskState.PLANNING, manifest.TaskState.EXECUTING,
                manifest.TaskState.VERIFYING,
            ),
        }[source])
        with pytest.raises(tm.TransitionRejectedError):
            _hop(machine, manifest.TaskState.COMPLETED)
        assert machine.current_state == source


def test_self_pass_without_disposition_refused_and_silent_refused():
    machine = _drive(
        _machine(),
        manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
        manifest.TaskState.PLANNING, manifest.TaskState.EXECUTING,
        manifest.TaskState.VERIFYING, manifest.TaskState.AUDITING,
    )
    with pytest.raises(tm.TransitionRejectedError):
        _hop(machine, manifest.TaskState.COMPLETED)
    with pytest.raises(tm.TransitionRejectedError):
        _hop(machine, manifest.TaskState.REWORK_PENDING)
    with pytest.raises(tm.TransitionRejectedError):
        machine.transition(
            manifest.TaskState.CANCELLED,
            expected_from_state=machine.current_state,
            expected_state_version=machine.state_version,
            actor="director",
            reason="",
        )
    assert machine.current_state == manifest.TaskState.AUDITING


def test_terminal_states_have_no_outgoing():
    assert manifest.TASK_TERMINAL == frozenset(
        {manifest.TaskState.COMPLETED, manifest.TaskState.FAILED, manifest.TaskState.CANCELLED}
    )
    for terminal in manifest.TASK_TERMINAL:
        machine = _machine(terminal)
        with pytest.raises(tm.TerminalTransitionError):
            _hop(machine, manifest.TaskState.EXECUTING)
        assert machine.current_state == terminal
        assert machine.state_version == 0
        assert machine.history == ()


def test_escalated_is_non_terminal_suspended():
    assert manifest.TaskState.ESCALATED not in manifest.TASK_TERMINAL
    machine = _drive(
        _machine(),
        manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
        manifest.TaskState.PLANNING, manifest.TaskState.ESCALATED,
    )
    _hop(machine, manifest.TaskState.FAILED)
    assert machine.current_state == manifest.TaskState.FAILED
    machine2 = _drive(
        _machine(task_id="T2"),
        manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
        manifest.TaskState.PLANNING, manifest.TaskState.ESCALATED,
    )
    _hop(machine2, manifest.TaskState.CANCELLED)
    assert machine2.current_state == manifest.TaskState.CANCELLED


def test_auditing_disposition_map():
    for result, target in manifest.AUDIT_RESULT_TRANSITION_MAP.items():
        machine = _drive(
            _machine(task_id="T-%s" % result.value),
            manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
            manifest.TaskState.PLANNING, manifest.TaskState.EXECUTING,
            manifest.TaskState.VERIFYING, manifest.TaskState.AUDITING,
        )
        _hop(machine, target, **_edge_kwargs(machine.current_state, target))
        assert machine.current_state == target
        assert getattr(machine.history[-1], "to") == target
    auditing = _drive(
        _machine(task_id="T-NEG"),
        manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
        manifest.TaskState.PLANNING, manifest.TaskState.EXECUTING,
        manifest.TaskState.VERIFYING, manifest.TaskState.AUDITING,
    )
    with pytest.raises(tm.TransitionRejectedError):
        _hop(auditing, manifest.TaskState.COMPLETED, audit_result=manifest.AuditResult.FAIL)
    with pytest.raises(tm.TransitionRejectedError):
        _hop(auditing, manifest.TaskState.COMPLETED, audit_result=manifest.AuditResult.REWORK)
    assert auditing.current_state == manifest.TaskState.AUDITING


def _drive_to_suspendable(source, task_id):
    aware = _machine(task_id=task_id)
    if source == manifest.TaskState.REWORK_PENDING:
        return _drive(
            aware,
            manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
            manifest.TaskState.PLANNING, manifest.TaskState.EXECUTING,
            manifest.TaskState.REWORK_PENDING,
        )
    if source == manifest.TaskState.BLOCKED:
        return _drive(
            aware,
            manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
            manifest.TaskState.PLANNING, manifest.TaskState.EXECUTING,
            manifest.TaskState.BLOCKED,
        )
    return _drive(
        aware,
        manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
        manifest.TaskState.PLANNING, manifest.TaskState.ESCALATED,
    )


def test_override_without_record_refused():
    for source, target in manifest.TASK_CONDITIONAL_OVERRIDE_EDGES:
        machine = _drive_to_suspendable(source, "T-ovr-%s" % source.value)
        with pytest.raises(tm.TransitionRejectedError):
            _hop(machine, target)
        assert machine.current_state == source


def test_override_with_record_allowed_only_on_canonical_edges():
    for source, target in manifest.TASK_CONDITIONAL_OVERRIDE_EDGES:
        machine = _drive_to_suspendable(source, "T-acc-%s" % source.value)
        record = _hop(machine, target, override=_override(source))
        assert machine.current_state == manifest.TaskState.COMPLETED
        assert getattr(record, "to") == manifest.TaskState.COMPLETED
    executing = _drive(
        _machine(task_id="T-ovr-exec"),
        manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
        manifest.TaskState.PLANNING, manifest.TaskState.EXECUTING,
    )
    with pytest.raises(tm.TransitionRejectedError):
        _hop(executing, manifest.TaskState.COMPLETED, override=_override(executing.current_state))
    assert executing.current_state == manifest.TaskState.EXECUTING


def test_override_rejects_missing_authorization_wrong_source_and_fail():
    machine = _drive_to_suspendable(manifest.TaskState.BLOCKED, "T-ovr-neg")
    with pytest.raises(tm.TransitionRejectedError):
        _hop(machine, manifest.TaskState.COMPLETED, override=_override(
            manifest.TaskState.BLOCKED, authorized_by="", authorization_ref=""))
    with pytest.raises(tm.TransitionRejectedError):
        _hop(machine, manifest.TaskState.COMPLETED, override=_override(
            manifest.TaskState.BLOCKED, authorization_ref=""))
    with pytest.raises(tm.TransitionRejectedError):
        _hop(machine, manifest.TaskState.COMPLETED, override=_override(
            manifest.TaskState.ESCALATED))
    with pytest.raises(tm.TransitionRejectedError):
        _hop(machine, manifest.TaskState.COMPLETED, override=_override(
            manifest.TaskState.BLOCKED,
            original_result=manifest.AuditResult.FAIL,
        ))
    with pytest.raises(tm.TransitionRejectedError):
        _hop(machine, manifest.TaskState.COMPLETED, override=_override(
            manifest.TaskState.BLOCKED,
            completion_disposition=manifest.CompletionDisposition.VERIFIED_PASS,
        ))
    assert machine.current_state == manifest.TaskState.BLOCKED


def test_restart_reroute_goes_via_rework_pending_without_count():
    for reason in (
        tm.RestartReason.AMENDMENT_RESTART,
        tm.RestartReason.FALLBACK_REROUTE,
    ):
        machine = _drive(
            _machine(task_id="T-rs-%s" % reason.value),
            manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
            manifest.TaskState.PLANNING, manifest.TaskState.EXECUTING,
        )
        record, increments = machine.request_restart(
            reason,
            expected_state_version=machine.state_version,
            actor="director",
        )
        assert machine.current_state == manifest.TaskState.REWORK_PENDING
        assert getattr(record, "to") == manifest.TaskState.REWORK_PENDING
        assert increments is False
        assert tm.increments_correction_count(reason) is False
        assert tm.increments_correction_count(tm.EXECUTION_RETRY) is False
    verifying = _drive(
        _machine(task_id="T-rs-retry"),
        manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
        manifest.TaskState.PLANNING, manifest.TaskState.EXECUTING,
        manifest.TaskState.VERIFYING,
    )
    record, increments = verifying.request_restart(
        tm.EXECUTION_RETRY,
        expected_state_version=verifying.state_version,
        actor="director",
    )
    assert verifying.current_state == manifest.TaskState.REWORK_PENDING
    assert increments is False


def test_restart_from_wrong_state_refused():
    created = _machine(task_id="T-rs-bad")
    with pytest.raises(tm.TransitionRejectedError):
        created.request_restart(
            tm.RestartReason.AMENDMENT_RESTART,
            expected_state_version=created.state_version,
            actor="director",
        )
    auditing = _drive(
        _machine(task_id="T-rs-bad2"),
        manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
        manifest.TaskState.PLANNING, manifest.TaskState.EXECUTING,
        manifest.TaskState.VERIFYING, manifest.TaskState.AUDITING,
    )
    with pytest.raises(tm.TransitionRejectedError):
        auditing.request_restart(
            tm.EXECUTION_RETRY,
            expected_state_version=auditing.state_version,
            actor="director",
        )
    assert created.current_state == manifest.TaskState.CREATED
    assert auditing.current_state == manifest.TaskState.AUDITING


def test_rework_pending_to_executing_binds_new_run():
    machine = _drive_to_suspendable(manifest.TaskState.REWORK_PENDING, "T-run-bind")
    with pytest.raises(tm.TransitionRejectedError):
        _hop(machine, manifest.TaskState.EXECUTING)
    record = _hop(machine, manifest.TaskState.EXECUTING, run_id="run-2")
    assert machine.current_state == manifest.TaskState.EXECUTING
    assert record.run_id == "run-2"


def test_cas_commit_is_atomic_and_monotonic():
    machine = _drive(
        _machine(task_id="T-cas"),
        manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
        manifest.TaskState.PLANNING,
    )
    assert machine.state_version == 3
    assert [r.transition_sequence for r in machine.history] == [1, 2, 3]
    assert [r.new_state_version for r in machine.history] == [1, 2, 3]
    assert [getattr(r, "to") for r in machine.history] == [
        manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED, manifest.TaskState.PLANNING,
    ]


def test_stale_commit_fails_and_changes_nothing():
    machine = _drive(_machine(task_id="T-stale"), manifest.TaskState.PACKAGED)
    with pytest.raises(tm.StaleStateError):
        machine.transition(
            manifest.TaskState.ASSIGNED,
            expected_from_state=manifest.TaskState.PACKAGED,
            expected_state_version=99,
            actor="director",
            reason="stale-version",
        )
    with pytest.raises(tm.StaleStateError):
        machine.transition(
            manifest.TaskState.ASSIGNED,
            expected_from_state=manifest.TaskState.EXECUTING,
            expected_state_version=machine.state_version,
            actor="director",
            reason="stale-from",
        )
    assert machine.current_state == manifest.TaskState.PACKAGED
    assert machine.state_version == 1
    assert len(machine.history) == 1


def test_recovery_derives_latest_from_highest_version_sequence():
    machine = _drive(
        _machine(task_id="T-rec"),
        manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
        manifest.TaskState.PLANNING, manifest.TaskState.EXECUTING,
    )
    shuffled = list(reversed(machine.history))
    recovered = tm.TaskMachine.recover(task_id="T-rec", project_id="P1", records=shuffled)
    assert recovered.current_state == machine.current_state
    assert recovered.state_version == machine.state_version
    assert [r.transition_sequence for r in recovered.history] == [1, 2, 3, 4]


def test_recover_rejects_duplicate_sequence_or_version():
    machine = _drive(_machine(task_id="T-dup"), manifest.TaskState.PACKAGED)
    with pytest.raises(tm.TransitionRejectedError):
        tm.TaskMachine.recover(
            task_id="T-dup", project_id="P1", records=list(machine.history) + [machine.history[0]]
        )


def test_entering_blocked_captures_suspension_and_requires_target():
    machine = _drive(
        _machine(task_id="T-sus"),
        manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
        manifest.TaskState.PLANNING, manifest.TaskState.EXECUTING,
    )
    record = _hop(
        machine,
        manifest.TaskState.BLOCKED,
        suspended_from_state=manifest.TaskState.EXECUTING,
        resume_target_state=manifest.TaskState.VERIFYING,
    )
    assert machine.suspended_from_state == manifest.TaskState.EXECUTING
    assert machine.resume_target_state == manifest.TaskState.VERIFYING
    assert getattr(record, "suspended_from_state") == manifest.TaskState.EXECUTING
    assert getattr(record, "resume_target_state") == manifest.TaskState.VERIFYING
    fresh = _drive(
        _machine(task_id="T-sus-bare"),
        manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
        manifest.TaskState.PLANNING, manifest.TaskState.EXECUTING,
    )
    with pytest.raises(tm.TransitionRejectedError):
        _hop(fresh, manifest.TaskState.BLOCKED)
    assert fresh.current_state == manifest.TaskState.EXECUTING


def test_resume_enforces_recorded_target_not_inferred():
    machine = _drive(
        _machine(task_id="T-res"),
        manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
        manifest.TaskState.PLANNING, manifest.TaskState.EXECUTING,
    )
    _hop(machine, manifest.TaskState.BLOCKED, resume_target_state=manifest.TaskState.EXECUTING)
    _hop(machine, manifest.TaskState.EXECUTING)
    assert machine.current_state == manifest.TaskState.EXECUTING
    machine2 = _drive(
        _machine(task_id="T-res2"),
        manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
        manifest.TaskState.PLANNING, manifest.TaskState.EXECUTING,
    )
    _hop(machine2, manifest.TaskState.BLOCKED, resume_target_state=manifest.TaskState.EXECUTING)
    with pytest.raises(tm.TransitionRejectedError):
        _hop(machine2, manifest.TaskState.VERIFYING)
    assert machine2.current_state == manifest.TaskState.BLOCKED


def test_resume_redirect_via_decision_record_and_contract_gate():
    machine = _drive(
        _machine(task_id="T-red"),
        manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
        manifest.TaskState.PLANNING, manifest.TaskState.EXECUTING,
    )
    _hop(machine, manifest.TaskState.BLOCKED, resume_target_state=manifest.TaskState.EXECUTING)
    redirect = tm.DecisionRedirect(
        decision_id="dec-1",
        new_target_state=manifest.TaskState.VERIFYING,
        contract_hash="h1",
        expected_contract_hash="h1",
    )
    _hop(machine, manifest.TaskState.VERIFYING, redirect=redirect)
    assert machine.current_state == manifest.TaskState.VERIFYING
    assert machine.resume_target_state == manifest.TaskState.VERIFYING
    machine2 = _drive(
        _machine(task_id="T-red2"),
        manifest.TaskState.PACKAGED, manifest.TaskState.ASSIGNED,
        manifest.TaskState.PLANNING, manifest.TaskState.EXECUTING,
    )
    _hop(machine2, manifest.TaskState.BLOCKED, resume_target_state=manifest.TaskState.EXECUTING)
    stale_redirect = tm.DecisionRedirect(
        decision_id="dec-2",
        new_target_state=manifest.TaskState.VERIFYING,
        contract_hash="h2",
        expected_contract_hash="h1",
    )
    with pytest.raises(manifest.ContextWrongContractVersionError):
        _hop(machine2, manifest.TaskState.VERIFYING, redirect=stale_redirect)
    assert machine2.current_state == manifest.TaskState.BLOCKED


def _open_store(task_id="TQ1"):
    store = susp.QuarantineStore()
    record = store.open_suspension(
        suspension_id="sus-1",
        project_id="P1",
        task_id=task_id,
        run_id="run-1",
        attempt_id="att-1",
        source_task_state=manifest.TaskState.EXECUTING,
        reason="provider timeout",
        started_at="t0",
    )
    return store, record


def test_suspension_marks_suspended_and_halts_attempts():
    store, record = _open_store()
    assert record.run_suspension_state == susp.RunSuspensionState.SUSPENDED_BY_TASK
    assert record.status == "OPEN"
    assert record.resolved_at is None
    assert store.is_halted("TQ1") is True
    assert store.is_halted("OTHER") is False


def test_late_result_quarantined_never_auto_resumed():
    store, _ = _open_store()
    store.note_committed_output("artifact-committed-1")
    late = store.report_late_result(
        project_id="P1",
        task_id="TQ1",
        run_id="run-1",
        attempt_id="att-1",
        output_refs=("artifact-late-1",),
        contract_hash="h1",
        quarantined_at="t1",
    )
    assert late.disposition == susp.AttemptResultDisposition.LATE_AFTER_SUSPENSION
    quarantined = store.quarantine_result(late.quarantine_id)
    assert quarantined.disposition == susp.AttemptResultDisposition.QUARANTINED
    assert store.active_suspension_for("TQ1").status == "OPEN"
    assert store.is_halted("TQ1") is True
    assert store.committed_outputs == ("artifact-committed-1",)


def test_quarantine_survives_restart():
    store, _ = _open_store()
    late = store.report_late_result(
        project_id="P1",
        task_id="TQ1",
        run_id="run-1",
        attempt_id="att-1",
        output_refs=("artifact-late-1",),
        contract_hash="h1",
        quarantined_at="t1",
    )
    store.quarantine_result(late.quarantine_id)
    snapshot = store.export_records()
    revived = susp.QuarantineStore.import_records(snapshot)
    assert revived.active_suspension_for("TQ1").status == "OPEN"
    assert revived.quarantined_result(late.quarantine_id).disposition == (
        susp.AttemptResultDisposition.QUARANTINED
    )


def test_resume_requires_gates_and_never_reopens_finished_attempts():
    store, _ = _open_store()
    partial = susp.ResumeReadiness(
        context_recovery_check=True,
        attempt_execution_gate=False,
        ownership_revalidated=True,
        budget_revalidated=True,
        authorization_revalidated=True,
    )
    assert partial.ready() is False
    with pytest.raises(susp.ResumeRefusedError):
        store.resume_suspension("sus-1", partial, attempt_status="RUNNING", resolved_at="t9")
    full = susp.ResumeReadiness(True, True, True, True, True)
    assert full.ready() is True
    with pytest.raises(susp.ResumeRefusedError):
        store.resume_suspension(
            "sus-1", full, attempt_status=manifest.ExecutionAttemptStatus.CANCELLED, resolved_at="t9"
        )
    resolved = store.resume_suspension(
        "sus-1", full, attempt_status="RUNNING", resolved_at="t9"
    )
    assert resolved.status == "RESOLVED"
    assert resolved.resolved_at == "t9"
    assert store.is_halted("TQ1") is False


def _quarantined_store(task_id="TQ2"):
    store = susp.QuarantineStore()
    store.open_suspension(
        suspension_id="sus-9",
        project_id="P1",
        task_id=task_id,
        run_id="run-1",
        attempt_id="att-1",
        source_task_state=manifest.TaskState.EXECUTING,
        reason="provider timeout",
        started_at="t0",
    )
    late = store.report_late_result(
        project_id="P1",
        task_id=task_id,
        run_id="run-1",
        attempt_id="att-1",
        output_refs=("artifact-late-1",),
        contract_hash="h1",
        quarantined_at="t1",
    )
    store.quarantine_result(late.quarantine_id)
    return store, late


def _reconcile_kwargs(late, **over):
    kw = dict(
        reconciliation_id="rec-1",
        project_id="P1",
        task_id=late.task_id,
        run_id="run-1",
        attempt_id="att-1",
        suspension_id="sus-9",
        quarantine_id=late.quarantine_id,
        late_output_refs=("artifact-late-1",),
        decision=susp.LateResultDecision.ACCEPT_AS_EVIDENCE,
        decided_by="director",
        authorized=True,
        decided_at="t2",
        reason="output verified",
        contract_hash="h1",
        expected_contract_hash="h1",
        has_superseding_output=False,
        verification_ref="ver-1",
        policy_pass=True,
    )
    kw.update(over)
    return kw


def test_reconciliation_accept_rules_and_never_auto_resumes():
    store, late = _quarantined_store()
    with pytest.raises(susp.ReconciliationRejectedError):
        store.reconcile(**_reconcile_kwargs(late, authorized=False))
    with pytest.raises(manifest.ContextMissingError):
        store.reconcile(**_reconcile_kwargs(late, verification_ref=None))
    with pytest.raises(manifest.ContextWrongContractVersionError):
        store.reconcile(**_reconcile_kwargs(late, contract_hash="h2"))
    with pytest.raises(susp.ReconciliationRejectedError):
        store.reconcile(**_reconcile_kwargs(late, has_superseding_output=True))
    with pytest.raises(manifest.PolicyConflictError):
        store.reconcile(**_reconcile_kwargs(late, policy_pass=False))
    record = store.reconcile(**_reconcile_kwargs(late))
    assert record.decision == susp.LateResultDecision.ACCEPT_AS_EVIDENCE
    assert store.quarantined_result(late.quarantine_id).disposition == (
        susp.AttemptResultDisposition.RECONCILED_ACCEPTED
    )
    assert store.active_suspension_for(late.task_id).status == "OPEN"


def test_reconciliation_reject_and_terminal_never_reopened():
    store, late = _quarantined_store(task_id="TQ3")
    rejected = store.reconcile(**_reconcile_kwargs(late, decision=susp.LateResultDecision.REJECT))
    assert rejected.decision == susp.LateResultDecision.REJECT
    assert store.quarantined_result(late.quarantine_id).disposition == (
        susp.AttemptResultDisposition.RECONCILED_REJECTED
    )
    with pytest.raises(susp.ReconciliationRejectedError):
        store.reconcile(**_reconcile_kwargs(
            late, reconciliation_id="rec-2", task_terminal=True,
            decision=susp.LateResultDecision.ACCEPT_AS_EVIDENCE,
        ))
    with pytest.raises(susp.ReconciliationRejectedError):
        store.reconcile(**_reconcile_kwargs(
            late, reconciliation_id="rec-3", attempt_terminal=True,
            decision=susp.LateResultDecision.SUPERSEDED,
        ))
