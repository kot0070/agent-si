"""Lane B STEP2 context checkpoints: pin contract hash plus refs (M-P4-160).

Frozen shapes are reused from
:mod:`agent_si.context_keeper.interface` (never redefined here).
Writes emit the CONTEXT_CHECKPOINT journal row and consult the guard
``check_escape`` before workspace writes. Standard library only.
"""

from __future__ import annotations

import datetime
import hashlib
import importlib
import json
import os
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

#: Checkpoint rows file name inside a file-backed store dir.
_CHECKPOINTS_FILE = "checkpoints.json"


def _contract():
    """Return the frozen contract module, importing it late when needed."""
    try:
        return sys.modules[_CK_MODULE]
    except KeyError:
        return importlib.import_module(_CK_MODULE)


def _checkpoint_to_dict(record) -> dict:
    """Serialize a frozen checkpoint row to JSON-safe primitives."""
    return {
        "checkpoint_id": record.checkpoint_id,
        "project_id": record.project_id,
        "task_id": record.task_id,
        "run_id": record.run_id,
        "contract_hash": record.contract_hash,
        "context_refs": list(record.context_refs),
        "created_at": record.created_at,
        "hash": record.hash,
    }


def _checkpoint_from_dict(payload):
    """Rebuild the frozen checkpoint row (same class object, never a copy)."""
    contract = _contract()
    return contract.CheckpointRecord(
        checkpoint_id=payload["checkpoint_id"],
        project_id=payload["project_id"],
        task_id=payload["task_id"],
        run_id=payload["run_id"],
        contract_hash=payload["contract_hash"],
        context_refs=tuple(payload["context_refs"]),
        created_at=payload["created_at"],
        hash=payload["hash"],
    )


def _utc_now_iso() -> str:
    """Call-time UTC stamp in ISO form; idempotent writes keep the first."""
    return datetime.datetime.now(
        datetime.timezone.utc).isoformat().replace("+00:00", "Z")

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
        store_dir=None,
    ) -> None:
        self._journal_append = journal_append
        self._guard_check = guard_check
        self._workspace_root = workspace_root
        self._by_id: Dict[str, ck.CheckpointRecord] = {}
        self._order: List[str] = []
        self._store_dir = store_dir
        if store_dir is not None:
            os.makedirs(store_dir, exist_ok=True)
            self._load()

    def _path(self, name):
        return os.path.join(str(self._store_dir), name)

    def _write_json(self, name, payload):
        if self._store_dir is None:
            return
        tmp = self._path(name + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, self._path(name))

    def _load(self):
        try:
            with open(
                self._path(_CHECKPOINTS_FILE), encoding="utf-8"
            ) as fh:
                rows = json.load(fh)
        except FileNotFoundError:
            return
        for payload in rows:
            record = _checkpoint_from_dict(payload)
            checkpoint_id = record.checkpoint_id
            if checkpoint_id not in self._by_id:
                self._by_id[checkpoint_id] = record
                self._order.append(checkpoint_id)

    def _sync(self):
        if self._store_dir is not None:
            self._load()

    def _persist(self):
        self._write_json(
            _CHECKPOINTS_FILE,
            [
                _checkpoint_to_dict(self._by_id[checkpoint_id])
                for checkpoint_id in self._order
            ],
        )

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
            created_at=_utc_now_iso(),
            hash=digest,
        )
        self._by_id[checkpoint_id] = record
        self._order.append(checkpoint_id)
        self._persist()
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
        row = self._by_id.get(checkpoint_id)
        if row is None and self._store_dir is not None:
            self._sync()
            row = self._by_id.get(checkpoint_id)
        return row

    def latest_for_project(
        self, project_id: str
    ) -> Optional[ck.CheckpointRecord]:
        """Return the last checkpoint written for project_id, else None."""
        self._sync()
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
