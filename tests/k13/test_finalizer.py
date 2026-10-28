"""K13 finalizer + verification tests (Manifest sections 21C, 17C, 21D, 18B).

M2b accepted base: exercises src/agent_si/policies/verification.py and
src/agent_si/finalization/finalizer.py.
"""

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from agent_si.finalization import finalizer
from agent_si.policies import verification
from iface.frozen_manifest import manifest


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _criterion(ac_id, result="PASS", evidence=("ev-1",), failure_class=None):
    return verification.CriterionResult(
        criterion_result_id="cr-" + ac_id,
        ac_id=ac_id,
        result=result,
        severity=manifest_failure_severity(),
        verification_method="DeterministicVerify",
        evidence_refs=evidence,
        failure_class=failure_class,
    )


def manifest_failure_severity():
    return verification.FailureSeverity.MEDIUM


def _record(seq, scope="scope-1", result=manifest.VerificationResult.PASS,
            handling=None, task="T1", run="run-1"):
    return verification.VerificationRecord(
        verification_id="v-%s" % seq,
        verification_sequence=seq,
        project_id="P1",
        task_id=task,
        run_id=run,
        verification_scope_id=scope,
        verification_target_type=verification.VerificationTargetType.RUN_OUTPUT,
        contract_hash="h1",
        criterion_results=(_criterion("ac-1"),),
        result=result,
        handling_disposition=(
            handling if handling is not None
            else verification.VerificationHandlingDisposition.ACCEPT
        ),
    )


def _all_pass_snapshot():
    return {check: True for check in verification.GATE_CHECK_ORDER}


from dataclasses import dataclass


@dataclass(frozen=True)
class _AuditStub:
    audit_id: str
    result: object


def _audit_stub(result):
    return _AuditStub(audit_id="aud-1", result=result)


def _override(source=manifest.TaskState.BLOCKED, **kw):
    base = dict(
        override_id="ovr-1",
        project_id="P1",
        task_id="T1",
        run_id="run-1",
        created_at="t1",
        authorized_by="user:u1",
        authorization_ref="auth-1",
        original_result=manifest.AuditResult.BLOCKED,
        override_source_state=source,
        override_reason="accept residual risk",
        override_action="COMPLETE",
        accepted_risks=("residual-x",),
        evidence_refs=("ev-1",),
        scope="TASK",
        status=finalizer.OverrideRecordStatus.ACTIVE,
    )
    base.update(kw)
    return finalizer.OverrideRecord(**base)


def _finalize_kwargs(**kw):
    base = dict(
        finalization_id="fin-1",
        project_id="P1",
        task_id="T1",
        run_id="run-1",
        task_state=manifest.TaskState.COMPLETED,
        audit_result=manifest.AuditResult.PASS,
        audit_ref=_audit_stub(manifest.AuditResult.PASS),
        verification_ref="v-1",
        output_refs=("art-1",),
        metric_refs=("m-1",),
        accounting_complete=True,
        budget_settled=True,
        resources_released=True,
        completed_at="t9",
    )
    base.update(kw)
    return base


# --------------------------------------------------------------------------
# 21C scope ids: deterministic, canonicalised
# --------------------------------------------------------------------------

def test_run_scope_id_exact_shape():
    assert verification.run_output_scope_id("T1", "run-1", "h1") == (
        "TASK:T1:RUN:run-1:CONTRACT:h1:RUN_OUTPUT"
    )


def test_scope_ids_deterministic_and_canonicalised():
    assert verification.attempt_output_scope_id("T1", "run-1", "att-1") == (
        verification.attempt_output_scope_id("T1", "run-1", "att-1")
    )
    assert verification.subtask_output_scope_id("T1", "sub-1") == (
        "TASK:T1:SUBTASK:sub-1:SUBTASK_OUTPUT"
    )
    # same set = same id: order, duplicates and padding must not matter
    first = verification.multi_attempt_scope_id(["att-1", "att-2", "att-3"])
    second = verification.multi_attempt_scope_id(
        ["  att-3", "att-1", "att-2", "att-1", "att-2 "]
    )
    assert first == second
    assert verification.multi_attempt_scope_id(["att-1", "att-2"]) != first
    first_art = verification.artifact_set_scope_id(["b.bin", "a.bin"])
    assert first_art == verification.artifact_set_scope_id(["a.bin", "b.bin", "a.bin"])
    assert verification.artifact_set_scope_id(["a.bin"]) != first_art


def test_scope_id_rejects_blank_inputs():
    with pytest.raises(ValueError):
        verification.run_output_scope_id("T1", "run-1", "   ")
    with pytest.raises(ValueError):
        verification.multi_attempt_scope_id([])
    with pytest.raises(ValueError):
        verification.multi_attempt_scope_id(["   "])


# --------------------------------------------------------------------------
# 21C records: immutable, monotonic latest-wins
# --------------------------------------------------------------------------

def test_verification_record_frozen():
    record = _record(1)
    with pytest.raises(FrozenInstanceError):
        record.result = manifest.VerificationResult.FAIL
    with pytest.raises(FrozenInstanceError):
        record.verification_sequence = 99
    assert record.result == manifest.VerificationResult.PASS
    assert record.verification_sequence == 1


def test_latest_wins_monotonic_per_scope():
    first = _record(1, scope="S")
    second = _record(2, scope="S")
    third = _record(3, scope="S")
    superseding = replace(third, supersedes_verification_id="v-2")
    latest = verification.resolve_latest([second, first, superseding])
    assert latest["S"] == superseding
    assert verification.latest_for_scope([second, first], "S") == second
    assert verification.latest_for_scope([first], "MISSING") is None
    # history untouched: earlier records keep their own sequence/result
    assert first.verification_sequence == 1
    assert second.verification_sequence == 2


def test_criterion_missing_evidence_never_passes():
    no_evidence = _criterion("ac-1", evidence=())
    assert verification.criterion_effective_result(no_evidence) == (
        verification.CriterionVerificationResult.FAIL
    )
    with_evidence = _criterion("ac-1", evidence=("ev-1",))
    assert verification.criterion_effective_result(with_evidence) == (
        verification.CriterionVerificationResult.PASS
    )
    blocked = _criterion("ac-1", result="BLOCKED", evidence=())
    assert verification.criterion_effective_result(blocked) == (
        verification.CriterionVerificationResult.BLOCKED
    )


# --------------------------------------------------------------------------
# 21C canonical disposition (REWORK-exhausted preserves result -> ESCALATE)
# --------------------------------------------------------------------------

def test_canonical_disposition_map():
    assert verification.canonical_handling(manifest.VerificationResult.PASS) == (
        verification.VerificationHandlingDisposition.ACCEPT
    )
    assert verification.canonical_handling(
        manifest.VerificationResult.RETRY
    ) == verification.VerificationHandlingDisposition.RETRY_VERIFIER
    assert verification.canonical_handling(
        manifest.VerificationResult.RETRY, execution_producing=True
    ) == verification.VerificationHandlingDisposition.RETRY_EXECUTION
    assert verification.canonical_handling(
        manifest.VerificationResult.FALLBACK
    ) == verification.VerificationHandlingDisposition.FALLBACK
    assert verification.canonical_handling(
        manifest.VerificationResult.REWORK
    ) == verification.VerificationHandlingDisposition.REWORK
    exhausted = verification.canonical_handling(
        manifest.VerificationResult.REWORK, correction_budget_exhausted=True
    )
    assert exhausted == verification.VerificationHandlingDisposition.ESCALATE
    assert verification.canonical_handling(
        manifest.VerificationResult.BLOCKED
    ) == verification.VerificationHandlingDisposition.BLOCK
    assert verification.canonical_handling(
        manifest.VerificationResult.ESCALATE
    ) == verification.VerificationHandlingDisposition.ESCALATE
    assert verification.canonical_handling(
        manifest.VerificationResult.FAIL
    ) == verification.VerificationHandlingDisposition.FAIL


def test_rework_exhausted_preserves_result():
    record = _record(1, result=manifest.VerificationResult.REWORK,
                     handling=verification.VerificationHandlingDisposition.REWORK)
    handling = verification.handling_for_record(
        record, correction_budget_exhausted=True
    )
    assert handling == verification.VerificationHandlingDisposition.ESCALATE
    assert record.result == manifest.VerificationResult.REWORK


def test_failure_class_deterministic_paths():
    infra_retry = verification.failure_class_path(
        verification.VerificationFailureClass.VERIFICATION_INFRA_FAILURE,
        verification.FailureSeverity.HIGH, retry_budget=True,
    )
    assert infra_retry == "VERIFICATION_RETRY"
    infra_exhausted = verification.failure_class_path(
        verification.VerificationFailureClass.VERIFICATION_INFRA_FAILURE,
        verification.FailureSeverity.HIGH, retry_budget=False,
    )
    assert infra_exhausted == "ESCALATE"
    fmt_critical = verification.failure_class_path(
        verification.VerificationFailureClass.OUTPUT_FORMAT_FAILURE,
        verification.FailureSeverity.CRITICAL, retry_budget=True,
    )
    assert fmt_critical == "ESCALATE"
    ac_defect = verification.failure_class_path(
        verification.VerificationFailureClass.IMPLEMENTATION_AC_DEFECT,
        verification.FailureSeverity.MEDIUM, correction_budget=True,
    )
    assert ac_defect == "CORRECTION_LOOP"
    ac_defect_spent = verification.failure_class_path(
        verification.VerificationFailureClass.IMPLEMENTATION_AC_DEFECT,
        verification.FailureSeverity.MEDIUM, correction_budget=False,
    )
    assert ac_defect_spent == "ESCALATE"
    security_terminal = verification.failure_class_path(
        verification.VerificationFailureClass.SECURITY_OR_POLICY_FAILURE,
        verification.FailureSeverity.CRITICAL, terminal_violation=True,
    )
    assert security_terminal == "FAIL"
    unknown = verification.failure_class_path(
        verification.VerificationFailureClass.UNKNOWN_FAILURE,
        verification.FailureSeverity.LOW,
    )
    assert unknown == "BLOCKED"


# --------------------------------------------------------------------------
# 17C AttemptExecutionGate: frozen order, per-class dispositions
# --------------------------------------------------------------------------

def test_gate_allows_when_every_check_passes():
    decision = verification.AttemptExecutionGate.check(
        _all_pass_snapshot(), run_status=manifest.ExecutionRunStatus.RUNNING
    )
    assert decision.allowed is True
    assert decision.failed_check is None
    assert decision.side_effects_allowed is True


def test_gate_frozen_order_first_failure_wins():
    snapshot = _all_pass_snapshot()
    snapshot["budget_coverage"] = False
    snapshot["provider_health"] = False
    decision = verification.AttemptExecutionGate.check(
        snapshot, run_status=manifest.ExecutionRunStatus.RUNNING
    )
    assert decision.allowed is False
    assert decision.failed_check == "provider_health"
    assert decision.failure_class == verification.GateFailureClass.HEALTH_FAILURE
    assert decision.side_effects_allowed is False


def test_gate_phase_pre_run_vs_attempt():
    snapshot = _all_pass_snapshot()
    snapshot["budget_coverage"] = False
    pre_run = verification.AttemptExecutionGate.check(
        snapshot, run_status=manifest.ExecutionRunStatus.CREATED,
        recoverable=False, fallback_available=False,
    )
    assert pre_run.phase == "PRE_RUN"
    assert pre_run.disposition == "PRE_RUN_FAILURE_DISPOSITION"
    attempt = verification.AttemptExecutionGate.check(
        dict(snapshot), run_status=manifest.ExecutionRunStatus.RUNNING,
        recoverable=False, fallback_available=False,
    )
    assert attempt.phase == "ATTEMPT"
    assert attempt.disposition == "ATTEMPT_GATE_FAILURE_DISPOSITION"
    assert attempt.task_effect == "FAILED"
    assert attempt.run_effect == "FAILED/BUDGET_BLOCKED"


def test_gate_per_class_dispositions():
    snapshot = _all_pass_snapshot()
    snapshot["budget_coverage"] = False
    top_up = verification.AttemptExecutionGate.check(
        dict(snapshot), run_status=manifest.ExecutionRunStatus.RUNNING,
        recoverable=True,
    )
    assert top_up.task_effect == "BLOCKED"

    snapshot = _all_pass_snapshot()
    snapshot["resource_ownership_capacity"] = False
    resource = verification.AttemptExecutionGate.check(
        dict(snapshot), run_status=manifest.ExecutionRunStatus.RUNNING,
        same_run_rereserve=True,
    )
    assert resource.task_effect == "SAME_RUN_RETRY"

    snapshot = _all_pass_snapshot()
    snapshot["capability_compatibility"] = False
    capability = verification.AttemptExecutionGate.check(
        dict(snapshot), run_status=manifest.ExecutionRunStatus.RUNNING,
    )
    assert capability.failure_class == (
        verification.GateFailureClass.CAPABILITY_UNAVAILABLE
    )
    assert capability.task_effect == "ESCALATED"
    assert capability.run_effect == "FAILED/CAPABILITY_UNAVAILABLE"

    snapshot = _all_pass_snapshot()
    snapshot["contract_policy_refs"] = False
    conflict = verification.AttemptExecutionGate.check(
        dict(snapshot), run_status=manifest.ExecutionRunStatus.RUNNING,
        authority_conflict=True,
    )
    assert conflict.failure_class == verification.GateFailureClass.POLICY_BLOCK
    assert conflict.task_effect == "ESCALATED"
    terminal = verification.AttemptExecutionGate.check(
        dict(snapshot), run_status=manifest.ExecutionRunStatus.RUNNING,
        terminally_unsatisfiable=True,
    )
    assert terminal.task_effect == "FAILED"
    assert terminal.run_effect == "FAILED/POLICY_BLOCK"


def test_retry_kinds_and_correction_budgets():
    assert verification.classify_retry(False) == (
        verification.RetryKind.VERIFICATION_ONLY_RETRY
    )
    assert verification.classify_retry(True) == (
        verification.RetryKind.EXECUTION_PRODUCING_RETRY
    )
    only = verification.verification_only_effect()
    assert only.new_attempt is False
    assert only.task_transition == "STAY_VERIFYING"
    plan = verification.execution_producing_plan()
    assert plan.task_from == manifest.TaskState.VERIFYING
    assert plan.task_to == manifest.TaskState.REWORK_PENDING
    assert plan.task_reason == "EXECUTION_RETRY"
    assert plan.run_from == manifest.ExecutionRunStatus.VERIFYING
    assert plan.run_to == manifest.ExecutionRunStatus.RUNNING
    assert plan.new_attempt is True
    assert plan.increments_correction_count is False
    assert verification.correction_allowed(
        verification.CorrectionLoopKind.VERIFICATION_LOOP,
        verification_remaining=1, audit_remaining=0, runtime_remaining=1,
    ) is True
    assert verification.correction_allowed(
        verification.CorrectionLoopKind.VERIFICATION_LOOP,
        verification_remaining=1, audit_remaining=0, runtime_remaining=0,
    ) is False
    assert verification.correction_disposition(
        verification.CorrectionLoopKind.AUDIT_LOOP,
        verification_remaining=9, audit_remaining=0, runtime_remaining=9,
    ) == "ESCALATE"
    charged = verification.apply_correction_charge(
        verification.CorrectionLoopKind.VERIFICATION_LOOP,
        verification_count=1, audit_count=0, runtime_count=2,
    )
    assert charged == (2, 0, 3)


# --------------------------------------------------------------------------
# 21D FINALIZATION_MAPPING + Finalizer.finalize
# --------------------------------------------------------------------------

def test_finalization_mapping_rows():
    mapping = finalizer.FINALIZATION_MAPPING
    assert mapping[("COMPLETED", "PASS")] == (
        manifest.CompletionDisposition.VERIFIED_PASS
    )
    assert mapping[("COMPLETED", "OVERRIDE")] == (
        manifest.CompletionDisposition.ACCEPTED_RISK
    )
    assert mapping[("FAILED", "ANY")] == manifest.CompletionDisposition.FAILED
    assert mapping[("CANCELLED", "ANY")] == manifest.CompletionDisposition.CANCELLED


def test_finalize_verified_pass():
    record = finalizer.Finalizer.finalize(**_finalize_kwargs())
    assert record.completion_disposition == manifest.CompletionDisposition.VERIFIED_PASS
    assert record.audit_result == manifest.AuditResult.PASS
    assert record.task_state == manifest.TaskState.COMPLETED
    assert record.run_id == "run-1"
    assert record.output_refs == ("art-1",)
    with pytest.raises(FrozenInstanceError):
        record.completion_disposition = manifest.CompletionDisposition.FAILED


def test_finalize_exact_audit_ref_bind():
    with pytest.raises(finalizer.FinalizationError):
        finalizer.Finalizer.finalize(**_finalize_kwargs(
            audit_result=manifest.AuditResult.PASS,
            audit_ref=_audit_stub(manifest.AuditResult.REWORK),
        ))
    # audit result adopted from the authoritative ref when not passed twice
    kwargs = _finalize_kwargs()
    del kwargs["audit_result"]
    record = finalizer.Finalizer.finalize(**kwargs)
    assert record.audit_result == manifest.AuditResult.PASS


def test_finalize_null_run_pre_run_only():
    cancelled = finalizer.Finalizer.finalize(**_finalize_kwargs(
        task_state=manifest.TaskState.CANCELLED,
        run_id=None, audit_result=None, audit_ref=None, verification_ref=None,
        output_refs=(),
    ))
    assert cancelled.completion_disposition == manifest.CompletionDisposition.CANCELLED
    assert cancelled.run_id is None
    failed = finalizer.Finalizer.finalize(**_finalize_kwargs(
        task_state=manifest.TaskState.FAILED,
        run_id=None, audit_result=None, audit_ref=None, verification_ref=None,
        output_refs=(),
    ))
    assert failed.completion_disposition == manifest.CompletionDisposition.FAILED
    assert failed.run_id is None
    # COMPLETED needs a real run; the NOT_RUN sentinel is never invented
    with pytest.raises(finalizer.FinalizationError):
        finalizer.Finalizer.finalize(**_finalize_kwargs(run_id=None))
    with pytest.raises(finalizer.FinalizationError):
        finalizer.Finalizer.finalize(**_finalize_kwargs(run_id="NOT_RUN"))


def test_finalize_accepted_risk_gating():
    record = finalizer.Finalizer.finalize(**_finalize_kwargs(
        audit_result=manifest.AuditResult.BLOCKED,
        audit_ref=_audit_stub(manifest.AuditResult.BLOCKED),
        override=_override(),
    ))
    assert record.completion_disposition == manifest.CompletionDisposition.ACCEPTED_RISK
    # original AuditResult preserved, never rewritten to PASS
    assert record.audit_result == manifest.AuditResult.BLOCKED
    assert record.override_ref.original_result == manifest.AuditResult.BLOCKED
    # pre-audit accepted risk: no AuditResult yet, override carries the basis
    pre_audit = finalizer.Finalizer.finalize(**_finalize_kwargs(
        audit_result=None, audit_ref=None, verification_ref=None,
        override=_override(original_result=None),
    ))
    assert pre_audit.completion_disposition == (
        manifest.CompletionDisposition.ACCEPTED_RISK
    )
    assert pre_audit.audit_result is None
    # gating: authorization, risks and non-terminal source required
    with pytest.raises(finalizer.FinalizationError):
        finalizer.Finalizer.finalize(**_finalize_kwargs(
            audit_result=None, audit_ref=None, verification_ref=None,
            override=_override(authorization_ref=""),
        ))
    with pytest.raises(finalizer.FinalizationError):
        finalizer.Finalizer.finalize(**_finalize_kwargs(
            audit_result=None, audit_ref=None, verification_ref=None,
            override=_override(accepted_risks=()),
        ))
    with pytest.raises(finalizer.FinalizationError):
        finalizer.Finalizer.finalize(**_finalize_kwargs(
            audit_result=None, audit_ref=None, verification_ref=None,
            override=_override(source=manifest.TaskState.COMPLETED),
        ))
    # FAILED never converts via override
    with pytest.raises(finalizer.FinalizationError):
        finalizer.Finalizer.finalize(**_finalize_kwargs(
            task_state=manifest.TaskState.FAILED,
            audit_result=manifest.AuditResult.FAIL,
            audit_ref=_audit_stub(manifest.AuditResult.FAIL),
            override=_override(),
        ))


def test_finalize_state_audit_consistency_and_settlement():
    with pytest.raises(finalizer.FinalizationError):
        finalizer.Finalizer.finalize(**_finalize_kwargs(
            audit_result=manifest.AuditResult.REWORK,
            audit_ref=_audit_stub(manifest.AuditResult.REWORK),
        ))
    with pytest.raises(finalizer.FinalizationError):
        finalizer.Finalizer.finalize(**_finalize_kwargs(
            task_state=manifest.TaskState.FAILED,
            audit_result=manifest.AuditResult.PASS,
            audit_ref=_audit_stub(manifest.AuditResult.PASS),
        ))
    with pytest.raises(finalizer.FinalizationError):
        finalizer.Finalizer.finalize(**_finalize_kwargs(budget_settled=False))
    with pytest.raises(finalizer.FinalizationError):
        finalizer.Finalizer.finalize(**_finalize_kwargs(resources_released=False))
    with pytest.raises(finalizer.FinalizationError):
        finalizer.Finalizer.finalize(**_finalize_kwargs(accounting_complete=False))
    # VERIFIED_PASS needs attached output refs
    with pytest.raises(finalizer.FinalizationError):
        finalizer.Finalizer.finalize(**_finalize_kwargs(output_refs=()))
    # only terminal task states finalize
    with pytest.raises(finalizer.FinalizationError):
        finalizer.Finalizer.finalize(**_finalize_kwargs(
            task_state=manifest.TaskState.EXECUTING,
            audit_result=None, audit_ref=None, verification_ref=None,
            output_refs=(),
        ))


def test_finalize_never_rewrites_history():
    kwargs = _finalize_kwargs()
    before = dict(kwargs)
    first = finalizer.Finalizer.finalize(**kwargs)
    assert kwargs == before
    second = finalizer.Finalizer.finalize(**_finalize_kwargs())
    assert first == second
    assert first is not second
    assert first.audit_ref == _audit_stub(manifest.AuditResult.PASS)
