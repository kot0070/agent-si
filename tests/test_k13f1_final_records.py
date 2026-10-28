"""K13F1 M-FINAL lane: strict record-bound finalization (ARCH-641/642).

``Finalizer.finalize_with_records`` consumes the exact VerificationRecord +
AuditRecord: the outcome comes ONLY from authoritative records, the exact
audit ref is bound, and history is never rewritten. It refuses with
FinalizationError on missing/mismatched records; ``Finalizer.finalize``
keeps the legacy no-records path exactly as before.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from agent_si.assurance import audit_records
from agent_si.finalization import finalizer
from agent_si.policies import verification
from iface.frozen_manifest import manifest


def _criterion():
    return verification.CriterionResult(
        criterion_result_id="cr-ac-1",
        ac_id="ac-1",
        result=verification.CriterionVerificationResult.PASS,
        severity=verification.FailureSeverity.MEDIUM,
        verification_method="DeterministicVerify",
        evidence_refs=("ev-1",),
    )


def _verification_record(contract_hash="h-bound-1", **kw):
    base = dict(
        verification_id="v-bound-1",
        verification_sequence=1,
        project_id="P1",
        task_id="T1",
        run_id="run-1",
        verification_scope_id=(
            "TASK:T1:RUN:run-1:CONTRACT:h-bound-1:RUN_OUTPUT"
        ),
        verification_target_type=(
            verification.VerificationTargetType.RUN_OUTPUT
        ),
        contract_hash=contract_hash,
        criterion_results=(_criterion(),),
        result=manifest.VerificationResult.PASS,
        handling_disposition=(
            verification.VerificationHandlingDisposition.ACCEPT
        ),
    )
    base.update(kw)
    return verification.VerificationRecord(**base)


def _audit_record(contract_hash="h-bound-1", **kw):
    base = dict(
        audit_id="aud-bound-1",
        project_id="P1",
        task_id="T1",
        run_id="run-1",
        audit_scope_id="scope-1",
        audit_sequence=1,
        supersedes_audit_id=None,
        context_session_ref="sess-audit-1",
        producer_session_refs=("sess-prod-1",),
        implementer_model_ids=("impl-model-1",),
        contract_hash=contract_hash,
        audit_policy_ref="pol-1",
        artifact_refs=("art-1",),
        evidence_refs=("ev-1",),
        requirement_verdicts=(),
        context_integrity="PASS",
        result=audit_records.AuditResult.PASS,
        handling_disposition=(
            audit_records.AuditHandlingDisposition.COMPLETE
        ),
        failure_class=None,
        created_at="t1",
        decided_at=None,
    )
    base.update(kw)
    return audit_records.AuditRecord(**base)


def _bound_kwargs(**kw):
    bound_verification = _verification_record()
    bound_audit = _audit_record()
    base = dict(
        finalization_id="fin-bound-1",
        project_id="P1",
        task_id="T1",
        run_id="run-1",
        task_state=manifest.TaskState.COMPLETED,
        audit_result=manifest.AuditResult.PASS,
        audit_ref=bound_audit,
        verification_ref=bound_verification.verification_id,
        verification_record=bound_verification,
        audit_record=bound_audit,
        output_refs=("art-1",),
        metric_refs=("m-1",),
        accounting_complete=True,
        budget_settled=True,
        resources_released=True,
        completed_at="t9",
    )
    base.update(kw)
    return base


def test_missing_verification_refuses():
    kwargs = _bound_kwargs()
    del kwargs["verification_record"]
    with pytest.raises(finalizer.FinalizationError):
        finalizer.Finalizer.finalize_with_records(**kwargs)


def test_missing_audit_refuses():
    kwargs = _bound_kwargs()
    del kwargs["audit_record"]
    with pytest.raises(finalizer.FinalizationError):
        finalizer.Finalizer.finalize_with_records(**kwargs)


def test_hash_mismatch_refuses():
    other = _audit_record(contract_hash="h-other-2")
    kwargs = _bound_kwargs(audit_record=other, audit_ref=other)
    with pytest.raises(finalizer.FinalizationError):
        finalizer.Finalizer.finalize_with_records(**kwargs)


def test_blank_hash_refuses():
    blank_verification = _verification_record(contract_hash="")
    blank_audit = _audit_record(contract_hash="")
    kwargs = _bound_kwargs(
        verification_record=blank_verification,
        audit_record=blank_audit,
        verification_ref=blank_verification.verification_id,
        audit_ref=blank_audit,
    )
    with pytest.raises(finalizer.FinalizationError):
        finalizer.Finalizer.finalize_with_records(**kwargs)


def test_exact_accept_binds_refs():
    bound_verification = _verification_record()
    bound_audit = _audit_record()
    record = finalizer.Finalizer.finalize_with_records(
        **_bound_kwargs(
            verification_record=bound_verification,
            audit_record=bound_audit,
            verification_ref=bound_verification.verification_id,
            audit_ref=bound_audit,
        )
    )
    assert record.completion_disposition == (
        manifest.CompletionDisposition.VERIFIED_PASS
    )
    assert record.audit_result == manifest.AuditResult.PASS
    assert record.audit_ref == bound_audit
    assert record.verification_ref == bound_verification.verification_id
