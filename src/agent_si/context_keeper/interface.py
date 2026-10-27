"""Context-keeper cross-package interface (shapes only, no logic).

Frozen sources: RECORDS/day0/K13_MANIFEST.md sections 45A/45B (read-only;
0C wins clashes), RECORDS/day1/K13_IFACE_STUB.py V5 (shared names exact:
ContextIntegrityRecord fields, CONTEXT_VIOLATION_TYPES order, the
context_recovery_check predicate shape) and RECORDS/day0/0C_ARCHITECTURE.md
section 12 (K08 prefix src/agent_si/context_keeper/). Other packages code
against this module only. Every function body is `...` (no logic); real
behavior lives in the owning lane modules. Standard library only.

Calls out of this surface (referenced, never implemented here):
journal append_event emitting CONTEXT_CHECKPOINT / CONTEXT_RECOVERY,
guard check_escape before workspace writes, stop_all request_stop, and
the K04 budget/router calls get_state, compare_and_reserve, settle,
replay, select, record_fallback (budget observe+notify only; the keeper
never starts or stops external services). Product code imports this
module under TYPE_CHECKING only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple


class ContextViolation(str, Enum):
    """Frozen violation types (K13 section 45A)."""

    CONTEXT_MISSING = "CONTEXT_MISSING"
    CONTEXT_STALE = "CONTEXT_STALE"
    CONTEXT_CONFLICT = "CONTEXT_CONFLICT"
    CONTEXT_TRUNCATED = "CONTEXT_TRUNCATED"
    CONTEXT_UNAUTHORIZED_EXPANSION = "CONTEXT_UNAUTHORIZED_EXPANSION"
    CONTEXT_WRONG_TASK = "CONTEXT_WRONG_TASK"
    CONTEXT_WRONG_CONTRACT_VERSION = "CONTEXT_WRONG_CONTRACT_VERSION"
    CONTEXT_ARTIFACT_UNAVAILABLE = "CONTEXT_ARTIFACT_UNAVAILABLE"
    CONTEXT_RECOVERY_FAILED = "CONTEXT_RECOVERY_FAILED"
    CONTEXT_SUMMARY_DRIFT = "CONTEXT_SUMMARY_DRIFT"


class IncidentSeverity(str, Enum):
    """Shared severity (K13 sections 45A/46)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class ContextIntegrityRecord:
    """Authoritative violation row (names/order exact per K13 V5)."""

    context_event_id: str
    incident_ref: Optional[str]
    project_id: str
    task_id: str
    run_id: Optional[str]
    actor: str
    detected_by: str
    type: str
    severity: IncidentSeverity
    expected_context_refs: Tuple[str, ...]
    actual_context_refs: Tuple[str, ...]
    missing_refs: Tuple[str, ...]
    conflicting_refs: Tuple[str, ...]
    contract_hash: str
    detected_at: str
    impact: str
    resolution: str
    resolved_at: Optional[str]
    evidence_refs: Tuple[str, ...]


@dataclass(frozen=True)
class CheckpointRecord:
    """Pinned context checkpoint row."""

    checkpoint_id: str
    project_id: str
    task_id: str
    run_id: Optional[str]
    contract_hash: str
    context_refs: Tuple[str, ...]
    created_at: str
    hash: str


@dataclass(frozen=True)
class VerifyReport:
    """Recovery check outcome: ok plus a frozen code."""

    ok: bool
    code: str


#: Success code carried by VerifyReport.code.
OK_CODE = "OK"

#: Failure code carried by VerifyReport.code; the caller maps it to
#: BLOCKED/ESCALATED (K13 section 45A).
RECOVERY_FAILED_CODE = "CONTEXT_RECOVERY_FAILED"

#: Journal kind emitted when a checkpoint is written (called, never
#: implemented here).
CHECKPOINT_KIND = "CONTEXT_CHECKPOINT"

#: Journal kind emitted when recovery runs (called, never implemented here).
RECOVERY_KIND = "CONTEXT_RECOVERY"

#: Frozen violation types, order exact per K13 V5 CONTEXT_VIOLATION_TYPES.
CONTEXT_VIOLATION_TYPES = (
    "CONTEXT_MISSING",
    "CONTEXT_STALE",
    "CONTEXT_CONFLICT",
    "CONTEXT_TRUNCATED",
    "CONTEXT_UNAUTHORIZED_EXPANSION",
    "CONTEXT_WRONG_TASK",
    "CONTEXT_WRONG_CONTRACT_VERSION",
    "CONTEXT_ARTIFACT_UNAVAILABLE",
    "CONTEXT_RECOVERY_FAILED",
    "CONTEXT_SUMMARY_DRIFT",
)


@dataclass(frozen=True)
class Register:
    """Verbatim append-only context register (K13 section 45A)."""

    def append(self, record: ContextIntegrityRecord) -> ContextIntegrityRecord:
        """Persist record verbatim; a duplicate idempotent key returns it."""
        ...

    def read(self, context_event_id: str) -> Optional[ContextIntegrityRecord]:
        """Return the stored row for context_event_id, else None."""
        ...

    def list_unresolved(self, project_id: str) -> List[ContextIntegrityRecord]:
        """Return rows of project_id whose resolved_at is None."""
        ...

    def blocking_incidents(self, project_id: str) -> List[ContextIntegrityRecord]:
        """Return unresolved HIGH/CRITICAL rows of project_id."""
        ...


@dataclass(frozen=True)
class Recovery:
    """Recovery check plus recovery entry point (K13 section 45A)."""

    def verify(self, project_id: str) -> VerifyReport:
        """Frozen predicate (K13 V5 context_recovery_check shape): expected
        hash equals recovered hash, required refs available, unresolved
        incidents loaded, latest amendments loaded, active run consistent;
        else code CONTEXT_RECOVERY_FAILED."""
        ...

    def recover(self, project_id: str, checkpoint_id: str) -> VerifyReport:
        """Load the checkpoint, restore refs, then verify; emits the
        CONTEXT_RECOVERY journal row via the journal call."""
        ...


@dataclass(frozen=True)
class Checkpoints:
    """Checkpoint write/read entry points."""

    def write_checkpoint(self, project_id: str, task_id: str,
                         run_id: Optional[str], contract_hash: str,
                         context_refs: Tuple[str, ...]) -> CheckpointRecord:
        """Pin contract_hash plus refs; emits the CONTEXT_CHECKPOINT
        journal row; guard check_escape precedes workspace writes."""
        ...

    def read_checkpoint(self, checkpoint_id: str) -> Optional[CheckpointRecord]:
        """Return the stored checkpoint row for checkpoint_id, else None."""
        ...
