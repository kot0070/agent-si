"""Lane B integration (M-B-INT): REAL automation core, services and keeper.

End-to-end wiring of the real lane-B product modules on one shared set of
test-only cross-lane doubles: the global pause blocks runner.start_run and
a keeper-gated continuation together; a checkpoint pin round-trips through
recovery verify/recover on one shared journal double; the apps card
reflects the real pause flag plus real service rows; USER-write routes
refuse missing and wrong tokens; cancel keeps history in both lanes.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

import agent_si.automation.interface as auto_iface
from agent_si.automation import (
    apps_card,
    launcher,
    outage,
    pause,
    runner,
    scheduler,
    service_status,
    service_watch,
    templates,
    triggers,
)
from agent_si.automation.interface import AutomationError
from agent_si.context_keeper import interface as ck
from agent_si.context_keeper import checkpoints as keeper_checkpoints
from agent_si.context_keeper import recovery as keeper_recovery
from agent_si.context_keeper import register as keeper_register

try:
    import agent_si.backend.automation_routes as routes
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    _HAS_ROUTES = True
except ImportError:
    routes = None
    FastAPI = None
    TestClient = None
    _HAS_ROUTES = False

needs_routes = pytest.mark.skipif(not _HAS_ROUTES, reason="fastapi unavailable")

MODEL_ID = "meta/muse-spark-1.3-contributor"


# FAKE-OF: agent_si.watcher.journal.append_event
class SharedJournal:
    """One shared journal double for keeper rows and automation notices."""

    def __init__(self):
        self.calls = []
        self._seq = 0

    def append_event(self, project_id, source, kind, summary, refs=()):
        self._seq += 1
        entry = SimpleNamespace(
            entry_id="evt-%04d" % self._seq,
            timestamp="2026-10-27T00:00:00Z",
            hash="hash-%04d" % self._seq,
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


# FAKE-OF: agent_si.backend.stop_all.request_stop
class SharedStopAll:
    """One shared stop-all double for outage signals and keeper recovery."""

    def __init__(self):
        self.calls = []

    def request_stop(self, project_id, reason):
        self.calls.append((project_id, reason))
        return SimpleNamespace(
            project_id=project_id, stopped=True, reason=reason
        )


# FAKE-OF: agent_si.budget.gate.BudgetGate.get_state
class BudgetGateDouble:
    """Observe-only budget double: records get_state keys, reserves nothing."""

    def __init__(self):
        self.calls = []

    def get_state(self, key):
        self.calls.append(key)
        return {"key": key, "remaining": "100"}


# FAKE-OF: agent_si.toolguard.escape.check_escape
class AllowGuard:
    """Allow-all guard double accepting either lane call shape."""

    def __init__(self):
        self.calls = []

    def check_escape(self, *args):
        self.calls.append(tuple(args))
        return SimpleNamespace(allowed=True, reason="within workspace")


def _record(code, event_id="evt-001", project_id="proj-a",
            severity=None, contract_hash="hash-a",
            expected=("ref-a",), actual=("ref-a",),
            missing=(), conflicting=(), resolved_at=None):
    return ck.ContextIntegrityRecord(
        context_event_id=event_id,
        incident_ref=None,
        project_id=project_id,
        task_id="task-1",
        run_id="run-1",
        actor="watcher",
        detected_by="watcher",
        type=code,
        severity=ck.IncidentSeverity.HIGH if severity is None else severity,
        expected_context_refs=tuple(expected),
        actual_context_refs=tuple(actual),
        missing_refs=tuple(missing),
        conflicting_refs=tuple(conflicting),
        contract_hash=contract_hash,
        detected_at="2026-01-01T00:00:00Z",
        impact="impact",
        resolution="",
        resolved_at=resolved_at,
        evidence_refs=(),
    )


def _wire_hooks(doubles):
    runner.set_journal_hook(doubles["journal"].append_event)
    runner.set_budget_hook(None)
    launcher.set_journal_hook(doubles["journal"].append_event)
    launcher.set_guard_hook(doubles["guard"].check_escape)
    triggers.set_journal_hook(doubles["journal"].append_event)
    scheduler.set_journal_hook(doubles["journal"].append_event)
    scheduler.set_stop_hook(doubles["stopper"].request_stop)
    scheduler.set_clock(None)


def _gated_start(recovery, project_id, template_id):
    """Keeper-gated continuation: verify recovery before starting a run."""
    report = recovery.verify(project_id)
    if not report.ok:
        raise AutomationError(
            code="AUTOMATION_PAUSED",
            detail="keeper verify blocked continuation for %s" % project_id,
        )
    return runner.start_run(project_id, template_id)


@pytest.fixture(autouse=True)
def _clean_lane_b():
    service_status.reset_state()
    states = {
        service_id: (row["state"], row["timestamp"])
        for service_id, row in service_status._SERVICES.items()
    }
    pause.reset_state()
    runner.reset_state()
    triggers.reset_state()
    scheduler.reset_state()
    service_watch.reset_baseline()
    yield
    pause.reset_state()
    runner.reset_state()
    triggers.reset_state()
    scheduler.reset_state()
    service_watch.reset_baseline()
    launcher.set_journal_hook(None)
    launcher.set_guard_hook(None)
    for service_id, (state, stamp) in states.items():
        service_status._SERVICES[service_id]["state"] = state
        service_status._SERVICES[service_id]["timestamp"] = stamp


@pytest.fixture()
def doubles(monkeypatch):
    bundle = {
        "journal": SharedJournal(),
        "stopper": SharedStopAll(),
        "budget": BudgetGateDouble(),
        "guard": AllowGuard(),
    }
    monkeypatch.setattr(
        auto_iface, "journal_append_event", bundle["journal"].append_event
    )
    monkeypatch.setattr(
        auto_iface, "stop_all_request_stop", bundle["stopper"].request_stop
    )
    monkeypatch.setattr(
        service_status, "observe_budget", bundle["budget"].get_state
    )
    _wire_hooks(bundle)
    return bundle


def test_global_pause_blocks_start_and_gated_continuation(doubles):
    runner.register_template("tpl-nightly", "proj-a", name="nightly")
    register = keeper_register.Register()
    register.append(
        _record("CONTEXT_MISSING", event_id="evt-block",
                expected=("ref-a",), actual=(), missing=("ref-a",))
    )
    recovery = keeper_recovery.Recovery(register)
    pause.set_global(True, "drill")
    try:
        with pytest.raises(AutomationError) as excinfo:
            runner.start_run("proj-a", "tpl-nightly")
        assert excinfo.value.code == "AUTOMATION_PAUSED"
        with pytest.raises(AutomationError) as excinfo:
            _gated_start(recovery, "proj-a", "tpl-nightly")
        assert excinfo.value.code == "AUTOMATION_PAUSED"
        assert recovery.verify("proj-a").ok is False
    finally:
        pause.set_global(False, "")
    with pytest.raises(AutomationError) as excinfo:
        _gated_start(recovery, "proj-a", "tpl-nightly")
    assert "keeper" in (excinfo.value.detail or "")
    assert runner.list_runs("proj-a") == []


def test_gated_continuation_resumes_after_recovery(doubles):
    journal = doubles["journal"]
    runner.register_template("tpl-nightly", "proj-a", name="nightly")
    register = keeper_register.Register()
    register.append(
        _record("CONTEXT_MISSING", event_id="evt-rec",
                expected=("ref-a",), actual=(), missing=("ref-a",))
    )
    store = keeper_checkpoints.Checkpoints(
        journal_append=journal.append_event
    )
    pinned = store.write_checkpoint(
        project_id="proj-a", task_id="task-1", run_id="run-1",
        contract_hash="hash-a", context_refs=("ref-a",),
    )
    recovery = keeper_recovery.Recovery(
        register,
        checkpoints=store,
        journal_append=journal.append_event,
        request_stop=doubles["stopper"].request_stop,
    )
    pause.set_global(True, "drill")
    with pytest.raises(AutomationError):
        _gated_start(recovery, "proj-a", "tpl-nightly")
    pause.set_global(False, "")
    report = recovery.recover("proj-a", pinned.checkpoint_id)
    assert report.ok is True and report.code == ck.OK_CODE
    run = _gated_start(recovery, "proj-a", "tpl-nightly")
    assert run.state == "RUNNING"
    assert register.list_unresolved("proj-a") == []
    kinds = [row["kind"] for row in journal.calls]
    assert ck.CHECKPOINT_KIND in kinds and ck.RECOVERY_KIND in kinds
    assert kinds.index(ck.CHECKPOINT_KIND) < kinds.index(ck.RECOVERY_KIND)
    assert any(
        row["kind"] == "AUTOMATION_RUN" and run.run_id in row["refs"]
        for row in journal.calls
    )


def test_checkpoint_pin_recovery_roundtrip_shared_journal(doubles):
    journal = doubles["journal"]
    register = keeper_register.Register()
    store = keeper_checkpoints.Checkpoints(
        journal_append=journal.append_event
    )
    pinned = store.write_checkpoint(
        project_id="proj-a", task_id="task-1", run_id="run-1",
        contract_hash="hash-a", context_refs=("ref-a",),
    )
    assert pinned.contract_hash == "hash-a"
    assert pinned.context_refs == ("ref-a",)
    assert store.read_checkpoint(pinned.checkpoint_id) == pinned
    assert store.latest_for_project("proj-a") == pinned
    register.append(
        _record("CONTEXT_MISSING", event_id="evt-pin",
                expected=("ref-a",), actual=(), missing=("ref-a",))
    )
    recovery = keeper_recovery.Recovery(
        register,
        checkpoints=store,
        journal_append=journal.append_event,
        request_stop=doubles["stopper"].request_stop,
    )
    assert recovery.verify("proj-a").ok is False
    report = recovery.recover("proj-a", pinned.checkpoint_id)
    assert (report.ok, report.code) == (True, ck.OK_CODE)
    checkpoint_rows = [
        row for row in journal.calls if row["kind"] == ck.CHECKPOINT_KIND
    ]
    recovery_rows = [
        row for row in journal.calls if row["kind"] == ck.RECOVERY_KIND
    ]
    assert len(checkpoint_rows) == 1 and len(recovery_rows) == 1
    assert pinned.checkpoint_id in checkpoint_rows[0]["summary"]
    assert pinned.checkpoint_id in recovery_rows[0]["refs"]


def test_apps_card_reflects_real_pause_and_service_rows():
    card = apps_card.get_apps_card("proj-a")
    assert card.project_id == "proj-a"
    assert card.service_ids == service_status.services_for_project("proj-a")
    assert "svc-api" in card.service_ids
    assert card.paused is False
    pause.set_global(True, "drill")
    try:
        assert apps_card.get_apps_card("proj-a").paused is True
    finally:
        pause.set_global(False, "")
    pause.set_project("proj-a", True)
    try:
        assert apps_card.get_apps_card("proj-a").paused is True
    finally:
        pause.set_project("proj-a", False)
    assert apps_card.get_apps_card("proj-a").paused is False


USER_WRITES = (
    ("/api/v1/automations/pause",
     {"paused": True, "reason": "drill"}),
    ("/api/v1/automations/runs",
     {"project_id": "proj-a", "template_id": "tpl-nightly"}),
    ("/api/v1/outage/signal",
     {"project_id": "proj-a", "service_id": "svc-api",
      "severity": "HIGH", "summary": "loopback lost"}),
)


@pytest.fixture()
def client(monkeypatch):
    app = FastAPI()
    app.include_router(routes.router)
    monkeypatch.setattr(
        routes, "_auth_hook", lambda token: token == "token-live"
    )
    monkeypatch.setattr(routes, "_rate_hook", None)
    monkeypatch.setattr(
        auto_iface, "journal_append_event", SharedJournal().append_event
    )
    monkeypatch.setattr(
        auto_iface, "stop_all_request_stop", SharedStopAll().request_stop
    )
    return TestClient(app)


@needs_routes
@pytest.mark.parametrize("path,payload", USER_WRITES)
def test_user_writes_refuse_missing_token(client, path, payload):
    response = client.post(path, json=dict(payload))
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "SESSION_TOKEN_MISSING"


@needs_routes
@pytest.mark.parametrize("path,payload", USER_WRITES)
def test_user_writes_refuse_wrong_token(client, path, payload):
    response = client.post(
        path, json=dict(payload),
        headers={"x-ui-session-token": "token-wrong"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "SESSION_TOKEN_INVALID"


def test_cancel_keeps_history_both_lanes(doubles):
    journal = doubles["journal"]
    runner.register_template("tpl-nightly", "proj-a", name="nightly")
    run = runner.start_run("proj-a", "tpl-nightly")
    cancelled = runner.cancel_run("proj-a", run.run_id, reason="user-stop")
    assert cancelled.state == "CANCELLED"
    events = [
        entry["event"]
        for entry in runner.get_history("proj-a", run.run_id)
    ]
    assert "created" in events and "cancelled:user-stop" in events
    assert runner.get_finalization("proj-a", run.run_id) == {
        "reason": "user-stop", "finalized": True,
    }
    assert [
        row["kind"] for row in journal.calls
    ].count("AUTOMATION_RUN") >= 2
    register = keeper_register.Register()
    record = _record("CONTEXT_MISSING", event_id="evt-cancel")
    register.append(record)
    assert register.cancel_run("proj-a", "run-1") == 1
    assert register.read("evt-cancel") == record
    assert [
        row.context_event_id
        for row in register.list_unresolved("proj-a")
    ] == ["evt-cancel"]


def test_outage_stop_and_report_shared_doubles(doubles):
    journal = doubles["journal"]
    stopper = doubles["stopper"]
    report = outage.signal_outage(
        "proj-a", "svc-api", "HIGH", "loopback lost"
    )
    assert report.stopped is True
    assert report.project_id == "proj-a"
    assert report.service_id == "svc-api"
    assert len(stopper.calls) == 1
    assert "svc-api" in stopper.calls[0][1]
    rows = [
        row for row in journal.calls
        if row["kind"] == auto_iface.JournalKind.OUTAGE_SIGNAL.value
    ]
    assert len(rows) == 1
    assert report.journal_entry_id == rows[0]["entry"].entry_id
    assert report.report_id in rows[0]["refs"]
    assert "svc-api" in rows[0]["refs"]


def test_template_plan_to_running_run(doubles):
    journal = doubles["journal"]
    template = templates.instantiate("proj-a", "tpl-nightly")
    assert template.template_id == "tpl-nightly"
    plan = templates.materialize("proj-a", "tpl-nightly")
    assert plan["model"] == MODEL_ID == templates.MODEL_ID
    assert isinstance(plan["steps"], list) and plan["steps"] != []
    runner.register_template("tpl-nightly", "proj-a", name=template.name)
    triggers.register_trigger("trg-nightly", "proj-a", kind="LAUNCHER")
    fired = triggers.fire_trigger("proj-a", "trg-nightly")
    assert fired.state == "RUNNING" and fired.trigger_id == "trg-nightly"
    run = runner.start_run("proj-a", "tpl-nightly")
    assert run.state == "RUNNING"
    assert runner.get_run("proj-a", run.run_id).state == "RUNNING"
    assert any(
        row["kind"] == "AUTOMATION_RUN" for row in journal.calls
    )


def test_timer_fires_launcher_end_to_end(doubles):
    journal = doubles["journal"]
    guard = doubles["guard"]
    runner.register_template("tpl-nightly", "proj-a", name="nightly")
    triggers.register_trigger("trg-t1", "proj-a", kind="TIMER")
    scheduler.register_launcher("lch-1", "proj-a", "tpl-nightly")
    scheduler.register_timer(
        "tmr-1", "proj-a", 60.0, launcher_id="lch-1", first_due=1000.0,
    )
    run = scheduler.fire_timer("tmr-1", now=1000.0)
    assert run is not None and run.state == "RUNNING"
    assert runner.get_run("proj-a", run.run_id).state == "RUNNING"
    assert journal.calls, "firing must notify the shared journal"
    assert guard.calls, "launch must check the guard first"
    outcomes = [entry["outcome"] for entry in scheduler.ledger()]
    assert "timer-fired" in outcomes and "launcher-fired" in outcomes


def test_service_check_observes_budget_and_journal(doubles, monkeypatch):
    journal = doubles["journal"]
    budget = doubles["budget"]
    monkeypatch.setattr(
        service_status, "_probe_tcp", lambda *args: (True, False)
    )
    status = service_status.run_check(
        "svc-loopback", auto_iface.ServiceCheckKind.TCP
    )
    assert status.state == "UP"
    assert budget.calls, "run_check must observe the budget gate"
    assert all(key == "svc-loopback" for key in budget.calls)
    rows = [
        row for row in journal.calls
        if row["kind"] == auto_iface.JournalKind.SERVICE_STATE.value
    ]
    assert len(rows) == 1 and "svc-loopback" in rows[0]["refs"]
    card = apps_card.get_apps_card("proj-b")
    assert "svc-loopback" in card.service_ids
    assert service_status.get("svc-loopback").state == "UP"


def test_recover_critical_calls_shared_stop(doubles):
    journal = doubles["journal"]
    stopper = doubles["stopper"]
    register = keeper_register.Register()
    register.append(
        _record("CONTEXT_CONFLICT", event_id="evt-crit",
                severity=ck.IncidentSeverity.CRITICAL,
                expected=("ref-keep",), actual=(), missing=("ref-keep",))
    )
    store = keeper_checkpoints.Checkpoints()
    pinned = store.write_checkpoint(
        project_id="proj-a", task_id="task-1", run_id="run-1",
        contract_hash="hash-a", context_refs=("ref-a",),
    )
    recovery = keeper_recovery.Recovery(
        register,
        checkpoints=store,
        journal_append=journal.append_event,
        request_stop=stopper.request_stop,
    )
    report = recovery.recover("proj-a", pinned.checkpoint_id)
    assert report.ok is False
    assert report.code == ck.RECOVERY_FAILED_CODE
    assert stopper.calls == [("proj-a", keeper_recovery.STOP_REASON)]
    assert any(
        row["kind"] == ck.RECOVERY_KIND for row in journal.calls
    )
