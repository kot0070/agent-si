"""K13 M3A resource scheduler tests (Manifest sections 14, 27A, 28, 38).

RED-first: these tests import agent_si.runtime.scheduler, which does not
exist yet, so they must FAIL before the implementation lands.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from iface.frozen_manifest import manifest
from agent_si.runtime.scheduler import leases
from agent_si.runtime.scheduler import scheduler as sched


def test_manifest_verifies():
    assert manifest.MANIFEST_SHA256 == (
        "f256bab4d31be3cd9e86c22a1bdcef90b08ad62500a8eca2051705cc0a9b0690"
    )
    assert (
        manifest.verify_manifest(ROOT / "RECORDS" / "day0" / "K13_MANIFEST.md")
        is True
    )


def _req(**overrides):
    base = dict(
        project_id="P1",
        task_id="T1",
        run_id="R1",
        resource_type="local-gpu",
        requested_capacity=1,
        spent=0.0,
        reserved=0.0,
        hard_limit=100.0,
        requested_amount=10.0,
        override_ref=None,
        now=1000.0,
    )
    base.update(overrides)
    return sched.SchedulingRequest(**base)


def _store(capacity=2, timeout=60.0):
    return leases.LeaseStore(capacity_slots=capacity, lease_timeout=timeout)


def _config(**overrides):
    base = dict(
        max_parallel_global=2,
        max_parallel_per_provider=2,
        max_parallel_per_model=2,
        local_gpu_slots=1,
        local_cpu_slots=1,
        memory_budget=1024,
        gpu_memory_budget=1024,
        queue_policy="FIFO",
        priority_policy="FIFO",
    )
    base.update(overrides)
    return sched.SchedulerConfig(**base)


def _full_stack(store=None, log=None, **overrides):
    store = store or _store()
    log = log if log is not None else []
    released_budgets = []

    def _logged(name, fn):
        def wrapper(*args, **kwargs):
            log.append(name)
            return fn(*args, **kwargs)

        return wrapper

    persisted = {}

    def _persist_snapshot(snapshot):
        log.append("persist_snapshot")
        persisted["snapshot"] = snapshot
        return snapshot.resource_state_snapshot_id

    def _persist_decision(snapshot_id, run_id):
        log.append("persist_decision")
        assert persisted["snapshot"].resource_state_snapshot_id == snapshot_id
        return "dec-%s" % run_id

    def _budget_reserve(request):
        log.append("budget_reserve")
        if sched.budget_blocked(
            request.spent,
            request.reserved,
            request.hard_limit,
            request.requested_amount,
            request.override_ref,
        ):
            raise sched.BudgetBlockedError("hard budget blocks")
        return "bref-%s" % request.run_id

    def _budget_release(ref):
        log.append("budget_release")
        released_budgets.append(ref)

    def _gate(run_id):
        log.append("execution_gate")
        return True

    engine = sched.ResourceScheduler(
        _config(),
        store=overrides.pop("store", store),
        list_candidates=overrides.pop(
            "list_candidates",
            _logged("candidates", lambda request: ["local"]),
        ),
        budget_check=overrides.pop(
            "budget_check",
            _logged(
                "budget_precheck",
                lambda spent, reserved, hard, req, override=None: (
                    sched.budget_blocked(spent, reserved, hard, req, override)
                ),
            ),
        ),
        persist_snapshot=overrides.pop("persist_snapshot", _persist_snapshot),
        persist_decision=overrides.pop("persist_decision", _persist_decision),
        budget_reserve=overrides.pop("budget_reserve", _budget_reserve),
        budget_release=overrides.pop("budget_release", _budget_release),
        execution_gate=overrides.pop("execution_gate", _gate),
        **overrides
    )
    return engine, store, log, released_budgets


def _state_fingerprint(store):
    return (
        store.active_capacity(),
        store.queue_depth(),
        store.lease_count(),
        store.reservation_count(),
    )


def test_precheck_never_reserves():
    store = _store()
    before = _state_fingerprint(store)
    first = store.precheck(
        leases.LeaseRequest(
            project_id="P1", task_id="T1", run_id="R1",
            resource_type="local-gpu",
        ),
        now=1000.0,
    )
    assert first.eligible is True
    assert _state_fingerprint(store) == before
    second = store.precheck(
        leases.LeaseRequest(
            project_id="P1", task_id="T1", run_id="R2",
            resource_type="local-gpu",
        ),
        now=1001.0,
    )
    assert second.eligible is True
    assert _state_fingerprint(store) == before
    assert store.lease_count() == 0
    assert store.reservation_count() == 0
    # A precheck snapshot carries capacity facts but creates no lease.
    assert first.snapshot.queue_depth == 0
    assert first.snapshot.available_gpu_slots == 2


def test_precheck_needs_no_capacity_change_when_full():
    store = _store(capacity=1)
    before = _state_fingerprint(store)
    store.reserve(
        leases.LeaseRequest(
            project_id="P1", task_id="T1", run_id="R1",
            resource_type="local-gpu",
        ),
        now=1000.0,
    )
    filled = _state_fingerprint(store)
    assert filled != before
    outcome = store.precheck(
        leases.LeaseRequest(
            project_id="P1", task_id="T1", run_id="R2",
            resource_type="local-gpu",
        ),
        now=1001.0,
    )
    assert outcome.eligible is False
    assert _state_fingerprint(store) == filled


@pytest.mark.parametrize(
    "spent,reserved,hard,req,override,expected",
    [
        (50.0, 20.0, 100.0, 30.0, None, False),  # exactly at hard: allowed
        (50.0, 20.0, 100.0, 31.0, None, True),  # one over: BLOCK
        (0.0, 0.0, 100.0, 100.0, None, False),
        (0.0, 0.0, 100.0, 101.0, None, True),
        (90.0, 20.0, 100.0, 1.0, None, True),  # reserved counts
        (90.0, 20.0, 100.0, 1.0, "ovr:user-1", False),  # explicit user ref
        (0.0, 0.0, 0.0, 0.0, None, False),  # zero request on zero hard
        (0.0, 0.0, 0.0, 1.0, None, True),
    ],
)
def test_reserve_block_inequality(spent, reserved, hard, req, override, expected):
    assert (
        sched.budget_blocked(spent, reserved, hard, req, override) is expected
    )


def test_scheduler_blocks_without_reserving():
    store = _store()
    engine, _, _, _ = _full_stack(store=store)
    before = _state_fingerprint(store)
    result = engine.submit(
        _req(spent=90.0, reserved=20.0, requested_amount=1.0)
    )
    assert result.status == "BLOCKED"
    assert result.blocked_reason == "BUDGET_BLOCKED"
    assert result.lease is None
    assert result.attempt_status != manifest.ExecutionAttemptStatus.RUNNING
    assert _state_fingerprint(store) == before


def test_scheduler_user_override_unblocks():
    store = _store()
    engine, _, _, _ = _full_stack(store=store)
    result = engine.submit(
        _req(spent=90.0, reserved=20.0, requested_amount=1.0,
             override_ref="ovr:user-1")
    )
    assert result.status == "RUNNING"
    assert result.attempt_status == manifest.ExecutionAttemptStatus.RUNNING
    assert result.lease is not None


def test_queue_never_drops_excess():
    store = _store(capacity=1)
    engine, _, _, _ = _full_stack(store=store)
    first = engine.submit(_req(run_id="R1", now=1000.0))
    assert first.status == "RUNNING"
    queued = [
        engine.submit(_req(run_id="R%d" % i, now=1000.0 + i))
        for i in range(2, 6)
    ]
    assert [r.status for r in queued] == ["QUEUED"] * 4
    positions = sorted(r.queue_position for r in queued)
    assert positions == [1, 2, 3, 4]
    assert store.queue_depth() == 4
    # Freeing capacity promotes the head of the queue; nothing is lost.
    store.release(first.lease.lease_id, now=2000.0)
    promoted = store.promote(now=2000.0)
    assert len(promoted) == 1
    assert promoted[0].kind == "LEASE"
    assert promoted[0].lease.owner_run_id == "R2"
    assert store.queue_depth() == 3


def test_frozen_phase_order_and_snapshot_before_decision():
    store = _store()
    engine, _, log, _ = _full_stack(store=store)
    result = engine.submit(_req())
    assert result.status == "RUNNING"
    assert result.phases == sched.PHASE_ORDER
    assert log.index("persist_snapshot") < log.index("persist_decision")
    assert log.index("candidates") == 0
    assert log.index("execution_gate") < len(log)
    # Scheduler reserve precedes budget reserve; gate precedes run start.
    assert result.phases.index("sched_reserve") < result.phases.index(
        "budget_reserve"
    )
    assert result.phases.index("execution_gate") < result.phases.index(
        "run_start"
    )


def test_compensate_on_budget_reserve_failure():
    store = _store()

    def _failing_budget(request):
        raise sched.BudgetBlockedError("race lost")

    engine, _, _, released = _full_stack(
        store=store, budget_reserve=_failing_budget
    )
    result = engine.submit(_req())
    assert result.status == "BLOCKED"
    assert result.compensated is True
    assert result.attempt_status == manifest.ExecutionAttemptStatus.CREATED
    assert store.get_lease(result.lease_id).status == (
        leases.ResourceLeaseStatus.RELEASED
    )
    assert store.active_capacity() == 0


def test_compensate_on_execution_gate_failure():
    store = _store()
    engine, _, log, released = _full_stack(
        store=store, execution_gate=lambda run_id: False
    )
    result = engine.submit(_req())
    assert result.status == "BLOCKED"
    assert result.blocked_reason == "EXECUTION_GATE_DENIED"
    assert result.compensated is True
    assert result.attempt_status == manifest.ExecutionAttemptStatus.CREATED
    assert store.get_lease(result.lease_id).status == (
        leases.ResourceLeaseStatus.RELEASED
    )
    assert released == [result.budget_reservation_ref]


def test_config_rejects_zero_and_unlimited_parallel():
    with pytest.raises(ValueError):
        _config(max_parallel_global=0)
    with pytest.raises(ValueError):
        _config(max_parallel_global=None)
    with pytest.raises(ValueError):
        _config(max_parallel_per_provider=-3)
    with pytest.raises(ValueError):
        _config(max_parallel_per_model=True)
    with pytest.raises(ValueError):
        _config(queue_policy=123)
    # Local slots may each be 0 (CPU-only), but the derived capacity stays
    # finite and at least one: no unlimited local parallel inference.
    with pytest.raises(ValueError):
        _config(local_gpu_slots=0, local_cpu_slots=0)
    cfg = _config(
        max_parallel_global=1,
        max_parallel_per_provider=1,
        max_parallel_per_model=1,
    )
    assert cfg.capacity_slots == 1
    assert cfg.lease_timeout == sched.LEASE_TIMEOUT_DEFAULT
    assert [f for f in cfg.__dataclass_fields__] == [
        "max_parallel_global",
        "max_parallel_per_provider",
        "max_parallel_per_model",
        "local_gpu_slots",
        "local_cpu_slots",
        "memory_budget",
        "gpu_memory_budget",
        "queue_policy",
        "priority_policy",
    ]


def test_promote_bounded_single_head_grant():
    # Regression: promote() must return promptly, granting only the head.
    store = _store(capacity=1)
    store.reserve(
        leases.LeaseRequest(
            project_id="P1", task_id="T1", run_id="R1",
            resource_type="local-gpu",
        ),
        now=1000.0,
    )
    for i, rid in enumerate(("R2", "R3", "R4")):
        store.reserve(
            leases.LeaseRequest(
                project_id="P1", task_id="T1", run_id=rid,
                resource_type="local-gpu",
            ),
            now=1001.0 + i,
        )
    assert store.queue_depth() == 3
    store.release("lease-1", now=2000.0)
    granted = store.promote(now=2000.0)
    assert len(granted) == 1
    assert granted[0].kind == "LEASE"
    assert granted[0].lease.owner_run_id == "R2"
    assert all(outcome.kind != "QUEUED" for outcome in granted)
    assert store.queue_depth() == 2
    # FIFO holds across promotions: freeing the new head grants R3, drops none.
    store.release(granted[0].lease.lease_id, now=3000.0)
    again = store.promote(now=3000.0)
    assert len(again) == 1
    assert again[0].kind == "LEASE"
    assert again[0].lease.owner_run_id == "R3"
    assert store.queue_depth() == 1


def test_created_to_running_only_through_gate():
    assert (
        manifest.is_attempt_transition_allowed("CREATED", "RUNNING") is True
    )
    assert (
        manifest.is_run_transition_allowed("CREATED", "RUNNING") is True
    )
    store = _store()
    seen = []
    engine, _, _, _ = _full_stack(
        store=store, execution_gate=lambda run_id: seen.append(run_id) or True
    )
    result = engine.submit(_req())
    assert seen == ["R1"]
    assert result.run_status == manifest.ExecutionRunStatus.RUNNING
    assert result.attempt_status == manifest.ExecutionAttemptStatus.RUNNING
