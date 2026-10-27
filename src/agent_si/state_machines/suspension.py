"""Suspension runtime + quarantine + late-result reconciliation (Manifest section 12).

Entering BLOCKED / ESCALATED with live work halts new attempts and side
effects, marks runs SUSPENDED_BY_TASK, and quarantines late or
uncancellable results (LATE_AFTER_SUSPENSION -> QUARANTINED, never
auto-resume; quarantine survives restart; committed side effects stay
authoritative). Resume needs ContextRecoveryCheck + AttemptExecutionGate +
ownership / budget / authorization revalidation; cancelled or finished
attempts never reopen. Late results reconcile only via an explicit
Director / authorized-controller decision that never reopens terminals
and never auto-resumes.

Enum names and values come ONLY from the section-12 vocabulary
(RunSuspensionState, AttemptResultDisposition, LateResultDecision); the
``status`` field carries the local OPEN / RESOLVED convention the manifest
leaves open. Manifest Context* errors are reused where their gates apply.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

try:
    from iface.frozen_manifest import manifest
except ImportError:  # alternate layout: the iface/ directory itself on sys.path
    from frozen_manifest import manifest


class RunSuspensionState(str, Enum):
    """Manifest section 12 RunSuspensionState."""

    NONE = "NONE"
    SUSPENDED_BY_TASK = "SUSPENDED_BY_TASK"


class AttemptResultDisposition(str, Enum):
    """Manifest section 12 AttemptResultDisposition."""

    NORMAL = "NORMAL"
    LATE_AFTER_SUSPENSION = "LATE_AFTER_SUSPENSION"
    QUARANTINED = "QUARANTINED"
    RECONCILED_ACCEPTED = "RECONCILED_ACCEPTED"
    RECONCILED_REJECTED = "RECONCILED_REJECTED"


class LateResultDecision(str, Enum):
    """Manifest section 12 LateResultDecision."""

    ACCEPT_AS_EVIDENCE = "ACCEPT_AS_EVIDENCE"
    REJECT = "REJECT"
    SUPERSEDED = "SUPERSEDED"


class SuspensionError(Exception):
    """Unknown suspension, duplicate id, or illegal quarantine step."""


class ReconciliationRejectedError(SuspensionError):
    """A late-result reconciliation decision was refused."""


class ResumeRefusedError(SuspensionError):
    """Resume blocked: gates unmet or attempt already finished."""


OPEN = "OPEN"
RESOLVED = "RESOLVED"
"""Local SuspensionRecord.status convention (manifest leaves status open)."""


def _coerce_state(value: Any) -> Optional[manifest.TaskState]:
    if value is None or isinstance(value, manifest.TaskState):
        return value
    try:
        return manifest.TaskState(str(value))
    except ValueError:
        return None


@dataclasses.dataclass(frozen=True)
class SuspensionRecord:
    """Manifest section 12 SuspensionRecord (authoritative, persistent)."""

    suspension_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: Optional[str] = None
    attempt_id: Optional[str] = None
    source_task_state: Any = None
    reason: str = ""
    started_at: str = ""
    resolved_at: Optional[str] = None
    run_suspension_state: RunSuspensionState = RunSuspensionState.SUSPENDED_BY_TASK
    late_result_disposition: Optional[AttemptResultDisposition] = None
    evidence_refs: Tuple[str, ...] = ()
    status: str = OPEN

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_task_state", _coerce_state(self.source_task_state))
        if isinstance(self.run_suspension_state, str) and not isinstance(
            self.run_suspension_state, RunSuspensionState
        ):
            object.__setattr__(
                self, "run_suspension_state", RunSuspensionState(self.run_suspension_state)
            )
        if isinstance(self.late_result_disposition, str) and not isinstance(
            self.late_result_disposition, AttemptResultDisposition
        ):
            object.__setattr__(
                self,
                "late_result_disposition",
                AttemptResultDisposition(self.late_result_disposition),
            )
        if not isinstance(self.evidence_refs, tuple):
            object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs or ()))


@dataclasses.dataclass(frozen=True)
class LateResultReconciliationRecord:
    """Manifest section 12 LateResultReconciliationRecord (explicit decision only)."""

    reconciliation_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: str = ""
    attempt_id: str = ""
    suspension_id: str = ""
    late_output_refs: Tuple[str, ...] = ()
    decision: Any = None
    decided_by: str = ""
    decided_at: str = ""
    reason: str = ""
    verification_ref: Optional[str] = None
    evidence_refs: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.decision, str) and not isinstance(self.decision, LateResultDecision):
            object.__setattr__(self, "decision", LateResultDecision(self.decision))
        if not isinstance(self.late_output_refs, tuple):
            object.__setattr__(
                self, "late_output_refs", tuple(self.late_output_refs or ())
            )
        if not isinstance(self.evidence_refs, tuple):
            object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs or ()))


@dataclasses.dataclass(frozen=True)
class QuarantinedResult:
    """A late attempt result held outside the execution path until reconciled."""

    quarantine_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: str = ""
    attempt_id: str = ""
    suspension_id: str = ""
    output_refs: Tuple[str, ...] = ()
    contract_hash: str = ""
    disposition: AttemptResultDisposition = AttemptResultDisposition.LATE_AFTER_SUSPENSION
    quarantined_at: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.disposition, str) and not isinstance(
            self.disposition, AttemptResultDisposition
        ):
            object.__setattr__(
                self, "disposition", AttemptResultDisposition(self.disposition)
            )
        if not isinstance(self.output_refs, tuple):
            object.__setattr__(self, "output_refs", tuple(self.output_refs or ()))


@dataclasses.dataclass(frozen=True)
class ResumeReadiness:
    """Resume gates: ContextRecoveryCheck + AttemptExecutionGate + revalidations."""

    context_recovery_check: bool = False
    attempt_execution_gate: bool = False
    ownership_revalidated: bool = False
    budget_revalidated: bool = False
    authorization_revalidated: bool = False

    def ready(self) -> bool:
        """True only when every gate and revalidation holds."""
        return bool(
            self.context_recovery_check
            and self.attempt_execution_gate
            and self.ownership_revalidated
            and self.budget_revalidated
            and self.authorization_revalidated
        )


def _coerce_attempt_status(value: Any) -> Any:
    if isinstance(value, manifest.ExecutionAttemptStatus):
        return value
    try:
        return manifest.ExecutionAttemptStatus(str(value))
    except ValueError:
        return str(value)


class QuarantineStore:
    """In-memory quarantine with persistent-shape records (restart-safe via export)."""

    def __init__(self) -> None:
        self._suspensions: Dict[str, SuspensionRecord] = {}
        self._quarantined: Dict[str, QuarantinedResult] = {}
        self._reconciliations: Dict[str, LateResultReconciliationRecord] = {}
        self._committed: Tuple[str, ...] = ()

    @property
    def committed_outputs(self) -> Tuple[str, ...]:
        """Committed side effects stay authoritative; quarantine never removes them."""
        return self._committed

    def note_committed_output(self, ref: str) -> None:
        """Record an already-committed side-effect ref (authoritative, kept)."""
        if ref not in self._committed:
            self._committed = self._committed + (ref,)

    def open_suspension(
        self,
        *,
        suspension_id: str,
        project_id: str,
        task_id: str,
        run_id: Optional[str] = None,
        attempt_id: Optional[str] = None,
        source_task_state: Any = None,
        reason: str = "",
        started_at: str = "",
        evidence_refs: Tuple[str, ...] = (),
    ) -> SuspensionRecord:
        """Enter BLOCKED/ESCALATED with live work: halt attempts, mark suspended."""
        if suspension_id in self._suspensions:
            raise SuspensionError("duplicate suspension_id")
        record = SuspensionRecord(
            suspension_id=suspension_id,
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            attempt_id=attempt_id,
            source_task_state=source_task_state,
            reason=reason,
            started_at=started_at,
            run_suspension_state=RunSuspensionState.SUSPENDED_BY_TASK,
            evidence_refs=tuple(evidence_refs or ()),
            status=OPEN,
        )
        self._suspensions[suspension_id] = record
        return record

    def active_suspension_for(self, task_id: str) -> Optional[SuspensionRecord]:
        """Latest OPEN suspension for a task, or None (never inferred across tasks)."""
        for record in reversed(list(self._suspensions.values())):
            if record.task_id == task_id and record.status == OPEN:
                return record
        return None

    def is_halted(self, task_id: str) -> bool:
        """True while an OPEN suspension halts new attempts and side effects."""
        return self.active_suspension_for(task_id) is not None

    def report_late_result(
        self,
        *,
        project_id: str,
        task_id: str,
        run_id: str,
        attempt_id: str,
        output_refs: Tuple[str, ...] = (),
        contract_hash: str = "",
        quarantined_at: str = "",
        suspension_id: Optional[str] = None,
    ) -> QuarantinedResult:
        """A result arriving after suspension: LATE_AFTER_SUSPENSION, never resumed."""
        suspension = None
        if suspension_id is not None:
            suspension = self._suspensions.get(suspension_id)
        else:
            suspension = self.active_suspension_for(task_id)
        if suspension is None or suspension.status != OPEN:
            return QuarantinedResult(
                quarantine_id="%s:late:%s:normal" % (task_id, attempt_id),
                project_id=project_id,
                task_id=task_id,
                run_id=run_id,
                attempt_id=attempt_id,
                suspension_id=suspension.suspension_id if suspension else "",
                output_refs=tuple(output_refs or ()),
                contract_hash=contract_hash,
                disposition=AttemptResultDisposition.NORMAL,
                quarantined_at=quarantined_at,
            )
        quarantine_id = "%s:late:%s:%d" % (task_id, attempt_id, len(self._quarantined) + 1)
        late = QuarantinedResult(
            quarantine_id=quarantine_id,
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            attempt_id=attempt_id,
            suspension_id=suspension.suspension_id,
            output_refs=tuple(output_refs or ()),
            contract_hash=contract_hash,
            disposition=AttemptResultDisposition.LATE_AFTER_SUSPENSION,
            quarantined_at=quarantined_at,
        )
        self._quarantined[quarantine_id] = late
        self._suspensions[suspension.suspension_id] = dataclasses.replace(
            suspension,
            late_result_disposition=AttemptResultDisposition.LATE_AFTER_SUSPENSION,
        )
        return late

    def quarantined_result(self, quarantine_id: str) -> QuarantinedResult:
        """Read one held result by id."""
        try:
            return self._quarantined[quarantine_id]
        except KeyError:
            raise SuspensionError("unknown quarantine_id")

    def quarantine_result(self, quarantine_id: str) -> QuarantinedResult:
        """Move LATE_AFTER_SUSPENSION -> QUARANTINED; suspension stays OPEN."""
        late = self.quarantined_result(quarantine_id)
        if late.disposition != AttemptResultDisposition.LATE_AFTER_SUSPENSION:
            raise SuspensionError("only a late result can be quarantined")
        held = dataclasses.replace(late, disposition=AttemptResultDisposition.QUARANTINED)
        self._quarantined[quarantine_id] = held
        suspension = self._suspensions.get(late.suspension_id)
        if suspension is not None and suspension.status == OPEN:
            self._suspensions[suspension.suspension_id] = dataclasses.replace(
                suspension,
                late_result_disposition=AttemptResultDisposition.QUARANTINED,
            )
        return held

    def reconcile(
        self,
        *,
        reconciliation_id: str,
        project_id: str,
        task_id: str,
        run_id: str,
        attempt_id: str,
        suspension_id: str,
        quarantine_id: str,
        late_output_refs: Tuple[str, ...] = (),
        decision: Any = None,
        decided_by: str = "",
        authorized: bool = False,
        decided_at: str = "",
        reason: str = "",
        contract_hash: str = "",
        expected_contract_hash: str = "",
        has_superseding_output: bool = False,
        verification_ref: Optional[str] = None,
        policy_pass: bool = False,
        attempt_terminal: bool = False,
        task_terminal: bool = False,
        evidence_refs: Tuple[str, ...] = (),
    ) -> LateResultReconciliationRecord:
        """Decide one quarantined late result; never reopens, never auto-resumes."""
        if isinstance(decision, str) and not isinstance(decision, LateResultDecision):
            try:
                decision = LateResultDecision(decision)
            except ValueError:
                raise ReconciliationRejectedError("unknown late-result decision")
        if not isinstance(decision, LateResultDecision):
            raise ReconciliationRejectedError("unknown late-result decision")
        if not authorized:
            raise ReconciliationRejectedError("Director or authorized controller only")
        suspension = self._suspensions.get(suspension_id)
        if suspension is None:
            raise ReconciliationRejectedError("unknown suspension_id")
        if attempt_terminal or task_terminal:
            raise ReconciliationRejectedError("reconciliation never reopens terminals")
        late = self._quarantined.get(quarantine_id)
        if late is None or late.disposition != AttemptResultDisposition.QUARANTINED:
            raise ReconciliationRejectedError("only a quarantined result can reconcile")
        if decision == LateResultDecision.ACCEPT_AS_EVIDENCE:
            if contract_hash != expected_contract_hash:
                raise manifest.ContextWrongContractVersionError(
                    "late output under a superseded contract"
                )
            if has_superseding_output:
                raise ReconciliationRejectedError("a superseding output already exists")
            if not verification_ref:
                raise manifest.ContextMissingError("ACCEPT needs completed verification")
            if not policy_pass:
                raise manifest.PolicyConflictError("ACCEPT needs a policy pass")
            settled = AttemptResultDisposition.RECONCILED_ACCEPTED
        else:
            settled = AttemptResultDisposition.RECONCILED_REJECTED
        self._quarantined[quarantine_id] = dataclasses.replace(late, disposition=settled)
        record = LateResultReconciliationRecord(
            reconciliation_id=reconciliation_id,
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            attempt_id=attempt_id,
            suspension_id=suspension_id,
            late_output_refs=tuple(late_output_refs or ()),
            decision=decision,
            decided_by=decided_by,
            decided_at=decided_at,
            reason=reason,
            verification_ref=verification_ref,
            evidence_refs=tuple(evidence_refs or ()),
        )
        self._reconciliations[reconciliation_id] = record
        return record

    def resume_suspension(
        self,
        suspension_id: str,
        readiness: ResumeReadiness,
        *,
        attempt_status: Any,
        resolved_at: str = "",
    ) -> SuspensionRecord:
        """Resolve one suspension after all resume gates pass; finished attempts stay shut."""
        suspension = self._suspensions.get(suspension_id)
        if suspension is None:
            raise SuspensionError("unknown suspension_id")
        if suspension.status != OPEN:
            raise ResumeRefusedError("suspension is not open")
        if not readiness.ready():
            raise ResumeRefusedError("ContextRecoveryCheck + gate + revalidations required")
        if _coerce_attempt_status(attempt_status) in manifest.ATTEMPT_TERMINAL:
            raise ResumeRefusedError("cancelled or finished attempts never reopen")
        resolved = dataclasses.replace(suspension, status=RESOLVED, resolved_at=resolved_at)
        self._suspensions[suspension_id] = resolved
        return resolved

    def export_records(self) -> Dict[str, Any]:
        """Persistent-shape snapshot; import into a fresh store after restart."""

        def _dump(record: Any) -> Dict[str, Any]:
            data = dataclasses.asdict(record)
            for key, value in list(data.items()):
                if isinstance(value, Enum):
                    data[key] = value.value
            return data

        return {
            "suspensions": [_dump(r) for r in self._suspensions.values()],
            "quarantined": [_dump(r) for r in self._quarantined.values()],
            "reconciliations": [_dump(r) for r in self._reconciliations.values()],
            "committed": list(self._committed),
        }

    @classmethod
    def import_records(cls, snapshot: Dict[str, Any]) -> "QuarantineStore":
        """Restore a store from an export_records snapshot."""
        store = cls()
        for data in snapshot.get("suspensions", []):
            record = SuspensionRecord(**data)
            store._suspensions[record.suspension_id] = record
        for data in snapshot.get("quarantined", []):
            late = QuarantinedResult(**data)
            store._quarantined[late.quarantine_id] = late
        for data in snapshot.get("reconciliations", []):
            record = LateResultReconciliationRecord(**data)
            store._reconciliations[record.reconciliation_id] = record
        for ref in snapshot.get("committed", []):
            store.note_committed_output(ref)
        return store
