"""K03 stage lane STEP2: permission ladder (one ask per project, HUMAN gated).

The ladder is asked once per project as one list, in the frozen rung order;
a HUMAN step is allowed only after the ladder was asked for that project
and the HUMAN test carries its reason. The open ask is a single-operator
episode: one ask is open at a time per process, a refused permission check
abandons it (ask again), and the stage runner concludes it when the run
finishes or is sent back for fixing. Episode state is shared process-wide
with the stage runner through the episode bus (one operator console).
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from typing import List, Optional, Tuple

#: Named rungs in fixed order, asked before any HUMAN step.
LADDER_RUNGS = (
    "UI_AUTOMATION",
    "SCREEN_CAPTURE_AI_VISION",
    "EMULATORS_SIMULATORS",
    "BROWSER_PROFILES",
    "TEST_ACCOUNTS",
    "TEST_SERVER",
    "DEVICE_LOGS",
    "SANDBOX_INSTALL",
)

#: Frozen error-code names for this module (each pinned in its own test).
ERROR_CODES_LADDER = (
    "HUMAN_BEFORE_LADDER",
    "HUMAN_REASON_MISSING",
    "LADDER_ALREADY_ASKED",
)


class LadderError(Exception):
    """Ladder failure carrying the frozen ``.code`` name."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class LadderRung:
    rung_id: str
    enables: str
    risk: str


@dataclass(frozen=True)
class LadderAsk:
    project_id: str
    rung_ids: Tuple[str, ...]
    asked_at: str


#: What each rung enables and the risk it carries; order matches LADDER_RUNGS.
_RUNG_DETAIL = (
    ("UI_AUTOMATION", "drive the app UI without a human hand",
     "scripts can click the wrong control; review selectors first"),
    ("SCREEN_CAPTURE_AI_VISION", "see the screen like an operator",
     "vision may misread pixels; confirm before acting on them"),
    ("EMULATORS_SIMULATORS", "run device and OS variants locally",
     "emulators differ from real hardware; confirm on device"),
    ("BROWSER_PROFILES", "keep isolated browser state per run",
     "a profile may leak state between runs; reset it first"),
    ("TEST_ACCOUNTS", "sign in without owner credentials",
     "test accounts must never touch production data"),
    ("TEST_SERVER", "exercise backend flows off production",
     "test-server data is not production truth"),
    ("DEVICE_LOGS", "read on-device logs for failures",
     "logs may contain sensitive text; keep them local"),
    ("SANDBOX_INSTALL", "install builds in isolation",
     "installs must stay inside the sandbox"),
)

#: Process-wide episode bus key, shared with the stage runner module.
_BUS_KEY = "k03_stage_episode_bus"


def _episode_bus() -> types.ModuleType:
    """Return the process-wide single-operator permission-episode bus.

    ``open_project`` holds the project whose ask is currently open (or
    None); ``projects_asked`` records every project asked so far;
    ``parked_runs`` maps parked run ids to their park records. Ladder,
    stage-runner and ASK-resume modules all use this same bus object, so
    the state survives module reloads within one process.
    """
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
    return bus


def ladder_rungs() -> Tuple[str, ...]:
    """Return the rung ids in the frozen order."""
    return LADDER_RUNGS


def describe_rungs() -> List[LadderRung]:
    """Return one row per rung: what it enables and its risk."""
    return [
        LadderRung(rung_id=rung_id, enables=enables, risk=risk)
        for rung_id, enables, risk in _RUNG_DETAIL
    ]


def ask_ladder_once(project_id: str, asked_at: str) -> LadderAsk:
    """Ask the whole ladder once per project; re-ask raises."""
    bus = _episode_bus()
    if bus.open_project == project_id:
        bus.open_project = None
        raise LadderError(
            "LADDER_ALREADY_ASKED",
            "ladder for project %r is already asked; "
            "the open ask was abandoned, ask again" % project_id,
        )
    if bus.open_project is not None:
        raise LadderError(
            "LADDER_ALREADY_ASKED",
            "ladder for project %r is open; resolve it before asking %r"
            % (bus.open_project, project_id),
        )
    bus.open_project = project_id
    bus.projects_asked.add(project_id)
    return LadderAsk(
        project_id=project_id, rung_ids=LADDER_RUNGS, asked_at=asked_at
    )


def human_allowed(project_id: str, test_id: str, reason: Optional[str]) -> bool:
    """True only after the ladder was asked and a reason is given."""
    bus = _episode_bus()
    if project_id not in bus.projects_asked:
        bus.open_project = None
        raise LadderError(
            "HUMAN_BEFORE_LADDER",
            "project %r runs a HUMAN step before the ladder was asked; "
            "ask the ladder first" % project_id,
        )
    if not reason:
        bus.open_project = None
        raise LadderError(
            "HUMAN_REASON_MISSING",
            "HUMAN step %r of project %r carries no reason" % (test_id, project_id),
        )
    bus.open_project = None
    return True


#: Entry points: logical name -> symbol in this module.
ENTRY_POINTS = {
    "ladder_rungs": "ladder_rungs",
    "describe_rungs": "describe_rungs",
    "ask_ladder_once": "ask_ladder_once",
    "human_allowed": "human_allowed",
}
