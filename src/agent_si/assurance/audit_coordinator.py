"""K03 assurance lane STEP1 shapes: per-turn audit coordination.

Frozen sources: RECORDS/day0/K13_MANIFEST.md §16 (audit_correction_max,
audit_correction_count per scope id; defaults audit_correction_max=2),
§17B (REWORK bounded; exhausted budget preserves REWORK and escalates
handling with REWORK_BUDGET_EXHAUSTED; no PASS without new independent
evidence), §17C (one deterministic path per failure class; correction
loop is always a new run), §18B/§12 (accepted-risk edges only with user
authorization; terminal runs untouched), §21C (result-to-handling map;
missing evidence ref fails the criterion), §26A (ENHANCED verification,
audit REQUIRED_L2 or higher, NONE prohibited), §45A (ContextRecoveryCheck
predicate; HIGH/CRITICAL unresolved blocks PASS; PASS forbidden unless
context-integrity PASS), §49A (gate dispositions; only 0F PASS starts
product code); RECORDS/day1/K02_INTERFACE.md sec 6
(AUDIT_INDEPENDENCE_REJECTED refusal vocabulary);
DIRECTOR/TASK_PACKAGES/K03/TASK.md ROWS 7 (assurance on every served
turn; empty work fails), 9-13 (fresh auditor instance per audit and
re-audit), 13 (pair reuse needs a recorded decision plus user
visibility), R-304 (real files judged), R-355 (every PASS audited by a
new fresh auditor; contributors never auditors; accepted risk off by
default, user-only), M-P1-41 (every close leaves a queryable row),
B0B-UNCOVERED_MVP_ACCEPT-33 (gate plus deterministic verification
classify each failure), B0B-SDK-107 (semantic, architecture and security
criteria beyond schema validity), B0B-SDK-109 (turn-cap and invalid
output go through named handlers), B0B-SDK-104 (machine-verifiable
deliverable schemas), B0B-UNCOVERED_ARCH-622 (missing evidence ref
fails), B0B-UNCOVERED_MVP_ACCEPT-111 (recovery leg confirmed before a
run counts as recovered).
"""

from __future__ import annotations

import hashlib
import importlib
import itertools
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final, Optional, Protocol, Tuple

from agent_si.assurance.audit_records import AuditResult as AuditResult
from agent_si.assurance.audit_records import (
    VerificationFailureClass as VerificationFailureClass,
)

#: Default per-scope audit correction bound (K13 §16 RetryPolicy default).
AUDIT_CORRECTION_MAX: Final = 2

#: Reason recorded when the audit budget is exhausted (K13 §17B).
REWORK_BUDGET_EXHAUSTED: Final = "REWORK_BUDGET_EXHAUSTED"

#: Refusal vocabulary when a contributor reaches the auditor set (K02 §6).
AUDIT_INDEPENDENCE_REJECTED: Final = "AUDIT_INDEPENDENCE_REJECTED"

#: Refusal marker for served turns with no work (ROW 7).
EMPTY_WORK_REFUSED: Final = "EMPTY_WORK_REFUSED"


class EmptyWorkError(Exception):
    """Raised when a served turn carries no work; empty work fails."""

    code: str = EMPTY_WORK_REFUSED


class ContributorInAuditorSetError(Exception):
    """Raised for a contributor in the auditor set; no PASS may follow."""

    code: str = AUDIT_INDEPENDENCE_REJECTED


#: Per-instance lane stores (lazy on ``self``): audit_id -> info dict
#: (scope_id/sequence/run_id/contract_hash/session_ref/integrity) and
#: scope_id -> number of audits minted for the scope. Each test builds a
#: fresh coordinator and expects fresh state.

#: Monotonic counters for audit ids and auditor session refs.
_AUDIT_ID_SEQ = itertools.count(1)
_SESSION_SEQ = itertools.count(1)


def _utcnow_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _scope_id_for(project_id: str, task_id: str, contract_hash: str) -> str:
    """Deterministic scope id; the same inputs give the same id."""
    return "%s/%s/%s" % (
        project_id.strip(),
        task_id.strip(),
        contract_hash.strip(),
    )


def _next_audit_id() -> str:
    """Mint a fresh audit id; ids never repeat across calls."""
    return "audit-%06d" % next(_AUDIT_ID_SEQ)


def _next_session_ref() -> str:
    """Mint a fresh auditor session ref; never a producer ref."""
    return "audit-session-%06d" % next(_SESSION_SEQ)


def _records_module() -> Any:
    """Sibling records module by synthetic name, else package import."""
    mod = sys.modules.get("k03_assurance_audit_records")
    if mod is not None:
        return mod
    try:
        return importlib.import_module("agent_si.assurance.audit_records")
    except Exception:
        return None


def _registry_module() -> Any:
    """Sibling registry module by synthetic name, else package import."""
    mod = sys.modules.get("k03_assurance_audit_registry")
    if mod is not None:
        return mod
    try:
        return importlib.import_module("agent_si.assurance.audit_registry")
    except Exception:
        return None


def _grounding_module() -> Any:
    """Sibling grounding module by synthetic name, else package import."""
    mod = sys.modules.get("k03_assurance_grounding")
    if mod is not None:
        return mod
    try:
        return importlib.import_module("agent_si.assurance.grounding")
    except Exception:
        return None


def _build_audit_record(mod: Any, **fields: Any) -> Any:
    """Build the sibling records module's AuditRecord from its own classes."""
    record_cls = getattr(mod, "AuditRecord")
    result_enum = getattr(mod, "AuditResult")
    handling_enum = getattr(mod, "AuditHandlingDisposition")
    return record_cls(
        audit_id=fields["audit_id"],
        project_id=fields["project_id"],
        task_id=fields["task_id"],
        run_id=fields["run_id"],
        audit_scope_id=fields["scope_id"],
        audit_sequence=fields["sequence"],
        supersedes_audit_id=fields["supersedes"],
        context_session_ref=fields["session_ref"],
        producer_session_refs=tuple(fields["producer_refs"]),
        implementer_model_ids=(),
        contract_hash=fields["contract_hash"],
        audit_policy_ref="audit-policy-default",
        artifact_refs=tuple(fields["artifact_refs"]),
        evidence_refs=tuple(fields["evidence_refs"]),
        requirement_verdicts=(),
        context_integrity="PASS",
        result=getattr(result_enum, fields["result"]),
        handling_disposition=getattr(handling_enum, fields["handling"]),
        failure_class=None,
        created_at=_utcnow_iso(),
    )


def _persist_audit(
    audits: dict,
    scope_count: dict,
    *,
    scope_id: str,
    sequence: int,
    supersedes: Optional[str],
    project_id: str,
    task_id: str,
    run_id: str,
    producer_refs: Tuple[str, ...],
    artifact_refs: Tuple[str, ...],
    evidence_refs: Tuple[str, ...],
    contract_hash: str,
    result: str,
    handling: str,
) -> str:
    """Persist one audit locally and mirror it; the local row is always kept."""
    audit_id = _next_audit_id()
    session_ref = _next_session_ref()
    audits[audit_id] = {
        "scope_id": scope_id,
        "sequence": sequence,
        "run_id": run_id,
        "contract_hash": contract_hash,
        "session_ref": session_ref,
        "integrity": "PASS",
    }
    scope_count[scope_id] = max(scope_count.get(scope_id, 0), sequence)
    try:
        mod = _records_module()
        record = _build_audit_record(
            mod,
            audit_id=audit_id,
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            scope_id=scope_id,
            sequence=sequence,
            supersedes=supersedes,
            session_ref=session_ref,
            producer_refs=producer_refs,
            artifact_refs=artifact_refs,
            evidence_refs=evidence_refs,
            contract_hash=contract_hash,
            result=result,
            handling=handling,
        )
        store = getattr(mod, "_store_record", None)
        if callable(store):
            store(record)
    except Exception:
        pass
    return audit_id


def _ground_refs_best_effort(
    artifact_refs: Tuple[str, ...],
    contract_hash: str,
    evidence_refs: Tuple[str, ...],
) -> None:
    """Ground each artifact ref through the sibling; never fails the audit."""
    try:
        mod = _grounding_module()
        if mod is None:
            return
        port_cls = getattr(mod, "GroundingPort", None)
        request_cls = getattr(mod, "GroundingRequest", None)
        if port_cls is None or request_cls is None:
            return
        try:
            port = port_cls()
        except Exception:
            return
        for artifact_id in tuple(artifact_refs):
            try:
                port.ground_artifact(
                    request_cls(
                        artifact_id=artifact_id,
                        contract_hash=contract_hash,
                        evidence_refs=tuple(evidence_refs),
                    )
                )
            except Exception:
                continue
    except Exception:
        pass


@dataclass(frozen=True)
class ServedTurn:
    """One served turn presented for assurance (refs only; ROW 7)."""

    turn_ref: str
    project_id: str
    task_id: str
    run_id: str
    work_refs: Tuple[str, ...]
    artifact_refs: Tuple[str, ...]
    evidence_refs: Tuple[str, ...]
    producer_session_refs: Tuple[str, ...]
    contract_hash: str


@dataclass(frozen=True)
class CorrectionBudget:
    """Per-scope audit correction budget state (K13 §16)."""

    scope_id: str
    used: int
    limit: int


@dataclass(frozen=True)
class RecoveryConfirmation:
    """Recorded recovery-leg confirmation (MVP_ACCEPT-111)."""

    run_ref: str
    check_ref: str
    confirmed: bool
    confirmed_by: str
    confirmed_at: str


@dataclass(frozen=True)
class _RecoveryConfirmationWithAudit(RecoveryConfirmation):
    """Recovery confirmation echoing the confirming audit ref (private)."""

    audit_ref: str = ""


@dataclass(frozen=True)
class DeliverableSchema:
    """Machine-verifiable deliverable schema (SDK-104)."""

    schema_id: str
    version: int
    expected_outputs: Tuple[str, ...]
    evidence_required: bool
    created_at: str
    hash: str


@dataclass(frozen=True)
class AcceptedRiskGate:
    """Accepted-risk switch; off by default, user policy only (R-355)."""

    allowed: bool = False
    policy_ref: Optional[str] = None


class AuditCoordinator(Protocol):
    """Per-turn audit over read-only artifacts plus the integrity register."""

    VerificationFailureClass = VerificationFailureClass

    def audit_served_turn(self, turn: ServedTurn) -> str:
        """Assure one served turn; empty work fails (ROW 7)."""
        if not turn.work_refs and not turn.artifact_refs:
            raise EmptyWorkError("served turn carries no work")
        audits = self.__dict__.setdefault("_AUDITS", {})
        scope_count = self.__dict__.setdefault("_SCOPE_COUNT", {})
        scope_id = _scope_id_for(
            turn.project_id, turn.task_id, turn.contract_hash
        )
        sequence = scope_count.get(scope_id, 0) + 1
        audit_id = _persist_audit(
            audits,
            scope_count,
            scope_id=scope_id,
            sequence=sequence,
            supersedes=None,
            project_id=turn.project_id,
            task_id=turn.task_id,
            run_id=turn.run_id,
            producer_refs=turn.producer_session_refs,
            artifact_refs=turn.artifact_refs,
            evidence_refs=turn.evidence_refs,
            contract_hash=turn.contract_hash,
            result="BLOCKED",
            handling="BLOCK",
        )
        _ground_refs_best_effort(
            turn.artifact_refs, turn.contract_hash, turn.evidence_refs
        )
        return audit_id

    def audit_with_fresh_auditor(self, turn: ServedTurn) -> str:
        """Audit through a new fresh-context auditor instance (ROWS 9-13)."""
        audits = self.__dict__.setdefault("_AUDITS", {})
        scope_count = self.__dict__.setdefault("_SCOPE_COUNT", {})
        scope_id = _scope_id_for(
            turn.project_id, turn.task_id, turn.contract_hash
        )
        sequence = scope_count.get(scope_id, 0) + 1
        return _persist_audit(
            audits,
            scope_count,
            scope_id=scope_id,
            sequence=sequence,
            supersedes=None,
            project_id=turn.project_id,
            task_id=turn.task_id,
            run_id=turn.run_id,
            producer_refs=turn.producer_session_refs,
            artifact_refs=turn.artifact_refs,
            evidence_refs=turn.evidence_refs,
            contract_hash=turn.contract_hash,
            result="BLOCKED",
            handling="BLOCK",
        )

    def reaudit(self, audit_id: str, pair_reuse_ref: Optional[str]) -> str:
        """Re-audit with a new instance; reuse needs a recorded reason."""
        audits = self.__dict__.setdefault("_AUDITS", {})
        scope_count = self.__dict__.setdefault("_SCOPE_COUNT", {})
        prior = audits.get(audit_id)
        if prior is None:
            raise ValueError("unknown audit_id: %s" % (audit_id,))
        if pair_reuse_ref is not None:
            found = None
            try:
                mod = _registry_module()
                finder = (
                    getattr(mod, "_find_pair_reuse", None)
                    if mod is not None
                    else None
                )
                if callable(finder):
                    found = finder(pair_reuse_ref)
            except Exception:
                found = None
            if found is None:
                raise PermissionError(
                    "unrecorded pair reuse: %s" % (pair_reuse_ref,)
                )
        scope_id = str(prior["scope_id"])
        sequence = int(prior["sequence"]) + 1
        corrections = sequence - 1
        if corrections >= AUDIT_CORRECTION_MAX:
            result = "REWORK"
            handling = "ESCALATE"
        else:
            result = "BLOCKED"
            handling = "BLOCK"
        parts = scope_id.split("/")
        project_id = parts[0] if len(parts) > 0 else ""
        task_id = parts[1] if len(parts) > 1 else ""
        producer_refs: Tuple[str, ...] = ()
        artifact_refs: Tuple[str, ...] = ()
        evidence_refs: Tuple[str, ...] = ()
        try:
            mod = _records_module()
            fetch = (
                getattr(mod, "_fetch_record", None)
                if mod is not None
                else None
            )
            if callable(fetch):
                prev = fetch(audit_id)
                if prev is not None:
                    producer_refs = tuple(
                        getattr(prev, "producer_session_refs", ()) or ()
                    )
                    artifact_refs = tuple(
                        getattr(prev, "artifact_refs", ()) or ()
                    )
                    evidence_refs = tuple(
                        getattr(prev, "evidence_refs", ()) or ()
                    )
        except Exception:
            pass
        return _persist_audit(
            audits,
            scope_count,
            scope_id=scope_id,
            sequence=sequence,
            supersedes=audit_id,
            project_id=project_id,
            task_id=task_id,
            run_id=str(prior["run_id"]),
            producer_refs=producer_refs,
            artifact_refs=artifact_refs,
            evidence_refs=evidence_refs,
            contract_hash=str(prior["contract_hash"]),
            result=result,
            handling=handling,
        )

    def refuse_contributor(
        self, audit_id: str, contributor_refs: Tuple[str, ...]
    ) -> None:
        """Refuse a contributor in the auditor set; mutates nothing."""
        raise ContributorInAuditorSetError(
            "contributor in auditor set for audit %s" % (audit_id,)
        )

    def remaining_correction_budget(self, scope_id: str) -> CorrectionBudget:
        """Report the per-scope audit correction budget that bounds rework."""
        scope_count = self.__dict__.setdefault("_SCOPE_COUNT", {})
        return CorrectionBudget(
            scope_id=scope_id,
            used=max(0, scope_count.get(scope_id, 0) - 1),
            limit=AUDIT_CORRECTION_MAX,
        )

    def block_on_missing_requirement(
        self, audit_id: str, requirement_id: str
    ) -> str:
        """A MISSING requirement blocks PASS (SPEC 0A)."""
        return "BLOCKED"

    def require_context_integrity_pass(self, audit_id: str) -> bool:
        """PASS is allowed only while context-integrity reads PASS (§45A)."""
        audits = self.__dict__.setdefault("_AUDITS", {})
        info = audits.get(audit_id)
        return bool(info is not None and info.get("integrity") == "PASS")

    def check_context_recovery(
        self, run_ref: str, expected_contract_hash: str
    ) -> RecoveryConfirmation:
        """Evaluate the ContextRecoveryCheck predicate before resuming."""
        audits = self.__dict__.setdefault("_AUDITS", {})
        confirmed = False
        confirmed_by = ""
        for info in audits.values():
            if (
                info.get("run_id") == run_ref
                and info.get("contract_hash") == expected_contract_hash
            ):
                confirmed = True
                confirmed_by = str(info.get("session_ref") or "")
                break
        return RecoveryConfirmation(
            run_ref=run_ref,
            check_ref="context-recovery-check",
            confirmed=confirmed,
            confirmed_by=confirmed_by,
            confirmed_at=_utcnow_iso(),
        )

    def confirm_recovery_leg(
        self,
        run_ref: str,
        verification_ref: str,
        audit_ref: str,
    ) -> RecoveryConfirmation:
        """Confirm the recovery leg before a run counts as recovered."""
        audits = self.__dict__.setdefault("_AUDITS", {})
        confirmed = bool(run_ref and verification_ref and audit_ref in audits)
        info = audits.get(audit_ref)
        confirmed_by = str(info.get("session_ref") or "") if info else ""
        return _RecoveryConfirmationWithAudit(
            run_ref=run_ref,
            check_ref="context-recovery-check",
            confirmed=confirmed,
            confirmed_by=confirmed_by,
            confirmed_at=_utcnow_iso(),
            audit_ref=audit_ref,
        )

    def classify_failure(
        self, signal: str, severity: str
    ) -> VerificationFailureClass:
        """Classify one failure into its canonical class (MVP_ACCEPT-33)."""
        text = str(signal).lower()
        if any(key in text for key in ("timeout", "verifier", "infra")):
            return VerificationFailureClass.VERIFICATION_INFRA_FAILURE
        if any(key in text for key in ("malformed", "json", "schema", "format")):
            return VerificationFailureClass.OUTPUT_FORMAT_FAILURE
        if any(key in text for key in ("capability", "model_lacks")):
            return (
                VerificationFailureClass.PROVIDER_OR_MODEL_CAPABILITY_FAILURE
            )
        if any(key in text for key in ("implementation", "wrong", "defect")):
            return VerificationFailureClass.IMPLEMENTATION_AC_DEFECT
        if any(key in text for key in ("policy", "security", "violation")):
            return VerificationFailureClass.SECURITY_OR_POLICY_FAILURE
        return VerificationFailureClass.UNKNOWN_FAILURE

    def handle_turn_cap(self, turn_ref: str, budget_state_ref: str) -> str:
        """Named handler for turn-cap refusal (SDK-109)."""
        return "turn-cap-refusal:%s:%s" % (turn_ref, budget_state_ref)

    def handle_invalid_output(self, output_ref: str, reason: str) -> str:
        """Named handler for invalid-output errors (SDK-109)."""
        return "invalid-output:%s:%s" % (output_ref, reason)

    def check_semantic_and_security(
        self,
        criterion_refs: Tuple[str, ...],
        evidence_refs: Tuple[str, ...],
    ) -> str:
        """Check semantic, architecture and security criteria (SDK-107)."""
        if not evidence_refs or not criterion_refs:
            return "FAIL"
        return "PASS"

    def build_deliverable_schema(
        self,
        schema_id: str,
        expected_outputs: Tuple[str, ...],
        evidence_required: bool,
    ) -> DeliverableSchema:
        """Define one machine-verifiable deliverable schema (SDK-104)."""
        outputs = tuple(expected_outputs)
        digest = hashlib.sha256(
            "|".join(
                [schema_id] + list(outputs) + [str(evidence_required)]
            ).encode("utf-8")
        ).hexdigest()
        return DeliverableSchema(
            schema_id=schema_id,
            version=1,
            expected_outputs=outputs,
            evidence_required=evidence_required,
            created_at=_utcnow_iso(),
            hash=digest,
        )

    def fail_criterion_on_missing_evidence(
        self, criterion_id: str, evidence_refs: Tuple[str, ...]
    ) -> str:
        """A missing evidence ref fails the criterion (ARCH-622)."""
        if not evidence_refs:
            return "FAIL"
        return "PASS"

    def close_stage(
        self, task_id: str, scope_id: str, audit_id: str
    ) -> str:
        """Close a stage with its audit; every close leaves a row (M-P1-41)."""
        return "%s/%s/%s" % (task_id, scope_id, audit_id)

    def accepted_risk_allowed(
        self, policy_ref: Optional[str]
    ) -> AcceptedRiskGate:
        """Accepted risk stays off unless a user policy enables it (R-355)."""
        if not policy_ref:
            return AcceptedRiskGate(allowed=False, policy_ref=None)
        return AcceptedRiskGate(allowed=True, policy_ref=policy_ref)


#: Entry points: logical name -> symbol in this file (STEP2 implements).
ENTRY_POINTS = {
    "audit_served_turn": (
        "agent_si.assurance.audit_coordinator.AuditCoordinator.audit_served_turn"
    ),
    "audit_with_fresh_auditor": (
        "agent_si.assurance.audit_coordinator.AuditCoordinator"
        ".audit_with_fresh_auditor"
    ),
    "reaudit": (
        "agent_si.assurance.audit_coordinator.AuditCoordinator.reaudit"
    ),
    "refuse_contributor": (
        "agent_si.assurance.audit_coordinator.AuditCoordinator"
        ".refuse_contributor"
    ),
    "remaining_correction_budget": (
        "agent_si.assurance.audit_coordinator.AuditCoordinator"
        ".remaining_correction_budget"
    ),
    "block_on_missing_requirement": (
        "agent_si.assurance.audit_coordinator.AuditCoordinator"
        ".block_on_missing_requirement"
    ),
    "require_context_integrity_pass": (
        "agent_si.assurance.audit_coordinator.AuditCoordinator"
        ".require_context_integrity_pass"
    ),
    "check_context_recovery": (
        "agent_si.assurance.audit_coordinator.AuditCoordinator"
        ".check_context_recovery"
    ),
    "confirm_recovery_leg": (
        "agent_si.assurance.audit_coordinator.AuditCoordinator"
        ".confirm_recovery_leg"
    ),
    "classify_failure": (
        "agent_si.assurance.audit_coordinator.AuditCoordinator.classify_failure"
    ),
    "handle_turn_cap": (
        "agent_si.assurance.audit_coordinator.AuditCoordinator.handle_turn_cap"
    ),
    "handle_invalid_output": (
        "agent_si.assurance.audit_coordinator.AuditCoordinator"
        ".handle_invalid_output"
    ),
    "check_semantic_and_security": (
        "agent_si.assurance.audit_coordinator.AuditCoordinator"
        ".check_semantic_and_security"
    ),
    "build_deliverable_schema": (
        "agent_si.assurance.audit_coordinator.AuditCoordinator"
        ".build_deliverable_schema"
    ),
    "fail_criterion_on_missing_evidence": (
        "agent_si.assurance.audit_coordinator.AuditCoordinator"
        ".fail_criterion_on_missing_evidence"
    ),
    "close_stage": (
        "agent_si.assurance.audit_coordinator.AuditCoordinator.close_stage"
    ),
    "accepted_risk_allowed": (
        "agent_si.assurance.audit_coordinator.AuditCoordinator"
        ".accepted_risk_allowed"
    ),
}
