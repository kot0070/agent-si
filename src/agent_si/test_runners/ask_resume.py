"""K03 STEP2: ASK resume (buttons plus resume only; resume only).

A click on a decision resumes the parked run; typing stays possible while
parked. Parking records where the run waits; resume is idempotent, so the
park record stays for audit and repeated clicks re-affirm it. Unknown
decisions are refused before the park is even consulted; resuming a run
that was never parked is refused. Record schemas stay with K13 and the
execution writer stays with K06: this module carries buttons plus resume.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from enum import Enum
from typing import Dict

#: The three chat/run-view decisions, in button order.
ASK_DECISIONS = ("allow_once", "allow_project", "deny")


class AskDecision(str, Enum):
    ALLOW_ONCE = "allow_once"
    ALLOW_PROJECT = "allow_project"
    DENY = "deny"


#: Frozen error-code names for this module (each pinned in its own test).
ERROR_CODES_ASK = (
    "RESUME_WITHOUT_PARK",
    "RESUME_UNKNOWN_DECISION",
)


class AskError(Exception):
    """ASK-resume failure carrying the frozen ``.code`` name."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ParkedRun:
    run_id: str
    project_id: str
    parked_at_state: str
    reason: str


@dataclass(frozen=True)
class ResumeOutcome:
    run_id: str
    decision: AskDecision
    resumed: bool
    resume_target_state: str


#: Process-wide episode bus key, shared with the ladder and stage
#: runner modules; the park registry lives on the bus so parked runs
#: survive module reloads within one process (the park record is
#: operational state, owned here).
_BUS_KEY = "k03_stage_episode_bus"


def _park_registry() -> Dict[str, ParkedRun]:
    """Parked runs by run id; re-parking updates the record."""
    bus = sys.modules.get(_BUS_KEY)
    if bus is None:
        bus = types.ModuleType(_BUS_KEY)
        sys.modules[_BUS_KEY] = bus
    if not hasattr(bus, "open_project"):
        bus.open_project = None
    if not hasattr(bus, "projects_asked"):
        bus.projects_asked = set()
    if not hasattr(bus, "parked_runs"):
        bus.parked_runs = {}
    return bus.parked_runs


def _coerce_decision(decision: object) -> AskDecision:
    """Accept an AskDecision or its exact string value; else refuse."""
    if isinstance(decision, AskDecision):
        return decision
    if isinstance(decision, str):
        try:
            return AskDecision(decision)
        except ValueError:
            pass
    raise AskError(
        "RESUME_UNKNOWN_DECISION",
        "decision %r is not one of allow_once, allow_project, deny"
        % (decision,),
    )


def park_run(run_id: str, project_id: str, parked_at_state: str, reason: str) -> ParkedRun:
    """Park a run waiting on a permission ASK."""
    parked = ParkedRun(
        run_id=run_id,
        project_id=project_id,
        parked_at_state=parked_at_state,
        reason=reason,
    )
    _park_registry()[run_id] = parked
    return parked


def resume_run(run_id: str, decision: AskDecision) -> ResumeOutcome:
    """Resume a parked run on the user's button decision."""
    chosen = _coerce_decision(decision)
    parked = _park_registry().get(run_id)
    if parked is None:
        raise AskError(
            "RESUME_WITHOUT_PARK",
            "run %r was never parked on an ASK" % run_id,
        )
    return ResumeOutcome(
        run_id=run_id,
        decision=chosen,
        resumed=True,
        resume_target_state=parked.parked_at_state,
    )


def typed_input_allowed(run_id: str) -> bool:
    """Typing stays possible while a run is parked on an ASK."""
    return True


#: Entry points: logical name -> symbol in this module.
ENTRY_POINTS = {
    "park_run": "park_run",
    "resume_run": "resume_run",
    "typed_input_allowed": "typed_input_allowed",
}
