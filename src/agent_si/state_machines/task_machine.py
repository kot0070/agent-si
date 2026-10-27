"""Task state machine runtime (Manifest section 12 TASK_STATE_MACHINE).

Static edges come ONLY from the frozen manifest (``TASK_ALLOWED``,
``TASK_TERMINAL``, ``TASK_CONDITIONAL_OVERRIDE_EDGES``,
``TASK_DYNAMIC_RESUME_SOURCES``, ``AUDIT_RESULT_TRANSITION_MAP``,
``is_task_transition_allowed``); this module adds no state, edge, or enum
of its own to that vocabulary. ``RestartReason``,
``TransitionRejectedError`` / ``TerminalTransitionError`` /
``StaleStateError``, ``OverrideRecord`` and ``DecisionRedirect`` are the
section-12 runtime shapes the manifest names but does not freeze as enums.

Rules enforced here: TERMINAL states have no outgoing edge; EXECUTING /
VERIFYING never reach COMPLETED; AUDITING leaves only via the audit
disposition map (COMPLETED needs a PASS verdict, FAIL never converts);
conditional override edges need an explicit user OverrideRecord with
CompletionDisposition ACCEPTED_RISK; resume out of BLOCKED / ESCALATED is
validated against the recorded resume_target_state (a DecisionRecord /
Amendment redirect may change it, same-contract only); commits are
compare-and-set on (expected_from_state, expected_state_version) with
monotonic sequences and UNIQUE(task, sequence) / UNIQUE(task, version).
"""

from __future__ import annotations

import dataclasses
from dataclasses import field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

try:
    from iface.frozen_manifest import manifest
except ImportError:  # alternate layout: the iface/ directory itself on sys.path
    from frozen_manifest import manifest


class TransitionRejectedError(Exception):
    """A task edge was refused (forbidden, silent, bad disposition/override)."""


class TerminalTransitionError(TransitionRejectedError):
    """An outgoing edge from a TERMINAL task state was attempted."""


class StaleStateError(Exception):
    """CAS commit failed: expected (from, version) no longer current."""


class RestartReason(str, Enum):
    """Manifest section 12 restart/reroute reasons (no correction increment)."""

    AMENDMENT_RESTART = "AMENDMENT_RESTART"
    FALLBACK_REROUTE = "FALLBACK_REROUTE"


EXECUTION_RETRY = "EXECUTION_RETRY"
"""Retry-loop event EXECUTING/VERIFYING -> REWORK_PENDING (no count increment)."""

_RESTART_SOURCES = {
    RestartReason.AMENDMENT_RESTART: frozenset(
        {
            manifest.TaskState.EXECUTING,
            manifest.TaskState.VERIFYING,
            manifest.TaskState.AUDITING,
        }
    ),
    RestartReason.FALLBACK_REROUTE: frozenset(
        {
            manifest.TaskState.EXECUTING,
            manifest.TaskState.VERIFYING,
            manifest.TaskState.AUDITING,
        }
    ),
}
_RETRY_SOURCES = frozenset({manifest.TaskState.EXECUTING, manifest.TaskState.VERIFYING})
_SUSPENSION_ENTRY = frozenset({manifest.TaskState.BLOCKED, manifest.TaskState.ESCALATED})


def increments_correction_count(reason: Any) -> bool:
    """False for restart/reroute/retry events, True for anything else."""
    value = getattr(reason, "value", reason)
    if value == EXECUTION_RETRY:
        return False
    try:
        RestartReason(str(value))
    except ValueError:
        return True
    return False


@dataclasses.dataclass(frozen=True)
class OverrideRecord:
    """Section 18B user override authorizing one accepted-risk completion."""

    override_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: Optional[str] = None
    authorized_by: str = ""
    authorization_ref: str = ""
    completion_disposition: manifest.CompletionDisposition = (
        manifest.CompletionDisposition.ACCEPTED_RISK
    )
    original_result: Optional[manifest.AuditResult] = None
    override_source_state: Any = None
    override_reason: str = ""
    override_action: str = ""
    accepted_risks: Tuple[str, ...] = ()
    evidence_refs: Tuple[str, ...] = ()
    scope: str = ""
    status: str = "ACTIVE"

    def __post_init__(self) -> None:
        if not isinstance(self.accepted_risks, tuple):
            object.__setattr__(self, "accepted_risks", tuple(self.accepted_risks or ()))
        if not isinstance(self.evidence_refs, tuple):
            object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs or ()))

    def check_valid_for(self, source: manifest.TaskState) -> None:
        """Raise TransitionRejectedError unless this record authorizes source."""
        if not self.authorized_by or not self.authorization_ref:
            raise TransitionRejectedError("override needs explicit user authorization")
        if self.completion_disposition != manifest.CompletionDisposition.ACCEPTED_RISK:
            raise TransitionRejectedError("override needs disposition ACCEPTED_RISK")
        if _coerce_state(self.override_source_state) != source:
            raise TransitionRejectedError("override source does not match task state")
        if self.original_result == manifest.AuditResult.FAIL:
            raise TransitionRejectedError("FAIL never converts; recovery is a new task")


@dataclasses.dataclass(frozen=True)
class DecisionRedirect:
    """DecisionRecord/Amendment changing a recorded resume target (same contract)."""

    decision_id: str = ""
    new_target_state: Any = None
    contract_hash: str = ""
    expected_contract_hash: str = ""
    evidence_refs: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "new_target_state", _coerce_state(self.new_target_state))
        if not isinstance(self.evidence_refs, tuple):
            object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs or ()))


def _coerce_state(value: Any) -> Optional[manifest.TaskState]:
    if value is None or isinstance(value, manifest.TaskState):
        return value
    try:
        return manifest.TaskState(str(value))
    except ValueError:
        return None


def _check_resume_target(target: Any) -> manifest.TaskState:
    """A recorded resume target is concrete, legal, and same-contract working state."""
    state = _coerce_state(target)
    if state is None:
        raise TransitionRejectedError("resume target must be an explicit TaskState")
    if state in manifest.TASK_TERMINAL:
        raise TransitionRejectedError("resume target must not be terminal")
    if state in manifest.TASK_DYNAMIC_RESUME_SOURCES:
        raise TransitionRejectedError("resume target must not be a suspended state")
    return state


_TRANSITION_FIELD_TYPES: Tuple[Tuple[str, Any], ...] = (
    ("transition_id", str),
    ("project_id", str),
    ("task_id", str),
    ("run_id", Optional[str]),
    ("transition_sequence", int),
    ("expected_from_state", manifest.TaskState),
    ("expected_state_version", int),
    ("new_state_version", int),
    ("actor", str),
    ("from", manifest.TaskState),
    ("to", manifest.TaskState),
    ("reason", str),
    ("timestamp", str),
    ("evidence_ref", str),
    ("suspended_from_state", Optional[manifest.TaskState]),
    ("resume_target_state", Optional[manifest.TaskState]),
)


def _build_transition_class() -> Any:
    names = [name for name, _ in _TRANSITION_FIELD_TYPES]
    assert tuple(names) == tuple(manifest.TRANSITION_FIELDS), "record drifts from manifest"
    namespace: Dict[str, Any] = {
        "__annotations__": dict(_TRANSITION_FIELD_TYPES),
        "__doc__": "Manifest section 12 transition record (frozen, TRANSITION_FIELDS order).",
        "__module__": __name__,
    }
    cls = dataclasses.dataclass(frozen=True, init=False, repr=False, eq=False)(
        type("TaskTransition", (), namespace)
    )

    def __init__(self: Any, **kwargs: Any) -> None:
        for name in manifest.TRANSITION_FIELDS:
            if name not in kwargs:
                if name in ("run_id", "suspended_from_state", "resume_target_state"):
                    kwargs[name] = None
                elif name in ("timestamp", "evidence_ref"):
                    kwargs[name] = ""
                else:
                    raise TypeError("missing transition field: %s" % name)
        for name in kwargs:
            if name not in manifest.TRANSITION_FIELDS:
                raise TypeError("unknown transition field: %s" % name)
        for name in (
            "expected_from_state",
            "from",
            "to",
            "suspended_from_state",
            "resume_target_state",
        ):
            if kwargs[name] is not None:
                coerced = _coerce_state(kwargs[name])
                if coerced is None:
                    raise TransitionRejectedError("unknown TaskState in %s" % name)
                kwargs[name] = coerced
        for name in manifest.TRANSITION_FIELDS:
            object.__setattr__(self, name, kwargs[name])

    @classmethod
    def _create(cls: Any, **kwargs: Any) -> Any:
        if "from_state" in kwargs:
            kwargs["from"] = kwargs.pop("from_state")
        if "to_state" in kwargs:
            kwargs["to"] = kwargs.pop("to_state")
        return cls(**kwargs)

    def __repr__(self: Any) -> str:
        inner = ", ".join(
            "%s=%r" % (name, getattr(self, name)) for name in manifest.TRANSITION_FIELDS
        )
        return "%s(%s)" % (type(self).__qualname__, inner)

    def __eq__(self: Any, other: Any) -> bool:
        if type(other) is not type(self):
            return NotImplemented
        return all(getattr(self, name) == getattr(other, name) for name in manifest.TRANSITION_FIELDS)

    def __hash__(self: Any) -> int:
        return hash(tuple(getattr(self, name) for name in manifest.TRANSITION_FIELDS))

    cls.__init__ = __init__
    cls.__repr__ = __repr__
    cls.__eq__ = __eq__
    cls.__hash__ = __hash__
    cls.create = _create
    cls.field_names = classmethod(lambda c: list(manifest.TRANSITION_FIELDS))
    return cls


TaskTransition = _build_transition_class()
"""Frozen transition record; fields EXACTLY manifest.TRANSITION_FIELDS order."""


class TaskMachine:
    """One task's lifecycle: CAS commits, suspension capture, dynamic resume."""

    def __init__(
        self,
        *,
        task_id: str,
        project_id: str,
        initial_state: Any = manifest.TaskState.CREATED,
    ) -> None:
        state = _coerce_state(initial_state)
        if state is None:
            raise TransitionRejectedError("unknown initial TaskState")
        self.task_id = task_id
        self.project_id = project_id
        self.current_state = state
        self.state_version = 0
        self.transition_sequence = 0
        self.history: Tuple[Any, ...] = ()
        self.suspended_from_state: Optional[manifest.TaskState] = None
        self.resume_target_state: Optional[manifest.TaskState] = None
        self._seen_sequences = {0}
        self._seen_versions = {0}

    def transition(
        self,
        to: Any,
        *,
        expected_from_state: Any,
        expected_state_version: int,
        actor: str,
        reason: str,
        run_id: Optional[str] = None,
        timestamp: str = "",
        evidence_ref: str = "",
        audit_result: Any = None,
        override: Optional[OverrideRecord] = None,
        suspended_from_state: Any = None,
        resume_target_state: Any = None,
        redirect: Optional[DecisionRedirect] = None,
    ) -> Any:
        """CAS-commit one edge; refuse anything the manifest does not allow."""
        target = _coerce_state(to)
        if target is None:
            raise TransitionRejectedError("unknown target TaskState")
        source = self.current_state
        if source in manifest.TASK_TERMINAL:
            raise TerminalTransitionError("terminal state %s has no outgoing edge" % source.value)
        if self.current_state != _coerce_state(expected_from_state):
            raise StaleStateError("expected from-state is stale; re-read and retry")
        if self.state_version != expected_state_version:
            raise StaleStateError("expected state version is stale; re-read and retry")
        if not actor or not reason:
            raise TransitionRejectedError("silent transition refused: actor and reason required")
        self._check_edge(source, target, audit_result, override, redirect, run_id)
        new_suspended, new_target = self._capture_suspension(
            source, target, suspended_from_state, resume_target_state, redirect
        )
        sequence = self.transition_sequence + 1
        version = self.state_version + 1
        if sequence in self._seen_sequences:
            raise TransitionRejectedError("duplicate transition_sequence")
        if version in self._seen_versions:
            raise TransitionRejectedError("duplicate new_state_version")
        record = TaskTransition.create(
            transition_id="%s:t%04d" % (self.task_id, sequence),
            project_id=self.project_id,
            task_id=self.task_id,
            run_id=run_id,
            transition_sequence=sequence,
            expected_from_state=source,
            expected_state_version=self.state_version,
            new_state_version=version,
            actor=actor,
            from_state=source,
            to_state=target,
            reason=reason,
            timestamp=timestamp,
            evidence_ref=evidence_ref,
            suspended_from_state=new_suspended,
            resume_target_state=new_target,
        )
        self._seen_sequences.add(sequence)
        self._seen_versions.add(version)
        self.history = self.history + (record,)
        self.transition_sequence = sequence
        self.state_version = version
        self.current_state = target
        self.suspended_from_state = new_suspended
        self.resume_target_state = new_target
        return record

    def _check_edge(
        self,
        source: manifest.TaskState,
        target: manifest.TaskState,
        audit_result: Any,
        override: Optional[OverrideRecord],
        redirect: Optional[DecisionRedirect],
        run_id: Optional[str],
    ) -> None:
        if source == manifest.TaskState.AUDITING:
            self._check_auditing_edge(target, audit_result)
            return
        if manifest.is_task_transition_allowed(source, target):
            if source == manifest.TaskState.REWORK_PENDING and target == manifest.TaskState.EXECUTING:
                if not run_id:
                    raise TransitionRejectedError("REWORK_PENDING -> EXECUTING needs a new bound run")
            return
        if override is not None and (source, target) in manifest.TASK_CONDITIONAL_OVERRIDE_EDGES:
            if target != manifest.TaskState.COMPLETED:
                raise TransitionRejectedError("override completes only to COMPLETED")
            override.check_valid_for(source)
            return
        if source in manifest.TASK_DYNAMIC_RESUME_SOURCES and redirect is not None:
            self._check_redirect(source, target, redirect)
            return
        if source in manifest.TASK_DYNAMIC_RESUME_SOURCES and self.resume_target_state is not None:
            if target == self.resume_target_state:
                return
        raise TransitionRejectedError(
            "edge %s -> %s is not allowed" % (source.value, target.value)
        )

    def _check_auditing_edge(self, target: manifest.TaskState, audit_result: Any) -> None:
        if target == manifest.TaskState.CANCELLED:
            return
        if audit_result is None:
            raise TransitionRejectedError("AUDITING leaves only via audit disposition")
        try:
            result = audit_result
            if not isinstance(result, manifest.AuditResult):
                result = manifest.AuditResult(str(audit_result))
        except ValueError:
            raise TransitionRejectedError("unknown AuditResult")
        if manifest.AUDIT_RESULT_TRANSITION_MAP[result] != target:
            raise TransitionRejectedError("audit disposition does not map to target")
        if target == manifest.TaskState.COMPLETED and result != manifest.AuditResult.PASS:
            raise TransitionRejectedError("only PASS completes; FAIL never converts")

    def _check_redirect(
        self,
        source: manifest.TaskState,
        target: manifest.TaskState,
        redirect: DecisionRedirect,
    ) -> None:
        if redirect.contract_hash != redirect.expected_contract_hash:
            raise manifest.ContextWrongContractVersionError(
                "redirect under a superseded contract"
            )
        new_target = _check_resume_target(redirect.new_target_state)
        if target != new_target:
            raise TransitionRejectedError("resume must hit the redirected target")
        self.resume_target_state = new_target

    def _capture_suspension(
        self,
        source: manifest.TaskState,
        target: manifest.TaskState,
        suspended_from_state: Any,
        resume_target_state: Any,
        redirect: Optional[DecisionRedirect],
    ) -> Tuple[Optional[manifest.TaskState], Optional[manifest.TaskState]]:
        if target not in _SUSPENSION_ENTRY:
            return self.suspended_from_state, self.resume_target_state
        suspended = source
        if suspended_from_state is not None:
            claimed = _coerce_state(suspended_from_state)
            if claimed != source:
                raise TransitionRejectedError("suspended_from_state must be the state left")
            suspended = claimed
        if resume_target_state is None:
            raise TransitionRejectedError(
                "entering %s needs an explicit resume_target_state" % target.value
            )
        return suspended, _check_resume_target(resume_target_state)

    def request_restart(
        self,
        reason: Any,
        *,
        expected_state_version: int,
        actor: str,
        timestamp: str = "",
        evidence_ref: str = "",
    ) -> Tuple[Any, bool]:
        """Move EXECUTING/VERIFYING/AUDITING -> REWORK_PENDING; never counts correction."""
        value = getattr(reason, "value", reason)
        if value == EXECUTION_RETRY:
            allowed = _RETRY_SOURCES
        else:
            try:
                reason_enum = reason if isinstance(reason, RestartReason) else RestartReason(str(value))
            except ValueError:
                raise TransitionRejectedError("unknown restart reason")
            allowed = _RESTART_SOURCES[reason_enum]
        if self.current_state not in allowed:
            raise TransitionRejectedError("restart reason not legal from %s" % self.current_state.value)
        record = self.transition(
            manifest.TaskState.REWORK_PENDING,
            expected_from_state=self.current_state,
            expected_state_version=expected_state_version,
            actor=actor,
            reason=str(value),
            timestamp=timestamp,
            evidence_ref=evidence_ref,
        )
        return record, False

    @classmethod
    def recover(cls, *, task_id: str, project_id: str, records: List[Any]) -> "TaskMachine":
        """Rebuild from committed records; latest = highest version then sequence."""
        machine = cls(task_id=task_id, project_id=project_id)
        if not records:
            return machine
        seen_sequences = set()
        seen_versions = set()
        for record in records:
            if record.task_id != task_id:
                raise TransitionRejectedError("record belongs to another task")
            if record.transition_sequence in seen_sequences:
                raise TransitionRejectedError("duplicate transition_sequence")
            if record.new_state_version in seen_versions:
                raise TransitionRejectedError("duplicate new_state_version")
            seen_sequences.add(record.transition_sequence)
            seen_versions.add(record.new_state_version)
        ordered = sorted(records, key=lambda r: (r.new_state_version, r.transition_sequence))
        latest = ordered[-1]
        machine.current_state = _coerce_state(getattr(latest, "to"))
        machine.state_version = latest.new_state_version
        machine.transition_sequence = latest.transition_sequence
        machine.history = tuple(ordered)
        machine._seen_sequences = seen_sequences | {0}
        machine._seen_versions = seen_versions | {0}
        for record in reversed(ordered):
            suspended = getattr(record, "suspended_from_state")
            target = getattr(record, "resume_target_state")
            if suspended is not None or target is not None:
                machine.suspended_from_state = suspended
                machine.resume_target_state = target
                break
        return machine
