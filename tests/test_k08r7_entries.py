"""K08R7 entry behaviour tests (row plus lane plus author only).

Lane _task/K08R7/m_entry, author CODER-2 Sable. One behaviour test per
kit coverage row (26 rows: 174, 181, 186, 249, R-320..R-327, R-335..R-337,
R-364, R-366, M-P2-68, M-P3-94, M-P3-112, B0B-SDK-94/95/96/99, Q3, Q8);
each proves its 0C-named entry reachable from the app (route, scheduler
or CLI). Cross-lane doubles below are test-only FAKE-OF bindings, the
same convention as tests/test_reachability_k08.py; product files carry
no test doubles.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

import agent_si.automation.interface as auto_iface
import agent_si.watcher.interface as watcher_iface
from agent_si.automation import apps_card as _apps_card
from agent_si.automation import cleanup as _cleanup
from agent_si.automation import launcher as _launcher
from agent_si.automation import outage as _outage
from agent_si.automation import pause as _pause
from agent_si.automation import runner as _runner
from agent_si.automation import scheduler as _sched
from agent_si.automation import service_status as _services
from agent_si.automation import service_watch as _watch
from agent_si.automation import templates as _templates
from agent_si.automation import triggers as _triggers
from agent_si.backend.app import create_app
from agent_si.watcher import engine as _engine
from agent_si.watcher import integrity as _integrity
from agent_si.watcher import journal as _journal
from agent_si.watcher import presets as _presets
from agent_si.watcher import rules as _rules
from agent_si.watcher import status as _status
from agent_si.watcher.journal import WatcherError
from fastapi.testclient import TestClient

LIVE_TOKEN = "k08-r7-entry-live"
AUTO_PROJ = "proj-a"
W_PROJ = "proj-r7-entry"


# FAKE-OF: backend auth-hook boundary (test settings only)
def _fake_auth_hook(token):
    """Boundary auth hook: only the entry live token is accepted."""
    return token == LIVE_TOKEN


# FAKE-OF: backend rate-hook boundary (test settings only)
def _fake_rate_hook(key):
    """Boundary rate hook: entry traffic is never throttled."""
    return True


# FAKE-OF: backend model_factory boundary (test settings only)
def _fake_model_factory(name):
    """Boundary model factory: no model calls in entry tests."""
    raise auto_iface.AutomationError("TEMPLATE_NOT_FOUND")


# FAKE-OF: automation stop-all cross-lane call (other lane owns it)
def _auto_stop_double(project_id, reason):
    """Stop-all double: automation outage path observes stopped True."""
    return auto_iface.StopReceipt(
        project_id=project_id, stopped=True, reason=reason)


def _seam_settings():
    """Test settings for the seam app: boundary hooks only."""
    return {
        "env": "test",
        "auth_hook": _fake_auth_hook,
        "rate_hook": _fake_rate_hook,
        "model_factory": _fake_model_factory,
    }


def _w_verify(project_id, session_token=""):
    """Watcher entry wrapper: integrity verify tolerates the route kwarg."""
    return _integrity.verify(project_id)


def _w_evaluate(project_id, rule_id, session_token=""):
    """Watcher entry wrapper: rule evaluate tolerates the route kwarg."""
    return _rules.evaluate(project_id, rule_id)


def _w_stop_all(actor, project_id, grant_ref="", session_token=""):
    """Watcher entry wrapper: real stop-all behind the route kwarg."""
    from agent_si.backend import stop_all as _stop_all

    return _stop_all.request_stop(actor, project_id, grant_ref)


@pytest.fixture
def client(monkeypatch):
    """Fresh seam app on reset lane state with real entries bound."""
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
    _services.reset_state()
    _watch.reset_baseline()
    from agent_si.backend import stop_all as _stop_all

    _stop_all.reset_state()
    _runner.register_template("tpl-nightly", AUTO_PROJ, "nightly")
    _triggers.register_trigger(
        "trg-hourly", AUTO_PROJ, "TIMER", "hourly", True)
    monkeypatch.setattr(
        auto_iface, "journal_append_event", _journal.append_event)
    monkeypatch.setattr(
        auto_iface, "stop_all_request_stop", _auto_stop_double)
    monkeypatch.setattr(
        auto_iface, "guard_check_escape", lambda project_id, path: True)
    monkeypatch.setattr(watcher_iface, "append_event", _journal.append_event)
    monkeypatch.setattr(watcher_iface, "list_events", _journal.list_events)
    monkeypatch.setattr(watcher_iface, "verify_integrity", _w_verify)
    monkeypatch.setattr(watcher_iface, "evaluate_rule", _w_evaluate)
    monkeypatch.setattr(watcher_iface, "engine_tick", _engine.tick)
    monkeypatch.setattr(watcher_iface, "engine_decide", _engine.decide)
    monkeypatch.setattr(watcher_iface, "apply_preset", _presets.apply)
    monkeypatch.setattr(watcher_iface, "get_status", _status.get)
    monkeypatch.setattr(
        watcher_iface, "stop_all_request_stop", _w_stop_all)
    saved_imports = dict(_templates._IMPORTS)
    yield TestClient(create_app(_seam_settings()))
    _templates._IMPORTS.clear()
    _templates._IMPORTS.update(saved_imports)


def _authed(client, method, url, body=None):
    """POST/GET with the live boundary token in the header."""
    headers = {"x-ui-session-token": LIVE_TOKEN}
    if method == "GET":
        return client.get(url, params=body or {}, headers=headers)
    return client.post(url, json=body or {}, headers=headers)


def test_row_174_global_and_project_pause_recorded_runs(client):
    """Row 174: global plus per-project pause; runs recorded, governed."""
    paused = _authed(client, "POST", "/api/v1/automations/pause",
                     {"paused": True, "reason": "drill-174"})
    assert paused.status_code == 200
    effective = _authed(client, "GET", "/api/v1/automations/pause",
                        {"project_id": W_PROJ})
    assert effective.status_code == 200
    assert effective.json() is True
    _authed(client, "POST", "/api/v1/automations/pause",
            {"paused": False, "reason": ""})
    _pause.set_project(W_PROJ, True)
    scoped = _authed(client, "GET", "/api/v1/automations/pause",
                     {"project_id": W_PROJ})
    assert scoped.json() is True
    other = _authed(client, "GET", "/api/v1/automations/pause",
                    {"project_id": "proj-r7-other"})
    assert other.json() is False
    _pause.set_project(W_PROJ, False)
    _runner.register_template("tpl-r7-174", W_PROJ, "r7-174")
    _runner.set_journal_hook(_journal.append_event)
    try:
        _integrity.seal(W_PROJ)
        run = _runner.start_run(W_PROJ, "tpl-r7-174")
        assert run.state == "RUNNING"
    finally:
        _runner.set_journal_hook(None)
    rows = _journal.stored_rows(W_PROJ, "AUTOMATION_RUN")
    assert any("run started" in row.summary for row in rows)
    assert _integrity.verify(W_PROJ).ok is True


def test_row_181_outage_stop_and_report(client):
    """Row 181: outage is one clear stop-and-report signal."""
    response = _authed(client, "POST", "/api/v1/outage/signal", {
        "project_id": AUTO_PROJ, "service_id": "svc-api",
        "severity": "HIGH", "summary": "drill-181"})
    assert response.status_code == 200
    body = response.json()
    assert body["stopped"] is True
    assert body["journal_entry_id"] != ""
    rows = _journal.stored_rows(AUTO_PROJ, "OUTAGE_SIGNAL")
    assert any(body["report_id"] in row.refs for row in rows)


def test_row_186_default_preset_seeded(client):
    """Row 186: default watcher preset seeded on a fresh project."""
    fresh = "proj-r7-fresh-186"
    assert _presets.installed_cards(fresh) == ()
    cards = _presets.ensure_seeded(fresh)
    assert cards == ("card-hang", "card-guard")
    assert _presets.installed_cards(fresh) == cards
    assert _presets.ensure_seeded(fresh) == cards
    seed_rows = _journal.stored_rows(fresh, "SERVICE_STATE")
    assert any("seed standard preset" in row.summary for row in seed_rows)
    with pytest.raises(WatcherError) as excinfo:
        _presets.apply(fresh, "no-such-preset")
    assert excinfo.value.code == "PRESET_NOT_FOUND"


def test_row_249_apps_card_closing_pause(client):
    """Row 249: named apps card mirrors the closing (paused) state."""
    response = _authed(client, "GET", "/api/v1/apps/card",
                       {"project_id": AUTO_PROJ})
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == AUTO_PROJ
    assert "svc-api" in body["service_ids"]
    assert body["paused"] is False
    assert body["generated_at"] != ""
    _pause.set_global(True, "closing-249")
    try:
        closed = _authed(client, "GET", "/api/v1/apps/card",
                         {"project_id": AUTO_PROJ})
        assert closed.json()["paused"] is True
    finally:
        _pause.set_global(False, "")


def test_row_320_disk_and_own_temp_journaled(client):
    """Row R-320: disk check plus own-temp cleanup, journaled, own only."""
    with tempfile.TemporaryDirectory(prefix="r7-320-") as base:
        _runner.set_run_temp_base(base)
        try:
            _runner.set_journal_hook(_journal.append_event)
            try:
                disk = _runner.disk_check_runs(W_PROJ)
            finally:
                _runner.set_journal_hook(None)
            assert disk["ok"] is True
            assert disk["free"] > 0
            assert disk["total"] >= disk["free"]
            run = _runner.start_run(AUTO_PROJ, "tpl-nightly")
            run_dir = _cleanup.run_dir_for(base, run.run_id)
            Path(run_dir).mkdir(parents=True, exist_ok=True)
            (Path(run_dir) / "scratch.bin").write_bytes(b"x" * 16)
            _runner.set_journal_hook(_journal.append_event)
            try:
                receipt = _runner.cleanup_run_temp(
                    AUTO_PROJ, run.run_id)
            finally:
                _runner.set_journal_hook(None)
            assert receipt["removed"] == ["scratch.bin"]
            assert list(Path(run_dir).iterdir()) == []
            notes = _journal.stored_rows(AUTO_PROJ, "AUTOMATION_RUN")
            assert any("run temp cleaned" in row.summary for row in notes)
        finally:
            _runner.set_run_temp_base(None)
    with pytest.raises(ValueError):
        _cleanup.run_dir_for(base, "../escape-320")


def test_row_321_workspace_escape_seam(client):
    """Row R-321: escape detected from facts; alert plus block at seam.

    0C names agent_si.toolguard.escape.check_escape (other package, no
    in-repo implementation); this lane owns the refusal seam, proven
    here: a refusing guard hook blocks launch, and escaping run ids
    never resolve inside the temp base.
    """
    pending = _runner.create_pending(AUTO_PROJ, template_id="tpl-nightly")
    _launcher.set_guard_hook(lambda project_id, path: False)
    try:
        with pytest.raises(auto_iface.AutomationError) as excinfo:
            _launcher.launch(AUTO_PROJ, pending.run_id)
        assert excinfo.value.code == "AUTOMATION_PAUSED"
    finally:
        _launcher.set_guard_hook(None)
    with tempfile.TemporaryDirectory(prefix="r7-321-") as base:
        with pytest.raises(ValueError):
            _cleanup.run_dir_for(base, "..")
        with pytest.raises(ValueError):
            _cleanup.run_dir_for(base, "run/x")


def test_row_322_supervised_restart_journaled(client):
    """Row R-322: watcher untouchable; supervised restart journaled."""
    receipt = _engine.supervised_restart(W_PROJ, "sup-r7-322")
    assert receipt.accepted is True
    assert receipt.journal_entry_id != ""
    rows = _journal.stored_rows(W_PROJ, "SERVICE_STATE")
    assert any("supervised restart by sup-r7-322" in row.summary
               for row in rows)
    with pytest.raises(WatcherError) as excinfo:
        _engine.supervised_restart(W_PROJ, "")
    assert excinfo.value.code == "STOP_REASON_MISSING"


def test_row_323_stop_all_user_grant_journaled(client):
    """Row R-323: one-click Stop all, user-only or expiring grant."""
    from agent_si.backend import stop_all as _stop_all

    user = _authed(client, "POST", "/api/v1/stop-all",
                   {"actor": "user", "project_id": W_PROJ})
    assert user.status_code == 200
    assert user.json()["accepted"] is True
    rows = _journal.stored_rows(W_PROJ, "STOP_ALL")
    assert any("stop-all by user" in row.summary for row in rows)
    missing = _authed(client, "POST", "/api/v1/stop-all",
                      {"actor": "director", "project_id": W_PROJ})
    assert missing.status_code == 400
    assert missing.json()["detail"]["code"] == "STOP_REASON_MISSING"
    live = _stop_all.issue_grant("grant-r7-323", ttl_s=600.0)
    director = _authed(client, "POST", "/api/v1/stop-all",
                       {"actor": "director", "project_id": W_PROJ,
                        "grant_ref": live})
    assert director.json()["accepted"] is True
    refused = _authed(client, "POST", "/api/v1/stop-all",
                      {"actor": "agent-x", "project_id": W_PROJ,
                       "grant_ref": live})
    assert refused.json()["accepted"] is False
    expired = _stop_all.issue_grant("grant-r7-old", ttl_s=-1.0)
    gone = _authed(client, "POST", "/api/v1/stop-all",
                   {"actor": "director", "project_id": W_PROJ,
                    "grant_ref": expired})
    assert gone.json()["accepted"] is False
    assert "expired" in gone.json()["reason"]


def _endless_proc():
    """One safe endless child command for stop tests (portable)."""
    return subprocess.Popen(
        [sys.executable, "-c", "import time\nwhile True: time.sleep(0.05)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def test_row_324_alerts_never_stops_agents(client):
    """Row R-324: watcher alerts, never stops agents itself."""
    proc = _endless_proc()
    try:
        receipt = _engine.supervised_restart(W_PROJ, "sup-r7-324")
        assert receipt.accepted is True
        assert proc.poll() is None
        tick = _engine.tick(W_PROJ)
        assert tick.fired != ()
        # Idle tick: normal verdicts journal nothing (no row, no call).
        assert _journal.stored_rows(W_PROJ, "WATCH_DECISION") == ()
        _journal.append_event(
            W_PROJ, "agent-x", "TAMPER_ATTEMPT", "entry probe",
            ("ref-r7-324",))
        fired = _engine.tick(W_PROJ)
        assert fired.fired != ()
        alerts = _journal.stored_rows(W_PROJ, "WATCH_DECISION")
        assert len(alerts) == 1
        assert "rule-tamper" in alerts[0].summary
        assert alerts[0].refs == ("rule-tamper",)
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_row_325_local_ai_script_params(client):
    """Row R-325: local AI picks script plus params per rule."""
    card = _rules.describe("rule-tamper")
    assert card.model == "local"
    action = _engine.resolve_action(W_PROJ, "rule-tamper")
    assert action.script == "scripts/tamper_check.py"
    assert action.params == ("--model", "local", "--hang-minutes", "20")
    decision = _engine.decide(
        W_PROJ, "rule-tamper", action.script, action.params)
    assert decision.rule_id == "rule-tamper"
    assert _engine.last_choice(W_PROJ) == (
        "rule-tamper", action.script, action.params)


def test_row_326_hierarchy_stop(client):
    """Row R-326: stop on a running hierarchy stops everything."""
    from agent_si.backend import stop_all as _stop_all

    owned = [_endless_proc(), _endless_proc()]
    try:
        run = _runner.start_run(AUTO_PROJ, "tpl-nightly")
        _runner.begin_turn(AUTO_PROJ, run.run_id)
        for proc in owned:
            _stop_all.attach_child(W_PROJ, run.run_id, proc)
        receipt = _stop_all.request_stop("user", W_PROJ)
        assert receipt.accepted is True
        assert all(proc.poll() is not None for proc in owned)
        stopped = _runner.cancel_run(AUTO_PROJ, run.run_id, "r7-326")
        assert stopped.state == "CANCELLED"
        assert _stop_all.attached(W_PROJ) == ()
    finally:
        for proc in owned:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=10)


def test_row_327_cleanup_script_cli(client):
    """Row R-327: run temp files removed by the standard cleanup script."""
    with tempfile.TemporaryDirectory(prefix="r7-327-") as base:
        run = _runner.start_run(AUTO_PROJ, "tpl-nightly")
        run_dir = _cleanup.run_dir_for(base, run.run_id)
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        (Path(run_dir) / "a.tmp").write_bytes(b"a")
        nested = Path(run_dir) / "nested"
        nested.mkdir()
        (nested / "b.tmp").write_bytes(b"b")
        assert _cleanup.main(["--base", base, "--run", run.run_id]) == 0
        assert list(Path(run_dir).iterdir()) == []
        again = _cleanup.main(["--base", base, "--run", run.run_id])
        assert again == 0
        assert _cleanup.main(["--base", base]) == 2
        _runner.set_run_temp_base(base)
        try:
            (Path(run_dir) / "c.tmp").write_bytes(b"c")
            _runner.set_journal_hook(_journal.append_event)
            try:
                receipt = _runner.cleanup_run_temp(AUTO_PROJ, run.run_id)
            finally:
                _runner.set_journal_hook(None)
            assert receipt["removed"] == ["c.tmp"]
        finally:
            _runner.set_run_temp_base(None)


def test_row_335_timers_launchers_metrics(client):
    """Row R-335: timers, auto-launchers, metric actions, recorded."""
    _runner.register_template("tpl-r7-335", AUTO_PROJ, "r7-335")
    _sched.register_launcher("lx-r7-335", AUTO_PROJ, "tpl-r7-335")
    _sched.register_timer("tm-r7-335", AUTO_PROJ, 60.0,
                          launcher_id="lx-r7-335", first_due=0.0)
    fired = _sched.tick_due(now=10.0)
    assert len(fired) == 1
    assert fired[0].state == "RUNNING"
    outcomes = [entry["outcome"] for entry in _sched.ledger()]
    assert "timer-fired" in outcomes
    _sched.register_timer("tm-r7-skip", AUTO_PROJ, 60.0,
                          launcher_id="lx-r7-335", catchup="skip",
                          first_due=0.0)
    assert _sched.fire_timer("tm-r7-skip", now=600.0) is None
    assert _sched.ledger()[-1]["outcome"] == "catchup-skip"
    _sched.register_metric("mm-r7-335", AUTO_PROJ, 5.0, action="notify")
    assert _sched.evaluate_metric("mm-r7-335", 1.0) is None
    assert _sched.evaluate_metric("mm-r7-335", 9.0).state == "RUNNING"
    assert _sched.ledger()[-1]["outcome"] == "metric-fired"
    _pause.set_project(AUTO_PROJ, True)
    try:
        with pytest.raises(auto_iface.AutomationError) as excinfo:
            _sched.fire_launcher("lx-r7-335", now=20.0)
        assert excinfo.value.code == "AUTOMATION_PAUSED"
    finally:
        _pause.set_project(AUTO_PROJ, False)


def test_row_336_local_default_cloud_off(client, monkeypatch):
    """Row R-336: local AI default, cloud fallback, off, per project."""
    assert _rules.MODELS == ("local", "API", "OFF")
    assert _rules.describe("rule-guard").model == "local"
    monkeypatch.setitem(
        _rules.RULES, "rule-r7-api",
        _rules.RuleCard("rule-r7-api", "guard", "API", 20))
    monkeypatch.setitem(
        _rules.RULES, "rule-r7-off",
        _rules.RuleCard("rule-r7-off", "guard", "OFF", 20))
    api_action = _engine.resolve_action(W_PROJ, "rule-r7-api")
    assert api_action.params == ("--model", "API", "--hang-minutes", "20")
    off_action = _engine.resolve_action(W_PROJ, "rule-r7-off")
    assert off_action.params == ("--model", "OFF", "--hang-minutes", "20")
    assert _presets.apply("proj-r7-336a", "strict") == (
        "card-hang", "card-guard", "card-tamper")
    assert _presets.apply("proj-r7-336b", "cautious") == ("card-hang",)
    assert _presets.installed_cards(
        "proj-r7-336a") != _presets.installed_cards("proj-r7-336b")


def test_row_337_usage_leak_protected(client):
    """Row R-337: usage fields, leak scan, protected refused."""
    response = _authed(client, "GET", "/api/v1/services/svc-api/status")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "UP"
    assert body["in_use"] is True
    assert body["last_used"] != ""
    assert body["last_agent"] == "agent-1"
    report = _services.scan_container("svc-container")
    assert report.verdict == "CLEAN"
    assert report.checked > 0
    assert report.findings == 0
    assert report.locations == ()
    with pytest.raises(auto_iface.AutomationError) as excinfo:
        _services.run_check("svc-vault", "HTTP")
    assert excinfo.value.code == "SERVICE_CHECK_REFUSED"
    rows = _journal.stored_rows("proj-b", "SERVICE_STATE")
    assert any("check refused" in row.summary for row in rows)


def test_row_364_rule_cards_presets_standard(client):
    """Row R-364: rule cards, presets, own area, model, 20-min hang."""
    tamper = _rules.describe("rule-tamper")
    assert (tamper.area, tamper.model, tamper.hang_minutes) == (
        "tamper", "local", 20)
    assert _rules.HANG_DEFAULT_MINUTES == 20
    assert _presets.TABLE["standard"] == ("card-hang", "card-guard")
    assert _presets.apply(W_PROJ, "strict") == (
        "card-hang", "card-guard", "card-tamper")
    with pytest.raises(WatcherError) as excinfo:
        _rules.describe("rule-missing")
    assert excinfo.value.code == "RULE_NOT_FOUND"
    status = _authed(client, "GET", "/api/v1/watcher/status",
                     {"project_id": W_PROJ})
    assert status.status_code == 200
    assert status.json()["project_id"] == W_PROJ


def test_row_366_declared_services_outage_linkage(client):
    """Row R-366: check types, UP/DOWN/DEGRADED, observe, usage, link."""
    _services.declare_service(
        "svc-r7-366", kind="tcp", host="127.0.0.1", tcp_port=9,
        project_id=W_PROJ)
    fresh = _services.get("svc-r7-366")
    assert fresh.state == "DOWN"
    observed = _services.run_check("svc-r7-366", "TCP")
    assert observed.state in ("UP", "DOWN", "DEGRADED")
    assert observed.timestamp != ""
    linked = _outage.link_observation_to_outage(
        W_PROJ, "svc-r7-366", "HIGH", "drill-366")
    assert linked.stopped is False
    assert linked.journal_entry_id != ""
    link_rows = _journal.stored_rows(W_PROJ, "OUTAGE_SIGNAL")
    assert any(linked.report_id in row.refs for row in link_rows)
    with pytest.raises(auto_iface.AutomationError) as excinfo:
        _outage.link_observation_to_outage(
            AUTO_PROJ, "svc-api", "HIGH", "no outage")
    assert excinfo.value.code == "SERVICE_CHECK_REFUSED"


def test_row_mp2_68_provider_outage_telemetry_audits(client):
    """Row M-P2-68: helper-provider outage, telemetry, small free audit."""
    response = _authed(client, "POST", "/api/v1/outage/signal", {
        "project_id": "proj-b", "service_id": "svc-cache",
        "severity": "CRITICAL", "summary": "provider down mp2-68"})
    assert response.status_code == 200
    body = response.json()
    assert body["severity"] == "CRITICAL"
    assert body["stopped"] is True
    telemetry = _journal.stored_rows("proj-b", "OUTAGE_SIGNAL")
    assert any(body["report_id"] in row.refs for row in telemetry)
    audit = _services.scan_container("svc-container")
    assert audit.verdict == "CLEAN"
    for location in audit.locations:
        assert "=" not in location
        assert "secretref:" not in location
    first = _services.observe_budget("svc-cache")
    assert _services.observe_budget("svc-cache") == first
    state = _services.run_check("svc-cache", "HTTP")
    assert state.timestamp != ""
    assert any("svc-cache" in row.refs
               for row in _journal.stored_rows("proj-b", "SERVICE_STATE"))


def test_row_mp3_94_catchup_survives_restart(client):
    """Row M-P3-94: missed fires skip or run once; survive restart."""
    _runner.register_template("tpl-r7-94", AUTO_PROJ, "r7-94")
    _sched.register_launcher("lx-r7-94", AUTO_PROJ, "tpl-r7-94")
    _sched.register_timer("tm-r7-once", AUTO_PROJ, 60.0,
                          launcher_id="lx-r7-94", catchup="once",
                          first_due=0.0)
    run = _sched.fire_timer("tm-r7-once", now=600.0)
    assert run is not None
    assert run.state == "RUNNING"
    assert _sched.ledger()[-1]["outcome"] == "catchup-once"
    with tempfile.TemporaryDirectory(prefix="r7-94-") as base:
        state_path = str(Path(base) / "sched.json")
        _sched.save_state(state_path)
        _sched.reset_state()
        _sched.load_state(state_path)
    _sched.register_launcher("lx-r7-94", AUTO_PROJ, "tpl-r7-94")
    timer = _sched.get_timer("tm-r7-once")
    assert timer["next_due"] == 660.0
    assert _sched.fire_timer("tm-r7-once", now=659.0) is None
    assert _sched.fire_timer("tm-r7-once", now=660.0) is not None


def test_row_mp3_112_builtin_or_import_only(client):
    """Row M-P3-112: no script builder; built-in or import only."""
    with pytest.raises(auto_iface.AutomationError) as excinfo:
        _templates.instantiate(AUTO_PROJ, "tpl-scripted")
    assert excinfo.value.code == "TEMPLATE_NOT_FOUND"
    plan = _templates.materialize(AUTO_PROJ, "tpl-nightly")
    assert plan["model"] == "meta/muse-spark-1.3-contributor"
    assert plan["project_id"] == AUTO_PROJ
    for step in plan["steps"]:
        assert step["action"] in _templates.ACTION_CATALOG
        assert step["outputs"] != []
    spec = {"name": "r7-import", "version": 1, "steps": [
        {"action": "service.check",
         "with": {"service_id": "svc-api"},
         "outputs": ["service_id", "state", "checked_at"]}]}
    assert _templates.import_template("tpl-r7-112", spec) == "tpl-r7-112"
    imported = _templates.instantiate(AUTO_PROJ, "tpl-r7-112")
    assert imported.template_id == "tpl-r7-112"
    bad = {"name": "bad", "version": 1, "steps": [
        {"action": "service.stop", "with": {}, "outputs": ["ok"]}]}
    with pytest.raises(ValueError):
        _templates.import_template("tpl-r7-bad", bad)
    response = _authed(client, "POST",
                       "/api/v1/automations/templates/tpl-nightly/instantiate",
                       {"project_id": AUTO_PROJ})
    assert response.status_code == 200
    assert response.json()["template_id"] == "tpl-nightly"


def test_row_b0b_sdk_94_cancel_modes(client):
    """Row B0B-SDK-94: immediate plus after-turn cancellation, immediate."""
    import inspect

    assert inspect.signature(_runner.cancel_run).parameters[
        "mode"].default == "immediate"
    run = _runner.start_run(AUTO_PROJ, "tpl-nightly")
    immediate = _runner.cancel_run(AUTO_PROJ, run.run_id, "r7-94a")
    assert immediate.state == "CANCELLED"
    other = _runner.start_run(AUTO_PROJ, "tpl-nightly")
    _runner.begin_turn(AUTO_PROJ, other.run_id)
    flagged = _runner.cancel_run(
        AUTO_PROJ, other.run_id, "r7-94b", mode="after-turn")
    assert flagged.state == "RUNNING"
    with pytest.raises(ValueError):
        _runner.cancel_run(AUTO_PROJ, other.run_id, mode="nope")
    _runner.complete_turn(AUTO_PROJ, other.run_id)


def test_row_b0b_sdk_95_immediate_stops_at_once(client):
    """Row B0B-SDK-95: immediate cancellation stops at once, run done."""
    run = _runner.start_run(AUTO_PROJ, "tpl-nightly")
    stopped = _runner.cancel_run(AUTO_PROJ, run.run_id, "r7-95")
    assert stopped.state == "CANCELLED"
    final = _runner.get_finalization(AUTO_PROJ, run.run_id)
    assert final == {"reason": "r7-95", "finalized": True}
    history = _runner.get_history(AUTO_PROJ, run.run_id)
    assert history[0]["event"] == "created"
    assert history[-1]["event"] == "cancelled:r7-95"


def test_row_b0b_sdk_96_turn_left_uncompleted(client):
    """Row B0B-SDK-96: immediate cancellation leaves the turn open."""
    run = _runner.start_run(AUTO_PROJ, "tpl-nightly")
    opened = _runner.begin_turn(AUTO_PROJ, run.run_id)
    stopped = _runner.cancel_run(AUTO_PROJ, run.run_id, "r7-96")
    assert stopped.state == "CANCELLED"
    events = [entry["event"]
              for entry in _runner.get_history(AUTO_PROJ, run.run_id)]
    assert "turn-started:%d" % opened["turn"] in events
    assert "turn-completed:%d" % opened["turn"] not in events


def test_row_b0b_sdk_99_after_turn_finishes(client):
    """Row B0B-SDK-99: after-turn cancellation waits for the turn."""
    run = _runner.start_run(AUTO_PROJ, "tpl-nightly")
    opened = _runner.begin_turn(AUTO_PROJ, run.run_id)
    flagged = _runner.cancel_run(
        AUTO_PROJ, run.run_id, "r7-99", mode="after-turn")
    assert flagged.state == "RUNNING"
    done = _runner.complete_turn(AUTO_PROJ, run.run_id)
    assert done["turn"] == opened["turn"]
    assert done["state"] == "CANCELLED"
    events = [entry["event"]
              for entry in _runner.get_history(AUTO_PROJ, run.run_id)]
    assert "turn-completed:%d" % opened["turn"] in events
    assert events[-1] == "cancelled:r7-99"


def test_row_q3_emergency_stop_windows(client):
    """Row Q3: Emergency Stop leaves 0 processes of the run; rest kept."""
    from agent_si.backend import stop_all as _stop_all

    owned = [_endless_proc(), _endless_proc()]
    owner = _endless_proc()
    try:
        run = _runner.start_run(AUTO_PROJ, "tpl-nightly")
        for proc in owned:
            _stop_all.attach_child(W_PROJ, run.run_id, proc)
        assert len(_stop_all.attached(W_PROJ)) == 2
        receipt = _stop_all.request_stop("user", W_PROJ)
        assert receipt.accepted is True
        assert all(proc.poll() is not None for proc in owned)
        assert owner.poll() is None
        rows = _journal.stored_rows(W_PROJ, "STOP_ALL")
        assert any("stop-all by user" in row.summary for row in rows)
        assert _stop_all.attached(W_PROJ) == ()
    finally:
        for proc in owned + [owner]:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=10)


def test_row_q8_standard_scripts_planted(client):
    """Row Q8: standard script set, each proven on a planted case."""
    from agent_si.watcher import engine as _script_engine

    assert _script_engine.STANDARD_SCRIPTS == (
        "restart-hung-agent-once",
        "signal-higher-level",
        "data-leak-scan",
        "workspace-check",
        "budget-watch",
        "temp-file-janitor",
        "dependent-service-watch",
    )
    with tempfile.TemporaryDirectory(prefix="r7-q8-") as base:
        run = _runner.start_run(AUTO_PROJ, "tpl-nightly")
        run_dir = _cleanup.run_dir_for(base, run.run_id)
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        (Path(run_dir) / "janitor.tmp").write_bytes(b"j")
        _services.declare_service(
            "svc-r7-q8", kind="tcp", host="127.0.0.1", tcp_port=9,
            project_id=W_PROJ)
        _journal.append_event(
            W_PROJ, "watcher", "TAMPER_ATTEMPT", "planted q8", ())
        cases = [
            ("restart-hung-agent-once", (), {"supervisor_ref": "sup-q8"}),
            ("signal-higher-level", (), {}),
            ("data-leak-scan", ("svc-container",), {}),
            ("workspace-check", (), {}),
            ("budget-watch", (), {}),
            ("temp-file-janitor", (run.run_id,),
             {"run_temp_base": base}),
            ("dependent-service-watch", (), {}),
        ]
        for script, params, kwargs in cases:
            result = _script_engine.run_script(
                W_PROJ, script, params, **kwargs)
            assert result.outcome not in ("", "FAILED"), script
            rows = _journal.stored_rows(W_PROJ, "SERVICE_STATE")
            assert any("script %s" % script in row.summary
                       for row in rows), script
        second = _script_engine.run_script(
            W_PROJ, "dependent-service-watch")
        assert second.outcome == "no-change"
        with pytest.raises(WatcherError) as excinfo:
            _script_engine.run_script(W_PROJ, "no-such-script")
        assert excinfo.value.code == "RULE_NOT_FOUND"
    assert _presets.apply("proj-r7-q8a", "strict") != _presets.apply(
        "proj-r7-q8b", "standard")
