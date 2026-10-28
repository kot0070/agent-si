"""External-action idempotency (Manifest section 19A).

ActionExecution records carry an idempotency_key. Rules enforced here:

- no blind duplicates of messages, POST mutations, issue/PR actions,
  remote writes, or charges;
- provider idempotency keys where supported, else persist + verify prior
  external state before any repeat;
- retry of an unprotected mutation (no key, or no replay protection) is
  prohibited and raises UnprotectedMutationError;
- a duplicate registration returns the stored record (idempotent replay);
- a settled (terminal) record is never settled twice.

Prior-state verification: a repeat is permitted only when the observed
external state matches the state recorded on the action; a mismatch raises
PriorStateMismatchError instead of re-executing blindly.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Union


class ActionExecutionStatus(str, Enum):
    """Manifest section 19A ActionExecutionStatus."""

    CREATED = "CREATED"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN_EXTERNAL_STATE = "UNKNOWN_EXTERNAL_STATE"


TERMINAL_STATUSES = frozenset(
    {
        ActionExecutionStatus.SUCCEEDED,
        ActionExecutionStatus.FAILED,
        ActionExecutionStatus.CANCELLED,
    }
)
"""Settled records; never transition out (never-double-settle)."""

_ALLOWED_TRANSITIONS = {
    ActionExecutionStatus.CREATED: frozenset({ActionExecutionStatus.IN_PROGRESS}),
    ActionExecutionStatus.IN_PROGRESS: frozenset(
        {
            ActionExecutionStatus.SUCCEEDED,
            ActionExecutionStatus.FAILED,
            ActionExecutionStatus.CANCELLED,
            ActionExecutionStatus.UNKNOWN_EXTERNAL_STATE,
        }
    ),
    ActionExecutionStatus.UNKNOWN_EXTERNAL_STATE: frozenset(
        {ActionExecutionStatus.IN_PROGRESS}
    ),
    ActionExecutionStatus.SUCCEEDED: frozenset(),
    ActionExecutionStatus.FAILED: frozenset(),
    ActionExecutionStatus.CANCELLED: frozenset(),
}


class UnprotectedMutationError(Exception):
    """Retry/register of a mutation with no idempotency/replay protection."""


class PriorStateMismatchError(Exception):
    """Observed external state differs from the recorded prior state: no repeat."""


class AlreadySettledError(Exception):
    """A terminal ActionExecution was settled twice (never-double-settle)."""


class ActionTransitionError(Exception):
    """Illegal ActionExecutionStatus transition."""


def _coerce_status(value: object) -> ActionExecutionStatus:
    if isinstance(value, ActionExecutionStatus):
        return value
    return ActionExecutionStatus(str(value))


@dataclass(frozen=True)
class ActionExecution:
    """Manifest section 19A ActionExecution. Immutable; repeats are new reads.

    D2 decision (KEEP): ``prior_state`` (default "") and ``protected``
    (default True) are manifest section 19A behaviour -- prior-state
    verification before any repeat and the unprotected-mutation
    prohibition. Both keep non-breaking defaults so existing callers
    constructing ActionExecution without them are unaffected.
    """

    action_id: str
    project_id: str
    task_id: str
    run_id: str
    idempotency_key: str
    authorization_ref: str = ""
    attempt: int = 1
    status: ActionExecutionStatus = ActionExecutionStatus.CREATED
    external_ref: Optional[str] = None
    prior_state: str = ""
    protected: bool = True
    created_at: str = ""
    completed_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", _coerce_status(self.status))


def derive_idempotency_key(
    *,
    project_id: str,
    task_id: str,
    action: str,
    payload_hash: str,
    contract_hash: str = "",
) -> str:
    """Deterministic key: same inputs always yield the same key (one action, one key)."""
    canonical = "|".join(
        (project_id, task_id, action, payload_hash, contract_hash)
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _to_record(execution: ActionExecution) -> Dict[str, object]:
    return {
        "action_id": execution.action_id,
        "project_id": execution.project_id,
        "task_id": execution.task_id,
        "run_id": execution.run_id,
        "idempotency_key": execution.idempotency_key,
        "authorization_ref": execution.authorization_ref,
        "attempt": execution.attempt,
        "status": execution.status.value,
        "external_ref": execution.external_ref,
        "prior_state": execution.prior_state,
        "protected": execution.protected,
        "created_at": execution.created_at,
        "completed_at": execution.completed_at,
    }


def _from_record(record: Dict[str, object]) -> ActionExecution:
    data = dict(record)
    data["status"] = _coerce_status(data.get("status", ActionExecutionStatus.CREATED))
    return ActionExecution(
        action_id=str(data.get("action_id", "")),
        project_id=str(data.get("project_id", "")),
        task_id=str(data.get("task_id", "")),
        run_id=str(data.get("run_id", "")),
        idempotency_key=str(data.get("idempotency_key", "")),
        authorization_ref=str(data.get("authorization_ref", "")),
        attempt=int(data.get("attempt", 1)),
        status=data["status"],
        external_ref=data.get("external_ref"),
        prior_state=str(data.get("prior_state", "")),
        protected=bool(data.get("protected", True)),
        created_at=str(data.get("created_at", "")),
        completed_at=str(data.get("completed_at", "")),
    )


class ActionLog:
    """Append-only, restart-safe ActionExecution registry keyed by idempotency key.

    Duplicate registration returns the stored record (idempotent replay, no
    blind duplicate). State persists atomically (tmp file + replace + fsync)
    and reloads on construction.
    """

    def __init__(self, path: Union[str, Path]) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()

    def _load(self) -> Dict[str, Dict[str, object]]:
        try:
            text = self._path.read_bytes().decode("utf-8")
        except FileNotFoundError:
            return {}
        try:
            doc = json.loads(text)
        except ValueError as exc:
            raise ValueError("action log at %s is not valid JSON: %s" % (self._path, exc))
        if not isinstance(doc, dict) or not isinstance(doc.get("actions"), dict):
            raise ValueError("action log at %s has no 'actions' object" % self._path)
        return {str(key): value for key, value in doc["actions"].items()}

    def _save(self, actions: Dict[str, Dict[str, object]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        payload = json.dumps(
            {"version": 1, "actions": actions},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        with open(tmp, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self._path)

    def register(self, execution: ActionExecution) -> ActionExecution:
        """Persist a new action, or return the stored record for a duplicate key.

        Empty idempotency key or protected=False raises
        UnprotectedMutationError: unprotected mutations are never registered
        for blind retry.
        """
        if not execution.idempotency_key:
            raise UnprotectedMutationError(
                "refusing unprotected mutation action %r: no idempotency key"
                % execution.action_id
            )
        if not execution.protected:
            raise UnprotectedMutationError(
                "refusing unprotected mutation action %r: no replay protection"
                % execution.action_id
            )
        with self._lock:
            actions = self._load()
            stored = actions.get(execution.idempotency_key)
            if stored is not None:
                return _from_record(stored)
            actions[execution.idempotency_key] = _to_record(execution)
            self._save(actions)
            return execution

    def lookup(self, idempotency_key: str) -> Optional[ActionExecution]:
        """Stored record for a key, or None (restart-safe read)."""
        with self._lock:
            stored = self._load().get(idempotency_key)
            return _from_record(stored) if stored is not None else None

    def begin(self, idempotency_key: str) -> ActionExecution:
        """Move CREATED -> IN_PROGRESS; any other source state raises."""
        with self._lock:
            actions = self._load()
            stored = actions.get(idempotency_key)
            if stored is None:
                raise UnprotectedMutationError(
                    "no persisted action for key %r: blind start prohibited"
                    % idempotency_key
                )
            current = _from_record(stored)
            if current.status != ActionExecutionStatus.CREATED:
                raise ActionTransitionError(
                    "begin allowed only from CREATED, got %s" % current.status.value
                )
            progressed = ActionExecution(
                **{**_to_record(current), "status": ActionExecutionStatus.IN_PROGRESS}
            )
            actions[idempotency_key] = _to_record(progressed)
            self._save(actions)
            return progressed

    def settle(
        self,
        idempotency_key: str,
        status: Union[str, ActionExecutionStatus],
        *,
        external_ref: Optional[str] = None,
        completed_at: str = "",
    ) -> ActionExecution:
        """Settle once into a terminal status; a second settle raises."""
        target = _coerce_status(status)
        if target not in TERMINAL_STATUSES:
            raise ActionTransitionError(
                "settle requires a terminal status, got %s" % target.value
            )
        with self._lock:
            actions = self._load()
            stored = actions.get(idempotency_key)
            if stored is None:
                raise UnprotectedMutationError(
                    "no persisted action for key %r: blind settle prohibited"
                    % idempotency_key
                )
            current = _from_record(stored)
            if current.status in TERMINAL_STATUSES:
                raise AlreadySettledError(
                    "action %r already settled as %s: never-double-settle"
                    % (current.action_id, current.status.value)
                )
            if target not in _ALLOWED_TRANSITIONS[current.status]:
                raise ActionTransitionError(
                    "cannot settle %s -> %s"
                    % (current.status.value, target.value)
                )
            settled = ActionExecution(
                **{
                    **_to_record(current),
                    "status": target,
                    "external_ref": external_ref
                    if external_ref is not None
                    else current.external_ref,
                    "completed_at": completed_at or current.completed_at,
                }
            )
            actions[idempotency_key] = _to_record(settled)
            self._save(actions)
            return settled

    def verify_repeat(
        self, idempotency_key: str, observed_prior_state: str
    ) -> ActionExecution:
        """Permit a repeat only with protection + matching prior external state.

        Unknown key or unprotected record -> UnprotectedMutationError (no
        blind retry of unprotected mutation). Protected record with differing
        recorded prior state -> PriorStateMismatchError. Match returns the
        stored record for idempotent replay.
        """
        with self._lock:
            stored = self._load().get(idempotency_key)
            if stored is None:
                raise UnprotectedMutationError(
                    "no persisted action for key %r: blind repeat prohibited"
                    % idempotency_key
                )
            current = _from_record(stored)
            if not current.protected:
                raise UnprotectedMutationError(
                    "action %r has no replay protection: repeat prohibited"
                    % current.action_id
                )
            if current.prior_state != observed_prior_state:
                raise PriorStateMismatchError(
                    "prior external state changed for action %r: recorded %r "
                    "vs observed %r; verify before any repeat"
                    % (current.action_id, current.prior_state, observed_prior_state)
                )
            return current


__all__ = [
    "ActionExecutionStatus",
    "TERMINAL_STATUSES",
    "UnprotectedMutationError",
    "PriorStateMismatchError",
    "AlreadySettledError",
    "ActionTransitionError",
    "ActionExecution",
    "derive_idempotency_key",
    "ActionLog",
]
