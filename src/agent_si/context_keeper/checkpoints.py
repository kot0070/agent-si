"""Lane B STEP2 context checkpoints: pin contract hash plus refs (M-P4-160).

Frozen shapes are reused from
:mod:`agent_si.context_keeper.interface` (never redefined here).
Writes emit the CONTEXT_CHECKPOINT journal row and consult the guard
``check_escape`` before workspace writes. Standard library only.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

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
_FROZEN_NAMES = ("CheckpointRecord",)

def __getattr__(name):
    """Expose frozen row names late (identity with the contract module)."""
    if name in _FROZEN_NAMES:
        return getattr(_ck(), name)
    raise AttributeError(
        "module %r has no attribute %r" % (__name__, name)
    )

#: Reused frozen checkpoint row (identity with the contract module;
#: provided late through __getattr__ above, never redefined here).

#: Model that produced checkpoint rows (M-A provenance pin).
MODEL_ID = "meta/muse-spark-1.3-contributor"

#: Journal source for checkpoint rows (interface module name).
CHECKPOINT_SOURCE = "agent_si.context_keeper.checkpoints"

#: Guard identity used for workspace writes.
GUARD_AGENT_ID = "context-keeper"

#: Deterministic creation stamp; writes are idempotent by content.
_CREATED_AT = "2026-01-01T00:00:00Z"

_HEX_DIGITS = frozenset("0123456789abcdef")


def hash_refs(contract_hash: str, context_refs: Tuple[str, ...]) -> str:
    """Hash the pinned material: contract hash plus ordered refs (P13)."""
    material = contract_hash + "\n" + "\n".join(tuple(context_refs))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _is_hex_digest(value: str) -> bool:
    """Check a 64-char lowercase hex digest (P13 integrity gate)."""
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in _HEX_DIGITS for char in value)
    )


def _checkpoint_id(
    project_id: str,
    task_id: str,
    run_id: Optional[str],
    contract_hash: str,
    context_refs: Tuple[str, ...],
) -> str:
    material = "\n".join(
        [project_id, task_id, run_id or "", contract_hash] + list(context_refs)
    )
    return "chk-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class BenchmarkReport:
    """Save-restore benchmark outcome with sourced-or-UNKNOWN markers."""

    restored_ok: bool
    saved_refs: Tuple[str, ...]
    restored_refs: Tuple[str, ...]
    markers: Tuple[Tuple[str, str], ...]
    sourced_count: int
    unknown_count: int


class Checkpoints:
    """Checkpoint write/read entry points."""

    def __init__(
        self,
        journal_append: Optional[Callable[..., object]] = None,
        guard_check: Optional[Callable[..., object]] = None,
        workspace_root: Optional[str] = None,
    ) -> None:
        self._journal_append = journal_append
        self._guard_check = guard_check
        self._workspace_root = workspace_root
        self._by_id: Dict[str, ck.CheckpointRecord] = {}
        self._order: List[str] = []

    def write_checkpoint(
        self,
        project_id: str,
        task_id: str,
        run_id: Optional[str],
        contract_hash: str,
        context_refs: Tuple[str, ...],
    ) -> ck.CheckpointRecord:
        """Pin contract_hash plus refs; emits CONTEXT_CHECKPOINT row."""
        refs = tuple(context_refs)
        digest = hash_refs(contract_hash, refs)
        if not _is_hex_digest(digest):
            raise ValueError("invalid checkpoint hash: %r" % (digest,))
        checkpoint_id = _checkpoint_id(
            project_id, task_id, run_id, contract_hash, refs
        )
        if self._guard_check is not None:
            path = "%s/%s.json" % (project_id, checkpoint_id)
            verdict = self._guard_check(
                GUARD_AGENT_ID, path, self._workspace_root
            )
            if not getattr(verdict, "allowed", False):
                raise ValueError(
                    "workspace escape blocked: %r"
                    % (getattr(verdict, "reason", path),)
                )
        stored = self._by_id.get(checkpoint_id)
        if stored is not None:
            return stored
        record = _ck().CheckpointRecord(
            checkpoint_id=checkpoint_id,
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            contract_hash=contract_hash,
            context_refs=refs,
            created_at=_CREATED_AT,
            hash=digest,
        )
        self._by_id[checkpoint_id] = record
        self._order.append(checkpoint_id)
        if self._journal_append is not None:
            self._journal_append(
                project_id,
                CHECKPOINT_SOURCE,
                "CONTEXT_CHECKPOINT",
                "context checkpoint %s model %s" % (checkpoint_id, MODEL_ID),
                refs,
            )
        return record

    def read_checkpoint(
        self, checkpoint_id: str
    ) -> Optional[ck.CheckpointRecord]:
        """Return the stored checkpoint row for checkpoint_id, else None."""
        return self._by_id.get(checkpoint_id)

    def latest_for_project(
        self, project_id: str
    ) -> Optional[ck.CheckpointRecord]:
        """Return the last checkpoint written for project_id, else None."""
        for checkpoint_id in reversed(self._order):
            record = self._by_id[checkpoint_id]
            if record.project_id == project_id:
                return record
        return None

    def benchmark_save_restore(
        self,
        project_id: str,
        task_id: str,
        run_id: Optional[str],
        contract_hash: str,
        context_refs: Tuple[str, ...],
        provenance_fn: Callable[[str], str],
    ) -> BenchmarkReport:
        """Save refs to a checkpoint, restore them, mark sourced-or-UNKNOWN."""
        refs = tuple(context_refs)
        written = self.write_checkpoint(
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            contract_hash=contract_hash,
            context_refs=refs,
        )
        restored = self.read_checkpoint(written.checkpoint_id)
        restored_refs = restored.context_refs if restored is not None else ()
        markers = tuple((ref, provenance_fn(ref)) for ref in refs)
        sourced_count = sum(
            1 for _, marker in markers if marker == keeper_register.SOURCED
        )
        unknown_count = sum(
            1 for _, marker in markers if marker == keeper_register.UNKNOWN
        )
        return BenchmarkReport(
            restored_ok=restored is not None
            and tuple(restored_refs) == refs,
            saved_refs=refs,
            restored_refs=tuple(restored_refs),
            markers=markers,
            sourced_count=sourced_count,
            unknown_count=unknown_count,
        )
