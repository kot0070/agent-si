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

import functools
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
    verification_id: Optional[str] = None
    verification_result: Optional[str] = None
    audit_id: Optional[str] = None
    verdict: Optional[str] = None
    close_row_id: Optional[str] = None
    phase: Optional[str] = None
    code: Optional[str] = None


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
    verification_id: Optional[str] = None
    verification_result: Optional[str] = None
    audit_id: Optional[str] = None
    verdict: Optional[str] = None
    close_row_id: Optional[str] = None
    phase: Optional[str] = None
    code: Optional[str] = None


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

#: Assurance outcome per stage run id; the stage read merges it.
_ASSURANCE_STATUS: Dict[str, Dict[str, Optional[str]]] = {}


def stage_assurance_status(run_id: str) -> Dict[str, Optional[str]]:
    """Return the stored assurance outcome for one stage run."""
    stored = _ASSURANCE_STATUS.get(run_id)
    if stored is None:
        return {}
    return dict(stored)


def _store_assurance_status(run_id: str, status: Dict[str, Optional[str]]) -> None:
    """Remember one assurance outcome for the stage read."""
    _ASSURANCE_STATUS[run_id] = dict(status)



def _journal(project_id, run_id, phase, status, note=""):
    """Append one watcher journal row for a served stage step (never breaks the stage).

    PART1DRIVE4 F06 (01.11): the live F04 chain runs through the teststage routes
    (start/advance/record/finish here), but P6JOURNAL wired only
    assurance.coordinator.run_assurance, so the journal stayed [] for a full chain.
    """
    try:
        from agent_si.state_machines import run_machine as _run_machine
        _run_machine.emit_lifecycle_event(
            project_id or "", run_id, phase, status, note)
    except Exception:  # journal rows are evidence, never a stage failure
        pass


def start_stage(project_id: str, plan_id: str, run_id: str) -> StageRun:
    """Open a stage run in PLAN state for an existing plan."""
    run = StageRun(
        run_id=run_id, project_id=project_id, plan_id=plan_id,
        state=StageState.PLAN,
    )
    _RUNS[run_id] = run
    _RESULTS[run_id] = []
    _ASSURANCE_STATUS.pop(run_id, None)
    _journal(project_id, run_id, "plan", "PLAN", "stage run opened plan=%s" % plan_id)
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
    _journal(current.project_id, current.run_id,
             "start" if str(getattr(target_state, "value", target_state)).endswith("RUNNING") else "advance",
             str(getattr(target_state, "value", target_state)), "stage advanced")
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
    stored = _ASSURANCE_STATUS.get(run_id, {})
    return StageCounters(
        active=active,
        passed=passed,
        remaining=remaining,
        verification_id=stored.get("verification_id"),
        verification_result=stored.get("verification_result"),
        audit_id=stored.get("audit_id"),
        verdict=stored.get("verdict"),
        close_row_id=stored.get("close_row_id"),
        phase=stored.get("phase"),
        code=stored.get("code"),
    )


def _finish_stage_impl(
    run_id: str,
    project_id: Optional[str] = None,
    task_id: Optional[str] = None,
    contract_hash: Optional[str] = None,
    project_dir: Optional[str] = None,
    work_refs: Optional[List[str]] = None,
    artifact_refs: Optional[List[str]] = None,
    evidence_refs: Optional[List[str]] = None,
    producer_session_refs: Optional[List[str]] = None,
    tool_rows: Optional[List[Dict[str, object]]] = None,
    criteria: Optional[List[Dict[str, object]]] = None,
    implementer_model_ids: Optional[List[str]] = None,
    auditor_candidates: Optional[List[Dict[str, object]]] = None,
    task_class: Optional[str] = None,
    minimum_level: Optional[str] = None,
    scope_id: Optional[str] = None,
    pair_reuse: Optional[Dict[str, object]] = None,
) -> StageRun:
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
    assurance_requested = (
        task_id is not None
        or contract_hash is not None
        or project_dir is not None
        or work_refs is not None
        or artifact_refs is not None
        or evidence_refs is not None
        or producer_session_refs is not None
        or tool_rows is not None
        or criteria is not None
        or implementer_model_ids is not None
        or auditor_candidates is not None
        or scope_id is not None
        or pair_reuse is not None
    )
    if not assurance_requested:
        project_id_legacy = current.project_id if current is not None else None
        finished = StageRun(
            run_id=run_id,
            project_id=project_id_legacy if project_id_legacy is not None else "",
            plan_id=current.plan_id if current is not None else "",
            state=StageState.RESULTS,
        )
        _RUNS[run_id] = finished
        _conclude_episode(project_id_legacy)
        return finished
    from agent_si.backend import assurance_mount as _assurance_mount

    effective_project = (
        project_id if project_id is not None
        else (current.project_id if current is not None else "")
    )
    effective_task = task_id if task_id is not None else ""
    effective_contract = contract_hash if contract_hash is not None else ""
    effective_dir = project_dir if project_dir is not None else ""
    if not effective_task.strip() or not effective_contract.strip():
        raise StageError(
            "STAGE_BAD_TRANSITION",
            "finish needs task_id and contract_hash for assurance",
        )
    if not effective_dir.strip():
        raise StageError(
            "STAGE_BAD_TRANSITION",
            "finish needs project_dir for assurance",
        )
    effective_project = str(effective_project)
    effective_task = str(effective_task).strip()
    effective_contract = str(effective_contract).strip()
    effective_dir = str(effective_dir).strip()
    work = [str(item) for item in (work_refs or [])]
    artifacts = [str(item) for item in (artifact_refs or [])]
    evidence = [str(item) for item in (evidence_refs or [])]
    producers = [str(item) for item in (producer_session_refs or [])]
    tools = list(tool_rows or [])
    crits = list(criteria or [])
    implementers = [str(item) for item in (implementer_model_ids or [])]
    candidates_raw = list(auditor_candidates or [])
    effective_class = (
        task_class.strip() if isinstance(task_class, str) and task_class.strip()
        else "served-turn"
    )
    effective_level = (
        minimum_level.strip()
        if isinstance(minimum_level, str) and minimum_level.strip()
        else "L2"
    )
    if not work and not artifacts:
        raise StageError(
            _assurance_mount._chain_coordinator.EmptyWorkError.code,
            "served finish carries no work; empty work fails",
        )
    registry = _assurance_mount._Registry()
    coordinator = _assurance_mount._Coordinator()
    pair_decision_id: Optional[str] = None
    if pair_reuse is not None:
        if not isinstance(pair_reuse, dict):
            raise StageError(
                "STAGE_BAD_TRANSITION",
                "finish needs pair_reuse as a JSON object",
            )
        raw_decision = pair_reuse.get("decision_id")
        if not isinstance(raw_decision, str) or not raw_decision.strip():
            raise StageError(
                "STAGE_BAD_TRANSITION",
                "finish needs a non-empty pair_reuse decision_id",
            )
        pair_decision_id = raw_decision.strip()
        registry.record_pair_reuse(
            _assurance_mount._chain_registry.SourcingDecision(
                decision_id=pair_decision_id,
                project_id=effective_project,
                scope=str(pair_reuse.get("scope") or ""),
                statement=str(pair_reuse.get("statement") or ""),
                reason=str(pair_reuse.get("reason") or ""),
                authority=str(pair_reuse.get("authority") or "USER"),
                decided_by=str(
                    pair_reuse.get("decided_by") or "stage-finish"),
                visible_to_user=bool(
                    pair_reuse.get("visible_to_user", True)),
                user_resolution_ref=pair_reuse.get("user_resolution_ref"),
                created_at=_assurance_mount._utcnow(),
            )
        )
    try:
        verification = _assurance_mount._chain_checker.verify_run(
            project_dir=effective_dir,
            tool_rows=list(tools),
            criteria=list(crits),
            project_id=effective_project,
            task_id=effective_task,
            run_id=run_id,
            contract_hash=effective_contract,
        )
    except Exception as exc:
        _assurance_mount._turns.record_turn(
            effective_task,
            _assurance_mount._TURN_PLAN,
            _assurance_mount._NO_AUDIT_ACTION,
            "phase=VERIFY_REFUSED verification=none result=ERROR "
            "note=%s: %s" % (type(exc).__name__, exc),
        )
        status = {
            "verification_id": None,
            "verification_result": "ERROR",
            "audit_id": None,
            "verdict": None,
            "close_row_id": None,
            "phase": "VERIFY_REFUSED",
            "code": "VERIFY_REFUSED",
        }
        _store_assurance_status(run_id, status)
        state = current.state if current is not None else StageState.RUNNING
        return StageRun(
            run_id=run_id,
            project_id=effective_project,
            plan_id=current.plan_id if current is not None else "",
            state=state,
            verification_id=None,
            verification_result="ERROR",
            audit_id=None,
            verdict=None,
            close_row_id=None,
            phase="VERIFY_REFUSED",
            code="VERIFY_REFUSED",
        )
    verification_id = verification.verification_id
    verification_result = getattr(
        verification.result, "value", str(verification.result))
    if verification_result != "PASS":
        _assurance_mount._turns.record_turn(
            effective_task,
            _assurance_mount._TURN_PLAN,
            _assurance_mount._NO_AUDIT_ACTION,
            "phase=VERIFY_REFUSED verification=%s result=%s"
            % (verification_id, verification_result),
        )
        status = {
            "verification_id": verification_id,
            "verification_result": verification_result,
            "audit_id": None,
            "verdict": None,
            "close_row_id": None,
            "phase": "VERIFY_REFUSED",
            "code": "VERIFY_REFUSED",
        }
        _store_assurance_status(run_id, status)
        state = current.state if current is not None else StageState.RUNNING
        return StageRun(
            run_id=run_id,
            project_id=effective_project,
            plan_id=current.plan_id if current is not None else "",
            state=state,
            verification_id=verification_id,
            verification_result=verification_result,
            audit_id=None,
            verdict=None,
            close_row_id=None,
            phase="VERIFY_REFUSED",
            code="VERIFY_REFUSED",
        )
    for position, raw in enumerate(candidates_raw):
        if not isinstance(raw, dict):
            raise StageError(
                "STAGE_BAD_TRANSITION",
                "auditor candidate %d must be a JSON object" % position,
            )
        provider_id = raw.get("provider_id")
        model = raw.get("model")
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise StageError(
                "STAGE_BAD_TRANSITION",
                "finish needs a non-empty auditor candidate provider_id",
            )
        if not isinstance(model, str) or not model.strip():
            raise StageError(
                "STAGE_BAD_TRANSITION",
                "finish needs a non-empty auditor candidate model",
            )
        cap_refs = raw.get("capability_evidence_refs")
        cap_list = list(cap_refs) if isinstance(cap_refs, list) else []
        registry.register_candidate(
            _assurance_mount._chain_registry.AuditorCandidate(
                provider_id=provider_id.strip(),
                provider_instance=(
                    raw.get("provider_instance")
                    if isinstance(raw.get("provider_instance"), str)
                    else None
                ),
                model=model.strip(),
                capability_evidence_refs=tuple(
                    str(item) for item in cap_list),
                registered_at="",
            )
        )
    auditor_models = {
        str(raw.get("model", "")).strip()
        for raw in candidates_raw
        if isinstance(raw, dict)
    }

    def _refuse(refs: Tuple[str, ...]) -> None:
        try:
            coordinator.refuse_contributor("", tuple(refs))
        except (
            _assurance_mount._chain_coordinator.ContributorInAuditorSetError
        ) as exc:
            _assurance_mount._turns.record_turn(
                effective_task,
                _assurance_mount._TURN_PLAN,
                _assurance_mount._NO_AUDIT_ACTION,
                "phase=REFUSED code=%s contributors=%s"
                % (exc.code, ",".join(tuple(refs))),
            )
            _store_assurance_status(run_id, {
                "verification_id": verification_id,
                "verification_result": verification_result,
                "audit_id": None,
                "verdict": None,
                "close_row_id": None,
                "phase": "REFUSED",
                "code": exc.code,
            })
            raise StageError(exc.code, str(exc)) from None

    overlap = sorted(
        {name for name in implementers if name and name in auditor_models}
    )
    if overlap:
        _refuse(tuple(overlap))
    try:
        selection = registry.select_auditor(
            effective_class,
            tuple(implementers),
            effective_level,
        )
    except _assurance_mount._chain_registry.NoEligibleAuditorError as exc:
        _assurance_mount._turns.record_turn(
            effective_task,
            _assurance_mount._TURN_PLAN,
            _assurance_mount._NO_AUDIT_ACTION,
            "phase=BLOCKED code=%s verification=%s"
            % (exc.code, verification_id),
        )
        status = {
            "verification_id": verification_id,
            "verification_result": verification_result,
            "audit_id": None,
            "verdict": None,
            "close_row_id": None,
            "phase": "BLOCKED",
            "code": exc.code,
        }
        _store_assurance_status(run_id, status)
        state = current.state if current is not None else StageState.RUNNING
        return StageRun(
            run_id=run_id,
            project_id=effective_project,
            plan_id=current.plan_id if current is not None else "",
            state=state,
            verification_id=verification_id,
            verification_result=verification_result,
            audit_id=None,
            verdict=None,
            close_row_id=None,
            phase="BLOCKED",
            code=exc.code,
        )
    if not registry.check_separate_model(
        selection.auditor.model, tuple(implementers)
    ):
        _refuse((selection.auditor.model,))
    turn = _assurance_mount._chain_coordinator.ServedTurn(
        turn_ref=run_id,
        project_id=effective_project,
        task_id=effective_task,
        run_id=run_id,
        work_refs=tuple(work),
        artifact_refs=tuple(artifacts),
        evidence_refs=tuple(evidence),
        producer_session_refs=tuple(producers),
        contract_hash=effective_contract,
    )
    audit_id = coordinator.audit_with_fresh_auditor(turn)
    scope = scope_id.strip() if isinstance(
        scope_id, str) and scope_id.strip() else "%s/%s/%s" % (
        effective_project, effective_task, effective_contract)
    row_id = coordinator.close_stage(effective_task, scope, audit_id)
    stored = _assurance_mount._chain_records._fetch_record(audit_id)
    verdict = getattr(
        getattr(stored, "result", None), "value", None) or "UNKNOWN"
    audit_session = getattr(stored, "context_session_ref", "") or ""
    _assurance_mount._turns.record_turn(
        effective_task,
        _assurance_mount._TURN_PLAN,
        audit_id,
        "phase=CLOSED verification=%s verdict=%s close=%s "
        "auditor=%s session=%s"
        % (
            verification_id,
            verdict,
            row_id,
            selection.auditor.model,
            audit_session,
        ),
    )
    _store_assurance_status(run_id, {
        "verification_id": verification_id,
        "verification_result": verification_result,
        "audit_id": audit_id,
        "verdict": verdict,
        "close_row_id": row_id,
        "phase": "CLOSED",
        "code": None,
    })
    finished = StageRun(
        run_id=run_id,
        project_id=effective_project,
        plan_id=current.plan_id if current is not None else "",
        state=StageState.RESULTS,
        verification_id=verification_id,
        verification_result=verification_result,
        audit_id=audit_id,
        verdict=verdict,
        close_row_id=row_id,
        phase="CLOSED",
        code=None,
    )
    _RUNS[run_id] = finished
    _conclude_episode(current.project_id if current is not None else None)
    return finished



@functools.wraps(_finish_stage_impl)
def finish_stage(run_id, *args, **kwargs) -> StageRun:
    """Close a run into RESULTS (see _finish_stage_impl) and journal the outcome."""
    finished = _finish_stage_impl(run_id, *args, **kwargs)
    _journal(getattr(finished, "project_id", "") or kwargs.get("project_id") or "",
             run_id, "finish",
             str(getattr(getattr(finished, "state", ""), "value", getattr(finished, "state", ""))),
             "phase=%s code=%s" % (getattr(finished, "phase", None), getattr(finished, "code", None)))
    return finished


finish_stage.__name__ = finish_stage.__qualname__ = "finish_stage"

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


def register_stage_routes(app):
    """Mount STAGE_ROUTES on a FastAPI app; returns the app.

    Every handler calls exactly its declared REALIZATION_MAP entry: the
    dotted path is resolved lazily per request (importlib + getattr at
    request time), so this module never imports sibling lane modules at
    the top and wraps-spies on the entry observe the call. Parameters come
    from the query string merged over by the JSON body, matched against the
    entry signature (missing required parameters are 400); Enum-typed
    parameters accept their string values and dataclass-typed parameters
    accept dicts. Entry failures map to 4xx with the message text
    preserved, unexpected failures to 500.
    """
    import importlib
    import inspect
    import typing
    from fastapi import HTTPException, Request

    def _bind(app, http_method, path):
        """Duck-type binder (same shape as kb_routes._bind)."""
        binder = None
        try:
            binder = app.get if http_method == "GET" else app.post
        except AttributeError:
            binder = None
        if binder is None:
            return app.route(path, methods=[http_method])
        return binder(path)

    def _resolve(dotted):
        module_name, _, attr = dotted.rpartition(".")
        return getattr(importlib.import_module(module_name), attr)

    def _coerce(annotation, value):
        if annotation is None:
            return value
        if isinstance(annotation, type):
            import enum as _enum

            if issubclass(annotation, _enum.Enum) and isinstance(value, str):
                return annotation(value)
            if hasattr(annotation, "__dataclass_fields__") and isinstance(
                    value, dict):
                hints = typing.get_type_hints(annotation)
                return annotation(**{
                    key: _coerce(hints.get(key), item)
                    for key, item in value.items()
                })
        return value

    def _status_for(exc):
        if isinstance(exc, KeyError):
            return 404
        if isinstance(exc, (ValueError, TypeError)):
            return 400
        if isinstance(exc, StageError):
            return 400
        if (type(exc).__module__.startswith("agent_si.test_runners")
                and getattr(exc, "code", None) is not None):
            return 400
        return 500

    def _detail(exc):
        code = getattr(exc, "code", None)
        text = str(exc)
        if code is not None and str(code) not in text:
            return "%s: %s" % (code, text)
        return text

    def _make_handler(dotted):
        # NOTE: `from __future__ import annotations` keeps closure
        # annotations as strings that FastAPI cannot resolve (it sees
        # module globals, not these locals); assign the real objects so
        # `request` injects the Request instead of becoming a query param.
        async def _serve_stage_route(request):
            try:
                body = await request.json()
            except Exception:
                body = None
            merged = dict(request.query_params)
            if isinstance(body, dict):
                merged.update(body)
            try:
                entry = _resolve(dotted)
                try:
                    hints = typing.get_type_hints(entry)
                except Exception:
                    hints = {}
                signature = inspect.signature(entry)
                kwargs = {}
                for name, param in signature.parameters.items():
                    if param.kind in (
                            inspect.Parameter.VAR_POSITIONAL,
                            inspect.Parameter.VAR_KEYWORD):
                        continue
                    if name in merged:
                        if name in hints:
                            annotation = hints[name]
                        elif param.annotation is inspect.Parameter.empty:
                            annotation = None
                        else:
                            annotation = param.annotation
                        kwargs[name] = _coerce(annotation, merged[name])
                    elif param.default is inspect.Parameter.empty:
                        raise TypeError(
                            "missing required parameter %r for %s"
                            % (name, dotted))
                result = entry(**kwargs)
            except Exception as exc:
                raise HTTPException(
                    status_code=_status_for(exc),
                    detail=_detail(exc)) from exc
            return result

        _serve_stage_route.__annotations__ = {"request": Request}
        return _serve_stage_route

    for _key, _dotted in REALIZATION_MAP.items():
        _method, _, _path = _key.partition(" ")
        _bind(app, _method, _path)(_make_handler(_dotted))
    return app
