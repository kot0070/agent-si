"""K03 0C assurance coordinator: verify leg, audit leg, finalize leg.

The coordinator runs verify, audit, finalize over one assurance run. A
failed verification never reaches audit and a failed audit never
finalizes. Every step is recorded on the returned outcome and the
execution run status moves at every phase through the existing
transition writer, using manifest run-status members only (audit
spellings are never run statuses).

The verify leg lazy-imports the M-CHECK checker module
``agent_si.assurance.verification.checker`` and its ``verify_run`` with
run data; when that module is not importable the coordinator refuses
with a precise error before any audit or finalize work. The audit leg
builds the served turn from the run data, calls the real
``AuditCoordinator.audit_served_turn`` entry and loads the exact audit
record by the returned audit id. The finalize leg calls the real
``Finalizer.finalize_with_records`` with the bound records.

Verification and audit resolve artifacts through the one shared
grounding module ``agent_si.assurance.grounding``; this module adds no
grounding code of its own.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from agent_si.assurance import audit_coordinator
from agent_si.assurance import audit_records
from agent_si.assurance import grounding
from agent_si.finalization import finalizer
from agent_si.policies import verification
from agent_si.state_machines import run_machine

#: M-CHECK checker module lazy-imported by the verify leg.
CHECKER_MODULE = "agent_si.assurance.verification.checker"

#: Outcome phases reported on AssuranceOutcome.phase.
VERIFY_REFUSED = "VERIFY_REFUSED"
AUDIT_REFUSED = "AUDIT_REFUSED"
FINALIZED = "FINALIZED"

#: The one shared grounding entry the verify and audit legs resolve
#: artifacts through; the coordinator adds no grounding of its own.
SHARED_GROUNDING_ENTRY = grounding.SHARED_GROUNDING_ENTRY


class AssuranceRefused(Exception):
    """The coordinator refused assurance work (fail-closed, nothing ran)."""

    code = "ASSURANCE_REFUSED"


class _LiveAuditCoordinator(audit_coordinator.AuditCoordinator):
    """Concrete binding of the real audit entry; adds no behavior."""


@dataclass(frozen=True)
class AssuranceStep:
    """One recorded coordinator step: the leg, the run status after the
    step and a short note naming the records and ids involved."""

    leg: str
    status: str
    note: str


@dataclass(frozen=True)
class AssuranceOutcome:
    """One assurance run: terminal phase, pass flag, the steps recorded
    on the way, the ids minted and the run-status trail in order."""

    phase: str
    ok: bool
    verification_id: Optional[str]
    audit_id: Optional[str]
    finalization_id: Optional[str]
    records: Tuple[AssuranceStep, ...]
    status_trail: Tuple[str, ...]


def _move(run, to_status, termination_reason):
    """Move one run edge through the existing transition writer."""
    return run_machine.transition_run(
        run,
        expected_status=run.status,
        expected_version=0,
        to_status=to_status,
        termination_reason=termination_reason,
    )


def run_assurance(
    *,
    project_id: str,
    task_id: str,
    run_id: str,
    contract_hash: str,
    artifact_refs: Tuple[str, ...] = (),
    evidence_refs: Tuple[str, ...] = (),
    work_refs: Tuple[str, ...] = (),
    producer_session_refs: Tuple[str, ...] = (),
    tool_rows: Tuple[Any, ...] = (),
    project_dir: str = "",
    task_state: Any = None,
    output_refs: Tuple[str, ...] = (),
    metric_refs: Tuple[str, ...] = (),
    accounting_complete: bool = False,
    budget_settled: bool = False,
    resources_released: bool = False,
) -> AssuranceOutcome:
    """Run verify, audit, finalize over run data; return one outcome.

    Failed verification returns before any served turn is built and
    before any audit or finalize call; a non-PASS audit returns before
    any finalize call. The execution run status starts at RUNNING and
    moves at every phase through the existing transition writer.
    """
    artifact_refs = tuple(artifact_refs)
    evidence_refs = tuple(evidence_refs)
    work_refs = tuple(work_refs)
    producer_session_refs = tuple(producer_session_refs)
    tool_rows = tuple(tool_rows)
    output_refs = tuple(output_refs)
    metric_refs = tuple(metric_refs)
    run = run_machine.ExecutionRun(
        run_id=run_id,
        project_id=project_id,
        task_id=task_id,
        contract_hash=contract_hash,
        status="RUNNING",
    )
    trail = ["RUNNING"]
    run_machine.emit_lifecycle_event(
        project_id, run_id, "plan", "RUNNING", "assurance run planned"
    )
    try:
        checker = importlib.import_module(CHECKER_MODULE)
    except ImportError as exc:
        raise AssuranceRefused(
            "assurance checker %r is not importable (%s); refusing "
            "before any audit or finalize work" % (CHECKER_MODULE, exc)
        ) from exc
    verify_run = getattr(checker, "verify_run", None)
    if not callable(verify_run):
        raise AssuranceRefused(
            "assurance checker %r has no callable verify_run; refusing "
            "before any audit or finalize work" % (CHECKER_MODULE,)
        )
    run = _move(run, "VERIFYING", "NONE")
    trail.append("VERIFYING")
    run_machine.emit_lifecycle_event(
        project_id, run_id, "start", "VERIFYING", "verification started"
    )
    try:
        verification_record = verify_run(
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            contract_hash=contract_hash,
            artifact_refs=artifact_refs,
            evidence_refs=evidence_refs,
            work_refs=work_refs,
            producer_session_refs=producer_session_refs,
            tool_rows=tool_rows,
            project_dir=project_dir,
            task_state=task_state,
        )
    except Exception as exc:
        run = _move(run, "FAILED", "VERIFICATION_FAILED")
        trail.append("FAILED")
        run_machine.emit_lifecycle_event(
            project_id, run_id, "finish", "FAILED", "verification raised"
        )
        return AssuranceOutcome(
            phase=VERIFY_REFUSED,
            ok=False,
            verification_id=None,
            audit_id=None,
            finalization_id=None,
            records=(
                AssuranceStep(
                    leg="verify",
                    status="FAILED",
                    note=(
                        "verification raised %s: %s; no record, "
                        "no audit, no finalize"
                        % (type(exc).__name__, exc)
                    ),
                ),
            ),
            status_trail=tuple(trail),
        )
    verification_id = verification_record.verification_id
    failed = [
        criterion
        for criterion in verification_record.criterion_results
        if criterion.result
        != verification.CriterionVerificationResult.PASS
    ]
    steps = [
        AssuranceStep(
            leg="verify",
            status="VERIFYING",
            note=(
                "verification=%s criteria=%d shared-grounding=%s"
                % (
                    verification_id,
                    len(verification_record.criterion_results),
                    SHARED_GROUNDING_ENTRY,
                )
            ),
        )
    ]
    if failed:
        run = _move(run, "FAILED", "VERIFICATION_FAILED")
        trail.append("FAILED")
        run_machine.emit_lifecycle_event(
            project_id, run_id, "finish", "FAILED", "verification refused"
        )
        steps.append(
            AssuranceStep(
                leg="verify",
                status="FAILED",
                note=(
                    "verification refused: %d of %d criterion "
                    "results not PASS; no audit, no finalize"
                    % (
                        len(failed),
                        len(verification_record.criterion_results),
                    )
                ),
            )
        )
        return AssuranceOutcome(
            phase=VERIFY_REFUSED,
            ok=False,
            verification_id=verification_id,
            audit_id=None,
            finalization_id=None,
            records=tuple(steps),
            status_trail=tuple(trail),
        )
    run = _move(run, "AUDITING", "NONE")
    trail.append("AUDITING")
    run_machine.emit_lifecycle_event(
        project_id, run_id, "advance", "AUDITING", "audit started"
    )
    turn = audit_coordinator.ServedTurn(
        turn_ref=run_id,
        project_id=project_id,
        task_id=task_id,
        run_id=run_id,
        work_refs=work_refs,
        artifact_refs=artifact_refs,
        evidence_refs=evidence_refs,
        producer_session_refs=producer_session_refs,
        contract_hash=contract_hash,
    )
    try:
        audit_id = _LiveAuditCoordinator().audit_served_turn(turn)
    except Exception as exc:
        run = _move(run, "FAILED", "AUDIT_FAIL")
        trail.append("FAILED")
        run_machine.emit_lifecycle_event(
            project_id, run_id, "finish", "FAILED", "audit raised"
        )
        steps.append(
            AssuranceStep(
                leg="audit",
                status="FAILED",
                note=(
                    "audit raised %s: %s; no record, no finalize"
                    % (type(exc).__name__, exc)
                ),
            )
        )
        return AssuranceOutcome(
            phase=AUDIT_REFUSED,
            ok=False,
            verification_id=verification_id,
            audit_id=None,
            finalization_id=None,
            records=tuple(steps),
            status_trail=tuple(trail),
        )
    audit_record = audit_records._fetch_record(audit_id)
    steps.append(
        AssuranceStep(
            leg="audit",
            status="AUDITING",
            note="audit=%s verification=%s" % (audit_id, verification_id),
        )
    )
    if audit_record is None or (
        audit_record.result != audit_records.AuditResult.PASS
    ):
        seen = (
            "missing"
            if audit_record is None
            else getattr(
                audit_record.result, "value", audit_record.result
            )
        )
        run = _move(run, "FAILED", "AUDIT_FAIL")
        trail.append("FAILED")
        run_machine.emit_lifecycle_event(
            project_id, run_id, "finish", "FAILED", "audit refused"
        )
        steps.append(
            AssuranceStep(
                leg="audit",
                status="FAILED",
                note=(
                    "audit refused: result %s is not PASS; no finalize"
                    % (seen,)
                ),
            )
        )
        return AssuranceOutcome(
            phase=AUDIT_REFUSED,
            ok=False,
            verification_id=verification_id,
            audit_id=audit_id,
            finalization_id=None,
            records=tuple(steps),
            status_trail=tuple(trail),
        )
    finalization_record = finalizer.Finalizer.finalize_with_records(
        verification_record=verification_record,
        audit_record=audit_record,
        project_id=project_id,
        task_id=task_id,
        run_id=run_id,
        task_state=task_state,
        audit_ref=audit_record,
        verification_ref=verification_record.verification_id,
        output_refs=output_refs,
        metric_refs=metric_refs,
        accounting_complete=accounting_complete,
        budget_settled=budget_settled,
        resources_released=resources_released,
    )
    run_machine.emit_lifecycle_event(
        project_id,
        run_id,
        "record",
        "AUDITING",
        "finalization=%s" % finalization_record.finalization_id,
    )
    run = _move(run, "SUCCEEDED", "COMPLETED")
    trail.append("SUCCEEDED")
    run_machine.emit_lifecycle_event(
        project_id,
        run_id,
        "finish",
        "SUCCEEDED",
        "finalization=%s" % finalization_record.finalization_id,
    )
    steps.append(
        AssuranceStep(
            leg="finalize",
            status="SUCCEEDED",
            note=(
                "finalization=%s verification=%s audit=%s"
                % (
                    finalization_record.finalization_id,
                    verification_id,
                    audit_id,
                )
            ),
        )
    )
    return AssuranceOutcome(
        phase=FINALIZED,
        ok=True,
        verification_id=verification_id,
        audit_id=audit_id,
        finalization_id=finalization_record.finalization_id,
        records=tuple(steps),
        status_trail=tuple(trail),
    )


__all__ = [
    "CHECKER_MODULE",
    "VERIFY_REFUSED",
    "AUDIT_REFUSED",
    "FINALIZED",
    "SHARED_GROUNDING_ENTRY",
    "AssuranceRefused",
    "AssuranceStep",
    "AssuranceOutcome",
    "run_assurance",
]
