"""Amendment lifecycle helpers (Manifest section 15 AMENDMENTS).

Amendments never rewrite history: terminal tasks are never reopened, terminal
runs are never superseded via amendment, and IMMEDIATE effects are expressed
as transition descriptors returned to the caller. This module mutates nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Tuple

try:
    from iface.frozen_manifest import manifest
except ImportError:  # alternate layout: the iface/ directory itself on sys.path
    from frozen_manifest import manifest

CONTRACT_AFFECTING = "CONTRACT_AFFECTING"
NON_CONTRACT_AFFECTING = "NON_CONTRACT_AFFECTING"

APPLY = "APPLY"
REJECT_NEW_TASK_REQUIRED = "REJECT_NEW_TASK_REQUIRED"

TERMINAL_TASK_STATES = frozenset(
    {
        manifest.TaskState.COMPLETED,
        manifest.TaskState.FAILED,
        manifest.TaskState.CANCELLED,
    }
)
"""Manifest section 12 TERMINAL (section 15 terminal-task rule)."""

_SCOPE_PRECEDENCE = {
    manifest.AmendmentScope.GLOBAL: 0,
    manifest.AmendmentScope.PHASE: 1,
    manifest.AmendmentScope.TASK: 2,
}


class TerminalTaskAmendmentError(Exception):
    """IMMEDIATE amendment targets a terminal task (Manifest section 15).

    Directive: the Director rejects, or creates a NEW task (new task_id,
    linked via supersedes_task_id / parent_task_id) with its own lifecycle;
    the terminal task is never reopened and no new run attaches to it.
    """


@dataclass(frozen=True)
class AmendmentTarget:
    """Minimal amendment target: which task/phase the amendment addresses."""

    task_id: Optional[str] = None
    phase_id: Optional[str] = None


@dataclass(frozen=True)
class AmendmentChange:
    """Minimal amendment change: touched contract fields plus a summary."""

    fields: Tuple[str, ...] = ()
    summary: str = ""

    def __post_init__(self) -> None:
        if self.fields is None:
            object.__setattr__(self, "fields", ())
        elif not isinstance(self.fields, tuple):
            object.__setattr__(self, "fields", tuple(self.fields))


@dataclass(frozen=True)
class TransitionDescriptor:
    """A requested state transition; a record of intent, not a mutation."""

    action: str
    target: str
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class Amendment:
    """Manifest section 15 Amendment. Immutable."""

    amendment_id: str = ""
    project_id: str = ""
    amendment_sequence: int = 0
    scope: manifest.AmendmentScope = manifest.AmendmentScope.TASK
    effective_from: manifest.EffectiveFrom = manifest.EffectiveFrom.NEXT_TASK
    target: AmendmentTarget = field(default_factory=AmendmentTarget)
    change: AmendmentChange = field(default_factory=AmendmentChange)
    reason: str = ""
    created_at: str = ""
    source: str = ""
    status: manifest.AmendmentStatus = manifest.AmendmentStatus.PENDING

    def __post_init__(self) -> None:
        if isinstance(self.scope, str) and not isinstance(
            self.scope, manifest.AmendmentScope
        ):
            object.__setattr__(
                self, "scope", manifest.AmendmentScope(self.scope)
            )
        if isinstance(self.effective_from, str) and not isinstance(
            self.effective_from, manifest.EffectiveFrom
        ):
            object.__setattr__(
                self, "effective_from", manifest.EffectiveFrom(self.effective_from)
            )
        if isinstance(self.status, str) and not isinstance(
            self.status, manifest.AmendmentStatus
        ):
            object.__setattr__(
                self, "status", manifest.AmendmentStatus(self.status)
            )


def _scope_key(scope: Any) -> manifest.AmendmentScope:
    if isinstance(scope, manifest.AmendmentScope):
        return scope
    return manifest.AmendmentScope(str(scope))


def order_amendments(amendments: Iterable[Amendment]) -> List[Amendment]:
    """Deterministic precedence (section 15): GLOBAL, then PHASE, then TASK.

    Within equal precedence, ascending amendment_sequence applies; narrower
    scope wins ties on sequence (TASK sorts after GLOBAL/PHASE).
    """
    return sorted(
        list(amendments),
        key=lambda item: (
            _SCOPE_PRECEDENCE[_scope_key(item.scope)],
            item.amendment_sequence,
        ),
    )


def classify(change: AmendmentChange, contract_fields: Iterable[str] = manifest.TASK_CONTRACT_FIELDS) -> str:
    """CONTRACT_AFFECTING vs NON_CONTRACT_AFFECTING (section 15 classes).

    Touches any contract_hash-covered field (goal, requirements, acceptance
    criteria, permissions, policy refs, workspace constraints, required
    outputs) -> CONTRACT_AFFECTING; runtime metadata only, proven outside the
    hash -> NON_CONTRACT_AFFECTING.
    """
    covered = set(contract_fields)
    for touched in change.fields:
        if touched in covered:
            return CONTRACT_AFFECTING
    return NON_CONTRACT_AFFECTING


def _coerce_task_state(value: Any) -> manifest.TaskState:
    if isinstance(value, manifest.TaskState):
        return value
    return manifest.TaskState(str(value))


def _coerce_effective_from(value: Any) -> manifest.EffectiveFrom:
    if isinstance(value, manifest.EffectiveFrom):
        return value
    return manifest.EffectiveFrom(str(value))


def apply_terminal_task_rule(task_state: Any, effective_from: Any) -> str:
    """Enforce the section 15 terminal-task rule.

    Returns APPLY when the amendment may proceed, REJECT_NEW_TASK_REQUIRED
    when a terminal task needs a new task instead, and raises
    TerminalTaskAmendmentError for terminal state + IMMEDIATE (never reopens
    COMPLETED / FAILED / CANCELLED; no new run attaches).
    """
    state = _coerce_task_state(task_state)
    timing = _coerce_effective_from(effective_from)
    if state in TERMINAL_TASK_STATES:
        if timing == manifest.EffectiveFrom.IMMEDIATE:
            raise TerminalTaskAmendmentError(
                "IMMEDIATE amendment rejected for terminal task state %s: "
                "never reopen COMPLETED/FAILED/CANCELLED and attach no new "
                "run; Director creates a NEW task linked via "
                "supersedes_task_id/parent_task_id (Manifest section 15)." % state.value
            )
        return REJECT_NEW_TASK_REQUIRED
    return APPLY


def _coerce_run_status(value: Any) -> manifest.ExecutionRunStatus:
    if isinstance(value, manifest.ExecutionRunStatus):
        return value
    return manifest.ExecutionRunStatus(str(value))


def apply_immediate_effect(
    amendment: Amendment,
    task_state: Any,
    active_run_id: Optional[str] = None,
    active_run_status: Any = None,
) -> Tuple[TransitionDescriptor, ...]:
    """Describe IMMEDIATE effects as descriptors; mutates nothing (section 15).

    Never rewrites historical run data: the active non-terminal run (if any)
    is described as transitioning to CANCELLED + CANCELLED_BY_AMENDMENT via a
    recorded transition, terminal runs are left immutable, and the new
    contract version/hash plus its new bound run are described as creations.
    Non-IMMEDIATE amendments yield no immediate descriptors (empty tuple).
    """
    timing = _coerce_effective_from(amendment.effective_from)
    if timing != manifest.EffectiveFrom.IMMEDIATE:
        return ()
    apply_terminal_task_rule(task_state, timing)
    descriptors: List[TransitionDescriptor] = []
    if active_run_id is not None and active_run_status is not None:
        status = _coerce_run_status(active_run_status)
        if status not in manifest.RUN_TERMINAL:
            descriptors.append(
                TransitionDescriptor(
                    action="CANCEL_RUN",
                    target=active_run_id,
                    reason=manifest.RunTerminationReason.CANCELLED_BY_AMENDMENT.value,
                    detail=(
                        "active non-terminal run to CANCELLED via recorded "
                        "transition; terminal runs immutable (section 15 "
                        "IMMEDIATE rule)"
                    ),
                )
            )
    descriptors.append(
        TransitionDescriptor(
            action="NEW_CONTRACT_VERSION",
            target=amendment.project_id,
            reason="AMENDMENT_IMMEDIATE",
            detail=(
                "new contract version + hash, then a new run bound to it; "
                "history never rewritten (section 15)"
            ),
        )
    )
    return tuple(descriptors)


__all__ = [
    "CONTRACT_AFFECTING",
    "NON_CONTRACT_AFFECTING",
    "APPLY",
    "REJECT_NEW_TASK_REQUIRED",
    "TERMINAL_TASK_STATES",
    "TerminalTaskAmendmentError",
    "AmendmentTarget",
    "AmendmentChange",
    "TransitionDescriptor",
    "Amendment",
    "order_amendments",
    "classify",
    "apply_terminal_task_rule",
    "apply_immediate_effect",
]
