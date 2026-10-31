"""K08NEXT watcher-core served proofs: 8 rows via create_app + TestClient.

Row order: R-325 local-AI script+params | R-336 action modes per project |
R-337 usage fields, leak scan, protected refused | R-363 outage plus
restart, watcher stays live | R-364 rule cards, presets, unknown-rule 404 |
R-366 declared services, observe, usage, outage link | M-P2-68 provider
outage stop-and-report, telemetry, free audit | M-P3-94 timer pause (skip)
plus resume (run once) plus survive app restart.

Every test drives the served app (create_app + HTTP client, loopback TEST
data only). Lane setup (resolve_action, settings, declare_service, outage,
timers) uses real product APIs; facts are verified over served watcher
routes plus the owned lane stores. No doubles, no skip/xfail.
"""

import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

from fastapi.testclient import TestClient  # noqa: E402

import agent_si.automation.interface as auto_iface  # noqa: E402
from agent_si.automation import outage as _auto_outage  # noqa: E402
from agent_si.automation import pause as _pause  # noqa: E402
from agent_si.automation import runner as _runner  # noqa: E402
from agent_si.automation import scheduler as _sched  # noqa: E402
from agent_si.automation import launcher as _launcher  # noqa: E402
from agent_si.automation import service_status as _services  # noqa: E402
from agent_si.automation import service_watch as _watch  # noqa: E402
from agent_si.automation import triggers as _triggers  # noqa: E402
from agent_si.backend import stop_all as _stop_all  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.watcher import alerts as _alerts  # noqa: E402
from agent_si.watcher import engine as _engine  # noqa: E402
from agent_si.watcher import guard as _guard  # noqa: E402
from agent_si.watcher import integrity as _integrity  # noqa: E402
from agent_si.watcher import journal as _journal  # noqa: E402
from agent_si.watcher import outage as _watch_outage  # noqa: E402
from agent_si.watcher import presets as _presets  # noqa: E402
from agent_si.watcher import rules as _rules  # noqa: E402
from agent_si.watcher import status as _status  # noqa: E402
from agent_si.watcher.journal import WatcherError  # noqa: E402

TESTID = "k08watcher-served"
TOKEN = "k08watcher-token"


def _settings():
    return {"testing": True, "ui_session_token": TOKEN}


def _auth():
    return {"x-ui-session-token": TOKEN}


def _client():
    return TestClient(create_app(_settings()))


@pytest.fixture(autouse=True)
def _lane():
    """Reset every touched lane store; no doubles, real backends only."""
    _pause.reset_state()
    _runner.reset_state()
    _triggers.reset_state()
    _sched.reset_state()
    _launcher.set_journal_hook(None)
    _launcher.set_guard_hook(None)
    _journal.reset_state()
    _integrity.reset_state()
    _rules.reset_state()
    _engine.reset_state()
    _presets.reset_state()
    _status.reset_state()
    _alerts.reset_state()
    _guard.reset_state()
    _watch_outage.reset_state()
    _services.reset_state()
    _watch.reset_baseline()
    _stop_all.reset_state()
    yield
    _stop_all.reset_state()
    _journal.reset_state()
    _integrity.reset_state()
    _rules.reset_state()
    _engine.reset_state()
    _presets.reset_state()
    _status.reset_state()
    _watch_outage.reset_state()
    _services.reset_state()
    _watch.reset_baseline()
    _pause.reset_state()
    _runner.set_run_temp_base(None)


def _spawn_sleeper():
    """One real endless child process for stop tests (portable)."""
    return subprocess.Popen(
        [sys.executable, "-c", "import time\nwhile True: time.sleep(0.05)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _reap(proc):
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()
                proc.wait(timeout=10)
    except Exception:
        pass


def _served_journal(client, project_id, kind):
    resp = client.get("/api/v1/watcher/journal",
                      params={"project_id": project_id, "kind": kind})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_r325_local_ai_script_params_served_evaluate():
    """Row R-325 [k08watcher-served]: local AI picks script plus params."""
    assert TESTID == "k08watcher-served"
    client = _client()
    pid = "k08w-r325-p1"
    action = _engine.resolve_action(pid, "rule-tamper")
    assert action.script == "scripts/tamper_check.py"
    assert action.params == ("--model", "local", "--hang-minutes", "20")
    assert _engine.recorded_actions(pid) == (action,)
    resp = client.post("/api/v1/watcher/rules/rule-tamper/evaluate",
                       json={"project_id": pid}, headers=_auth())
    assert resp.status_code == 200, resp.text
    # No SERVICE_STATE heartbeat on this project (resolve_action records
    # AUTOMATION_RUN only), so the hang detector honestly escalates.
    assert resp.json()["verdict"] == "ESCALATE"
    decisions = _served_journal(client, pid, "WATCH_DECISION")
    assert any(row["entry_id"] == resp.json()["journal_entry_id"]
               for row in decisions)
    runs = _served_journal(client, pid, "AUTOMATION_RUN")
    assert len(runs) == 1
    assert any(row.entry_id == runs[0]["entry_id"]
               for row in _journal.stored_rows(pid, "AUTOMATION_RUN"))
    decision = _engine.decide(pid, "rule-tamper", action.script,
                              action.params)
    assert decision.rule_id == "rule-tamper"
    assert _engine.last_choice(pid) == (
        "rule-tamper", action.script, action.params)


def test_r336_action_modes_per_project_served_fire():
    """Row R-336 [k08watcher-served]: action modes served per project."""
    assert TESTID == "k08watcher-served"
    client = _client()
    pid = "k08w-r336-p1"
    other = "k08w-r336-p2"
    before = len(_journal.stored_rows(pid))
    assert _rules.get_watcher_settings(pid).action_mode == "local_ai_default"
    assert len(_journal.stored_rows(pid)) == before
    fired = client.post("/api/v1/watcher/timers/tm-k08w-336a/fire",
                        json={"project_id": pid}, headers=_auth())
    assert fired.status_code == 200, fired.text
    assert fired.json()["action_mode"] == "local_ai_default"
    assert fired.json()["event"] == "TIMER_FIRED"
    rows = _served_journal(client, pid, "AUTOMATION_RUN")
    assert any(row["entry_id"] == fired.json()["journal_entry_id"]
               for row in rows)
    assert any("mode=local_ai_default" in row.summary for row in
               _journal.stored_rows(pid, "AUTOMATION_RUN"))
    assert _rules.update_watcher_settings(pid, "cloud_fallback").action_mode \
        == "cloud_fallback"
    cloud = client.post("/api/v1/watcher/timers/tm-k08w-336b/fire",
                        json={"project_id": pid}, headers=_auth())
    assert cloud.status_code == 200, cloud.text
    assert cloud.json()["action_mode"] == "cloud_fallback"
    assert _rules.update_watcher_settings(other, "off").action_mode == "off"
    still = client.post("/api/v1/watcher/timers/tm-k08w-336c/fire",
                        json={"project_id": pid}, headers=_auth())
    assert still.json()["action_mode"] == "cloud_fallback"
    assert _rules.update_watcher_settings(pid, "off").action_mode == "off"
    off = client.post("/api/v1/watcher/timers/tm-k08w-336d/fire",
                      json={"project_id": pid}, headers=_auth())
    assert off.json()["action_mode"] == "off"
    with pytest.raises(WatcherError) as excinfo:
        _rules.update_watcher_settings(pid, "no-such-mode")
    assert excinfo.value.code == "SETTING_NOT_FOUND"
    assert _rules.get_watcher_settings(pid).action_mode == "off"
    refused = client.post("/api/v1/watcher/timers/tm-k08w-336e/pause",
                          json={"project_id": pid, "paused": True,
                                "reason": ""},
                          headers=_auth())
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"]["code"] == "PAUSE_REASON_MISSING"


def test_r337_usage_leak_protected_served_alerts():
    """Row R-337 [k08watcher-served]: usage, leak scan, protected refused."""
    assert TESTID == "k08watcher-served"
    client = _client()
    pid = "k08w-r337-p1"
    _services.declare_service("svc-k08w-337", kind="tcp", host="127.0.0.1",
                              tcp_port=9, project_id=pid)
    _services.record_usage("svc-k08w-337", active=True,
                           last_agent="agent-k08w")
    usage = _engine.service_usage(pid)
    assert len(usage.services) == 1
    row = usage.services[0]
    assert row.service_id == "svc-k08w-337"
    assert row.in_use is True
    assert row.last_used != ""
    assert row.last_agent == "agent-k08w"
    empty = _engine.service_usage("k08w-r337-nobody")
    assert empty.services == ()
    assert empty.next_step != ""
    served = client.get("/api/v1/services/svc-api/status")
    assert served.status_code == 200, served.text
    assert served.json()["in_use"] is True
    assert served.json()["last_used"] != ""
    assert served.json()["last_agent"] == "agent-1"
    _journal.append_event(pid, "agent-x", "TAMPER_ATTEMPT",
                          "escape probe k08w-337", ("/outside/evil.txt",))
    result = _engine.run_script(pid, "data-leak-scan", ("svc-container",))
    assert result.outcome == "clean"
    assert any(row["entry_id"] == result.journal_entry_id
               for row in _served_journal(client, pid, "SERVICE_STATE"))
    scan = _services.scan_container("svc-container")
    assert scan.verdict == "CLEAN"
    assert scan.checked > 0
    assert scan.findings == 0
    for location in scan.locations:
        assert "=" not in location
        assert "secretref:" not in location
    with pytest.raises(WatcherError) as excinfo:
        _engine.decide(pid, "rule-tamper", "/outside/evil.txt", ())
    assert excinfo.value.code == "GOVERNANCE_MISMATCH"
    blocks = _served_journal(client, pid, "GUARD_BLOCK")
    assert len(blocks) == 1
    assert any("workspace escape blocked" in found.summary for found in
               _journal.stored_rows(pid, "GUARD_BLOCK"))
    alerts = client.get("/api/v1/watcher/alerts",
                        params={"project_id": pid})
    assert alerts.status_code == 200, alerts.text
    verdicts = {entry["rule_id"]: entry["verdict"]
                for entry in alerts.json()["alerts"]}
    assert verdicts["rule-tamper"] == "BLOCK"
    assert verdicts["rule-guard"] == "BLOCK"


def test_r363_outage_restart_watcher_live_served_evaluate():
    """Row R-363 [k08watcher-served]: outage once, restart, watcher live."""
    assert TESTID == "k08watcher-served"
    client = _client()
    pid = "k08w-r363-p1"
    proc = _spawn_sleeper()
    try:
        _stop_all.attach_child(pid, "run-k08w-363-1", proc)
        first = _watch_outage.signal_outage(pid, "svc-a", "k08w outage 363")
        assert first.stopped is True
        assert proc.poll() is not None
    finally:
        _reap(proc)
    assert len(_served_journal(client, pid, "STOP_ALL")) == 1
    outage_rows = _served_journal(client, pid, "OUTAGE_SIGNAL")
    assert len(outage_rows) == 1
    stored = _journal.stored_rows(pid, "OUTAGE_SIGNAL")
    assert len(stored) == 1
    assert "STOP_AND_REPORT" in stored[0].summary
    assert stored[0].refs == ("svc-a", "k08w outage 363")
    assert outage_rows[0]["entry_id"] == first.journal_entry_id
    second = _watch_outage.signal_outage(pid, "svc-a", "k08w outage 363")
    assert second.stopped is False
    assert second.journal_entry_id == first.journal_entry_id
    assert len(_served_journal(client, pid, "STOP_ALL")) == 1
    assert len(_served_journal(client, pid, "OUTAGE_SIGNAL")) == 1
    receipt = _engine.supervised_restart(pid, "sup-k08w-363")
    assert receipt.accepted is True
    assert any(row["entry_id"] == receipt.journal_entry_id
               for row in _served_journal(client, pid, "SERVICE_STATE"))
    evaluated = client.post("/api/v1/watcher/rules/rule-tamper/evaluate",
                            json={"project_id": pid}, headers=_auth())
    assert evaluated.status_code == 200, evaluated.text


def test_r364_cards_presets_unknown_rule_served_status():
    """Row R-364 [k08watcher-served]: cards, presets, 404, status served."""
    assert TESTID == "k08watcher-served"
    client = _client()
    pid = "k08w-r364-p1"
    tamper = _rules.describe("rule-tamper")
    assert (tamper.area, tamper.model, tamper.hang_minutes) == (
        "tamper", "local", 20)
    assert _rules.HANG_DEFAULT_MINUTES == 20
    assert _presets.TABLE["standard"] == ("card-hang", "card-guard")
    assert _presets.apply(pid, "strict") == (
        "card-hang", "card-guard", "card-tamper")
    with pytest.raises(WatcherError) as excinfo:
        _rules.describe("rule-missing")
    assert excinfo.value.code == "RULE_NOT_FOUND"
    before = len(_served_journal(client, pid, "WATCH_DECISION"))
    missing = client.post("/api/v1/watcher/rules/rule-missing/evaluate",
                          json={"project_id": pid}, headers=_auth())
    assert missing.status_code == 404, missing.text
    assert missing.json()["detail"]["code"] == "RULE_NOT_FOUND"
    assert len(_served_journal(client, pid, "WATCH_DECISION")) == before
    status = client.get("/api/v1/watcher/status",
                        params={"project_id": pid})
    assert status.status_code == 200, status.text
    assert status.json()["project_id"] == pid
    assert status.json()["integrity_ok"] is True


def test_r366_declared_services_observe_link_served_journal(monkeypatch):
    """Row R-366 [k08watcher-served]: observe, usage, link, journaled."""
    assert TESTID == "k08watcher-served"
    # Boundary hook only (r7 fixture pattern): cross-lane journal reference
    # owned by the watcher lane; the served app leaves it unbound.
    monkeypatch.setattr(auto_iface, "journal_append_event",
                        _journal.append_event)
    client = _client()
    pid = "k08w-r366-p1"
    _services.declare_service("svc-k08w-366", kind="tcp", host="127.0.0.1",
                              tcp_port=9, project_id=pid)
    fresh = _services.get("svc-k08w-366")
    assert fresh.state == "DOWN"
    observed = _services.run_check("svc-k08w-366", "TCP")
    assert observed.state in ("UP", "DOWN", "DEGRADED")
    assert observed.timestamp != ""
    usage = _engine.service_usage(pid)
    assert any(item.service_id == "svc-k08w-366"
               for item in usage.services)
    depend = _engine.run_script(pid, "dependent-service-watch", ())
    assert depend.outcome.startswith("changed")
    assert any(row["entry_id"] == depend.journal_entry_id
               for row in _served_journal(client, pid, "SERVICE_STATE"))
    linked = _auto_outage.link_observation_to_outage(
        pid, "svc-k08w-366", "HIGH", "drill-k08w-366")
    assert linked.stopped is False
    assert linked.journal_entry_id != ""
    link_rows = _served_journal(client, pid, "OUTAGE_SIGNAL")
    assert any(row["entry_id"] == linked.journal_entry_id
               for row in link_rows)
    assert any(linked.report_id in row.refs for row in
               _journal.stored_rows(pid, "OUTAGE_SIGNAL"))
    with pytest.raises(auto_iface.AutomationError) as excinfo:
        _auto_outage.link_observation_to_outage(
            "proj-a", "svc-api", "HIGH", "no outage")
    assert excinfo.value.code == "SERVICE_CHECK_REFUSED"


def test_mp2_68_provider_outage_telemetry_audit_served_journal():
    """Row M-P2-68 [k08watcher-served]: outage, telemetry, free audit."""
    assert TESTID == "k08watcher-served"
    client = _client()
    pid = "k08w-mp268-p1"
    proc = _spawn_sleeper()
    try:
        _stop_all.attach_child(pid, "run-k08w-mp268-1", proc)
        report = _watch_outage.signal_outage(
            pid, "svc-cache", "provider down mp2-68")
        assert report.stopped is True
        assert proc.poll() is not None
    finally:
        _reap(proc)
    assert len(_served_journal(client, pid, "STOP_ALL")) == 1
    telemetry = _served_journal(client, pid, "OUTAGE_SIGNAL")
    assert len(telemetry) == 1
    assert telemetry[0]["entry_id"] == report.journal_entry_id
    stored = _journal.stored_rows(pid, "OUTAGE_SIGNAL")
    assert stored[0].refs == ("svc-cache", "provider down mp2-68")
    audit = _engine.run_script(pid, "data-leak-scan", ("svc-container",))
    assert audit.outcome == "clean"
    assert any(row["entry_id"] == audit.journal_entry_id
               for row in _served_journal(client, pid, "SERVICE_STATE"))
    scan = _services.scan_container("svc-container")
    assert scan.verdict == "CLEAN"
    for location in scan.locations:
        assert "=" not in location
        assert "secretref:" not in location
    assert _services.observe_budget("svc-cache") == \
        _services.observe_budget("svc-cache")


def test_mp3_94_timer_skip_once_survive_restart_served_fire():
    """Row M-P3-94 [k08watcher-served]: skip, run once, survive restart."""
    assert TESTID == "k08watcher-served"
    client = _client()
    pid = "k08w-mp394-p1"
    first = client.post("/api/v1/watcher/timers/tm-k08w-94a/fire",
                        json={"project_id": pid}, headers=_auth())
    assert first.status_code == 200, first.text
    assert first.json()["event"] == "TIMER_FIRED"
    paused = client.post("/api/v1/watcher/timers/tm-k08w-94a/pause",
                         json={"project_id": pid, "paused": True,
                               "reason": "k08w drill 94"},
                         headers=_auth())
    assert paused.status_code == 200, paused.text
    assert paused.json()["paused"] is True
    before = len(_served_journal(client, pid, "AUTOMATION_RUN"))
    skipped = client.post("/api/v1/watcher/timers/tm-k08w-94a/fire",
                          json={"project_id": pid}, headers=_auth())
    assert skipped.status_code == 409, skipped.text
    assert skipped.json()["detail"]["code"] == "AUTOMATION_PAUSED"
    assert len(_served_journal(client, pid, "AUTOMATION_RUN")) == before
    resumed = client.post("/api/v1/watcher/timers/tm-k08w-94a/pause",
                          json={"project_id": pid, "paused": False,
                                "reason": ""},
                          headers=_auth())
    assert resumed.status_code == 200, resumed.text
    once = client.post("/api/v1/watcher/timers/tm-k08w-94a/fire",
                       json={"project_id": pid}, headers=_auth())
    assert once.status_code == 200, once.text
    assert len(_served_journal(client, pid, "AUTOMATION_RUN")) == before + 1
    restarted = TestClient(create_app(_settings()))
    assert any(row["entry_id"] == first.json()["journal_entry_id"]
               for row in _served_journal(restarted, pid, "AUTOMATION_RUN"))
    again = restarted.post("/api/v1/watcher/timers/tm-k08w-94b/fire",
                           json={"project_id": pid}, headers=_auth())
    assert again.status_code == 200, again.text
    assert again.json()["event"] == "TIMER_FIRED"
