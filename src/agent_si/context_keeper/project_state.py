"""Lane B R176 PROJECT_STATE regeneration (keeper slice).

R176: PROJECT_STATE is DERIVED and MUST be regenerated and validated
from authoritative records before execution continuation. The K08-scope
authoritative records are the keeper rows: unresolved
ContextIntegrityRecords, the latest CheckpointRecord (recomputed-hash
validated) and the recovery verify outcome. Regeneration is read-only
assembly: it writes nothing to the register. Checkpoints whose stored
hash fails recomputation are excluded and reported, never trusted.
Standard library only.
"""

from __future__ import annotations

import datetime
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from agent_si.context_keeper import checkpoints as keeper_checkpoints

if TYPE_CHECKING:
    from agent_si.context_keeper import interface as ck


#: Dotted name of the frozen context-keeper contract module. Product
#: code keeps no static import of it; the module object and the frozen
#: row types are resolved late so the same class objects the keeper
#: tests use are returned.
_CK_MODULE = "agent_si.context_keeper.interface"


def _ck():
    """Return the frozen context-keeper contract module object."""
    try:
        return sys.modules[_CK_MODULE]
    except KeyError:
        raise RuntimeError(
            "frozen contract %r is not imported" % (_CK_MODULE,)
        )


#: Frozen row names re-exported late (same class objects, never copies).
_FROZEN_NAMES = (
    "CheckpointRecord",
    "ContextIntegrityRecord",
    "VerifyReport",
)

def __getattr__(name):
    """Expose frozen row names late (identity with the contract module)."""
    if name in _FROZEN_NAMES:
        return getattr(_ck(), name)
    raise AttributeError(
        "module %r has no attribute %r" % (__name__, name)
    )

#: Reused frozen rows (identity with the contract module;
#: provided late through __getattr__ above, never redefined here).

#: Model that produced regeneration rows (M-A provenance pin).
MODEL_ID = "meta/muse-spark-1.3-contributor"

#: Verify code used when no verify report is supplied.
NOT_VERIFIED_CODE = "NOT_VERIFIED"


def _utc_now_iso() -> str:
    """Call-time UTC stamp in ISO form (never a fixed value)."""
    return datetime.datetime.now(
        datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _blocking_severities():
    """Frozen blocking severities, resolved late (HIGH/CRITICAL)."""
    severe = _ck().IncidentSeverity
    return (severe.HIGH, severe.CRITICAL)


@dataclass(frozen=True)
class ProjectState:
    """Validated PROJECT_STATE derived from keeper records (R176)."""

    project_id: str
    generated_at: str
    unresolved: Tuple[ck.ContextIntegrityRecord, ...]
    refs: Tuple[str, ...]
    contract_hashes: Tuple[str, ...]
    checkpoint: Optional[ck.CheckpointRecord]
    checkpoint_id: Optional[str]
    checkpoint_valid: bool
    excluded: Tuple[str, ...]
    verify_ok: bool
    verify_code: str
    blocked: bool

    def as_mapping(self) -> Dict[str, object]:
        """Return the PROJECT_STATE as a plain mapping."""
        return {
            "project_id": self.project_id,
            "generated_at": self.generated_at,
            "unresolved_ids": tuple(
                row.context_event_id for row in self.unresolved),
            "unresolved_count": len(self.unresolved),
            "refs": self.refs,
            "contract_hashes": self.contract_hashes,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_valid": self.checkpoint_valid,
            "excluded": self.excluded,
            "verify_ok": self.verify_ok,
            "verify_code": self.verify_code,
            "blocked": self.blocked,
        }


def regenerate_project_state(
    project_id: str,
    register,
    checkpoints=None,
    verify_report=None,
) -> ProjectState:
    """Assemble a validated PROJECT_STATE mapping (R176).

    Reads the unresolved register rows plus the latest checkpoint for
    project_id, recomputes the checkpoint hash, and folds in the
    supplied verify outcome. A checkpoint whose stored hash differs
    from the recomputed hash is excluded and reported. Read-only:
    no register writes, no journal writes.
    """
    rows = tuple(register.list_unresolved(project_id))
    refs: List[str] = []
    for row in rows:
        for ref in row.expected_context_refs + row.actual_context_refs:
            if ref not in refs:
                refs.append(ref)
    hashes: List[str] = []
    for row in rows:
        if row.contract_hash not in hashes:
            hashes.append(row.contract_hash)
    latest = None
    if checkpoints is not None:
        latest = checkpoints.latest_for_project(project_id)
    checkpoint = None
    checkpoint_id = None
    checkpoint_valid = True
    excluded: List[str] = []
    if latest is not None:
        checkpoint_id = latest.checkpoint_id
        expected_hash = keeper_checkpoints.hash_refs(
            latest.contract_hash, latest.context_refs)
        if latest.hash != expected_hash:
            checkpoint_valid = False
            excluded.append(
                "checkpoint %s excluded: hash mismatch"
                % latest.checkpoint_id)
        else:
            checkpoint = latest
            for ref in latest.context_refs:
                if ref not in refs:
                    refs.append(ref)
    if verify_report is None:
        verify_ok = False
        verify_code = NOT_VERIFIED_CODE
    else:
        verify_ok = bool(verify_report.ok)
        verify_code = verify_report.code
    blocked = any(row.severity in _blocking_severities() for row in rows)
    return ProjectState(
        project_id=project_id,
        generated_at=_utc_now_iso(),
        unresolved=rows,
        refs=tuple(refs),
        contract_hashes=tuple(hashes),
        checkpoint=checkpoint,
        checkpoint_id=checkpoint_id,
        checkpoint_valid=checkpoint_valid,
        excluded=tuple(excluded),
        verify_ok=verify_ok,
        verify_code=verify_code,
        blocked=blocked,
    )
