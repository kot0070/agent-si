"""Lane B STEP2 recovery: check before continuation, restore, verify (45A).

Frozen shapes are reused from
:mod:`agent_si.context_keeper.interface` (never redefined here):
``VerifyReport``, ``OK_CODE`` and ``RECOVERY_FAILED_CODE``. Recovery emits
the CONTEXT_RECOVERY journal row and calls ``request_stop`` when a
CRITICAL incident stays unresolved after recovery. Standard library only.
"""

from __future__ import annotations

import datetime
import os
import sys
from typing import Callable, Optional, TYPE_CHECKING

from agent_si.context_keeper import checkpoints as keeper_checkpoints
from agent_si.context_keeper import project_state as keeper_project_state
from agent_si.context_keeper import register as keeper_register

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
_FROZEN_NAMES = ("VerifyReport",)

def __getattr__(name):
    """Expose frozen row names late (identity with the contract module)."""
    if name in _FROZEN_NAMES:
        return getattr(_ck(), name)
    raise AttributeError(
        "module %r has no attribute %r" % (__name__, name)
    )

#: Reused frozen recovery outcome (identity with the contract module;
#: provided late through __getattr__ above, never redefined here).

#: Model that produced recovery rows (M-A provenance pin).
MODEL_ID = "meta/muse-spark-1.3-contributor"

#: Journal source for recovery rows (interface module name).
RECOVERY_SOURCE = "agent_si.context_keeper.recovery"

#: Stop-all reason when CRITICAL stays unresolved after recovery.
STOP_REASON = "critical context incident unresolved after recovery"


def _utc_now_iso() -> str:
    """Call-time UTC stamp in ISO form (never a fixed value)."""
    return datetime.datetime.now(
        datetime.timezone.utc).isoformat().replace("+00:00", "Z")


class Recovery:
    """Recovery check plus recovery entry point (K13 section 45A)."""

    def __init__(
        self,
        register=None,
        checkpoints=None,
        journal_append: Optional[Callable[..., object]] = None,
        request_stop: Optional[Callable[..., object]] = None,
        store_dir=None,
    ) -> None:
        if isinstance(checkpoints, (str, os.PathLike)):
            if store_dir is None:
                store_dir = checkpoints
            checkpoints = None
        if isinstance(register, (str, os.PathLike)):
            if store_dir is None:
                store_dir = register
            register = None
        if store_dir is None and checkpoints is not None:
            store_dir = getattr(checkpoints, "_store_dir", None)
        if register is None:
            register = keeper_register.Register(store_dir=store_dir)
        if checkpoints is None and store_dir is not None:
            checkpoints = keeper_checkpoints.Checkpoints(store_dir=store_dir)
        self._register = register
        self._checkpoints = checkpoints
        self._journal_append = journal_append
        self._request_stop = request_stop

    def verify(self, project_id: str) -> ck.VerifyReport:
        """Check recovery state before continuation.

        ContextRecoveryCheck: OK unless a required ref is missing or
        unavailable, unresolved rows disagree on the contract hash
        (inconsistent active run), or the latest checkpoint (when
        present) is tampered or mismatched; incident severity alone
        never fails (PASS eligibility is a separate gate);
        else CONTEXT_RECOVERY_FAILED.
        """
        rows = self._register.list_unresolved(project_id)
        contract = _ck()
        ok = True
        for row in rows:
            if set(row.expected_context_refs) - set(row.actual_context_refs):
                ok = False
                break
            if row.missing_refs or row.conflicting_refs:
                ok = False
                break
        hashes = {row.contract_hash for row in rows}
        if len(hashes) > 1:
            ok = False
        latest = None
        if self._checkpoints is not None:
            latest = self._checkpoints.latest_for_project(project_id)
        if latest is not None:
            expected_hash = keeper_checkpoints.hash_refs(
                latest.contract_hash, latest.context_refs
            )
            if latest.hash != expected_hash:
                ok = False
            if rows and latest.contract_hash not in hashes:
                ok = False
        return contract.VerifyReport(
            ok=ok,
            code=contract.OK_CODE if ok else contract.RECOVERY_FAILED_CODE,
        )

    def regenerate_project_state(self, project_id: str):
        """Regenerate PROJECT_STATE from keeper records before continuation.

        Read-only R176 assembly over the unresolved register rows, the
        latest validated checkpoint and this recovery's verify outcome.
        """
        return keeper_project_state.regenerate_project_state(
            project_id,
            self._register,
            checkpoints=self._checkpoints,
            verify_report=self.verify(project_id),
        )

    def recover(
        self, project_id: str, checkpoint_id: str
    ) -> ck.VerifyReport:
        """Load the checkpoint, restore covered refs, then verify."""
        contract = _ck()
        self.regenerate_project_state(project_id)
        target = None
        if self._checkpoints is not None:
            target = self._checkpoints.read_checkpoint(checkpoint_id)
        if target is None or target.project_id != project_id:
            self._emit(project_id, checkpoint_id, False)
            return contract.VerifyReport(
                ok=False, code=contract.RECOVERY_FAILED_CODE
            )
        resolved_at = _utc_now_iso()
        for row in self._register.list_unresolved(project_id):
            if set(row.expected_context_refs) <= set(target.context_refs):
                self._register.mark_resolved(
                    row.context_event_id,
                    "recovered from %s" % checkpoint_id,
                    resolved_at,
                )
        report = self.verify(project_id)
        if not report.ok:
            remaining = self._register.list_unresolved(project_id)
            if any(
                row.severity == contract.IncidentSeverity.CRITICAL
                for row in remaining
            ):
                if self._request_stop is not None:
                    self._request_stop(project_id, STOP_REASON)
        self._emit(project_id, checkpoint_id, report.ok)
        return report

    def _emit(
        self, project_id: str, checkpoint_id: str, ok: bool
    ) -> None:
        if self._journal_append is None:
            return
        self._journal_append(
            project_id,
            RECOVERY_SOURCE,
            "CONTEXT_RECOVERY",
            "context recovery %s ok=%s model %s"
            % (checkpoint_id, ok, MODEL_ID),
            (checkpoint_id,),
        )
