"""Finalizer: outcome ONLY from authoritative records.

Manifest sections 21D FINALIZER and 18B COMPLETION_DISPOSITION.

``Finalizer.finalize`` assembles the outcome from authoritative records:
it checks state/audit consistency, binds the exact audit ref
(``audit_ref.result`` MUST equal ``FinalizationRecord.audit_result``),
attaches output ArtifactRefs, requires finalized accounting plus
settled/released budget and resource coverage, and writes an immutable
``FinalizationRecord``. It never rewrites history: every input is only
read, and each call returns a NEW record. Shared names come ONLY from
``iface.frozen_manifest.manifest``; 0C wins on any clash.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Tuple

try:
    from iface.frozen_manifest import manifest
except ImportError:  # alternate layout: the iface/ directory itself on sys.path
    from frozen_manifest import manifest


class FinalizationError(Exception):
    """State/audit/settlement evidence does not support finalization."""


class OverrideRecordStatus(str, Enum):
    """Manifest section 18B override record lifecycle (local: no clash)."""

    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    CANCELLED = "CANCELLED"


CONDITIONAL_OVERRIDE_SOURCES = frozenset(
    {
        manifest.TaskState.REWORK_PENDING,
        manifest.TaskState.BLOCKED,
        manifest.TaskState.ESCALATED,
    }
)
"""Manifest section 12 CONDITIONAL_USER_OVERRIDE_EDGES sources (18B)."""

NOT_RUN_SENTINEL = "NOT_RUN"
"""Never invented: a pre-run finalization carries run_id None (21D)."""


def _as_tuple(value: Any) -> Tuple:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    return tuple(value)


def _coerce_task_state(value: Any) -> manifest.TaskState:
    if isinstance(value, manifest.TaskState):
        return value
    return manifest.TaskState(str(value))


def _coerce_audit_result(value: Any) -> manifest.AuditResult:
    if isinstance(value, manifest.AuditResult):
        return value
    if isinstance(value, Enum):
        # Assurance-lane AuditResult enums are str-mixed, so str() reads
        # 'AuditResult.PASS'; the bound .value coerces to the manifest enum.
        return manifest.AuditResult(value.value)
    return manifest.AuditResult(str(value))


def _coerce_override_status(value: Any) -> OverrideRecordStatus:
    if isinstance(value, OverrideRecordStatus):
        return value
    return OverrideRecordStatus(str(value))


@dataclass(frozen=True)
class OverrideRecord:
    """Manifest section 18B OverrideRecord (authoritative, persistent).

    Never rewrites history: the original AuditResult is preserved and an
    override never fabricates a SUCCEEDED run. ``original_result`` is None
    only when no AuditResult exists yet (pre-audit accepted risk).
    """

    override_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: Optional[str] = None
    created_at: str = ""
    authorized_by: str = ""
    authorization_ref: str = ""
    original_result: Optional[manifest.AuditResult] = None
    override_source_state: Optional[manifest.TaskState] = None
    override_reason: str = ""
    override_action: str = ""
    accepted_risks: Tuple[str, ...] = ()
    evidence_refs: Tuple[str, ...] = ()
    scope: str = ""
    status: OverrideRecordStatus = OverrideRecordStatus.ACTIVE

    def __post_init__(self) -> None:
        if self.original_result is not None and not isinstance(
            self.original_result, manifest.AuditResult
        ):
            object.__setattr__(
                self, "original_result",
                _coerce_audit_result(self.original_result),
            )
        if self.override_source_state is not None and not isinstance(
            self.override_source_state, manifest.TaskState
        ):
            object.__setattr__(
                self, "override_source_state",
                _coerce_task_state(self.override_source_state),
            )
        object.__setattr__(
            self, "status", _coerce_override_status(self.status)
        )
        object.__setattr__(self, "accepted_risks", _as_tuple(self.accepted_risks))
        object.__setattr__(self, "evidence_refs", _as_tuple(self.evidence_refs))


@dataclass(frozen=True)
class FinalizationRecord:
    """Manifest section 21D FinalizationRecord. Immutable, never rewritten."""

    finalization_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: Optional[str] = None
    task_state: manifest.TaskState = manifest.TaskState.CANCELLED
    audit_ref: Any = None
    audit_result: Optional[manifest.AuditResult] = None
    completion_disposition: manifest.CompletionDisposition = (
        manifest.CompletionDisposition.CANCELLED
    )
    override_ref: Optional[OverrideRecord] = None
    verification_ref: Optional[str] = None
    output_refs: Tuple[str, ...] = ()
    metric_refs: Tuple[str, ...] = ()
    completed_at: str = ""
    limitations: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "task_state", _coerce_task_state(self.task_state)
        )
        if self.audit_result is not None and not isinstance(
            self.audit_result, manifest.AuditResult
        ):
            object.__setattr__(
                self, "audit_result",
                _coerce_audit_result(self.audit_result),
            )
        if not isinstance(
            self.completion_disposition, manifest.CompletionDisposition
        ):
            object.__setattr__(
                self, "completion_disposition",
                manifest.CompletionDisposition(str(self.completion_disposition)),
            )
        object.__setattr__(self, "output_refs", _as_tuple(self.output_refs))
        object.__setattr__(self, "metric_refs", _as_tuple(self.metric_refs))
        object.__setattr__(self, "limitations", _as_tuple(self.limitations))


FINALIZATION_MAPPING: Dict[Tuple[str, str], manifest.CompletionDisposition] = {
    ("COMPLETED", "PASS"): manifest.CompletionDisposition.VERIFIED_PASS,
    ("COMPLETED", "OVERRIDE"): manifest.CompletionDisposition.ACCEPTED_RISK,
    ("FAILED", "ANY"): manifest.CompletionDisposition.FAILED,
    ("CANCELLED", "ANY"): manifest.CompletionDisposition.CANCELLED,
}
"""Manifest section 21D mapping.

COMPLETED + audit PASS -> VERIFIED_PASS; COMPLETED + user override ->
ACCEPTED_RISK (original AuditResult preserved); FAILED -> FAILED;
CANCELLED -> CANCELLED. Pre-run (CANCELLED/FAILED before any run) maps
with run_id None; NOT_RUN is never invented.
"""


def completion_disposition_for(
    task_state: Any,
    audit_result: Any = None,
    override: Optional[OverrideRecord] = None,
) -> manifest.CompletionDisposition:
    """Read the FINALIZATION_MAPPING row without building a record."""
    state = _coerce_task_state(task_state)
    if state == manifest.TaskState.COMPLETED:
        if override is not None:
            return FINALIZATION_MAPPING[("COMPLETED", "OVERRIDE")]
        if audit_result is not None and (
            _coerce_audit_result(audit_result) == manifest.AuditResult.PASS
        ):
            return FINALIZATION_MAPPING[("COMPLETED", "PASS")]
        raise FinalizationError(
            "COMPLETED finalizes only with audit PASS or a user override"
        )
    if state == manifest.TaskState.FAILED:
        if override is not None:
            raise FinalizationError("FAILED never converts via override")
        return FINALIZATION_MAPPING[("FAILED", "ANY")]
    if state == manifest.TaskState.CANCELLED:
        if override is not None:
            raise FinalizationError("CANCELLED takes no override")
        return FINALIZATION_MAPPING[("CANCELLED", "ANY")]
    raise FinalizationError(
        "only terminal task states finalize, got %s" % state.value
    )


def _audit_result_of(ref: Any) -> Optional[manifest.AuditResult]:
    """Extract the authoritative result from an audit ref (duck-typed).

    Accepts an object carrying ``.result`` or a mapping with a
    ``"result"`` entry; None passes through as None.
    """
    if ref is None:
        return None
    if isinstance(ref, Mapping):
        raw = ref.get("result")
    else:
        raw = getattr(ref, "result", None)
    if raw is None:
        return None
    return _coerce_audit_result(raw)


class Finalizer:
    """Manifest section 21D Finalizer (K13, pure record assembly)."""

    @staticmethod
    def _check_override(
        override: OverrideRecord, task_state: manifest.TaskState
    ) -> None:
        if not isinstance(override, OverrideRecord):
            raise FinalizationError("override must be an OverrideRecord")
        if override.status != OverrideRecordStatus.ACTIVE:
            raise FinalizationError("override must be ACTIVE")
        if not override.authorized_by or not override.authorization_ref:
            raise FinalizationError(
                "accepted risk needs user authorization + authorization_ref"
            )
        if not override.override_reason:
            raise FinalizationError("accepted risk needs override_reason")
        if not override.accepted_risks:
            raise FinalizationError("accepted risk needs accepted_risks[]")
        source = override.override_source_state
        if source is None or source not in CONDITIONAL_OVERRIDE_SOURCES:
            raise FinalizationError(
                "accepted risk only from a non-terminal override edge "
                "source (REWORK_PENDING, BLOCKED, ESCALATED)"
            )
        if task_state != manifest.TaskState.COMPLETED:
            raise FinalizationError(
                "override completes only to COMPLETED via the canonical edge"
            )

    @staticmethod
    def _check_record_binding(
        *,
        verification_record: Any,
        audit_record: Any,
        project_id: str,
        task_id: str,
        run_id: Optional[str],
        verification_ref: Optional[str],
        audit_ref: Any,
    ) -> None:
        """Require the exact records bound to the finalization inputs.

        No sibling module imports this one, so the record types are
        imported lazily here to keep finalization import-light. Inputs are
        only read; nothing is mutated.
        """
        from agent_si.assurance.audit_records import (
            AuditRecord as _AuditRecord,
        )
        from agent_si.policies.verification import (
            VerificationRecord as _VerificationRecord,
        )

        if verification_record is None:
            raise FinalizationError(
                "record-bound finalization needs verification_record"
            )
        if audit_record is None:
            raise FinalizationError(
                "record-bound finalization needs audit_record"
            )
        if not isinstance(verification_record, _VerificationRecord):
            raise FinalizationError(
                "verification_record must be a VerificationRecord"
            )
        if not isinstance(audit_record, _AuditRecord):
            raise FinalizationError(
                "audit_record must be an AuditRecord"
            )
        if (
            verification_ref is None
            or verification_ref != verification_record.verification_id
        ):
            raise FinalizationError(
                "verification_ref must equal "
                "verification_record.verification_id exactly"
            )
        if audit_ref is None or audit_ref != audit_record:
            raise FinalizationError(
                "audit_ref must be the exact AuditRecord"
            )
        for label, record in (
            ("verification_record", verification_record),
            ("audit_record", audit_record),
        ):
            if record.task_id != task_id or record.project_id != project_id:
                raise FinalizationError(
                    "%s must bind task_id/project_id exactly" % label
                )
            if run_id is None:
                if str(record.run_id or "").strip():
                    raise FinalizationError(
                        "%s must carry a blank run_id for run_id None"
                        % label
                    )
            elif record.run_id != run_id:
                raise FinalizationError(
                    "%s must bind run_id exactly" % label
                )
        if not str(verification_record.contract_hash or "").strip():
            raise FinalizationError(
                "verification_record must commit to a contract_hash"
            )
        if verification_record.contract_hash != audit_record.contract_hash:
            raise FinalizationError(
                "verification_record and audit_record must commit to "
                "the same contract_hash"
            )

    @staticmethod
    def finalize(
        *,
        finalization_id: str = "",
        project_id: str,
        task_id: str,
        run_id: Optional[str] = None,
        task_state: Any,
        audit_result: Any = None,
        audit_ref: Any = None,
        verification_ref: Optional[str] = None,
        override: Optional[OverrideRecord] = None,
        output_refs: Tuple[str, ...] = (),
        metric_refs: Tuple[str, ...] = (),
        accounting_complete: bool = False,
        budget_settled: bool = False,
        resources_released: bool = False,
        limitations: Tuple[str, ...] = (),
        completed_at: str = "",
    ) -> FinalizationRecord:
        """Assemble the outcome from authoritative records only (21D, 18B).

        Checks state/audit consistency, binds the exact audit ref,
        attaches output refs, requires finalized accounting plus
        settled/released budget and resource coverage, and returns a NEW
        immutable FinalizationRecord. History is never rewritten: no input
        is mutated and no run status (notably SUCCEEDED) is fabricated.

        The legacy no-records path behaves exactly as before. Callers that
        must bind the exact VerificationRecord + AuditRecord use
        ``finalize_with_records`` instead (strict record-bound path).
        """
        state = _coerce_task_state(task_state)
        if state not in manifest.TASK_TERMINAL:
            raise FinalizationError(
                "only terminal task states finalize, got %s" % state.value
            )
        if run_id == NOT_RUN_SENTINEL:
            raise FinalizationError(
                "run_id %r is never invented; pre-run uses run_id None"
                % NOT_RUN_SENTINEL
            )
        if run_id is not None and not str(run_id).strip():
            raise FinalizationError("run_id must be a real id or None")

        ref_result = _audit_result_of(audit_ref)
        given = None if audit_result is None else _coerce_audit_result(
            audit_result)
        if ref_result is not None and given is not None and ref_result != given:
            raise FinalizationError(
                "audit_ref.result MUST equal FinalizationRecord.audit_result"
            )
        effective = ref_result if ref_result is not None else given

        if override is not None:
            Finalizer._check_override(override, state)
        if state == manifest.TaskState.FAILED and override is not None:
            raise FinalizationError("FAILED never converts via override")
        if state == manifest.TaskState.COMPLETED:
            if override is None and effective != manifest.AuditResult.PASS:
                raise FinalizationError(
                    "COMPLETED finalizes only with audit PASS or a user "
                    "override"
                )
            if run_id is None:
                raise FinalizationError(
                    "COMPLETED needs a real run_id; pre-run null-run maps "
                    "only to FAILED or CANCELLED"
                )
        if state == manifest.TaskState.FAILED:
            if effective == manifest.AuditResult.PASS:
                raise FinalizationError("FAILED is inconsistent with audit PASS")

        disposition = completion_disposition_for(
            state, effective, override
        )
        if disposition == manifest.CompletionDisposition.VERIFIED_PASS and (
            not tuple(output_refs or ())
        ):
            raise FinalizationError(
                "VERIFIED_PASS needs attached output ArtifactRefs"
            )
        missing = []
        if not accounting_complete:
            missing.append("accounting")
        if not budget_settled:
            missing.append("budget")
        if not resources_released:
            missing.append("resources")
        if missing:
            raise FinalizationError(
                "finalization requires settled " + "+".join(missing)
            )
        return FinalizationRecord(
            finalization_id=finalization_id,
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            task_state=state,
            audit_ref=audit_ref,
            audit_result=effective,
            completion_disposition=disposition,
            override_ref=override,
            verification_ref=verification_ref,
            output_refs=tuple(output_refs or ()),
            metric_refs=tuple(metric_refs or ()),
            completed_at=completed_at,
            limitations=tuple(limitations or ()),
        )

    @staticmethod
    def finalize_with_records(
        *,
        verification_record: Any = None,
        audit_record: Any = None,
        finalization_id: str = "",
        project_id: str,
        task_id: str,
        run_id: Optional[str] = None,
        task_state: Any,
        audit_result: Any = None,
        audit_ref: Any = None,
        verification_ref: Optional[str] = None,
        override: Optional[OverrideRecord] = None,
        output_refs: Tuple[str, ...] = (),
        metric_refs: Tuple[str, ...] = (),
        accounting_complete: bool = False,
        budget_settled: bool = False,
        resources_released: bool = False,
        limitations: Tuple[str, ...] = (),
        completed_at: str = "",
    ) -> FinalizationRecord:
        """Strict record-bound finalization (21D, 18B; ARCH-641/642).

        Both exact records are required: refs/hashes must bind to the
        finalization inputs via ``_check_record_binding``, and any
        missing/mismatched record refuses with FinalizationError (a
        missing record refuses with FinalizationError, never TypeError).
        On success delegates to ``finalize`` without record kwargs.
        """
        Finalizer._check_record_binding(
            verification_record=verification_record,
            audit_record=audit_record,
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            verification_ref=verification_ref,
            audit_ref=audit_ref,
        )
        return Finalizer.finalize(
            finalization_id=finalization_id,
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            task_state=task_state,
            audit_result=audit_result,
            audit_ref=audit_ref,
            verification_ref=verification_ref,
            override=override,
            output_refs=output_refs,
            metric_refs=metric_refs,
            accounting_complete=accounting_complete,
            budget_settled=budget_settled,
            resources_released=resources_released,
            limitations=limitations,
            completed_at=completed_at,
        )


__all__ = [
    "FinalizationError",
    "OverrideRecordStatus",
    "CONDITIONAL_OVERRIDE_SOURCES",
    "NOT_RUN_SENTINEL",
    "OverrideRecord",
    "FinalizationRecord",
    "FINALIZATION_MAPPING",
    "completion_disposition_for",
    "Finalizer",
]
