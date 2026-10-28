"""K13 cancellation + incidents tests (Manifest sections 14A, 14B, 45B, 46, 45A).

RED->GREEN: this file FAILS without
src/agent_si/runtime/scheduler/cancellation.py and
src/agent_si/domain/incidents.py (import error at collection), and PASSES
with them. Cancellation is not rollback: canonical reasons only (never a
generic CANCELLED), history kept, partial usage/time/cost finalized where
measurable, active attempts CANCELLED, reservations/leases released, and
audit/verification history immutable. Incidents index context violations
only; truth stays in ContextIntegrityRecord.
"""

from dataclasses import FrozenInstanceError
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from iface.frozen_manifest import manifest
from agent_si.domain import incidents
from agent_si.runtime.scheduler import cancellation

MANIFEST_DOC = ROOT / "iface" / "frozen_manifest" / "K13_MANIFEST.md"


def test_manifest_sha_pins_file():
    assert manifest.MANIFEST_SHA256 == "f256bab4d31be3cd9e86c22a1bdcef90b08ad62500a8eca2051705cc0a9b0690"
    assert manifest.verify_manifest(MANIFEST_DOC) is True
    assert manifest.verify_manifest(ROOT / "iface" / "frozen_manifest" / "NOPE.md") is False


def test_canonical_reasons_accepted():
    for name in ("CANCELLED_BY_USER", "CANCELLED_BY_AMENDMENT"):
        reason = cancellation.validate_cancellation_reason(name)
        assert reason == manifest.RunTerminationReason(name)
        assert cancellation.is_cancellation_reason(reason) is True
        assert reason in cancellation.CANCELLATION_REASONS


def test_generic_cancelled_rejected():
    for bad in ("CANCELLED", "cancelled", "", None, 123):
        with pytest.raises(cancellation.NonCanonicalCancellationReasonError):
            cancellation.validate_cancellation_reason(bad)
        assert cancellation.is_cancellation_reason(bad) is False
    # A run/agent status CANCELLED is not a termination reason either.
    with pytest.raises(cancellation.NonCanonicalCancellationReasonError):
        cancellation.validate_cancellation_reason(manifest.ExecutionRunStatus.CANCELLED)


def test_non_cancellation_members_rejected():
    # Policy/resource failures terminate as FAILED with their own reason;
    # they must never be funnelled through cancellation finalization.
    for name in (
        "NONE",
        "COMPLETED",
        "EXECUTION_FAILED",
        "POLICY_BLOCK",
        "RESOURCE_FAILURE",
        "BUDGET_BLOCKED",
    ):
        with pytest.raises(cancellation.NonCanonicalCancellationReasonError):
            cancellation.validate_cancellation_reason(
                manifest.RunTerminationReason(name)
            )
        assert (
            cancellation.is_cancellation_reason(manifest.RunTerminationReason(name))
            is False
        )


def _attempt(attempt_id, status, run_id="run-1"):
    return cancellation.CancellableAttempt(
        attempt_id=attempt_id, run_id=run_id, status=status
    )


def test_running_attempt_cancelled():
    attempt = _attempt("att-1", "RUNNING")
    out = cancellation.cancel_attempt(attempt, "CANCELLED_BY_USER")
    assert out.status == manifest.ExecutionAttemptStatus.CANCELLED
    assert out.attempt_id == "att-1"
    assert attempt.status == manifest.ExecutionAttemptStatus.RUNNING
    assert manifest.is_attempt_transition_allowed("RUNNING", "CANCELLED") is True
    with pytest.raises(FrozenInstanceError):
        out.status = manifest.ExecutionAttemptStatus.SUCCEEDED  # type: ignore


def test_created_and_terminal_attempts_kept():
    # CREATED has no manifest edge to CANCELLED (ATTEMPT_ALLOWED); terminal
    # attempts never reopen. History is kept, never rewritten.
    before = [
        _attempt("att-created", "CREATED"),
        _attempt("att-ok", "SUCCEEDED"),
        _attempt("att-fail", "FAILED"),
        _attempt("att-cancelled", "CANCELLED"),
    ]
    snapshot = [(a.attempt_id, a.status) for a in before]
    out = cancellation.cancel_attempts(before, "run-1", "CANCELLED_BY_AMENDMENT")
    assert [a.status for a in out] == [
        manifest.ExecutionAttemptStatus.CREATED,
        manifest.ExecutionAttemptStatus.SUCCEEDED,
        manifest.ExecutionAttemptStatus.FAILED,
        manifest.ExecutionAttemptStatus.CANCELLED,
    ]
    assert [(a.attempt_id, a.status) for a in before] == snapshot


def test_attempt_run_mismatch_rejected():
    with pytest.raises(cancellation.AttemptRunMismatchError):
        cancellation.cancel_attempts(
            [_attempt("att-1", "RUNNING", run_id="run-2")],
            "run-1",
            "CANCELLED_BY_USER",
        )


def test_terminal_run_transition_rejected():
    for bad in ("SUCCEEDED", "FAILED", "CANCELLED", "SUPERSEDED"):
        with pytest.raises(cancellation.IllegalCancellationTransitionError):
            cancellation.finalize_cancellation(
                run_id="run-1",
                reason="CANCELLED_BY_USER",
                from_status=bad,
            )
    for ok in ("CREATED", "RUNNING", "VERIFYING", "AUDITING", "REWORK_REQUIRED"):
        assert manifest.is_run_transition_allowed(ok, "CANCELLED") is True
        final = cancellation.finalize_cancellation(
            run_id="run-1", reason="CANCELLED_BY_AMENDMENT", from_status=ok
        )
        assert final.to_status == manifest.ExecutionRunStatus.CANCELLED


def test_finalize_end_to_end():
    attempts = [_attempt("att-1", "RUNNING"), _attempt("att-2", "SUCCEEDED")]
    final = cancellation.finalize_cancellation(
        run_id="run-1",
        reason=manifest.RunTerminationReason.CANCELLED_BY_USER,
        from_status="RUNNING",
        attempts=attempts,
        measured_usage={"tokens": 120.0, "seconds": 31.5},
        unmeasurable_usage=("cost",),
        reservation_ids=("res-1",),
        lease_ids=("lease-1", "lease-2"),
        audit_refs=("audit-1",),
        verification_refs=("ver-1",),
    )
    assert final.run_id == "run-1"
    assert final.reason == manifest.RunTerminationReason.CANCELLED_BY_USER
    assert final.to_status == manifest.ExecutionRunStatus.CANCELLED
    assert [a.status for a in final.attempts] == [
        manifest.ExecutionAttemptStatus.CANCELLED,
        manifest.ExecutionAttemptStatus.SUCCEEDED,
    ]
    assert final.usage is not None
    assert dict(final.usage.measured) == {"tokens": 120.0, "seconds": 31.5}
    assert final.usage.unmeasurable == ("cost",)
    assert [(d.kind, d.ref) for d in final.releases] == [
        ("reservation", "res-1"),
        ("lease", "lease-1"),
        ("lease", "lease-2"),
    ]
    assert all(d.action == "release" for d in final.releases)
    assert final.audit_refs == ("audit-1",)
    assert final.verification_refs == ("ver-1",)
    assert final.history_kept is True
    # Inputs untouched: cancellation never rewrites history.
    assert [a.status for a in attempts] == [
        manifest.ExecutionAttemptStatus.RUNNING,
        manifest.ExecutionAttemptStatus.SUCCEEDED,
    ]
    with pytest.raises(FrozenInstanceError):
        final.reason = manifest.RunTerminationReason.POLICY_BLOCK  # type: ignore


def test_finalize_without_usage_has_no_usage_record():
    final = cancellation.finalize_cancellation(
        run_id="run-1", reason="CANCELLED_BY_USER"
    )
    assert final.usage is None
    assert final.releases == ()
    assert final.attempts == ()


def test_partial_usage_disjoint_and_finite():
    with pytest.raises(cancellation.InvalidPartialUsageError):
        cancellation.finalize_partial_usage(
            "run-1", {"tokens": 5.0}, unmeasurable=("tokens",)
        )
    for bad in (float("nan"), float("inf"), "many"):
        with pytest.raises(cancellation.InvalidPartialUsageError):
            cancellation.finalize_partial_usage("run-1", {"tokens": bad})


def test_incident_severity_shared_and_types_frozen():
    assert incidents.IncidentSeverity is manifest.IncidentSeverity
    for name in (
        "workspace_violation",
        "provider_failure",
        "model_failure",
        "scheduler_failure",
        "test_failure",
        "audit_failure",
        "scope_deviation",
        "security_issue",
        "retry_exhausted",
        "fallback_exhausted",
        "unsafe_action",
        "data_corruption_risk",
        "capability_mismatch",
    ):
        assert name in incidents.INCIDENT_TYPES
        rec = incidents.IncidentRecord(
            incident_id="inc-%s" % name,
            project_id="P1",
            timestamp="t0",
            task_id="T1",
            severity="HIGH",
            type=name,
        )
        assert rec.severity == manifest.IncidentSeverity.HIGH
    with pytest.raises(incidents.UnknownIncidentTypeError):
        incidents.IncidentRecord(incident_id="inc-x", type="CANCELLED")
    with pytest.raises(FrozenInstanceError):
        rec.severity = manifest.IncidentSeverity.LOW  # type: ignore


def test_context_integrity_index_only():
    truth = incidents.ContextIntegrityRecord(
        context_event_id="ctx-1",
        project_id="P1",
        task_id="T1",
        type="CONTEXT_MISSING",
        missing_refs=("handoff-9",),
        contract_hash="h1",
    )
    assert truth.incident_ref is None
    for bad in ("context_missing", "MISSING", "workspace_violation"):
        with pytest.raises(incidents.UnknownContextViolationTypeError):
            incidents.ContextIntegrityRecord(context_event_id="ctx-x", type=bad)
    index = incidents.index_context_violation(
        truth, incident_id="inc-1", type="scheduler_failure", timestamp="t1"
    )
    assert index.incident_id == "inc-1"
    assert index.severity == truth.severity
    linked = incidents.link_incident(truth, "inc-1")
    assert linked.incident_ref == "inc-1"
    assert truth.incident_ref is None
    assert incidents.check_index_linkage(index, linked) is True
    with pytest.raises(incidents.IncidentLinkError):
        incidents.link_incident(linked, "inc-2")
    with pytest.raises(incidents.IncidentLinkError):
        incidents.check_index_linkage(index, truth)

