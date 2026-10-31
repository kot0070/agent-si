"""K08OPEN10 served pause plus disk-cleanup proof (testid k08open10-pause).

Lane K08OPEN10, author CODER-1 Ember. Row 174 (global plus per-project
pause; runs recorded under governance) and row R-320 (disk check plus
own-temp cleanup, journaled, own folders only). Every behaviour runs
through TestClient(create_app(settings)) plus HTTP on the real watcher
backend (real lane modules; test-file boundary hooks only, the same
convention as tests/test_k08r7_entries.py). Product files carry no
test doubles.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

from fastapi.testclient import TestClient

import agent_si.automation.interface as auto_iface
import agent_si.watcher.interface as watcher_iface
from agent_si.automation import cleanup as _cleanup
from agent_si.automation import launcher as _launcher
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

LIVE_TOKEN = "k08-open10-entry-live"
PROJ_A = "proj-open10-a"
PROJ_B = "proj-open10-b"
DISK_PROJ = "proj-open10-disk"


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
    _runner.register_template("tpl-open10-a", PROJ_A, "open10-a")
    _runner.register_template("tpl-open10-b", PROJ_B, "open10-b")
    _runner.register_template("tpl-open10-disk", DISK_PROJ, "open10-disk")
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
    _pause.reset_state()
    _runner.set_journal_hook(None)
    _runner.set_run_temp_base(None)


def _authed(client, method, url, body=None):
    """POST/GET with the live boundary token in the header."""
    headers = {"x-ui-session-token": LIVE_TOKEN}
    if method == "GET":
        return client.get(url, params=body or {}, headers=headers)
    return client.post(url, json=body or {}, headers=headers)


def test_row174_global_pause_served(client):
    """Row 174: global pause set via POST, effective via GET, runs refused."""
    assert _pause.is_effective(PROJ_A) is False
    paused = _authed(client, "POST", "/api/v1/automations/pause",
                     {"paused": True, "reason": "open10-global"})
    assert paused.status_code == 200
    for project_id in (PROJ_A, PROJ_B):
        effective = _authed(client, "GET", "/api/v1/automations/pause",
                            {"project_id": project_id})
        assert effective.status_code == 200
        assert effective.json() is True
    for project_id, template_id in (
            (PROJ_A, "tpl-open10-a"), (PROJ_B, "tpl-open10-b")):
        refused = _authed(client, "POST", "/api/v1/automations/runs",
                          {"project_id": project_id,
                           "template_id": template_id})
        assert refused.status_code == 409
        assert refused.json()["detail"]["code"] == "AUTOMATION_PAUSED"
    unpaused = _authed(client, "POST", "/api/v1/automations/pause",
                       {"paused": False, "reason": ""})
    assert unpaused.status_code == 200
    _runner.set_journal_hook(_journal.append_event)
    try:
        started = _authed(client, "POST", "/api/v1/automations/runs",
                          {"project_id": PROJ_A,
                           "template_id": "tpl-open10-a"})
    finally:
        _runner.set_journal_hook(None)
    assert started.status_code == 200
    assert started.json()["state"] == "RUNNING"
    rows = _journal.stored_rows(PROJ_A, "AUTOMATION_RUN")
    assert any("run started" in row.summary for row in rows)


def test_row174_project_pause_scoped_served(client):
    """Row 174: per-project pause effective for that project only."""
    _pause.set_project(PROJ_A, True)
    try:
        scoped = _authed(client, "GET", "/api/v1/automations/pause",
                         {"project_id": PROJ_A})
        assert scoped.status_code == 200
        assert scoped.json() is True
        other = _authed(client, "GET", "/api/v1/automations/pause",
                        {"project_id": PROJ_B})
        assert other.status_code == 200
        assert other.json() is False
        refused = _authed(client, "POST", "/api/v1/automations/runs",
                          {"project_id": PROJ_A,
                           "template_id": "tpl-open10-a"})
        assert refused.status_code == 409
        assert refused.json()["detail"]["code"] == "AUTOMATION_PAUSED"
        allowed = _authed(client, "POST", "/api/v1/automations/runs",
                          {"project_id": PROJ_B,
                           "template_id": "tpl-open10-b"})
        assert allowed.status_code == 200
        assert allowed.json()["state"] == "RUNNING"
    finally:
        _pause.set_project(PROJ_A, False)
    cleared = _authed(client, "GET", "/api/v1/automations/pause",
                      {"project_id": PROJ_A})
    assert cleared.json() is False


def test_row320_disk_check_journaled_served(client):
    """Row R-320: disk check journaled with ok/free/total on the seam."""
    assert client is not None
    with tempfile.TemporaryDirectory(prefix="open10-320-") as base:
        _runner.set_run_temp_base(base)
        _runner.set_journal_hook(_journal.append_event)
        try:
            disk = _runner.disk_check_runs(DISK_PROJ)
        finally:
            _runner.set_journal_hook(None)
            _runner.set_run_temp_base(None)
    assert disk["ok"] is True
    assert disk["free"] > 0
    assert disk["total"] >= disk["free"]
    rows = _journal.stored_rows(DISK_PROJ, "AUTOMATION_RUN")
    assert any("run temp disk" in row.summary for row in rows)


def test_row320_own_temp_cleanup_served(client):
    """Row R-320: one run's own temp cleaned, journaled, dir left empty."""
    with tempfile.TemporaryDirectory(prefix="open10-320-") as base:
        _runner.set_run_temp_base(base)
        try:
            started = _authed(client, "POST", "/api/v1/automations/runs",
                              {"project_id": DISK_PROJ,
                               "template_id": "tpl-open10-disk"})
            assert started.status_code == 200
            run_id = started.json()["run_id"]
            run_dir = _cleanup.run_dir_for(base, run_id)
            Path(run_dir).mkdir(parents=True, exist_ok=True)
            (Path(run_dir) / "scratch.bin").write_bytes(b"x" * 16)
            _runner.set_journal_hook(_journal.append_event)
            try:
                receipt = _runner.cleanup_run_temp(DISK_PROJ, run_id)
            finally:
                _runner.set_journal_hook(None)
            assert receipt["removed"] == ["scratch.bin"]
            assert list(Path(run_dir).iterdir()) == []
        finally:
            _runner.set_run_temp_base(None)
    notes = _journal.stored_rows(DISK_PROJ, "AUTOMATION_RUN")
    assert any("run temp cleaned" in row.summary for row in notes)


def test_row320_escaping_run_ids_refused(client):
    """Row R-320: escaping run ids refused; nothing outside the base moved."""
    assert client is not None
    with tempfile.TemporaryDirectory(prefix="open10-320-") as tmp:
        base = os.path.join(tmp, "base")
        os.makedirs(base, exist_ok=True)
        outside = os.path.join(tmp, "outside.txt")
        keeper = os.path.join(base, "keeper.txt")
        with open(outside, "w", encoding="utf-8") as handle:
            handle.write("keep-outside")
        with open(keeper, "w", encoding="utf-8") as handle:
            handle.write("keep-inside")
        bad_ids = [
            "..",
            os.path.abspath(tmp),
            "sub/dir",
            "sub\\dir",
        ]
        _runner.set_run_temp_base(base)
        try:
            for bad in bad_ids:
                with pytest.raises(ValueError):
                    _cleanup.run_dir_for(base, bad)
                with pytest.raises(ValueError):
                    _runner.cleanup_run_temp(DISK_PROJ, bad)
        finally:
            _runner.set_run_temp_base(None)
        with open(outside, encoding="utf-8") as handle:
            assert handle.read() == "keep-outside"
        with open(keeper, encoding="utf-8") as handle:
            assert handle.read() == "keep-inside"
        assert sorted(os.listdir(base)) == ["keeper.txt"]

def test_row174_pause_decisions_journaled_served(client):
    """Row 174: pause set/clear decisions journaled; scope effective served."""
    _pause.set_journal_hook(_journal.append_event)
    try:
        global_set = _authed(client, "POST", "/api/v1/automations/pause",
                             {"paused": True, "reason": "open10-gov"})
        assert global_set.status_code == 200
        _pause.set_project(PROJ_A, True)
        effective = _authed(client, "GET", "/api/v1/automations/pause",
                            {"project_id": PROJ_A})
        assert effective.status_code == 200
        assert effective.json() is True
        refused = _authed(client, "POST", "/api/v1/automations/runs",
                          {"project_id": PROJ_A,
                           "template_id": "tpl-open10-a"})
        assert refused.status_code == 409
        assert refused.json()["detail"]["code"] == "AUTOMATION_PAUSED"
        _pause.set_project(PROJ_A, False)
    finally:
        _authed(client, "POST", "/api/v1/automations/pause",
                {"paused": False, "reason": ""})
        _pause.set_journal_hook(None)
    scoped = _journal.stored_rows(PROJ_A, "AUTOMATION_RUN")
    assert any("project pause set" in row.summary for row in scoped)
    assert any("project pause cleared" in row.summary for row in scoped)
    system_rows = _journal.stored_rows("", "AUTOMATION_RUN")
    assert any("global pause set" in row.summary for row in system_rows)
    assert any("global pause cleared" in row.summary for row in system_rows)
