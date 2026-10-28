# CODER-1 Harbor: K13 0C GuardedToolDispatcher — every SDK tool call passes admission, limiter and sequence checks.
"""Guarded tool-call dispatcher for the K13 SDK adapter (0C ARCHITECTURE 1.4).

Every SDK tool call passes admission, limiter and sequence checks before it
runs; an install-class tool call parks the run as APPROVAL_WAITING; a refused
call never runs, returns an honest refusal to the model, and is recorded.

Wiring: the adapter constructs exactly one GuardedToolDispatcher and reuses
it for every tool call (one guarded dispatcher per adapter); real K06
admission/limiter/sequence predicates arrive later through these same
callable slots. The class itself holds no global state: sequence numbers and
records live on the instance. This module never rebuilds SDK features.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

INSTALL_TOOL_CLASS = "install"
APPROVAL_WAITING = "APPROVAL_WAITING"
REFUSED = "REFUSED"

__all__ = [
    "INSTALL_TOOL_CLASS",
    "APPROVAL_WAITING",
    "REFUSED",
    "ToolCall",
    "GuardDecision",
    "GuardRecord",
    "GuardOutcome",
    "GuardedToolDispatcher",
]


@dataclass(frozen=True)
class ToolCall:
    """Tool-call request row; refs only, never inline secrets."""

    tool_name: str
    tool_class: str = ""
    action_id: str = ""
    project_id: str = ""
    task_id: str = ""
    run_id: str = ""
    args_ref: str = ""


@dataclass(frozen=True)
class GuardDecision:
    """Admission outcome for one tool call."""

    allowed: bool
    parked: bool
    reason: str
    refusal: str = ""


@dataclass(frozen=True)
class GuardRecord:
    """Stored execution row for one guarded tool call."""

    action_id: str
    tool_name: str
    tool_class: str
    decision: str
    reason: str
    seq: int


@dataclass(frozen=True)
class GuardOutcome:
    """Result of one guarded_call: what ran, what was refused or parked."""

    executed: bool
    parked: bool
    refusal: str
    result: Any
    record: GuardRecord


class GuardedToolDispatcher:
    """Guard every SDK tool call: admission, then limiter, then sequence.

    The adapter constructs exactly one GuardedToolDispatcher and reuses it
    for every tool call; the dispatcher itself keeps no global state (each
    instance owns its own monotonic sequence and record list).
    """

    def __init__(
        self,
        admission: Optional[Callable[[ToolCall], Tuple[bool, str]]] = None,
        limiter: Optional[Callable[[ToolCall], Tuple[bool, str]]] = None,
        sequence: Optional[Callable[[ToolCall], Tuple[bool, str]]] = None,
    ) -> None:
        self._admission = admission
        self._limiter = limiter
        self._sequence = sequence
        self._records: list[GuardRecord] = []
        self._next_seq = 1

    @property
    def records(self) -> Tuple[GuardRecord, ...]:
        """Every GuardRecord appended so far, oldest first."""
        return tuple(self._records)

    def _record(
        self,
        call: ToolCall,
        allowed: bool,
        parked: bool,
        reason: str,
        refusal: str,
    ) -> GuardDecision:
        if parked:
            decision = "PARKED"
        elif allowed:
            decision = "ALLOWED"
        else:
            decision = REFUSED
        record = GuardRecord(
            action_id=call.action_id,
            tool_name=call.tool_name,
            tool_class=call.tool_class,
            decision=decision,
            reason=reason,
            seq=self._next_seq,
        )
        self._next_seq += 1
        self._records.append(record)
        return GuardDecision(
            allowed=allowed, parked=parked, reason=reason, refusal=refusal
        )

    def dispatch(self, call: ToolCall) -> GuardDecision:
        """Run admission, limiter, then sequence; first False wins and nothing runs."""
        for check_name, predicate in (
            ("admission", self._admission),
            ("limiter", self._limiter),
            ("sequence", self._sequence),
        ):
            if predicate is None:
                reason = check_name + " unbound: closed by default"
                return self._record(
                    call, False, False, reason, check_name + " refused: " + reason
                )
            ok, reason = predicate(call)
            if not ok:
                return self._record(
                    call, False, False, reason, check_name + " refused: " + reason
                )
        if call.tool_class == INSTALL_TOOL_CLASS:
            return self._record(call, False, True, APPROVAL_WAITING, "")
        return self._record(call, True, False, "allowed", "")

    def guarded_call(
        self, call: ToolCall, run_fn: Callable[[ToolCall], Any]
    ) -> GuardOutcome:
        """Wiring hook for the tool-call path: run run_fn exactly once if allowed."""
        decision = self.dispatch(call)
        record = self._records[-1]
        if decision.allowed:
            return GuardOutcome(
                executed=True,
                parked=False,
                refusal="",
                result=run_fn(call),
                record=record,
            )
        if decision.parked:
            return GuardOutcome(
                executed=False, parked=True, refusal="", result=None, record=record
            )
        return GuardOutcome(
            executed=False,
            parked=False,
            refusal=decision.refusal,
            result=None,
            record=record,
        )
