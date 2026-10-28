"""K05R3 M-SCHED queue tests (RED before bench_runner queue lands).

Rows: B0B-UNCOVERED_ARCH-189 (excess queues under caps), 767 (safety caps
still refuse; only the busy count-limit queues), SPEC 38 (owner+expiry
leases/reservations, bounded parallel runs). Real clock + short TTLs only;
no canned product values. Fakes live here only, none needed (real entries).
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

import pytest

from agent_si.local import bench_runner as runner
from agent_si.local.bench_protocol import BenchLevel
from agent_si.local.bench_runner import (
    BenchBusyError,
    BenchRefusedError,
    RunHandle,
    RunReservation,
    RunSkip,
)


@pytest.fixture(autouse=True)
def _drain_scheduler():
    yield
    try:
        active = runner._ACTIVE_RUN_ID
    except AttributeError:
        active = None
    if active is not None:
        try:
            runner.stop_run(active)
        except KeyError:
            pass
    for rsv in runner.list_reservations():
        if rsv.status == "queued":
            try:
                runner.cancel_reservation(rsv.reservation_id, rsv.owner)
            except (KeyError, BenchRefusedError):
                pass


def test_189_excess_queues_under_cap() -> None:
    first = runner.start_run("m-one", BenchLevel.Quick, True)
    assert isinstance(first, RunHandle)
    second = runner.queue_run("m-two", BenchLevel.Quick, True, owner="team-a")
    assert isinstance(second, RunReservation)
    assert second.owner == "team-a"
    assert second.status == "queued"
    assert second.expires_at > second.created_at


def test_767_safety_cap_still_refuses_and_queues_nothing() -> None:
    before = len(runner.list_reservations())
    with pytest.raises(BenchRefusedError) as excinfo:
        runner.queue_run("m-noauth", BenchLevel.Quick, False, owner="team-a")
    assert runner.SESSION_TOKEN_REFUSED in str(excinfo.value)
    assert len(runner.list_reservations()) == before


def test_189_promote_after_stop_runs_oldest_first() -> None:
    runner.start_run("m-one", BenchLevel.Quick, True)
    waiting = runner.queue_run("m-two", BenchLevel.Quick, True, owner="team-b")
    assert isinstance(waiting, RunReservation)
    assert runner.pump_queue() is None  # busy: never a second parallel run
    runner.stop_run(runner._ACTIVE_RUN_ID)
    promoted = runner.pump_queue()
    assert isinstance(promoted, RunHandle)
    assert promoted.model_id == "m-two"
    lease = runner.lease_for_run(promoted.run_id)
    assert lease is not None and lease.owner == "team-b"
    assert runner.lease_is_live(lease.lease_id) is True


def test_38_reservation_expiry_skips_promotion() -> None:
    runner.start_run("m-one", BenchLevel.Quick, True)
    waiting = runner.queue_run(
        "m-two", BenchLevel.Quick, True, owner="team-c", ttl_s=0.05
    )
    assert isinstance(waiting, RunReservation)
    time.sleep(0.15)  # real clock past the TTL
    runner.stop_run(runner._ACTIVE_RUN_ID)
    assert runner.pump_queue() is None
    assert waiting.status == "expired"


def test_38_parallel_bound_is_one() -> None:
    assert runner.MAX_ACTIVE_RUNS == 1
    runner.start_run("m-one", BenchLevel.Quick, True)
    runner.queue_run("m-two", BenchLevel.Quick, True, owner="team-d")
    runner.queue_run("m-three", BenchLevel.Quick, True, owner="team-d")
    assert runner.pump_queue() is None
    active = [
        rid for rid in runner.list_run_ids() if runner._ACTIVE_RUN_ID == rid
    ]
    assert len(active) <= runner.MAX_ACTIVE_RUNS


def test_38_lease_owner_release_and_expiry() -> None:
    handle = runner.queue_run(
        "m-free", BenchLevel.Quick, True, owner="team-e", lease_ttl_s=60.0
    )
    assert isinstance(handle, RunHandle)  # free slot starts at once
    lease = runner.lease_for_run(handle.run_id)
    assert lease is not None and lease.owner == "team-e"
    assert lease.expires_at > lease.created_at
    runner.release_lease(lease.lease_id, "team-e")
    assert runner.lease_is_live(lease.lease_id) is False
    with pytest.raises(BenchRefusedError):
        runner.renew_lease(lease.lease_id, "team-e")

    short = runner.queue_run(
        "m-short", BenchLevel.Quick, True, owner="team-f", lease_ttl_s=0.05
    )
    # slot busy (m-free still active): short waits in the queue; cancel it,
    # stop the active run, then prove lease expiry on a fresh short lease.
    if isinstance(short, RunReservation):
        runner.cancel_reservation(short.reservation_id, "team-f")
    runner.stop_run(handle.run_id)
    fresh = runner.queue_run(
        "m-short", BenchLevel.Quick, True, owner="team-f", lease_ttl_s=0.05
    )
    assert isinstance(fresh, RunHandle)
    fresh_lease = runner.lease_for_run(fresh.run_id)
    assert fresh_lease is not None
    time.sleep(0.15)  # real clock past the lease TTL
    assert runner.lease_is_live(fresh_lease.lease_id) is False


def test_189_queue_full_refuses_busy() -> None:
    runner.start_run("m-one", BenchLevel.Quick, True)
    for idx in range(runner.MAX_QUEUED_RESERVATIONS):
        got = runner.queue_run(f"m-w{idx}", BenchLevel.Quick, True, owner="team-g")
        assert isinstance(got, RunReservation)
    with pytest.raises(BenchBusyError):
        runner.queue_run("m-overflow", BenchLevel.Quick, True, owner="team-g")


def test_offline_skips_and_never_queues() -> None:
    before = len(runner.list_reservations())
    got = runner.queue_run("m-offline", BenchLevel.Quick, True, owner="team-h")
    assert isinstance(got, RunSkip) and got.reason != ""
    assert len(runner.list_reservations()) == before
