"""K08R3 RUN lane behaviour checks (coder-1, run lane).

Covers BUILD_PLAN rows R-320 (disk check plus own-temp cleanup, journaled,
own folders only), R-327 (run temp files removed by the standard cleanup
script), B0B-SDK-94/95/96/99 (immediate plus after-turn cancellation with
immediate default; immediate stops at once; immediate leaves the turn
uncompleted; after-turn finishes the current turn), and the K08-kept sides
of B0B-641/642 (runner history plus finalization receipt stay REAL; record
inputs belong to K13 plus the assurance lane per HANDOFF_K13_RUN.md).

Real inputs only: tmp_path dirs, the real disk probe, real turn sequences,
the real clock, plain-dict record outputs. CODER-2 appends service-lane
tests below; keep imports additive and fixtures file-local.
"""

import json
import os
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

from agent_si.automation import pause
from agent_si.automation import runner
from agent_si.automation.interface import AutomationError


class _Notices:
    """Test-local journal recorder: stores automation notifications."""

    def __init__(self):
        self.calls = []

    def append_event(self, project_id, source, kind, summary, refs=()):
        self.calls.append(
            {
                "project_id": project_id,
                "source": source,
                "kind": kind,
                "summary": summary,
                "refs": tuple(refs),
            }
        )
        return {"entry_id": "evt-%04d" % len(self.calls)}


@pytest.fixture
def _run_lane():
    pause.reset_state()
    runner.reset_state()
    runner.set_run_temp_base(None)
    notes = _Notices()
    runner.set_journal_hook(notes.append_event)
    runner.set_budget_hook(None)
    runner.register_template("tpl-k08r3", "proj-k08r3", name="k08r3")
    return {"journal": notes}


def _start(project="proj-k08r3", template="tpl-k08r3"):
    return runner.start_run(project, template)


def _events(project, run_id):
    return [entry["event"] for entry in runner.get_history(project, run_id)]


def _summaries(notes):
    return [call["summary"] for call in notes["journal"].calls]


# --- B0B-SDK-94: immediate plus after-turn cancellation, immediate default ---

def test_cancel_default_mode_is_immediate(_run_lane):
    run = _start()
    turn = runner.begin_turn("proj-k08r3", run.run_id)
    assert turn["turn"] == 1
    cancelled = runner.cancel_run("proj-k08r3", run.run_id, reason="user-stop")
    assert cancelled.state == "CANCELLED"
    assert runner.get_run("proj-k08r3", run.run_id).state == "CANCELLED"
    assert "cancelled:user-stop" in _events("proj-k08r3", run.run_id)


# --- B0B-SDK-95: immediate cancellation stops at once, run complete ---

def test_immediate_cancel_stops_at_once(_run_lane):
    run = _start()
    runner.begin_turn("proj-k08r3", run.run_id)
    cancelled = runner.cancel_run(
        "proj-k08r3", run.run_id, reason="user-stop", mode="immediate"
    )
    assert cancelled.state == "CANCELLED"
    assert runner.get_run("proj-k08r3", run.run_id).state == "CANCELLED"
    final = runner.get_finalization("proj-k08r3", run.run_id)
    assert final == {"reason": "user-stop", "finalized": True}
    assert _run_lane["journal"].calls


# --- B0B-SDK-96: immediate cancellation leaves the turn uncompleted ---

def test_immediate_cancel_leaves_turn_uncompleted(_run_lane):
    run = _start()
    runner.begin_turn("proj-k08r3", run.run_id)
    runner.cancel_run("proj-k08r3", run.run_id, reason="user-stop")
    events = _events("proj-k08r3", run.run_id)
    assert "turn-started:1" in events
    assert "turn-completed:1" not in events
    assert "cancelled:user-stop" in events


# --- B0B-SDK-99: after-turn cancellation finishes the current turn first ---

def test_after_turn_cancel_finishes_turn_before_stopping(_run_lane):
    run = _start()
    runner.begin_turn("proj-k08r3", run.run_id)
    mid = runner.cancel_run(
        "proj-k08r3", run.run_id, reason="user-stop", mode="after-turn"
    )
    assert mid.state == "RUNNING"
    assert runner.get_run("proj-k08r3", run.run_id).state == "RUNNING"
    done = runner.complete_turn("proj-k08r3", run.run_id)
    assert done["state"] == "CANCELLED"
    assert runner.get_run("proj-k08r3", run.run_id).state == "CANCELLED"
    events = _events("proj-k08r3", run.run_id)
    assert events.index("turn-completed:1") < events.index("cancelled:user-stop")
    final = runner.get_finalization("proj-k08r3", run.run_id)
    assert final == {"reason": "user-stop", "finalized": True}


def test_after_turn_cancel_without_open_turn_stops_at_once(_run_lane):
    run = _start()
    cancelled = runner.cancel_run(
        "proj-k08r3", run.run_id, reason="user-stop", mode="after-turn"
    )
    assert cancelled.state == "CANCELLED"
    assert "cancelled:user-stop" in _events("proj-k08r3", run.run_id)


def test_cancel_modes_work_while_paused(_run_lane):
    run = _start()
    runner.begin_turn("proj-k08r3", run.run_id)
    pause.set_global(True, "drill")
    assert (
        runner.cancel_run("proj-k08r3", run.run_id, mode="immediate").state
        == "CANCELLED"
    )
    pause.set_global(False, "")
    second = _start()
    runner.begin_turn("proj-k08r3", second.run_id)
    pause.set_global(True, "drill")
    mid = runner.cancel_run(
        "proj-k08r3", second.run_id, reason="late", mode="after-turn"
    )
    assert mid.state == "RUNNING"
    assert (
        runner.complete_turn("proj-k08r3", second.run_id)["state"] == "CANCELLED"
    )
    pause.set_global(False, "")


# --- B0B-641/642 K08-kept sides: history plus finalization stay REAL ---

def test_history_and_finalization_kept_across_turns_and_cancel(_run_lane):
    run = _start()
    runner.begin_turn("proj-k08r3", run.run_id)
    runner.complete_turn("proj-k08r3", run.run_id)
    runner.cancel_run("proj-k08r3", run.run_id, reason="user-stop")
    events = _events("proj-k08r3", run.run_id)
    for wanted in (
        "created",
        "turn-started:1",
        "turn-completed:1",
        "cancelled:user-stop",
    ):
        assert wanted in events
    assert runner.get_finalization("proj-k08r3", run.run_id) == {
        "reason": "user-stop",
        "finalized": True,
    }
    kinds = [call["kind"] for call in _run_lane["journal"].calls]
    assert kinds.count("AUTOMATION_RUN") >= 3


def test_turn_ops_reject_unknown_run_and_bad_mode(_run_lane):
    with pytest.raises(AutomationError) as excinfo:
        runner.begin_turn("proj-k08r3", "run-9999")
    assert excinfo.value.code == "AUTOMATION_RUN_NOT_FOUND"
    with pytest.raises(ValueError):
        runner.cancel_run("proj-k08r3", "run-9999", mode="someday")
    with pytest.raises(AutomationError) as excinfo:
        runner.complete_turn("proj-k08r3", "run-9999")
    assert excinfo.value.code in ("AUTOMATION_RUN_NOT_FOUND",)


def test_turn_cancel_fields_round_trip_through_save_load(_run_lane, tmp_path):
    run = _start()
    runner.begin_turn("proj-k08r3", run.run_id)
    runner.cancel_run(
        "proj-k08r3", run.run_id, reason="user-stop", mode="after-turn"
    )
    assert runner.get_run("proj-k08r3", run.run_id).state == "RUNNING"
    run_file = tmp_path / "runs.json"
    runner.save_state(str(run_file))
    payload = json.loads(run_file.read_text(encoding="utf-8"))
    assert payload["schema"] == 1
    runner.reset_state()
    runner.set_journal_hook(_run_lane["journal"].append_event)
    runner.load_state(str(run_file))
    done = runner.complete_turn("proj-k08r3", run.run_id)
    assert done["state"] == "CANCELLED"
    events = _events("proj-k08r3", run.run_id)
    assert events.index("turn-completed:1") < events.index("cancelled:user-stop")
    assert runner.get_finalization("proj-k08r3", run.run_id) == {
        "reason": "user-stop",
        "finalized": True,
    }


# --- R-320: disk check plus own-temp cleanup, journaled, own folders only ---

def test_disk_check_reports_real_disk(_run_lane, tmp_path):
    info = runner.disk_check_runs("proj-k08r3", base=str(tmp_path))
    assert info["path"] == str(tmp_path)
    assert info["total"] > 0
    assert info["free"] >= 0
    assert info["free"] <= info["total"]
    assert info["ok"] is True
    assert any(
        "disk" in summary for summary in _summaries(_run_lane)
    )


def test_cleanup_removes_only_inside_run_dir(_run_lane, tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    run = _start()
    run_dir = base / run.run_id
    run_dir.mkdir()
    (run_dir / "scratch.bin").write_bytes(b"x" * 64)
    nested = run_dir / "nested"
    nested.mkdir()
    (nested / "deep.bin").write_bytes(b"y" * 32)
    outside = tmp_path / "elsewhere.bin"
    outside.write_bytes(b"keep me")
    receipt = runner.cleanup_run_temp(
        "proj-k08r3", run.run_id, base=str(base)
    )
    assert receipt["refused"] is False
    assert sorted(receipt["removed"]) == ["nested", "scratch.bin"]
    assert list(run_dir.iterdir()) == []
    assert (run_dir / "scratch.bin").exists() is False
    assert (nested / "deep.bin").exists() is False
    assert outside.read_bytes() == b"keep me"
    assert any(
        run.run_id in summary for summary in _summaries(_run_lane)
    )


def test_cleanup_never_deletes_outside_base(_run_lane, tmp_path):
    from agent_si.automation import cleanup as cleanup_mod

    base = tmp_path / "base"
    base.mkdir()
    sentinel = tmp_path / "sentinel.bin"
    sentinel.write_bytes(b"keep me")
    with pytest.raises(ValueError):
        cleanup_mod.clean_run_temp(str(base), "..")
    with pytest.raises(ValueError):
        runner.cleanup_run_temp("proj-k08r3", "../escape", base=str(base))
    assert sentinel.read_bytes() == b"keep me"
    assert list(base.iterdir()) == []


# --- R-327: run temp files removed by the standard cleanup script ---

def test_cancel_from_run_path_cleans_run_temp(_run_lane, tmp_path):
    runner.set_run_temp_base(str(tmp_path))
    run = _start()
    owned = tmp_path / run.run_id
    owned.mkdir()
    (owned / "work.bin").write_bytes(b"z" * 16)
    runner.cancel_run("proj-k08r3", run.run_id, reason="user-stop")
    assert (owned / "work.bin").exists() is False
    assert any(
        run.run_id in summary for summary in _summaries(_run_lane)
    )


def test_cleanup_script_entry_cleans_run_temp(tmp_path):
    from agent_si.automation import cleanup as cleanup_mod

    run_dir = tmp_path / "run-0007"
    run_dir.mkdir()
    (run_dir / "work.bin").write_bytes(b"z" * 16)
    assert cleanup_mod.main(["--base", str(tmp_path), "--run", "run-0007"]) == 0
    assert (run_dir / "work.bin").exists() is False
    assert (tmp_path / "run-0007").is_dir()
    assert os.path.isdir(str(tmp_path))


# --- K08R3 service lane (CODER-2 Slate): R-366 journal/notify half, R-320 disk probe ---
#
# Covers BUILD_PLAN row R-366 (declared services served UP/DOWN/DEGRADED from
# last observation; observe via budget read degrading to None; notify via
# journal SERVICE_STATE on change; usage from metadata via record APIs; outage
# linkage as an additive notify-only path) and the service_watch half of R-320
# (observe-only disk probe, journal when low). Real inputs only: own declared
# service ids under proj-k08r3-svc (never fixture rows), real loopback probe
# results via monkeypatched probe functions, real disk reads, computed UTC
# stamps. Fixture imports (sys/os/json/pytest) are reused from above; lane
# imports below are additive and the _svc_lane fixture is file-local.

from datetime import datetime as _datetime
from datetime import timezone as _timezone

import agent_si.automation.interface as auto_iface
from agent_si.automation import outage
from agent_si.automation import service_status
from agent_si.automation import service_watch
from agent_si.automation import templates

_SVC_PROJECT = "proj-k08r3-svc"
_SVC_HTTP = "svc-k08r3-a"
_SVC_TCP = "svc-k08r3-b"
_SVC_CONTAINER = "svc-k08r3-c"
_SVC_AGENT = "agent-k08r3"


class _SvcJournal:
    """Test-local service-lane journal recorder (test double only)."""

    def __init__(self):
        self.calls = []

    def append_event(self, project_id, source, kind, summary, refs=()):
        entry = auto_iface.JournalEntry(
            entry_id="svc-evt-%04d" % (len(self.calls) + 1),
            timestamp=_datetime.now(_timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            hash="svc-hash-%04d" % (len(self.calls) + 1),
        )
        self.calls.append(
            {
                "project_id": project_id,
                "source": source,
                "kind": kind,
                "summary": summary,
                "refs": tuple(refs),
                "entry": entry,
            }
        )
        return entry


class _SvcStopper:
    """Test-local stop-all recorder (test double only)."""

    def __init__(self):
        self.calls = []

    def request_stop(self, project_id, reason):
        receipt = auto_iface.StopReceipt(
            project_id=project_id, stopped=True, reason=reason
        )
        self.calls.append(receipt)
        return receipt


class _SvcBudget:
    """Test-local budget double: observe-only record of get_state calls."""

    def __init__(self):
        self.calls = []

    def get_state(self, key):
        self.calls.append(key)
        return {"key": key, "remaining": "100"}


@pytest.fixture
def _svc_lane(monkeypatch):
    seed_rows = {
        service_id: dict(row)
        for service_id, row in service_status._SERVICES.items()
    }
    seed_dispatch = {
        service_id: dict(meta)
        for service_id, meta in service_status._DISPATCH_META.items()
    }
    seed_egress = {
        service_id: dict(meta)
        for service_id, meta in service_status._EGRESS_META.items()
    }
    seed_descriptors = {
        service_id: {
            "env": dict(descriptor.get("env", {})),
            "files": tuple(descriptor.get("files", ())),
        }
        for service_id, descriptor in (
            service_status._CONTAINER_DESCRIPTORS.items()
        )
    }
    journal = _SvcJournal()
    stopper = _SvcStopper()
    monkeypatch.setattr(
        auto_iface, "journal_append_event", journal.append_event
    )
    monkeypatch.setattr(
        auto_iface, "stop_all_request_stop", stopper.request_stop
    )
    service_watch.reset_baseline()
    yield {"journal": journal, "stopper": stopper}
    service_status._SERVICES.clear()
    service_status._SERVICES.update(
        {service_id: dict(row) for service_id, row in seed_rows.items()}
    )
    service_status._DISPATCH_META.clear()
    service_status._DISPATCH_META.update(
        {service_id: dict(meta) for service_id, meta in seed_dispatch.items()}
    )
    service_status._EGRESS_META.clear()
    service_status._EGRESS_META.update(
        {service_id: dict(meta) for service_id, meta in seed_egress.items()}
    )
    service_status._CONTAINER_DESCRIPTORS.clear()
    service_status._CONTAINER_DESCRIPTORS.update(
        {
            service_id: {
                "env": dict(descriptor["env"]),
                "files": tuple(descriptor["files"]),
            }
            for service_id, descriptor in seed_descriptors.items()
        }
    )
    service_watch.reset_baseline()


def _svc_age_seconds(stamp):
    parsed = _datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=_timezone.utc
    )
    return abs((_datetime.now(_timezone.utc) - parsed).total_seconds())


def _svc_declare_http(service_id=_SVC_HTTP):
    return service_status.declare_service(
        service_id,
        kind="http",
        host="127.0.0.1",
        http_port=18080,
        tcp_port=18081,
        path="/healthz",
        project_id=_SVC_PROJECT,
    )


# --- R-366: declared services served UP/DOWN/DEGRADED from last observation ---


def test_svc_declared_row_serves_observed_state(_svc_lane, monkeypatch):
    _svc_declare_http()
    monkeypatch.setattr(service_status, "_probe_http", lambda *a: (True, False))
    status = service_status.run_check(
        _SVC_HTTP, auto_iface.ServiceCheckKind.HTTP
    )
    assert isinstance(status, auto_iface.ServiceStatus)
    assert status.service_id == _SVC_HTTP
    assert status.state == "UP"
    assert service_status.get(_SVC_HTTP).state == "UP"
    assert _svc_age_seconds(status.timestamp) < 300
    assert status.timestamp != service_status._SEED_NOW
    assert status.in_use is False


def test_svc_down_and_degraded_from_last_observation(_svc_lane, monkeypatch):
    _svc_declare_http()
    journal = _svc_lane["journal"]
    monkeypatch.setattr(service_status, "_probe_http", lambda *a: (False, False))
    monkeypatch.setattr(service_status, "_probe_tcp", lambda *a: (False, False))
    assert (
        service_status.run_check(
            _SVC_HTTP, auto_iface.ServiceCheckKind.HTTP
        ).state
        == "DOWN"
    )
    assert service_status.get(_SVC_HTTP).state == "DOWN"
    monkeypatch.setattr(service_status, "_probe_http", lambda *a: (True, True))
    assert (
        service_status.run_check(
            _SVC_HTTP, auto_iface.ServiceCheckKind.HTTP
        ).state
        == "DEGRADED"
    )
    kinds = [row["kind"] for row in journal.calls]
    assert kinds and all(kind == "SERVICE_STATE" for kind in kinds)


def test_svc_usage_record_takes_real_inputs(_svc_lane):
    _svc_declare_http()
    first = service_status._utcnow()
    second = service_status._utcnow()
    service_status.record_usage(
        _SVC_HTTP, active=True, last_agent=_SVC_AGENT, last_used=first
    )
    service_status.record_egress(_SVC_HTTP, last_egress=second)
    status = service_status.get(_SVC_HTTP)
    assert status.in_use is True
    assert status.last_agent == _SVC_AGENT
    assert status.last_used == max(first, second)
    service_status.record_usage(
        _SVC_HTTP, active=False, last_agent=_SVC_AGENT
    )
    assert _svc_age_seconds(service_status.get(_SVC_HTTP).last_used) < 300
    with pytest.raises(auto_iface.AutomationError) as excinfo:
        service_status.record_usage(
            "svc-k08r3-missing", active=True, last_agent=_SVC_AGENT
        )
    assert excinfo.value.code == "SERVICE_NOT_FOUND"
    with pytest.raises(auto_iface.AutomationError) as excinfo:
        service_status.record_egress("svc-k08r3-missing")
    assert excinfo.value.code == "SERVICE_NOT_FOUND"


def test_svc_budget_observed_and_degrades_to_none(_svc_lane, monkeypatch):
    _svc_declare_http()
    monkeypatch.setitem(sys.modules, "agent_si.budget.gate", None)
    assert service_status.observe_budget(_SVC_HTTP) is None
    assert service_status.get(_SVC_HTTP).service_id == _SVC_HTTP
    budget = _SvcBudget()
    monkeypatch.setattr(service_status, "observe_budget", budget.get_state)
    monkeypatch.setattr(service_status, "_probe_http", lambda *a: (True, False))
    service_status.run_check(_SVC_HTTP, auto_iface.ServiceCheckKind.HTTP)
    service_status.get(_SVC_HTTP)
    assert budget.calls == [_SVC_HTTP, _SVC_HTTP]


def test_svc_watch_notifies_declared_change(_svc_lane, monkeypatch):
    _svc_declare_http()
    journal = _svc_lane["journal"]
    first = service_watch.tick(_SVC_PROJECT)
    assert first.checked == 1
    assert first.changed == (_SVC_HTTP,)
    assert len(first.journal_entry_ids) == 1
    assert _svc_age_seconds(first.checked_at) < 300
    quiet = service_watch.tick(_SVC_PROJECT)
    assert quiet.changed == ()
    assert len(journal.calls) == 1
    monkeypatch.setattr(service_status, "_probe_http", lambda *a: (True, True))
    service_status.run_check(_SVC_HTTP, auto_iface.ServiceCheckKind.HTTP)
    before = len(journal.calls)
    changed = service_watch.tick(_SVC_PROJECT)
    assert changed.changed == (_SVC_HTTP,)
    assert len(journal.calls) == before + 1
    assert journal.calls[-1]["kind"] == "SERVICE_STATE"


# --- R-366: outage linkage is observe plus notify only, never auto-stop ---


def _svc_drive_down(monkeypatch, service_id=_SVC_HTTP):
    monkeypatch.setattr(service_status, "_probe_http", lambda *a: (False, False))
    monkeypatch.setattr(service_status, "_probe_tcp", lambda *a: (False, False))
    status = service_status.run_check(
        service_id, auto_iface.ServiceCheckKind.HTTP
    )
    assert status.state == "DOWN"
    return status


def test_svc_link_outage_reports_without_stop(_svc_lane, monkeypatch):
    _svc_declare_http()
    _svc_drive_down(monkeypatch)
    journal = _svc_lane["journal"]
    stopper = _svc_lane["stopper"]
    before = len(journal.calls)
    report = outage.link_observation_to_outage(
        _SVC_PROJECT,
        _SVC_HTTP,
        auto_iface.OutageSeverity.CRITICAL,
        "loopback lost",
    )
    assert isinstance(report, auto_iface.OutageReport)
    assert report.project_id == _SVC_PROJECT
    assert report.service_id == _SVC_HTTP
    assert report.severity == "CRITICAL"
    assert report.stopped is False
    assert report.journal_entry_id == journal.calls[-1]["entry"].entry_id
    assert report.journal_entry_id != ""
    assert _svc_age_seconds(report.reported_at) < 300
    assert len(journal.calls) == before + 1
    project_id, source, kind = (
        journal.calls[-1]["project_id"],
        journal.calls[-1]["source"],
        journal.calls[-1]["kind"],
    )
    assert (project_id, source, kind) == (
        _SVC_PROJECT,
        "automation",
        "OUTAGE_SIGNAL",
    )
    assert report.report_id in journal.calls[-1]["refs"]
    assert _SVC_HTTP in journal.calls[-1]["refs"]
    assert stopper.calls == []


def test_svc_link_outage_refuses_healthy_service(_svc_lane, monkeypatch):
    _svc_declare_http()
    monkeypatch.setattr(service_status, "_probe_http", lambda *a: (True, False))
    service_status.run_check(_SVC_HTTP, auto_iface.ServiceCheckKind.HTTP)
    journal = _svc_lane["journal"]
    stopper = _svc_lane["stopper"]
    before = len(journal.calls)
    with pytest.raises(auto_iface.AutomationError) as excinfo:
        outage.link_observation_to_outage(
            _SVC_PROJECT, _SVC_HTTP, "HIGH", "nothing wrong"
        )
    assert excinfo.value.code == "SERVICE_CHECK_REFUSED"
    assert len(journal.calls) == before
    assert stopper.calls == []


def test_svc_link_outage_unknown_service_raises(_svc_lane):
    journal = _svc_lane["journal"]
    stopper = _svc_lane["stopper"]
    with pytest.raises(auto_iface.AutomationError) as excinfo:
        outage.link_observation_to_outage(
            _SVC_PROJECT, "svc-k08r3-missing", "HIGH", "nothing there"
        )
    assert excinfo.value.code == "SERVICE_NOT_FOUND"
    assert journal.calls == []
    assert stopper.calls == []


# --- R-320: service_watch disk probe is observe-only plus journal-when-low ---


def test_svc_disk_probe_reads_real_disk(_svc_lane, tmp_path):
    journal = _svc_lane["journal"]
    info = service_watch.probe_disk(_SVC_PROJECT, path=str(tmp_path))
    assert info["path"] == str(tmp_path)
    assert info["total"] > 0
    assert 0 <= info["free"] <= info["total"]
    assert info["ok"] is True
    assert journal.calls == []
    local = service_watch.probe_disk(_SVC_PROJECT)
    assert local["path"] == os.getcwd()
    assert local["total"] > 0
    assert local["ok"] is True


def test_svc_disk_probe_journals_when_low(_svc_lane, tmp_path):
    journal = _svc_lane["journal"]
    baseline = service_watch.probe_disk(_SVC_PROJECT, path=str(tmp_path))
    assert baseline["ok"] is True
    info = service_watch.probe_disk(
        _SVC_PROJECT, path=str(tmp_path), low_bytes=baseline["total"] + 1
    )
    assert info["ok"] is False
    assert info["free"] <= info["total"]
    assert len(journal.calls) == 1
    assert journal.calls[0]["kind"] == "SERVICE_STATE"
    assert str(tmp_path) in journal.calls[0]["refs"]
    with pytest.raises(ValueError):
        service_watch.probe_disk(_SVC_PROJECT, low_bytes=-1)


# --- Leak fixes within pins: secretref-only descriptors, caller project ---


def test_svc_descriptor_secretref_only(_svc_lane):
    service_status.declare_service(
        _SVC_CONTAINER,
        kind="container",
        host="127.0.0.1",
        project_id=_SVC_PROJECT,
    )
    service_status.declare_container_descriptor(
        _SVC_CONTAINER,
        env={
            "SVC_K08R3_API_TOKEN": "secretref:svc-k08r3-c/api-token",
            "PORT": "9000",
        },
        files=("/etc/k08r3/config.yaml",),
    )
    clean = service_status.scan_container(_SVC_CONTAINER)
    assert clean.verdict == "CLEAN"
    assert clean.findings == 0
    assert clean.locations == ()
    with pytest.raises(ValueError):
        service_status.declare_container_descriptor(
            _SVC_CONTAINER,
            env={"SVC_K08R3_API_TOKEN": "RAW-VALUE-K08R3-0000"},
        )
    assert service_status.scan_container(_SVC_CONTAINER).verdict == "CLEAN"
    with pytest.raises(auto_iface.AutomationError) as excinfo:
        service_status.declare_container_descriptor(
            "svc-k08r3-missing", env={}
        )
    assert excinfo.value.code == "SERVICE_NOT_FOUND"


def test_svc_findings_locations_name_keys_not_values(_svc_lane, monkeypatch):
    service_status.declare_service(
        _SVC_CONTAINER,
        kind="container",
        host="127.0.0.1",
        project_id=_SVC_PROJECT,
    )
    marker = "RAW-VALUE-K08R3-0001"
    monkeypatch.setattr(
        service_status,
        "_read_descriptor",
        lambda service_id: {
            "env": {"LEAKED_K08R3_API_TOKEN": marker, "PORT": "9000"},
            "files": (),
        },
    )
    report = service_status.scan_container(_SVC_CONTAINER)
    assert report.verdict == "FINDINGS"
    assert report.findings == 1
    assert report.locations == ("env:LEAKED_K08R3_API_TOKEN",)
    assert marker not in repr(report)
    assert all(marker not in location for location in report.locations)


def test_svc_declare_validates_inputs(_svc_lane):
    before = set(service_status.service_ids())
    with pytest.raises(ValueError):
        service_status.declare_service(
            _SVC_HTTP, kind="rocket", project_id=_SVC_PROJECT
        )
    with pytest.raises(ValueError):
        service_status.declare_service("", project_id=_SVC_PROJECT)
    with pytest.raises(ValueError):
        service_status.declare_service(_SVC_HTTP, project_id="")
    assert set(service_status.service_ids()) == before


def test_svc_templates_resolve_caller_project(_svc_lane):
    caller = "proj-k08r3-tpl"
    for template_id in templates.BUILTIN_TEMPLATE_IDS:
        template = templates.instantiate(caller, template_id)
        assert template.project_id == caller
        plan = templates.materialize(caller, template_id)
        assert plan["template_id"] == template_id
        assert plan["project_id"] == caller
        assert "proj-a" not in json.dumps(plan)
        for step in plan["steps"]:
            assert step["action"] in templates.ACTION_CATALOG
            for output in step["outputs"]:
                assert output in templates.ACTION_CATALOG[step["action"]]
            service_ref = step["with"].get("service_id")
            if service_ref is not None:
                assert service_ref in service_status.service_ids()

