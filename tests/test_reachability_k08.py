"""K08 reachability: every declared route is served by the seam app.

Reads HTTP_ROUTES + ROUTE_ENTRY_POINTS from BOTH interface modules at
run time (no hardcoded route list); builds create_app(test settings);
asserts every declared route reachable: GET -> 200, POST with a live
token via the x-ui-session-token header -> 200, POST without a token ->
401/403. Sample path ids and bodies are per-entry test data only; the
route list itself always comes from the declared modules.
"""

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

import agent_si.automation.interface as auto_iface
import agent_si.watcher.interface as watcher_iface
from agent_si.automation import pause as _auto_pause
from agent_si.automation import runner as _auto_runner
from agent_si.automation import triggers as _auto_triggers
from agent_si.backend.app import create_app
from agent_si.watcher import engine as _watcher_engine
from agent_si.watcher import integrity as _watcher_integrity
from agent_si.watcher import journal as _watcher_journal
from agent_si.watcher import presets as _watcher_presets
from agent_si.watcher import rules as _watcher_rules
from agent_si.watcher import status as _watcher_status
from fastapi.testclient import TestClient

LIVE_TOKEN = "k08-reach-live"
AUTO_PROJ = "proj-a"
WATCH_PROJ = "proj-reach-k08"


# FAKE-OF: backend auth-hook boundary (test settings only)
def _fake_auth_hook(token):
    """Boundary auth hook: only the live reachability token is accepted."""
    return token == LIVE_TOKEN


# FAKE-OF: backend rate-hook boundary (test settings only)
def _fake_rate_hook(key):
    """Boundary rate hook: reachability traffic is never throttled."""
    return True


# FAKE-OF: backend model_factory boundary (test settings only)
def _fake_model_factory(name):
    """Boundary model factory: no model calls in reachability tests."""
    raise auto_iface.AutomationError("TEMPLATE_NOT_FOUND")


def _reach_stop(project_id, reason):
    """Local stop-all default for runs without an in-repo stop lane."""
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


@pytest.fixture
def seam_client(monkeypatch):
    """Fresh seam app on reset lane state (deterministic 200s)."""
    _auto_pause.reset_state()
    _auto_runner.reset_state()
    _auto_triggers.reset_state()
    _watcher_journal.reset_state()
    _watcher_integrity.reset_state()
    _watcher_rules.reset_state()
    _watcher_engine.reset_state()
    _watcher_presets.reset_state()
    _watcher_status.reset_state()
    _auto_runner.register_template("tpl-nightly", AUTO_PROJ, "nightly")
    _auto_triggers.register_trigger(
        "trg-hourly", AUTO_PROJ, "TIMER", "hourly", True)
    _auto_runner.create_pending(AUTO_PROJ)
    _watcher_journal.append_event(
        WATCH_PROJ, "watcher", "SERVICE_STATE", "reach seed", ())
    # Cross-lane doubles the HTTP seam resolves late off the interface:
    # identical to the contract-suite bindings, restored after the test.
    monkeypatch.setattr(
        auto_iface, "journal_append_event", _watcher_journal.append_event)
    monkeypatch.setattr(
        auto_iface, "guard_check_escape", lambda project_id, path: True)
    monkeypatch.setattr(
        auto_iface, "stop_all_request_stop", _reach_stop)
    return TestClient(create_app(_seam_settings()))


#: Sample {id} path fill per frozen entry name (test data, not routes).
_ENTRY_PATH_ID = {
    "get_service_status": "svc-api",
    "run_service_check": "svc-api",
    "fire_trigger": "trg-hourly",
    "instantiate_template": "tpl-nightly",
    "launch": "run-0001",
    "resume": "run-0001",
    "evaluate_rule": "rule-tamper",
}


def _project_for(entry, method):
    """Owning project for one entry: seeded automation rows or fresh."""
    if method == "GET" and entry in ("get_status", "list_events"):
        return WATCH_PROJ
    if entry in ("verify_integrity", "evaluate_rule",
                 "stop_all_request_stop"):
        return WATCH_PROJ
    return AUTO_PROJ


def _body_for(entry, project):
    """POST body per frozen entry name (no token: it rides the header)."""
    if entry == "set_global_pause":
        return {"paused": False, "reason": ""}
    if entry == "run_service_check":
        return {"check": "HTTP"}
    if entry == "start_run":
        return {"project_id": project, "template_id": "tpl-nightly"}
    if entry in ("fire_trigger", "instantiate_template",
                 "launch", "resume"):
        return {"project_id": project}
    if entry == "signal_outage":
        return {"project_id": project, "service_id": "svc-api",
                "severity": "HIGH", "summary": "reach check"}
    if entry in ("verify_integrity", "evaluate_rule"):
        return {"project_id": project}
    if entry == "stop_all_request_stop":
        return {"actor": "user", "project_id": project}
    raise AssertionError("no POST body for entry %r" % (entry,))


def _declared_cases():
    """One case per declared route, resolved from the modules at run time."""
    cases = []
    for mod in (auto_iface, watcher_iface):
        routes = mod.HTTP_ROUTES
        entries = mod.ROUTE_ENTRY_POINTS
        assert set(entries) == {
            "%s %s" % (method, path) for method, path in routes
        }, mod.__name__
        for method, path in routes:
            key = "%s %s" % (method, path)
            entry = entries[key]
            assert callable(getattr(mod, entry, None)), key
            cases.append(pytest.param(method, path, entry, id=key))
    return cases


def _fill_path(path, entry):
    """Fill the {id} placeholder from the per-entry sample table."""
    if "{id}" not in path:
        return path
    assert entry in _ENTRY_PATH_ID, entry
    return path.replace("{id}", _ENTRY_PATH_ID[entry])


def test_every_declared_route_reachable(seam_client):
    """GET -> 200; POST with header token -> 200; POST bare -> 401/403."""
    for mod in (auto_iface, watcher_iface):
        for method, path in mod.HTTP_ROUTES:
            entry = mod.ROUTE_ENTRY_POINTS["%s %s" % (method, path)]
            url = _fill_path(path, entry)
            project = _project_for(entry, method)
            if method == "GET":
                response = seam_client.get(url, params={"project_id": project})
                assert response.status_code == 200, url
                continue
            body = _body_for(entry, project)
            live = seam_client.post(
                url, json=dict(body),
                headers={"x-ui-session-token": LIVE_TOKEN})
            assert live.status_code == 200, url
            refused = seam_client.post(url, json=dict(body))
            assert refused.status_code in (401, 403), url


@pytest.mark.parametrize(
    "method,path,entry", [p.values for p in _declared_cases()])
def test_declared_route_case(seam_client, method, path, entry):
    """Per-route case so a removed registration line turns one case RED."""
    url = _fill_path(path, entry)
    project = _project_for(entry, method)
    if method == "GET":
        response = seam_client.get(url, params={"project_id": project})
        assert response.status_code == 200
        return
    body = _body_for(entry, project)
    live = seam_client.post(
        url, json=dict(body), headers={"x-ui-session-token": LIVE_TOKEN})
    assert live.status_code == 200
    refused = seam_client.post(url, json=dict(body))
    assert refused.status_code in (401, 403)
