"""K05R5 M-BENCH journal: scheduler state survives kill/restart via a file.

RED before the bench_runner journal lands (runner.recover_journal and
runner.set_journal_path do not exist); GREEN after. The kill/restart is a
real journal file plus a memory wipe (fresh-process state): no reloads, so
co-resident test modules keep their references. Real clock plus short TTLs
only; no canned product values.
"""
from __future__ import annotations

import itertools
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

import pytest

from agent_si.local import bench_runner as runner
from agent_si.local.bench_protocol import BenchLevel
from agent_si.local.bench_runner import BenchRefusedError, RunHandle, RunReservation


def _wipe_scheduler_memory() -> None:
    """Simulated kill: fresh-process memory; only the journal file survives."""
    runner._RUNS.clear()
    runner._PROGRESS.clear()
    runner._RUN_ROWS.clear()
    runner._RESERVATIONS.clear()
    runner._QUEUE.clear()
    runner._LEASES.clear()
    runner._RUN_LEASE.clear()
    runner._ACTIVE_RUN_ID = None
    runner._RUN_SEQ = itertools.count(1)
    runner._RESERVATION_SEQ = itertools.count(1)
    runner._LEASE_SEQ = itertools.count(1)
    # The explicit override dies with the process; the env var survives it.
    runner.set_journal_path(None)


@pytest.fixture()
def journal_file(tmp_path, monkeypatch):
    target = tmp_path / "bench.journal"
    monkeypatch.setenv(runner.JOURNAL_ENV_VAR, str(target))
    runner.set_journal_path(None)
    _wipe_scheduler_memory()
    yield target
    try:
        if runner._ACTIVE_RUN_ID is not None:
            runner.stop_run(runner._ACTIVE_RUN_ID)
    except KeyError:
        pass
    for rsv in runner.list_reservations():
        if rsv.status == "queued":
            try:
                runner.cancel_reservation(rsv.reservation_id, rsv.owner)
            except (KeyError, BenchRefusedError):
                pass
    runner.set_journal_path(None)


def test_recover_without_journal_touches_nothing(journal_file, monkeypatch) -> None:
    monkeypatch.delenv(runner.JOURNAL_ENV_VAR)
    handle = runner.start_run("FAKE-OF: journal noop", BenchLevel.Quick, True)
    assert isinstance(handle, RunHandle)
    report = runner.recover_journal()
    assert report == {
        "restored_runs": 0,
        "restored_queued": 0,
        "expired": 0,
        "interrupted_run_id": None,
    }
    assert runner._ACTIVE_RUN_ID == handle.run_id
    assert runner.run_progress(handle.run_id).stopped is False
    assert not journal_file.exists()


def test_restart_restores_queue_and_reconciles_active(journal_file) -> None:
    active = runner.start_run("FAKE-OF: journal m1", BenchLevel.Quick, True)
    assert isinstance(active, RunHandle)
    first = runner.queue_run(
        "FAKE-OF: journal m2", BenchLevel.Quick, True, owner="team-j1"
    )
    second = runner.queue_run(
        "FAKE-OF: journal m3", BenchLevel.Standard, True, owner="team-j2"
    )
    short = runner.queue_run(
        "FAKE-OF: journal m4", BenchLevel.Quick, True, owner="team-j3", ttl_s=0.05
    )
    assert isinstance(first, RunReservation)
    assert isinstance(second, RunReservation)
    assert isinstance(short, RunReservation)
    time.sleep(0.15)  # real clock past the short TTL
    assert journal_file.is_file()
    lines = [
        line
        for line in journal_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) >= 1
    # Kill: wipe every in-memory word; the journal file is the survivor.
    _wipe_scheduler_memory()
    assert runner.list_run_ids() == []
    assert runner.list_reservations() == []
    # Restart: rebuild from the file and reconcile the kill.
    report = runner.recover_journal()
    assert report == {
        "restored_runs": 1,
        "restored_queued": 2,
        "expired": 1,
        "interrupted_run_id": active.run_id,
    }
    assert runner.list_run_ids() == [active.run_id]
    assert runner._ACTIVE_RUN_ID is None  # slot freed: nothing runs after a kill
    assert runner.run_progress(active.run_id).stopped is True
    live = {rsv.reservation_id: rsv for rsv in runner.list_reservations()}
    assert live[first.reservation_id].status == "queued"
    assert live[first.reservation_id].owner == "team-j1"
    assert live[second.reservation_id].status == "queued"
    assert live[second.reservation_id].owner == "team-j2"
    assert live[short.reservation_id].status == "expired"
    promoted = runner.pump_queue()
    assert isinstance(promoted, RunHandle)
    assert promoted.model_id == "FAKE-OF: journal m2"  # FIFO: oldest live first
    lease = runner.lease_for_run(promoted.run_id)
    assert lease is not None and lease.owner == "team-j1"
    assert runner.lease_is_live(lease.lease_id) is True
    runner.stop_run(promoted.run_id)
    fresh = runner.start_run("FAKE-OF: journal m5", BenchLevel.Quick, True)
    assert isinstance(fresh, RunHandle)
    assert fresh.run_id not in (active.run_id, promoted.run_id)
    assert '"event": "recovered"' in journal_file.read_text(encoding="utf-8")


def test_torn_tail_line_is_ignored(journal_file) -> None:
    active = runner.start_run("FAKE-OF: journal torn", BenchLevel.Quick, True)
    assert isinstance(active, RunHandle)
    waiting = runner.queue_run(
        "FAKE-OF: journal torn2", BenchLevel.Quick, True, owner="team-j4"
    )
    assert isinstance(waiting, RunReservation)
    _wipe_scheduler_memory()
    with open(str(journal_file), "a", encoding="utf-8") as fh:
        fh.write('{"v": 1, "event": "torn tail\n')
    report = runner.recover_journal()
    assert report["restored_runs"] == 1
    assert report["restored_queued"] == 1
    assert report["interrupted_run_id"] == active.run_id


def test_garbage_only_journal_recovers_nothing(journal_file) -> None:
    journal_file.write_text("not json\n{\"v\": 999}\n", encoding="utf-8")
    report = runner.recover_journal()
    assert report == {
        "restored_runs": 0,
        "restored_queued": 0,
        "expired": 0,
        "interrupted_run_id": None,
    }
    assert runner.list_run_ids() == []
    assert runner.list_reservations() == []
