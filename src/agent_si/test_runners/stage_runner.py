"""K03 TEST stage runner STEP2: plan -> permission -> running -> results.

A stage run moves one step at a time along PLAN -> PERMISSION -> RUNNING ->
RESULTS. Results carry per-test terminal statuses with openable output
refs; FLAKY never counts as PASS and BLOCKED, MANUAL_REQUIRED and SKIP_NA
always carry a reason. Counters count what the runner recorded: passed for
PASS rows, remaining for recorded non-PASS rows, active for in-flight rows
(zero at rest since every recorded status is terminal). Failures go back
for fixing through a refix request. Finishing a run or sending it back
concludes the run's permission episode on the shared episode bus.
Provider-facing legs carry the K04 budget-gateway record shapes (field
names mirror the K04 BudgetGate; the gate implementation stays with K04):
spend is reserved before any billable leg, an ASK is raised near the cap
(leg recorded, settle held until the ASK resolves), and settled legs are
deduplicated. Demo tiers mirror the gate shape: single legs below the
review floor pass clean, legs at or above the review floor raise a soft
warn, legs near the demo cap record a pending cap ASK, and legs at or
above the hard cap are blocked.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

#: Exact shipped-preset model id (never retyped, never a second id).
MODEL_ID = "meta/muse-spark-1.3-contributor"


class StageState(str, Enum):
    PLAN = "PLAN"
    PERMISSION = "PERMISSION"
    RUNNING = "RUNNING"
    RESULTS = "RESULTS"


#: Per-test terminal statuses (FLAKY never counts as PASS; BLOCKED,
#: MANUAL_REQUIRED and SKIP_NA always carry a reason).
TEST_STATUSES = ("PASS", "FAIL", "BLOCKED", "MANUAL_REQUIRED", "SKIP_NA", "FLAKY")

#: Frozen error-code names for this module (each pinned in its own test;
#: gateway codes keep K04 parity).
ERROR_CODES_STAGE = (
    "STAGE_BAD_TRANSITION",
    "EMPTY_STAGE_RESULTS",
    "NO_FAILURES_FOR_REFIX",
    "SPEND_WITHOUT_RESERVATION",
    "CAP_ASK_UNRESOLVED",
    "BUDGET_SOFT_WARN",
    "BUDGET_HARD_BLOCKED",
    "DUPLICATE_SETTLEMENT_REFUSED",
    "STATUS_REASON_MISSING",
    "UNKNOWN_TEST_STATUS",
)


class StageError(Exception):
    """Stage failure carrying the frozen ``.code`` name."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


#: One legal step along PLAN -> PERMISSION -> RUNNING -> RESULTS.
_NEXT_STATE = {
    StageState.PLAN: StageState.PERMISSION,
    StageState.PERMISSION: StageState.RUNNING,
    StageState.RUNNING: StageState.RESULTS,
}

#: Statuses that must always carry a reason.
_REASON_REQUIRED = ("BLOCKED", "MANUAL_REQUIRED", "SKIP_NA")

#: Demo tiers mirroring the K04 gate shape (production caps stay with K04):
#: single legs below REVIEW_AT pass clean; REVIEW_AT..NEAR_CAP_AT raise a
#: soft warn; NEAR_CAP_AT..HARD_BLOCK_AT record a pending cap ASK (settle
#: held); at or above HARD_BLOCK_AT the leg is blocked.
DEMO_CAP_BASE = 1000.0
SPEND_REVIEW_AT = 50.0
SPEND_NEAR_CAP_AT = 900.0
SPEND_HARD_BLOCK_AT = 5000.0

#: Process-wide episode bus key, shared with the permission ladder module.
_BUS_KEY = "k03_stage_episode_bus"


def _episode_bus() -> types.ModuleType:
    """Return the process-wide single-operator permission-episode bus.

    Shared with the ladder and ASK-resume modules; attributes are
    ensured no matter which module first creates the bus.
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


def _conclude_episode(project_id: Optional[str]) -> None:
    """Conclude the open permission episode for one project, if it is open."""
    if project_id is None:
        return
    bus = _episode_bus()
    if bus.open_project == project_id:
        bus.open_project = None


@dataclass(frozen=True)
class StageRun:
    run_id: str
    project_id: str
    plan_id: str
    state: StageState


@dataclass(frozen=True)
class TestResult:
    run_id: str
    test_id: str
    status: str
    output_ref: Optional[str]
    reason: Optional[str]


@dataclass(frozen=True)
class StageCounters:
    active: int
    passed: int
    remaining: int


@dataclass(frozen=True)
class RefixRequest:
    run_id: str
    failure_ids: Tuple[str, ...]
    requested_at: str


@dataclass(frozen=True)
class SpendReservation:
    reservation_id: str
    project_id: str
    task_id: str
    run_id: str
    estimated_amount: float
    provider_request_ref: str
    model: str


@dataclass(frozen=True)
class SpendSettlement:
    settlement_id: str
    reservation_id: str
    provider_usage_evidence_ref: Optional[str]
    provider_request_ref: str
    dedupe_key: str
    actual_amount: Optional[float]
    status: str


#: Stage runs by run id; restarting a run id replans it from PLAN.
_RUNS: Dict[str, StageRun] = {}

#: Recorded terminal results by run id, in recording order.
_RESULTS: Dict[str, List[TestResult]] = {}

#: Spend reservations by reservation id.
_RESERVATIONS: Dict[str, SpendReservation] = {}

#: Reservations whose near-cap ASK is still unresolved: settle is held.
_CAP_ASK_PENDING: set = set()

#: Settle dedupe keys already consumed.
_SETTLED_DEDUPE_KEYS: set = set()

#: Reservation sequence for unique reservation ids.
_RESERVATION_SEQ = [0]


def start_stage(project_id: str, plan_id: str, run_id: str) -> StageRun:
    """Open a stage run in PLAN state for an existing plan."""
    run = StageRun(
        run_id=run_id, project_id=project_id, plan_id=plan_id,
        state=StageState.PLAN,
    )
    _RUNS[run_id] = run
    _RESULTS[run_id] = []
    return run


def advance_stage(run: StageRun, target_state: StageState) -> StageRun:
    """Move one step along PLAN -> PERMISSION -> RUNNING -> RESULTS."""
    current = _RUNS.get(run.run_id)
    state = current.state if current is not None else run.state
    if current is None or _NEXT_STATE.get(state) != target_state:
        raise StageError(
            "STAGE_BAD_TRANSITION",
            "run %r cannot move from %s to %s; one step at a time along "
            "PLAN -> PERMISSION -> RUNNING -> RESULTS"
            % (run.run_id, state, target_state),
        )
    advanced = StageRun(
        run_id=current.run_id,
        project_id=current.project_id,
        plan_id=current.plan_id,
        state=target_state,
    )
    _RUNS[current.run_id] = advanced
    return advanced


def record_result(
    run_id: str,
    test_id: str,
    status: str,
    output_ref: Optional[str],
    reason: Optional[str],
) -> TestResult:
    """Record one per-test status with an openable output ref."""
    if run_id not in _RUNS:
        raise StageError(
            "STAGE_BAD_TRANSITION",
            "run %r never started; results belong to a started run" % run_id,
        )
    if status not in TEST_STATUSES:
        raise StageError(
            "UNKNOWN_TEST_STATUS",
            "status %r is outside the terminal vocabulary" % (status,),
        )
    if status in _REASON_REQUIRED and not reason:
        raise StageError(
            "STATUS_REASON_MISSING",
            "status %r for test %r carries no reason" % (status, test_id),
        )
    recorded = TestResult(
        run_id=run_id,
        test_id=test_id,
        status=status,
        output_ref=output_ref,
        reason=reason,
    )
    _RESULTS.setdefault(run_id, []).append(recorded)
    return recorded


def stage_counters(run_id: str) -> StageCounters:
    """Active / passed / remaining counters for the run view."""
    rows = _RESULTS.get(run_id, [])
    passed = sum(1 for row in rows if row.status == "PASS")
    remaining = sum(1 for row in rows if row.status != "PASS")
    active = sum(1 for row in rows if row.status not in TEST_STATUSES)
    return StageCounters(active=active, passed=passed, remaining=remaining)


def finish_stage(run_id: str) -> StageRun:
    """Close a run into RESULTS; runs without recorded results fail."""
    rows = _RESULTS.get(run_id, [])
    if not rows:
        raise StageError(
            "EMPTY_STAGE_RESULTS",
            "run %r has no recorded results to close" % run_id,
        )
    current = _RUNS.get(run_id)
    if current is not None and current.state == StageState.RESULTS:
        raise StageError(
            "STAGE_BAD_TRANSITION",
            "run %r is already closed in RESULTS" % run_id,
        )
    project_id = current.project_id if current is not None else None
    finished = StageRun(
        run_id=run_id,
        project_id=project_id if project_id is not None else "",
        plan_id=current.plan_id if current is not None else "",
        state=StageState.RESULTS,
    )
    _RUNS[run_id] = finished
    _conclude_episode(project_id)
    return finished


def request_refix(run_id: str, failure_ids: List[str], requested_at: str) -> RefixRequest:
    """Send failures back for fixing; empty failure lists are refused."""
    if not failure_ids:
        raise StageError(
            "NO_FAILURES_FOR_REFIX",
            "run %r sends no failures back for fixing" % run_id,
        )
    current = _RUNS.get(run_id)
    _conclude_episode(current.project_id if current is not None else None)
    return RefixRequest(
        run_id=run_id, failure_ids=tuple(failure_ids),
        requested_at=requested_at,
    )


def gateway_spend_leg(
    project_id: str,
    task_id: str,
    run_id: str,
    estimated_amount: float,
    provider_request_ref: str,
    model: str,
) -> SpendReservation:
    """Reserve gateway spend before any billable provider leg."""
    if estimated_amount >= SPEND_HARD_BLOCK_AT:
        raise StageError(
            "BUDGET_HARD_BLOCKED",
            "leg %.2f for project %r is at or above the hard cap"
            % (estimated_amount, project_id),
        )
    if estimated_amount >= SPEND_NEAR_CAP_AT:
        _RESERVATION_SEQ[0] += 1
        reservation = SpendReservation(
            reservation_id="res-%s-%s-%d"
            % (project_id, run_id, _RESERVATION_SEQ[0]),
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            estimated_amount=estimated_amount,
            provider_request_ref=provider_request_ref,
            model=model,
        )
        _RESERVATIONS[reservation.reservation_id] = reservation
        _CAP_ASK_PENDING.add(reservation.reservation_id)
        return reservation
    if estimated_amount >= SPEND_REVIEW_AT:
        raise StageError(
            "BUDGET_SOFT_WARN",
            "leg %.2f for project %r needs review before spend"
            % (estimated_amount, project_id),
        )
    _RESERVATION_SEQ[0] += 1
    reservation = SpendReservation(
        reservation_id="res-%s-%s-%d" % (project_id, run_id, _RESERVATION_SEQ[0]),
        project_id=project_id,
        task_id=task_id,
        run_id=run_id,
        estimated_amount=estimated_amount,
        provider_request_ref=provider_request_ref,
        model=model,
    )
    _RESERVATIONS[reservation.reservation_id] = reservation
    return reservation


def settle_spend_leg(settlement: SpendSettlement) -> SpendSettlement:
    """Settle a reserved leg; duplicates refused, caps enforced, spend kept."""
    if settlement.reservation_id not in _RESERVATIONS:
        raise StageError(
            "SPEND_WITHOUT_RESERVATION",
            "settlement %r has no reservation %r"
            % (settlement.settlement_id, settlement.reservation_id),
        )
    if settlement.reservation_id in _CAP_ASK_PENDING:
        raise StageError(
            "CAP_ASK_UNRESOLVED",
            "reservation %r sits near the cap with its ASK unresolved"
            % (settlement.reservation_id,),
        )
    if settlement.dedupe_key in _SETTLED_DEDUPE_KEYS:
        raise StageError(
            "DUPLICATE_SETTLEMENT_REFUSED",
            "settlement %r reuses dedupe key %r"
            % (settlement.settlement_id, settlement.dedupe_key),
        )
    _SETTLED_DEDUPE_KEYS.add(settlement.dedupe_key)
    return SpendSettlement(
        settlement_id=settlement.settlement_id,
        reservation_id=settlement.reservation_id,
        provider_usage_evidence_ref=settlement.provider_usage_evidence_ref,
        provider_request_ref=settlement.provider_request_ref,
        dedupe_key=settlement.dedupe_key,
        actual_amount=settlement.actual_amount,
        status="SETTLED",
    )


#: Frozen HTTP surface: (method, path) pairs served for this lane.
STAGE_ROUTES = (
    ("POST", "/api/v1/teststage/plans"),
    ("POST", "/api/v1/teststage/permissions/ask"),
    ("POST", "/api/v1/teststage/runs/start"),
    ("POST", "/api/v1/teststage/runs/advance"),
    ("POST", "/api/v1/teststage/runs/results"),
    ("GET", "/api/v1/teststage/runs/counters"),
    ("POST", "/api/v1/teststage/runs/finish"),
    ("POST", "/api/v1/teststage/runs/refix"),
    ("POST", "/api/v1/teststage/runs/spend-leg"),
    ("POST", "/api/v1/teststage/runs/spend-settle"),
    ("POST", "/api/v1/teststage/ask/resume"),
)

#: Route -> entry point that serves it (dotted path; STEP2 implements).
REALIZATION_MAP = {
    "POST /api/v1/teststage/plans": "agent_si.test_runners.test_planner.derive_plan",
    "POST /api/v1/teststage/permissions/ask": "agent_si.test_runners.permission_ladder.ask_ladder_once",
    "POST /api/v1/teststage/runs/start": "agent_si.test_runners.stage_runner.start_stage",
    "POST /api/v1/teststage/runs/advance": "agent_si.test_runners.stage_runner.advance_stage",
    "POST /api/v1/teststage/runs/results": "agent_si.test_runners.stage_runner.record_result",
    "GET /api/v1/teststage/runs/counters": "agent_si.test_runners.stage_runner.stage_counters",
    "POST /api/v1/teststage/runs/finish": "agent_si.test_runners.stage_runner.finish_stage",
    "POST /api/v1/teststage/runs/refix": "agent_si.test_runners.stage_runner.request_refix",
    "POST /api/v1/teststage/runs/spend-leg": "agent_si.test_runners.stage_runner.gateway_spend_leg",
    "POST /api/v1/teststage/runs/spend-settle": "agent_si.test_runners.stage_runner.settle_spend_leg",
    "POST /api/v1/teststage/ask/resume": "agent_si.test_runners.ask_resume.resume_run",
}

#: Entry points: logical name -> symbol in this module.
ENTRY_POINTS = {
    "start_stage": "start_stage",
    "advance_stage": "advance_stage",
    "record_result": "record_result",
    "stage_counters": "stage_counters",
    "finish_stage": "finish_stage",
    "request_refix": "request_refix",
    "gateway_spend_leg": "gateway_spend_leg",
    "settle_spend_leg": "settle_spend_leg",
}
