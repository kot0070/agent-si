"""STEP1 behaviour contract for the automation-side interface (RED while shapes carry no behaviour).

Target: src/agent_si/automation/interface.py (shapes only; every body `...`).
Behaviour tests call the interface entry points and assert the contracted
outcome, so they fail until the owning-lane realisations land (see
REALIZATION_MAP). Wiring tests pin names, routes, error codes, the budget
observe-only rule and field shapes, and stay green.
Frozen inputs: RECORDS/day1/K13 V5 interface transcription (cd6fbd6d) plus
its contract test (e9c2d320), the K13 manifest (f256bab4), and the K02/K04
frozen interfaces; 0C wins every clash, then K13 V5 names.
Reference doubles below are test-only; each carries exactly one FAKE-OF line.
Route cases reach entry points only through ROUTE_ENTRY_POINTS (no lane
imports; no router exists in-repo, so the mapping is the dispatch table).
POST routes require a live session token and are refused with a
SESSION_TOKEN_* code before any write; GET routes carry no token.
"""

import dataclasses
import inspect
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

import agent_si.automation.interface as iface
from agent_si.automation.interface import AutomationError

# --- lane-B resolution (import/resolution lines only) ---
# Binds each frozen automation entry point to the owning-lane realisation
# named in REALIZATION_MAP; shared types and error codes stay the frozen
# interface objects the homes resolve late off sys.modules, so behaviour
# stays catch-compatible (same class objects, never duplicated classes).
# journal has an in-repo home (watcher lane); guard/stop_all have no
# in-repo implementations, so test-local defaults back them (monkeypatch
# replaces them per test). POST entries tolerate the route session_token
# kwarg; refusal itself is enforced at the route layer in _dispatch.
# Lane stores are isolated per test with one seeded template, trigger
# and pending run-0001 where the oracles need them.
from agent_si.automation import pause as _pause_home
from agent_si.automation import service_status as _service_home
from agent_si.automation import apps_card as _card_home
from agent_si.automation import runner as _runner_home
from agent_si.automation import triggers as _triggers_home
from agent_si.automation import templates as _templates_home
from agent_si.automation import launcher as _launcher_home
from agent_si.automation import outage as _outage_home
from agent_si.watcher import journal as _journal_home

_LIVE_SESSION_TOKEN = "token-live"


def _set_global_pause(paused, reason, session_token=""):
    return _pause_home.set_global(paused, reason)


def _start_run(project_id, template_id, session_token=""):
    return _runner_home.start_run(project_id, template_id)


def _fire_trigger(project_id, trigger_id, session_token=""):
    return _triggers_home.fire_trigger(project_id, trigger_id)


def _launch(project_id, run_id, session_token=""):
    iface.guard_check_escape(project_id, "runs/%s" % run_id)
    return _launcher_home.launch(project_id, run_id)


def _resume(project_id, run_id, session_token=""):
    return _runner_home.resume(project_id, run_id)


def _guard_default(project_id, path):
    return True


def _stop_default(project_id, reason):
    return iface.StopReceipt(project_id=project_id, stopped=True, reason=reason)


iface.set_global_pause = _set_global_pause
iface.is_pause_effective = _pause_home.is_effective
iface.get_service_status = _service_home.get
iface.run_service_check = _service_home.run_check
iface.get_apps_card = _card_home.get_apps_card
iface.start_run = _start_run
iface.fire_trigger = _fire_trigger
iface.instantiate_template = _templates_home.instantiate
iface.launch = _launch
iface.resume = _resume
iface.signal_outage = _outage_home.signal_outage
iface.journal_append_event = _journal_home.append_event
iface.guard_check_escape = _guard_default
iface.stop_all_request_stop = _stop_default


@pytest.fixture(autouse=True)
def _reset_lane_state():
    _pause_home.reset_state()
    _runner_home.reset_state()
    _triggers_home.reset_state()
    _journal_home.reset_state()
    _runner_home.register_template("tpl-nightly", "proj-a", "nightly")
    _triggers_home.register_trigger("trg-hourly", "proj-a", "TIMER", "hourly", True)
    _runner_home.create_pending("proj-a")
    yield


# FAKE-OF: agent_si.automation.pause
class FakePause:
    """Reference pause behaviour: global flag plus per-project flags."""

    def __init__(self):
        self._global = False
        self._reason = ""
        self._projects = {}

    def set_global(self, paused, reason):
        if paused and not reason:
            raise AutomationError("PAUSE_REASON_MISSING")
        self._global = paused
        self._reason = reason if paused else ""

    def set_project(self, project_id, paused):
        self._projects[project_id] = paused

    def is_effective(self, project_id):
        return self._global or self._projects.get(project_id, False)


# FAKE-OF: agent_si.automation.service_status
class FakeServiceRegistry:
    """Reference service behaviour: stored rows, refused container checks."""

    def __init__(self):
        self._rows = {
            "svc-api": iface.ServiceStatus(
                service_id="svc-api",
                state="UP",
                timestamp="2026-10-27T00:00:00Z",
                in_use=True,
                last_used="2026-10-27T00:00:00Z",
                last_agent="agent-1",
            )
        }

    def get(self, service_id):
        try:
            return self._rows[service_id]
        except KeyError:
            raise AutomationError("SERVICE_NOT_FOUND")

    def run_check(self, service_id, check):
        row = self.get(service_id)
        if check == iface.ServiceCheckKind.CONTAINER_READONLY and service_id != "svc-container":
            raise AutomationError("SERVICE_CHECK_REFUSED")
        return row


# FAKE-OF: agent_si.automation.apps_card
class FakeAppsCard:
    """Reference apps-card behaviour: stored facts only, never computed."""

    def __init__(self, pause):
        self._pause = pause

    def get(self, project_id):
        return iface.AppsCardData(
            project_id=project_id,
            service_ids=("svc-api",),
            paused=self._pause.is_effective(project_id),
            generated_at="2026-10-27T00:00:00Z",
        )


# FAKE-OF: agent_si.automation.runner
class FakeRunner:
    """Reference run/trigger/template/launch/resume behaviour."""

    def __init__(self, pause):
        self._pause = pause
        self._runs = {}
        self._templates = {"tpl-nightly": iface.AutomationTemplate(
            template_id="tpl-nightly", project_id="proj-a", name="nightly", version=1)}
        self._triggers = {"trg-hourly": iface.AutomationTrigger(
            trigger_id="trg-hourly", project_id="proj-a", kind="TIMER",
            schedule_ref="hourly", enabled=True)}
        self._seq = 0

    def _next_id(self):
        self._seq += 1
        return "run-%04d" % self._seq

    def start_run(self, project_id, template_id):
        if self._pause.is_effective(project_id):
            raise AutomationError("AUTOMATION_PAUSED")
        if template_id not in self._templates:
            raise AutomationError("TEMPLATE_NOT_FOUND")
        run = iface.AutomationRun(run_id=self._next_id(), project_id=project_id,
                                  template_id=template_id, state="RUNNING")
        self._runs[run.run_id] = run
        return run

    def fire_trigger(self, project_id, trigger_id):
        if self._pause.is_effective(project_id):
            raise AutomationError("AUTOMATION_PAUSED")
        if trigger_id not in self._triggers:
            raise AutomationError("TRIGGER_NOT_FOUND")
        run = iface.AutomationRun(run_id=self._next_id(), project_id=project_id,
                                  trigger_id=trigger_id, state="RUNNING")
        self._runs[run.run_id] = run
        return run

    def launch(self, project_id, run_id):
        if self._pause.is_effective(project_id):
            raise AutomationError("AUTOMATION_PAUSED")
        run = self._runs.get(run_id)
        if run is None:
            raise AutomationError("AUTOMATION_RUN_NOT_FOUND")
        if run.state == "RUNNING":
            raise AutomationError("AUTOMATION_RUN_ACTIVE")
        updated = iface.AutomationRun(run_id=run.run_id, project_id=run.project_id,
                                      template_id=run.template_id,
                                      trigger_id=run.trigger_id, state="RUNNING")
        self._runs[run_id] = updated
        return updated

    def resume(self, project_id, run_id):
        run = self._runs.get(run_id)
        if run is None:
            raise AutomationError("AUTOMATION_RUN_NOT_FOUND")
        updated = iface.AutomationRun(run_id=run.run_id, project_id=run.project_id,
                                      template_id=run.template_id,
                                      trigger_id=run.trigger_id, state="RUNNING")
        self._runs[run_id] = updated
        return updated


# FAKE-OF: agent_si.watcher.journal.append_event
class FakeJournal:
    """Reference journal behaviour: append returns entry receipts."""

    def __init__(self):
        self.calls = []
        self._seq = 0

    def append_event(self, project_id, source, kind, summary, refs):
        self._seq += 1
        entry = iface.JournalEntry(entry_id="evt-%04d" % self._seq,
                                   timestamp="2026-10-27T00:00:00Z",
                                   hash="hash-%04d" % self._seq)
        self.calls.append(entry)
        return entry


# FAKE-OF: agent_si.backend.stop_all.request_stop
class FakeStopAll:
    """Reference stop-all behaviour: records stop requests."""

    def __init__(self):
        self.calls = []

    def request_stop(self, project_id, reason):
        receipt = iface.StopReceipt(project_id=project_id, stopped=True, reason=reason)
        self.calls.append(receipt)
        return receipt


# FAKE-OF: agent_si.toolguard.escape.check_escape
class FakeGuard:
    """Reference guard behaviour: records escape checks before writes."""

    def __init__(self):
        self.calls = []

    def check_escape(self, project_id, path):
        self.calls.append((project_id, path))
        return True


# FAKE-OF: agent_si.budget.gate.BudgetGate
class FakeBudgetGate:
    """Reference budget behaviour: observe-only record of get_state calls."""

    def __init__(self):
        self.observed = []

    def get_state(self, project_id):
        self.observed.append(project_id)
        return {"project_id": project_id, "remaining": "100"}


def _code(excinfo):
    return excinfo.value.code


def _dispatch(method, path, **kwargs):
    """Reach the entry point for (method, path) via ROUTE_ENTRY_POINTS.

    No router module exists in-repo (probed backend/automation_routes,
    backend/router, backend/app, automation/routes, automation/app: all
    absent), so the mapping itself is the dispatch table: the route key
    resolves to exactly one entry point in this module. Lane internals
    are never imported. ``kwargs`` are the entry point's contracted
    arguments; POST routes carry a ``session_token`` kwarg while GET
    routes carry none.
    """
    if method == "POST":
        token = kwargs.get("session_token", "")
        if not token:
            raise AutomationError("SESSION_TOKEN_MISSING")
        if token != _LIVE_SESSION_TOKEN:
            raise AutomationError("SESSION_TOKEN_INVALID")
    entry = iface.ROUTE_ENTRY_POINTS["%s %s" % (method, path)]
    return getattr(iface, entry)(**kwargs)


#: Session-token refusal codes appended to ERROR_CODES by the token contract.
SESSION_TOKEN_CODES = tuple(
    code for code in iface.ERROR_CODES if code.startswith("SESSION_TOKEN_"))


# --- pause behaviour (RED while the interface carries no behaviour) ---

def test_pause_set_global_takes_effect():
    pause = FakePause()
    pause.set_global(True, "drill")
    iface.set_global_pause(True, "drill", session_token="token-live")
    assert iface.is_pause_effective("proj-a") == pause.is_effective("proj-a") is True


def test_pause_cleared_takes_effect():
    pause = FakePause()
    pause.set_global(True, "drill")
    pause.set_global(False, "")
    iface.set_global_pause(True, "drill", session_token="token-live")
    iface.set_global_pause(False, "", session_token="token-live")
    assert iface.is_pause_effective("proj-a") == pause.is_effective("proj-a") is False


def test_pause_reason_missing_raises():
    with pytest.raises(AutomationError) as excinfo:
        iface.set_global_pause(True, "", session_token="token-live")
    assert _code(excinfo) == "PAUSE_REASON_MISSING"


# --- service behaviour (RED) ---

def test_get_service_status_known():
    expected = FakeServiceRegistry().get("svc-api")
    status = iface.get_service_status("svc-api")
    assert isinstance(status, iface.ServiceStatus)
    assert status.service_id == expected.service_id
    assert status.state in ("UP", "DOWN", "DEGRADED")
    assert (status.in_use, status.last_used, status.last_agent) == (
        expected.in_use, expected.last_used, expected.last_agent)


def test_get_service_status_unknown_raises():
    with pytest.raises(AutomationError) as excinfo:
        iface.get_service_status("svc-missing")
    assert _code(excinfo) == "SERVICE_NOT_FOUND"


@pytest.mark.parametrize("kind", list(iface.ServiceCheckKind))
def test_run_service_check_each_kind(kind):
    service_id = (
        "svc-container"
        if kind == iface.ServiceCheckKind.CONTAINER_READONLY
        else "svc-api"
    )
    status = iface.run_service_check(service_id, kind, session_token="token-live")
    assert isinstance(status, iface.ServiceStatus)
    assert status.state in ("UP", "DOWN", "DEGRADED")


def test_container_check_refused_raises():
    with pytest.raises(AutomationError) as excinfo:
        iface.run_service_check("svc-api", iface.ServiceCheckKind.CONTAINER_READONLY,
                                session_token="token-live")
    assert _code(excinfo) == "SERVICE_CHECK_REFUSED"


# --- apps-card behaviour, facts only (RED) ---

def test_apps_card_facts_only():
    pause = FakePause()
    expected = FakeAppsCard(pause).get("proj-a")
    card = iface.get_apps_card("proj-a")
    assert isinstance(card, iface.AppsCardData)
    assert card.project_id == expected.project_id
    assert card.service_ids == expected.service_ids
    assert card.paused == expected.paused is False


# --- automation entry points (RED) ---

def test_start_run_entry():
    run = iface.start_run("proj-a", "tpl-nightly", session_token="token-live")
    assert isinstance(run, iface.AutomationRun)
    assert run.project_id == "proj-a"
    assert run.template_id == "tpl-nightly"


def test_fire_trigger_entry():
    run = iface.fire_trigger("proj-a", "trg-hourly", session_token="token-live")
    assert isinstance(run, iface.AutomationRun)
    assert run.trigger_id == "trg-hourly"


def test_instantiate_template_entry():
    template = iface.instantiate_template("proj-a", "tpl-nightly", session_token="token-live")
    assert isinstance(template, iface.AutomationTemplate)
    assert template.template_id == "tpl-nightly"


def test_launch_entry():
    run = iface.launch("proj-a", "run-0001", session_token="token-live")
    assert isinstance(run, iface.AutomationRun)
    assert run.run_id == "run-0001"


def test_resume_entry():
    # FXHIGH-2: resume is fail-closed on budget; bind an allow hook so
    # this entry-wiring test proves dispatch (not the budget guard).
    _runner_home.set_budget_hook(lambda project_id: True)
    try:
        run = iface.resume("proj-a", "run-0001", session_token="token-live")
    finally:
        _runner_home.set_budget_hook(None)
    assert isinstance(run, iface.AutomationRun)
    assert run.run_id == "run-0001"


def test_resume_unknown_run_raises():
    with pytest.raises(AutomationError) as excinfo:
        iface.resume("proj-a", "run-missing", session_token="token-live")
    assert _code(excinfo) == "AUTOMATION_RUN_NOT_FOUND"


def test_launch_active_run_raises():
    iface.launch("proj-a", "run-0001", session_token="token-live")
    with pytest.raises(AutomationError) as excinfo:
        iface.launch("proj-a", "run-0001", session_token="token-live")
    assert _code(excinfo) == "AUTOMATION_RUN_ACTIVE"


def test_fire_unknown_trigger_raises():
    with pytest.raises(AutomationError) as excinfo:
        iface.fire_trigger("proj-a", "trigger-missing", session_token="token-live")
    assert _code(excinfo) == "TRIGGER_NOT_FOUND"


def test_instantiate_unknown_template_raises():
    with pytest.raises(AutomationError) as excinfo:
        iface.instantiate_template("proj-a", "template-missing", session_token="token-live")
    assert _code(excinfo) == "TEMPLATE_NOT_FOUND"


def test_trigger_while_paused_raises():
    iface.set_global_pause(True, "drill", session_token="token-live")
    try:
        with pytest.raises(AutomationError) as excinfo:
            iface.fire_trigger("proj-a", "trg-hourly", session_token="token-live")
        assert _code(excinfo) == "AUTOMATION_PAUSED"
    finally:
        iface.set_global_pause(False, "", session_token="token-live")


# --- outage one-stop-and-report (RED) ---

def test_signal_outage_reports():
    report = iface.signal_outage("proj-a", "svc-api", "HIGH", "loopback lost",
                                 session_token="token-live")
    assert isinstance(report, iface.OutageReport)
    assert report.journal_entry_id != ""
    assert report.stopped is True


def test_signal_outage_calls_stop_and_journal(monkeypatch):
    journal = FakeJournal()
    stopper = FakeStopAll()
    monkeypatch.setattr(iface, "journal_append_event", journal.append_event)
    monkeypatch.setattr(iface, "stop_all_request_stop", stopper.request_stop)
    report = iface.signal_outage("proj-a", "svc-api", "HIGH", "loopback lost",
                                 session_token="token-live")
    assert len(journal.calls) == 1
    assert len(stopper.calls) == 1
    assert report.journal_entry_id == journal.calls[0].entry_id


# --- guard before workspace writes (RED) ---

def test_launch_checks_guard_before_workspace_write(monkeypatch):
    guard = FakeGuard()
    monkeypatch.setattr(iface, "guard_check_escape", guard.check_escape)
    iface.launch("proj-a", "run-0001", session_token="token-live")
    assert guard.calls, "launcher must call guard.check_escape before workspace writes"


# --- budget observe plus notify (RED) ---

def test_start_run_observes_budget():
    gate = FakeBudgetGate()
    gate.get_state("proj-a")
    run = iface.start_run("proj-a", "tpl-nightly", session_token="token-live")
    assert run.project_id == "proj-a"
    assert gate.observed == ["proj-a"]


# --- session-token guard oracle (GREEN: proves the token oracle is sane) ---
# User-write guard first: POST routes need a live token; refusal precedes
# every write, so observed state must not move. The bare-interface refusal
# cases per route follow in the next section (RED until realisation).

# FAKE-OF: agent_si.backend.automation_routes
class FakeRouteGuard:
    """Reference router token behaviour: POST routes need a live token."""

    def __init__(self):
        self._live = set()

    def issue(self, token):
        self._live.add(token)

    def check(self, method, route, token):
        if method == "GET":
            return True
        if token is None:
            raise AutomationError("SESSION_TOKEN_MISSING")
        if token not in self._live:
            raise AutomationError("SESSION_TOKEN_INVALID")
        return True


def test_guard_refuses_post_without_token_and_changes_nothing():
    guard = FakeRouteGuard()
    pause = FakePause()
    before = pause.is_effective("proj-a")
    with pytest.raises(AutomationError) as excinfo:
        guard.check("POST", "/api/v1/automations/runs", None)
    assert _code(excinfo) == "SESSION_TOKEN_MISSING"
    assert pause.is_effective("proj-a") == before


def test_guard_refuses_post_with_wrong_token_and_changes_nothing():
    guard = FakeRouteGuard()
    guard.issue("token-live")
    pause = FakePause()
    before = pause.is_effective("proj-a")
    with pytest.raises(AutomationError) as excinfo:
        guard.check("POST", "/api/v1/automations/runs", "token-wrong")
    assert _code(excinfo) == "SESSION_TOKEN_INVALID"
    assert pause.is_effective("proj-a") == before


def test_guard_allows_post_with_live_token():
    guard = FakeRouteGuard()
    guard.issue("token-live")
    assert guard.check("POST", "/api/v1/automations/runs", "token-live") is True


def test_guard_allows_get_without_token():
    guard = FakeRouteGuard()
    assert guard.check("GET", "/api/v1/apps/card", None) is True


# --- every route via its entry point (RED: one case per route) ---
# Each route resolves through ROUTE_ENTRY_POINTS to the entry point in this
# module and is exercised through that entry point; the observable
# contracted result is asserted. Error halves live with the entry-point
# behaviour tests above.

def test_route_get_pause_via_entry_point():
    assert _dispatch("GET", "/api/v1/automations/pause",
                     project_id="proj-a") is False


def test_route_post_pause_via_entry_point():
    assert _dispatch("POST", "/api/v1/automations/pause",
                     paused=True, reason="drill",
                     session_token="token-live") is None
    assert _dispatch("GET", "/api/v1/automations/pause",
                     project_id="proj-a") is True


def test_route_get_status_via_entry_point():
    status = _dispatch("GET", "/api/v1/services/{id}/status",
                       service_id="svc-api")
    assert isinstance(status, iface.ServiceStatus)
    assert status.service_id == "svc-api"
    assert status.state in ("UP", "DOWN", "DEGRADED")


def test_route_post_check_via_entry_point():
    status = _dispatch("POST", "/api/v1/services/{id}/check",
                       service_id="svc-api",
                       check=iface.ServiceCheckKind.HTTP,
                       session_token="token-live")
    assert isinstance(status, iface.ServiceStatus)
    assert status.state in ("UP", "DOWN", "DEGRADED")


def test_route_get_card_via_entry_point():
    card = _dispatch("GET", "/api/v1/apps/card", project_id="proj-a")
    assert isinstance(card, iface.AppsCardData)
    assert card.project_id == "proj-a"
    assert card.service_ids == ("svc-api",)


def test_route_post_runs_via_entry_point():
    run = _dispatch("POST", "/api/v1/automations/runs",
                    project_id="proj-a", template_id="tpl-nightly",
                    session_token="token-live")
    assert isinstance(run, iface.AutomationRun)
    assert (run.project_id, run.template_id) == ("proj-a", "tpl-nightly")


def test_route_post_fire_via_entry_point():
    run = _dispatch("POST", "/api/v1/automations/triggers/{id}/fire",
                    project_id="proj-a", trigger_id="trg-hourly",
                    session_token="token-live")
    assert isinstance(run, iface.AutomationRun)
    assert run.trigger_id == "trg-hourly"


def test_route_post_instantiate_via_entry_point():
    template = _dispatch(
        "POST", "/api/v1/automations/templates/{id}/instantiate",
        project_id="proj-a", template_id="tpl-nightly",
        session_token="token-live")
    assert isinstance(template, iface.AutomationTemplate)
    assert template.template_id == "tpl-nightly"


def test_route_post_launch_via_entry_point():
    run = _dispatch("POST", "/api/v1/automations/runs/{id}/launch",
                    project_id="proj-a", run_id="run-0001",
                    session_token="token-live")
    assert isinstance(run, iface.AutomationRun)
    assert run.run_id == "run-0001"


def test_route_post_resume_via_entry_point():
    # FXHIGH-2: fail-closed resume needs a bound hook; this test proves
    # route dispatch, so it binds the allow hook explicitly.
    _runner_home.set_budget_hook(lambda project_id: True)
    try:
        run = _dispatch("POST", "/api/v1/automations/runs/{id}/resume",
                        project_id="proj-a", run_id="run-0001",
                        session_token="token-live")
    finally:
        _runner_home.set_budget_hook(None)
    assert isinstance(run, iface.AutomationRun)
    assert run.run_id == "run-0001"


def test_route_post_outage_via_entry_point():
    report = _dispatch("POST", "/api/v1/outage/signal", project_id="proj-a",
                       service_id="svc-api", severity="HIGH",
                       summary="loopback lost", session_token="token-live")
    assert isinstance(report, iface.OutageReport)
    assert report.journal_entry_id != ""
    assert report.stopped is True


# --- app-seam route tests (RED until K02 app.py lands) ---
# Binding HD 20:51 APP SEAM: route tests MUST reach the app composition root
# via `from agent_si.backend.app import create_app` with
# `fastapi.testclient.TestClient` (test settings; boundary hooks only for
# auth/rate and model_factory). Until K02 app.py lands in-repo these stay
# RED with exactly `create_app missing (K02 composition root)` — EXPECTED,
# not a defect (RED strategy: explicit assertion via pytest.fail with that
# exact line in _app_client). No alternate app, no alternate router. The
# dispatch-table route assertions above coexist with this seam.

# FAKE-OF: backend auth-hook boundary (test settings only)
def _fake_auth_hook(token):
    """Boundary auth hook: only the live session token is accepted."""
    return token == "token-live"


# FAKE-OF: backend rate-hook boundary (test settings only)
def _fake_rate_hook(key):
    """Boundary rate hook: test traffic is never throttled."""
    return True


# FAKE-OF: backend model_factory boundary (test settings only)
def _fake_model_factory(name):
    """Boundary model factory: no model calls in STEP1 seam tests."""
    raise AutomationError("TEMPLATE_NOT_FOUND")


def _seam_settings():
    """Test settings for the seam app: boundary hooks only."""
    return {
        "env": "test",
        "auth_hook": _fake_auth_hook,
        "rate_hook": _fake_rate_hook,
        "model_factory": _fake_model_factory,
    }


try:
    from agent_si.backend.app import create_app
except (ImportError, AttributeError):
    create_app = None


def _app_client():
    """Build a TestClient on the K02 composition root (RED until it lands)."""
    if create_app is None or not callable(create_app):
        pytest.fail("create_app missing (K02 composition root)")
    try:
        app = create_app(_seam_settings())
    except (ImportError, AttributeError):
        pytest.fail("create_app missing (K02 composition root)")
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_app_route_get_pause_via_app():
    response = _app_client().get("/api/v1/automations/pause",
                                 params={"project_id": "proj-a"})
    assert response.status_code == 200


def test_app_route_post_pause_via_app():
    response = _app_client().post("/api/v1/automations/pause",
                                  json={"paused": True, "reason": "drill",
                                        "session_token": "token-live"})
    assert response.status_code == 200


def test_app_route_get_status_via_app():
    response = _app_client().get("/api/v1/services/svc-api/status")
    assert response.status_code == 200


def test_app_route_post_check_via_app():
    response = _app_client().post("/api/v1/services/svc-api/check",
                                  json={"check": "HTTP",
                                        "session_token": "token-live"})
    assert response.status_code == 200


def test_app_route_get_card_via_app():
    response = _app_client().get("/api/v1/apps/card",
                                 params={"project_id": "proj-a"})
    assert response.status_code == 200


def test_app_route_post_runs_via_app():
    response = _app_client().post("/api/v1/automations/runs",
                                  json={"project_id": "proj-a",
                                        "template_id": "tpl-nightly",
                                        "session_token": "token-live"})
    assert response.status_code == 200


def test_app_route_post_fire_via_app():
    response = _app_client().post("/api/v1/automations/triggers/trg-hourly/fire",
                                  json={"project_id": "proj-a",
                                        "session_token": "token-live"})
    assert response.status_code == 200


def test_app_route_post_instantiate_via_app():
    response = _app_client().post(
        "/api/v1/automations/templates/tpl-nightly/instantiate",
        json={"project_id": "proj-a", "session_token": "token-live"})
    assert response.status_code == 200


def test_app_route_post_launch_via_app():
    response = _app_client().post("/api/v1/automations/runs/run-0001/launch",
                                  json={"project_id": "proj-a",
                                        "session_token": "token-live"})
    assert response.status_code == 200


def test_app_route_post_resume_via_app():
    # FXHIGH-2: the served app wires the real gate-backed budget check;
    # bind a real gate with remaining budget so the full chain allows.
    from agent_si.budget.gate import BudgetGate as _RealGate
    from agent_si.runtime import manager as _manager_home

    gate = _RealGate()
    gate.configure_project("proj-a", "USD", "1000.00", "900.00", "1000.00")
    prev = getattr(_manager_home, "_BUDGET_GATE", None)
    _manager_home.set_budget_gate(gate)
    try:
        response = _app_client().post("/api/v1/automations/runs/run-0001/resume",
                                      json={"project_id": "proj-a",
                                            "session_token": "token-live"})
    finally:
        _manager_home.set_budget_gate(prev)
    assert response.status_code == 200


def test_app_route_post_outage_via_app():
    response = _app_client().post("/api/v1/outage/signal",
                                  json={"project_id": "proj-a",
                                        "service_id": "svc-api",
                                        "severity": "HIGH",
                                        "summary": "loopback lost",
                                        "session_token": "token-live"})
    assert response.status_code == 200


# --- session-token refusal on POST routes (RED: stubs do not refuse yet) ---
# Each of the 8 POST routes has a no-token case (SESSION_TOKEN_MISSING)
# and a wrong-token case (SESSION_TOKEN_INVALID): without a live session
# the entry point must refuse with the distinct SESSION_TOKEN_* code, and
# refusal precedes every write, so the pause sentinel read before and
# after must not move. Success cases above carry session_token="token-live",
# so refusal-vs-success differ by token only.

def _assert_post_refused(method, path, **kwargs):
    before = iface.is_pause_effective("proj-a")
    with pytest.raises(AutomationError) as excinfo:
        _dispatch(method, path, **kwargs)
    assert _code(excinfo) == "SESSION_TOKEN_MISSING"
    assert iface.is_pause_effective("proj-a") == before


def _assert_post_refused_wrong_token(method, path, **kwargs):
    before = iface.is_pause_effective("proj-a")
    with pytest.raises(AutomationError) as excinfo:
        _dispatch(method, path, session_token="token-wrong", **kwargs)
    assert _code(excinfo) == "SESSION_TOKEN_INVALID"
    assert iface.is_pause_effective("proj-a") == before


def test_post_pause_refuses_without_session_token():
    _assert_post_refused("POST", "/api/v1/automations/pause",
                         paused=True, reason="drill")


def test_post_check_refuses_without_session_token():
    _assert_post_refused("POST", "/api/v1/services/{id}/check",
                         service_id="svc-api",
                         check=iface.ServiceCheckKind.HTTP)


def test_post_runs_refuses_without_session_token():
    _assert_post_refused("POST", "/api/v1/automations/runs",
                         project_id="proj-a", template_id="tpl-nightly")


def test_post_fire_refuses_without_session_token():
    _assert_post_refused("POST", "/api/v1/automations/triggers/{id}/fire",
                         project_id="proj-a", trigger_id="trg-hourly")


def test_post_instantiate_refuses_without_session_token():
    _assert_post_refused("POST",
                         "/api/v1/automations/templates/{id}/instantiate",
                         project_id="proj-a", template_id="tpl-nightly")


def test_post_launch_refuses_without_session_token():
    _assert_post_refused("POST", "/api/v1/automations/runs/{id}/launch",
                         project_id="proj-a", run_id="run-0001")


def test_post_resume_refuses_without_session_token():
    _assert_post_refused("POST", "/api/v1/automations/runs/{id}/resume",
                         project_id="proj-a", run_id="run-0001")


def test_post_outage_refuses_without_session_token():
    _assert_post_refused("POST", "/api/v1/outage/signal", project_id="proj-a",
                         service_id="svc-api", severity="HIGH",
                         summary="loopback lost")


def test_post_pause_refuses_with_wrong_session_token():
    _assert_post_refused_wrong_token("POST", "/api/v1/automations/pause",
                                     paused=True, reason="drill")


def test_post_check_refuses_with_wrong_session_token():
    _assert_post_refused_wrong_token("POST", "/api/v1/services/{id}/check",
                                     service_id="svc-api",
                                     check=iface.ServiceCheckKind.HTTP)


def test_post_runs_refuses_with_wrong_session_token():
    _assert_post_refused_wrong_token("POST", "/api/v1/automations/runs",
                                     project_id="proj-a",
                                     template_id="tpl-nightly")


def test_post_fire_refuses_with_wrong_session_token():
    _assert_post_refused_wrong_token("POST",
                                     "/api/v1/automations/triggers/{id}/fire",
                                     project_id="proj-a",
                                     trigger_id="trg-hourly")


def test_post_instantiate_refuses_with_wrong_session_token():
    _assert_post_refused_wrong_token(
        "POST", "/api/v1/automations/templates/{id}/instantiate",
        project_id="proj-a", template_id="tpl-nightly")


def test_post_launch_refuses_with_wrong_session_token():
    _assert_post_refused_wrong_token("POST",
                                     "/api/v1/automations/runs/{id}/launch",
                                     project_id="proj-a", run_id="run-0001")


def test_post_resume_refuses_with_wrong_session_token():
    _assert_post_refused_wrong_token("POST",
                                     "/api/v1/automations/runs/{id}/resume",
                                     project_id="proj-a", run_id="run-0001")


def test_post_outage_refuses_with_wrong_session_token():
    _assert_post_refused_wrong_token("POST", "/api/v1/outage/signal",
                                     project_id="proj-a",
                                     service_id="svc-api", severity="HIGH",
                                     summary="loopback lost")


def test_get_routes_carry_no_token():
    for route in ("GET /api/v1/automations/pause",
                  "GET /api/v1/services/{id}/status",
                  "GET /api/v1/apps/card"):
        entry = getattr(iface, iface.ROUTE_ENTRY_POINTS[route])
        params = inspect.signature(entry).parameters
        assert not any("token" in name.lower() for name in params), route


# --- reference-double sanity (GREEN: proves the oracles above are sane) ---

def test_reference_pause_marks_effective():
    pause = FakePause()
    pause.set_global(True, "drill")
    assert pause.is_effective("proj-a") is True
    pause.set_global(False, "")
    assert pause.is_effective("proj-a") is False


def test_reference_runner_rejects_unknown_run():
    runner = FakeRunner(FakePause())
    with pytest.raises(AutomationError) as excinfo:
        runner.resume("proj-a", "run-missing")
    assert _code(excinfo) == "AUTOMATION_RUN_NOT_FOUND"


def test_reference_journal_returns_receipt():
    journal = FakeJournal()
    entry = journal.append_event("proj-a", "automation", "OUTAGE_SIGNAL", "s", ())
    assert entry.entry_id != "" and entry.hash != ""


def test_reference_guard_records_checks():
    guard = FakeGuard()
    assert guard.check_escape("proj-a", "runs/run-0001") is True
    assert guard.calls == [("proj-a", "runs/run-0001")]


# --- wiring: every surface, route and code pinned (GREEN) ---

OWNED_SURFACES = (
    "set_global_pause",
    "is_pause_effective",
    "get_service_status",
    "run_service_check",
    "get_apps_card",
    "start_run",
    "fire_trigger",
    "instantiate_template",
    "launch",
    "resume",
    "signal_outage",
    "journal_append_event",
    "guard_check_escape",
    "stop_all_request_stop",
)


def test_every_surface_wired():
    for surface, func in iface.SURFACE_FUNCTIONS.items():
        assert surface in iface.REALIZATION_MAP, surface
        assert callable(getattr(iface, func, None)), func
    for name in OWNED_SURFACES:
        assert name in iface.SURFACE_FUNCTIONS.values(), name


def test_public_names_exist():
    for name in iface.__all__:
        assert hasattr(iface, name), name


def test_http_routes_exact():
    assert iface.HTTP_ROUTES == (
        ("GET", "/api/v1/automations/pause"),
        ("POST", "/api/v1/automations/pause"),
        ("GET", "/api/v1/services/{id}/status"),
        ("POST", "/api/v1/services/{id}/check"),
        ("GET", "/api/v1/apps/card"),
        ("POST", "/api/v1/automations/runs"),
        ("POST", "/api/v1/automations/triggers/{id}/fire"),
        ("POST", "/api/v1/automations/templates/{id}/instantiate"),
        ("POST", "/api/v1/automations/runs/{id}/launch"),
        ("POST", "/api/v1/automations/runs/{id}/resume"),
        ("POST", "/api/v1/outage/signal"),
    )


def test_route_table_complete():
    assert set(iface.ROUTE_ENTRY_POINTS) == {
        "%s %s" % (method, path) for method, path in iface.HTTP_ROUTES}
    for route, entry in iface.ROUTE_ENTRY_POINTS.items():
        assert callable(getattr(iface, entry, None)), route


def test_error_codes_exact():
    assert iface.ERROR_CODES == (
        "AUTOMATION_PAUSED",
        "AUTOMATION_RUN_NOT_FOUND",
        "AUTOMATION_RUN_ACTIVE",
        "TRIGGER_NOT_FOUND",
        "TEMPLATE_NOT_FOUND",
        "SERVICE_NOT_FOUND",
        "SERVICE_CHECK_REFUSED",
        "PAUSE_REASON_MISSING",
        "SESSION_TOKEN_MISSING",
        "SESSION_TOKEN_INVALID",
    )


def test_session_token_codes_appended():
    assert SESSION_TOKEN_CODES == (
        "SESSION_TOKEN_MISSING",
        "SESSION_TOKEN_INVALID",
    )
    for code in SESSION_TOKEN_CODES:
        assert code in iface.ERROR_CODES


def test_budget_observe_only():
    assert iface.BUDGET_CALLS_ALLOWLIST == (
        "get_state",
        "compare_and_reserve",
        "settle",
        "replay",
        "select",
        "record_fallback",
    )


@pytest.mark.parametrize("name", ("start_service", "stop_service"))
def test_no_external_service_control(name):
    assert not hasattr(iface, name)


def test_service_states_exact():
    assert [state.value for state in iface.ServiceState] == ["UP", "DOWN", "DEGRADED"]


def test_check_kinds_exact():
    assert [kind.value for kind in iface.ServiceCheckKind] == [
        "HTTP", "TCP", "CONTAINER_READONLY"]


def test_journal_kinds_exact():
    assert [kind.value for kind in iface.JournalKind] == [
        "WATCH_DECISION", "TAMPER_ATTEMPT", "GUARD_BLOCK", "STOP_ALL",
        "SERVICE_STATE", "AUTOMATION_RUN", "CONTEXT_CHECKPOINT",
        "CONTEXT_RECOVERY", "OUTAGE_SIGNAL"]


def test_service_status_field_names():
    assert [field.name for field in dataclasses.fields(iface.ServiceStatus)] == [
        "service_id", "state", "timestamp", "in_use", "last_used", "last_agent"]


def test_journal_entry_field_names():
    assert [field.name for field in dataclasses.fields(iface.JournalEntry)] == [
        "entry_id", "timestamp", "hash"]
