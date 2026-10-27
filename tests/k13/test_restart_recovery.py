"""K13 M3A restart recovery tests (Manifest sections 12, 38, 45).

RED-first: these tests import agent_si.runtime.scheduler, which does not
exist yet, so they must FAIL before the implementation lands.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from iface.frozen_manifest import manifest
from agent_si.runtime.scheduler import leases
from agent_si.runtime.scheduler import scheduler as sched


def test_manifest_verifies():
    assert manifest.verify_manifest(
        ROOT / "RECORDS" / "day0" / "K13_MANIFEST.md"
    ) is True


def _persisted_lease(lease_id="lease-1", owner="R1", acquired=100.0,
                     expires=200.0, status=None):
    return leases.ResourceLease(
        lease_id=lease_id,
        project_id="P1",
        task_id="T1",
        run_id=owner,
        resource_type="local-gpu",
        resource_id="gpu-0",
        owner_run_id=owner,
        acquired_at=acquired,
        expires_at=expires,
        released_at=None,
        status=status or leases.ResourceLeaseStatus.ACTIVE,
        capacity_claim=1,
        evidence_ref="ev-1",
    )


def _persisted_reservation(reservation_id="resvn-1", owner="R1",
                           created=100.0, expires=200.0, status=None):
    return leases.ResourceReservation(
        reservation_id=reservation_id,
        project_id="P1",
        task_id="T1",
        run_id=owner,
        resource_type="local-gpu",
        resource_id="gpu-0",
        owner_run_id=owner,
        requested_capacity=1,
        created_at=created,
        expires_at=expires,
        fulfilled_at=None,
        released_at=None,
        status=status or leases.ResourceReservationStatus.ACTIVE,
        evidence_ref="ev-1",
    )


def _plan():
    return sched.PersistedPlanGraph(
        task_plan_id="plan-1",
        project_id="P1",
        task_id="T1",
        contract_hash="hash-abc",
        plan_status="ACTIVE",
        subtasks=(
            sched.PlannedSubtaskState(
                subtask_id="S1", status="COMPLETED", dependency_ids=()
            ),
            sched.PlannedSubtaskState(
                subtask_id="S2", status="RUNNING",
                dependency_ids=("S1",),
            ),
            sched.PlannedSubtaskState(
                subtask_id="S3", status="PLANNED",
                dependency_ids=("S2",),
            ),
        ),
    )


def _engine():
    store = leases.LeaseStore(capacity_slots=2, lease_timeout=60.0)
    engine = sched.ResourceScheduler(
        sched.SchedulerConfig(
            max_parallel_global=2,
            max_parallel_per_provider=2,
            max_parallel_per_model=2,
            local_gpu_slots=1,
            local_cpu_slots=1,
            memory_budget=1024,
            gpu_memory_budget=1024,
            queue_policy="FIFO",
            priority_policy="FIFO",
        ),
        store=store,
    )
    return engine, store


def test_expired_leases_never_trusted():
    engine, store = _engine()
    report = engine.recover(
        persisted_plan=_plan(),
        persisted_leases=(_persisted_lease(expires=200.0),),
        persisted_reservations=(_persisted_reservation(expires=200.0),),
        live_run_ids=("R1",),
        late_results=(),
        now=1000.0,
    )
    assert "lease-1" in report.lease_recovery.expired_untrusted_ids
    assert "lease-1" not in report.lease_recovery.trusted_lease_ids
    assert "R1" not in report.lease_recovery.revalidated_run_ids
    assert store.get_lease("lease-1").status == (
        leases.ResourceLeaseStatus.EXPIRED
    )
    assert report.restored_run_ids == ()


def test_orphans_released_not_resumed():
    engine, store = _engine()
    report = engine.recover(
        persisted_plan=_plan(),
        persisted_leases=(
            _persisted_lease(lease_id="lease-9", owner="R-gone",
                             expires=5000.0),
        ),
        persisted_reservations=(
            _persisted_reservation(reservation_id="resvn-9", owner="R-gone",
                                   expires=5000.0),
        ),
        live_run_ids=("R-live",),
        late_results=(),
        now=1000.0,
    )
    assert "lease-9" in report.lease_recovery.orphans_released_ids
    assert "lease-9" not in report.lease_recovery.trusted_lease_ids
    orphan = store.get_lease("lease-9")
    assert orphan.status == leases.ResourceLeaseStatus.ORPHANED
    assert orphan.released_at == 1000.0
    assert report.restored_run_ids == ()


def test_valid_ownership_revalidated():
    engine, store = _engine()
    report = engine.recover(
        persisted_plan=_plan(),
        persisted_leases=(_persisted_lease(expires=5000.0),),
        persisted_reservations=(_persisted_reservation(expires=5000.0),),
        live_run_ids=("R1",),
        late_results=(),
        now=1000.0,
    )
    assert report.lease_recovery.trusted_lease_ids == ("lease-1",)
    assert report.lease_recovery.expired_untrusted_ids == ()
    assert report.lease_recovery.orphans_released_ids == ()
    assert report.restored_run_ids == ("R1",)
    assert store.get_lease("lease-1").status == (
        leases.ResourceLeaseStatus.ACTIVE
    )


def test_plan_graph_restored():
    engine, _ = _engine()
    plan = _plan()
    report = engine.recover(
        persisted_plan=plan,
        persisted_leases=(),
        persisted_reservations=(),
        live_run_ids=(),
        late_results=(),
        now=1000.0,
    )
    assert report.plan_restored is True
    assert report.restored_plan_id == "plan-1"
    restored = report.restored_plan
    assert [s.subtask_id for s in restored.subtasks] == ["S1", "S2", "S3"]
    assert [s.status for s in restored.subtasks] == [
        "COMPLETED", "RUNNING", "PLANNED",
    ]
    by_id = {s.subtask_id: s for s in restored.subtasks}
    assert by_id["S2"].dependency_ids == ("S1",)
    assert by_id["S3"].dependency_ids == ("S2",)


def test_late_results_never_auto_resume():
    engine, store = _engine()
    late = (
        sched.LateResult(
            attempt_id="att-7", run_id="R1", output_ref="art-late-1",
            arrived_after_suspension=True,
        ),
        sched.LateResult(
            attempt_id="att-8", run_id="R1", output_ref="art-late-2",
            arrived_after_suspension=True,
        ),
    )
    before = (store.active_capacity(), store.queue_depth(),
              store.lease_count())
    report = engine.recover(
        persisted_plan=_plan(),
        persisted_leases=(_persisted_lease(expires=5000.0),),
        persisted_reservations=(_persisted_reservation(expires=5000.0),),
        live_run_ids=("R1",),
        late_results=late,
        now=1000.0,
    )
    assert tuple(r.attempt_id for r in report.quarantined_late_results) == (
        "att-7", "att-8",
    )
    assert report.auto_resumed == ()
    # Quarantine creates no leases and resumes no attempt; recover trusts the
    # live unexpired lease (revalidated ownership), so active_capacity is 1.
    assert (store.active_capacity(), store.queue_depth(),
            store.lease_count()) == (1, 0, before[2] + 1)
    assert report.lease_recovery.trusted_lease_ids == ("lease-1",)
