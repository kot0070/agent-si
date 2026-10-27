"""Resource scheduler with the frozen creation order (Manifest sec 38).

Frozen phase order: candidates -> precheck -> budget-precheck -> persist
snapshot -> persist decision -> bind -> sched-reserve -> budget-reserve ->
compensate on later-gate failure -> AttemptExecutionGate -> CREATED -> RUNNING.

The scheduler precheck is read-only and never reserves. Budget admission
follows the frozen inequality (BLOCK iff spent + reserved + req > hard,
unless an explicit user override ref is present). Late-gate failure runs
compensate(): the sched lease and any budget reservation are released and
the attempt never leaves CREATED. Collaborators (router candidates, budget
admission/reserve/release, persistence, execution gate) are injected as
plain callables so tests use fakes; this module imports no routing or
budget writer code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from iface.frozen_manifest import manifest
except ImportError:  # alternate layout: the iface/ folder on sys.path
    from frozen_manifest import manifest  # type: ignore[no-redef]

try:
    from agent_si.runtime.scheduler import leases as _leases
except ImportError:  # pragma: no cover - exercised only in odd layouts
    from . import leases as _leases  # type: ignore[no-redef]


PHASE_ORDER: Tuple[str, ...] = (
    "candidates",
    "precheck",
    "budget_precheck",
    "persist_snapshot",
    "persist_decision",
    "bind",
    "sched_reserve",
    "budget_reserve",
    "execution_gate",
    "run_start",
)


class BudgetBlockedError(Exception):
    """Hard-budget admission refused the reservation."""


class NoCandidateError(Exception):
    """Router offered no eligible candidate."""


def budget_blocked(
    spent: float,
    reserved: float,
    hard_limit: float,
    requested: float,
    override_ref: Optional[str] = None,
) -> bool:
    """Frozen admission inequality: BLOCK iff spent+reserved+req > hard.

    An explicit user override ref lifts the block; anything else (None or
    empty) leaves the inequality in force. The caller derives remaining as
    hard - spent - reserved; it is never stored as independent truth.
    """
    if override_ref:
        return False
    return spent + reserved + requested > hard_limit


# Sec-38 config carries no timeout knob, yet every bound lease needs an
# expiry (reserve outputs include lease_timeout and estimated_start derives
# from it). This single default is the lease bound used for all of them.
LEASE_TIMEOUT_DEFAULT = 60.0

# Internal derivation mapping (sec-38 nine -> runtime bounds):
# - LeaseStore capacity_slots = min(max_parallel_global,
#   max_parallel_per_provider, max_parallel_per_model,
#   local_gpu_slots + local_cpu_slots); the per-provider/per-model bounds act
#   as additional global caps here because SchedulingRequest carries no
#   provider/model key, so the tightest bound governs. local_gpu_slots and
#   local_cpu_slots may each be 0 (e.g. CPU-only), but the derived capacity
#   must stay >= 1: no unlimited local parallel inference.
# - LeaseStore lease_timeout = LEASE_TIMEOUT_DEFAULT (fixed; sec 38 names no
#   timeout field).
# - Queueing follows queue_policy ("excess demand queues, never drops");
#   priority_policy selects the drain order (FIFO head-first in promote()).
# The frozen behaviors are unchanged: precheck is read-only and never
# reserves; BLOCK iff spent + reserved + req > hard unless an explicit user
# override ref is present; frozen phase order with compensate() on late-gate
# (budget-reserve/execution-gate) failure; expired-untrusted, orphan-release,
# plan-restore, late-quarantine and always-empty auto_resumed on recovery.


@dataclass(frozen=True)
class SchedulerConfig:
    """Manifest sec 38 scheduler config, in manifest field order.

    Parallelism is always finite and at least one: the three max_parallel_*
    bounds are ints >= 1 and the derived capacity is >= 1.
    """

    max_parallel_global: int
    max_parallel_per_provider: int
    max_parallel_per_model: int
    local_gpu_slots: int
    local_cpu_slots: int
    memory_budget: int
    gpu_memory_budget: int
    queue_policy: str
    priority_policy: str

    def __post_init__(self) -> None:
        for name in (
            "max_parallel_global",
            "max_parallel_per_provider",
            "max_parallel_per_model",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("%s must be an int >= 1" % name)
            if value < 1:
                raise ValueError("%s must be an int >= 1" % name)
        for name in (
            "local_gpu_slots",
            "local_cpu_slots",
            "memory_budget",
            "gpu_memory_budget",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("%s must be an int >= 0" % name)
            if value < 0:
                raise ValueError("%s must be an int >= 0" % name)
        for name in ("queue_policy", "priority_policy"):
            if not isinstance(getattr(self, name), str):
                raise ValueError("%s must be a str" % name)
        if self.capacity_slots < 1:
            raise ValueError(
                "derived capacity must be >= 1: no unlimited local parallel"
            )

    @property
    def capacity_slots(self) -> int:
        """Effective local parallelism bound driving the LeaseStore."""
        return min(
            self.max_parallel_global,
            self.max_parallel_per_provider,
            self.max_parallel_per_model,
            self.local_gpu_slots + self.local_cpu_slots,
        )

    @property
    def lease_timeout(self) -> float:
        """Lease bound: fixed default, since sec 38 names no timeout field."""
        return LEASE_TIMEOUT_DEFAULT


@dataclass(frozen=True)
class SchedulingRequest:
    """One run creation ask: capacity facts plus budget facts."""

    project_id: str
    task_id: str
    run_id: str
    resource_type: str
    requested_capacity: int = 1
    spent: float = 0.0
    reserved: float = 0.0
    hard_limit: float = 0.0
    requested_amount: float = 0.0
    override_ref: Optional[str] = None
    now: float = 0.0


@dataclass(frozen=True)
class SchedulingResult:
    """Outcome of submit(); phases records the executed frozen prefix."""

    run_id: str
    status: str  # "RUNNING" | "BLOCKED" | "QUEUED" | "FAILED"
    phases: Tuple[str, ...]
    lease_id: Optional[str]
    lease: Optional[_leases.ResourceLease]
    reservation: Optional[_leases.ResourceReservation]
    budget_reservation_ref: Optional[str]
    queue_position: Optional[int]
    estimated_start: Optional[float]
    run_status: Any
    attempt_status: Any
    compensated: bool
    blocked_reason: Optional[str]


@dataclass(frozen=True)
class PlannedSubtaskState:
    """One planned subtask as persisted before the restart."""

    subtask_id: str
    status: str
    dependency_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PersistedPlanGraph:
    """Persisted task plan: subtasks plus dependency edges."""

    task_plan_id: str
    project_id: str
    task_id: str
    contract_hash: str
    plan_status: str
    subtasks: Tuple[PlannedSubtaskState, ...] = ()


@dataclass(frozen=True)
class LateResult:
    """Provider output that arrived after suspension: quarantined, never run."""

    attempt_id: str
    run_id: str
    output_ref: str
    arrived_after_suspension: bool = True


@dataclass(frozen=True)
class RestartRecoveryReport:
    """Restart answer: plan restored, leases reconciled, late output held."""

    plan_restored: bool
    restored_plan_id: Optional[str]
    restored_plan: Optional[PersistedPlanGraph]
    restored_run_ids: Tuple[str, ...]
    lease_recovery: Any
    quarantined_late_results: Tuple[LateResult, ...]
    auto_resumed: Tuple[str, ...]


class ResourceScheduler:
    """Executes the frozen creation order with injected collaborators."""

    def __init__(
        self,
        config: SchedulerConfig,
        store: Optional[_leases.LeaseStore] = None,
        list_candidates: Optional[Callable[[SchedulingRequest], list]] = None,
        budget_check: Optional[Callable[..., bool]] = None,
        budget_reserve: Optional[Callable[[SchedulingRequest], str]] = None,
        budget_release: Optional[Callable[[str], None]] = None,
        persist_snapshot: Optional[Callable[[Any], str]] = None,
        persist_decision: Optional[Callable[[str, str], str]] = None,
        execution_gate: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self._config = config
        self._store = store or _leases.LeaseStore(
            capacity_slots=config.capacity_slots,
            lease_timeout=config.lease_timeout,
        )
        self._list_candidates = list_candidates or (
            lambda request: ["local"]
        )
        self._budget_check = budget_check or (
            lambda spent, reserved, hard, req, override=None: budget_blocked(
                spent, reserved, hard, req, override
            )
        )
        self._budget_reserve = budget_reserve or (
            lambda request: self._default_budget_reserve(request)
        )
        self._released_budgets: List[str] = []
        self._budget_release = budget_release or self._released_budgets.append
        self._snapshots: Dict[str, Any] = {}
        self._persist_snapshot = persist_snapshot or self._store_snapshot
        self._decisions: Dict[str, str] = {}
        self._persist_decision = persist_decision or self._store_decision
        self._execution_gate = execution_gate or (lambda run_id: True)

    @property
    def config(self) -> SchedulerConfig:
        return self._config

    @property
    def store(self) -> _leases.LeaseStore:
        return self._store

    def _default_budget_reserve(self, request: SchedulingRequest) -> str:
        if budget_blocked(
            request.spent,
            request.reserved,
            request.hard_limit,
            request.requested_amount,
            request.override_ref,
        ):
            raise BudgetBlockedError("hard budget blocks")
        return "bref-%s" % request.run_id

    def _store_snapshot(self, snapshot: Any) -> str:
        snapshot_id = snapshot.resource_state_snapshot_id
        self._snapshots[snapshot_id] = snapshot
        return snapshot_id

    def _store_decision(self, snapshot_id: str, run_id: str) -> str:
        decision_id = "dec-%s" % run_id
        self._decisions[decision_id] = snapshot_id
        return decision_id

    def compensate(
        self,
        lease_id: Optional[str],
        budget_ref: Optional[str],
        now: float,
    ) -> bool:
        """Release the sched lease and any budget reservation. Idempotent."""
        if lease_id is not None:
            try:
                self._store.release(lease_id, now)
            except KeyError:
                # Idempotent best-effort release: an unknown lease is
                # already gone, so there is nothing left to release.
                pass
        if budget_ref is not None:
            try:
                self._budget_release(budget_ref)
            except Exception:
                # Idempotent best-effort release: a failing injected budget
                # releaser must never mask the admission/gate outcome.
                pass
        return True

    def submit(self, request: SchedulingRequest) -> SchedulingResult:
        phases: List[str] = []
        created = manifest.ExecutionAttemptStatus.CREATED

        def _blocked(reason: str, lease=None, reservation=None,
                     lease_id=None, budget_ref=None,
                     queue_position=None, estimated_start=None,
                     compensated=False) -> SchedulingResult:
            return SchedulingResult(
                run_id=request.run_id,
                status="BLOCKED",
                phases=tuple(phases),
                lease_id=lease_id,
                lease=lease,
                reservation=reservation,
                budget_reservation_ref=budget_ref,
                queue_position=queue_position,
                estimated_start=estimated_start,
                run_status=manifest.ExecutionRunStatus.CREATED,
                attempt_status=created,
                compensated=compensated,
                blocked_reason=reason,
            )

        candidates = self._list_candidates(request)
        phases.append("candidates")
        if not candidates:
            return _blocked("ROUTING_NO_ELIGIBLE_CANDIDATE")

        ask = _leases.LeaseRequest(
            project_id=request.project_id,
            task_id=request.task_id,
            run_id=request.run_id,
            resource_type=request.resource_type,
            requested_capacity=request.requested_capacity,
        )
        precheck = self._store.precheck(ask, request.now)
        phases.append("precheck")

        blocked = self._budget_check(
            request.spent,
            request.reserved,
            request.hard_limit,
            request.requested_amount,
            request.override_ref,
        )
        phases.append("budget_precheck")
        if blocked:
            return _blocked("BUDGET_BLOCKED")

        snapshot_id = self._persist_snapshot(precheck.snapshot)
        phases.append("persist_snapshot")
        self._persist_decision(snapshot_id, request.run_id)
        phases.append("persist_decision")
        phases.append("bind")

        outcome = self._store.reserve(ask, request.now)
        phases.append("sched_reserve")
        if outcome.kind == "QUEUED":
            return SchedulingResult(
                run_id=request.run_id,
                status="QUEUED",
                phases=tuple(phases),
                lease_id=None,
                lease=None,
                reservation=None,
                budget_reservation_ref=None,
                queue_position=outcome.queue_position,
                estimated_start=outcome.estimated_start,
                run_status=manifest.ExecutionRunStatus.CREATED,
                attempt_status=created,
                compensated=False,
                blocked_reason=None,
            )

        assert outcome.lease is not None
        try:
            budget_ref = self._budget_reserve(request)
        except Exception:
            self.compensate(outcome.lease.lease_id, None, request.now)
            phases.append("budget_reserve")
            return _blocked(
                "BUDGET_BLOCKED",
                lease=self._store.get_lease(outcome.lease.lease_id),
                reservation=outcome.reservation,
                lease_id=outcome.lease.lease_id,
                compensated=True,
            )
        phases.append("budget_reserve")

        gate_pass = self._execution_gate(request.run_id)
        phases.append("execution_gate")
        if not gate_pass:
            self.compensate(
                outcome.lease.lease_id, budget_ref, request.now
            )
            return _blocked(
                "EXECUTION_GATE_DENIED",
                lease=self._store.get_lease(outcome.lease.lease_id),
                reservation=outcome.reservation,
                lease_id=outcome.lease.lease_id,
                budget_ref=budget_ref,
                compensated=True,
            )

        if not manifest.is_run_transition_allowed("CREATED", "RUNNING"):
            raise NoCandidateError("frozen run edge CREATED -> RUNNING closed")
        if not manifest.is_attempt_transition_allowed("CREATED", "RUNNING"):
            raise NoCandidateError(
                "frozen attempt edge CREATED -> RUNNING closed"
            )
        phases.append("run_start")
        if outcome.reservation is not None:
            self._store.fulfill(
                outcome.reservation.reservation_id, request.now
            )
        return SchedulingResult(
            run_id=request.run_id,
            status="RUNNING",
            phases=tuple(phases),
            lease_id=outcome.lease.lease_id,
            lease=self._store.get_lease(outcome.lease.lease_id),
            reservation=outcome.reservation,
            budget_reservation_ref=budget_ref,
            queue_position=None,
            estimated_start=outcome.estimated_start,
            run_status=manifest.ExecutionRunStatus.RUNNING,
            attempt_status=manifest.ExecutionAttemptStatus.RUNNING,
            compensated=False,
            blocked_reason=None,
        )

    def recover(
        self,
        persisted_plan: PersistedPlanGraph,
        persisted_leases: Tuple[_leases.ResourceLease, ...],
        persisted_reservations: Tuple[_leases.ResourceReservation, ...],
        live_run_ids: Tuple[str, ...],
        late_results: Tuple[LateResult, ...],
        now: float,
    ) -> RestartRecoveryReport:
        """Restart: restore the plan graph, reconcile leases, hold late output.

        Late results are quarantined and never auto-resumed: the returned
        auto_resumed tuple is always empty and no attempt changes state.
        """
        lease_report = self._store.recover(
            persisted_leases, persisted_reservations,
            tuple(live_run_ids), now,
        )
        known = {sub.subtask_id for sub in persisted_plan.subtasks}
        edges_hold = all(
            dep in known
            for sub in persisted_plan.subtasks
            for dep in sub.dependency_ids
        )
        restored = bool(persisted_plan.task_plan_id) and edges_hold
        quarantined = tuple(
            result
            for result in late_results
            if result.arrived_after_suspension
        )
        return RestartRecoveryReport(
            plan_restored=restored,
            restored_plan_id=(
                persisted_plan.task_plan_id if restored else None
            ),
            restored_plan=persisted_plan if restored else None,
            restored_run_ids=lease_report.revalidated_run_ids,
            lease_recovery=lease_report,
            quarantined_late_results=quarantined,
            auto_resumed=(),
        )
