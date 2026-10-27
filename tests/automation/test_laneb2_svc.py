"""Lane B STEP2 coder tests: services, apps card, templates, outage, routes.

Target (this task only):
  src/agent_si/automation/service_status.py
  src/agent_si/automation/service_watch.py
  src/agent_si/automation/apps_card.py
  src/agent_si/automation/outage.py
  src/agent_si/automation/templates.py
  src/agent_si/backend/automation_routes.py

Behaviour tests call the lane modules directly (the frozen interface keeps
shapes only and is never touched). Cross-lane doubles below are test-only;
each carries exactly one FAKE-OF line. RED before the lane realisation,
GREEN after.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

import agent_si.automation.interface as auto_iface
from agent_si.automation import apps_card, outage, service_status, service_watch
from agent_si.automation import templates
from agent_si.automation.interface import AutomationError

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

LIVE_TOKEN = "token-live"
PLACEHOLDER_VALUE = "TEST-PLACEHOLDER-NOT-A-SECRET-0000"


# FAKE-OF: agent_si.automation.interface.journal_append_event
class FakeJournal:
    """Reference journal double: append returns receipts, records rows."""

    def __init__(self):
        self.calls = []
        self._seq = 0

    def append_event(self, project_id, source, kind, summary, refs):
        self._seq += 1
        entry = auto_iface.JournalEntry(
            entry_id="evt-%04d" % self._seq,
            timestamp="2026-10-27T00:00:00Z",
            hash="hash-%04d" % self._seq,
        )
        self.calls.append((project_id, source, kind, summary, tuple(refs), entry))
        return entry


# FAKE-OF: agent_si.automation.interface.stop_all_request_stop
class FakeStopAll:
    """Reference stop-all double: records requests, reports stopped."""

    def __init__(self):
        self.calls = []

    def request_stop(self, project_id, reason):
        receipt = auto_iface.StopReceipt(
            project_id=project_id, stopped=True, reason=reason
        )
        self.calls.append(receipt)
        return receipt


# FAKE-OF: agent_si.budget.gate.BudgetGate.get_state
class FakeBudgetGate:
    """Reference budget double: observe-only record of get_state calls."""

    def __init__(self):
        self.calls = []

    def get_state(self, key):
        self.calls.append(key)
        return {"key": key, "remaining": "100"}


def _code(excinfo):
    return excinfo.value.code


def _age_seconds(stamp):
    parsed = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    now = datetime.now(timezone.utc)
    return abs((now - parsed).total_seconds())


@pytest.fixture(autouse=True)
def _clean_lane_state():
    service_status.reset_state()
    states = {
        service_id: (row["state"], row["timestamp"])
        for service_id, row in service_status._SERVICES.items()
    }
    service_watch.reset_baseline()
    yield
    for service_id, (state, stamp) in states.items():
        service_status._SERVICES[service_id]["state"] = state
        service_status._SERVICES[service_id]["timestamp"] = stamp
    service_watch.reset_baseline()


@pytest.fixture()
def journal(monkeypatch):
    fake = FakeJournal()
    monkeypatch.setattr(
        auto_iface, "journal_append_event", fake.append_event
    )
    return fake


@pytest.fixture()
def stopper(monkeypatch):
    fake = FakeStopAll()
    monkeypatch.setattr(
        auto_iface, "stop_all_request_stop", fake.request_stop
    )
    return fake


@pytest.fixture()
def budget(monkeypatch):
    fake = FakeBudgetGate()
    monkeypatch.setattr(service_status, "observe_budget", fake.get_state)
    return fake


# --- P11: service status and checks ---

def test_get_known_service_up(budget):
    status = service_status.get("svc-api")
    assert isinstance(status, auto_iface.ServiceStatus)
    assert status.service_id == "svc-api"
    assert status.state == "UP"
    assert status.state in ("UP", "DOWN", "DEGRADED")


def test_get_down_and_degraded_rows(budget):
    assert service_status.get("svc-cache").state == "DOWN"
    assert service_status.get("svc-vault").state == "DEGRADED"


def test_get_unknown_service_raises(budget):
    with pytest.raises(AutomationError) as excinfo:
        service_status.get("svc-missing")
    assert _code(excinfo) == "SERVICE_NOT_FOUND"


def test_status_usage_from_metadata_only(budget):
    status = service_status.get("svc-api")
    dispatch = service_status._DISPATCH_META["svc-api"]
    egress = service_status._EGRESS_META["svc-api"]
    assert status.in_use == dispatch["active"] is True
    assert status.last_agent == dispatch["last_agent"] == "agent-1"
    assert status.last_used == max(dispatch["last_used"], egress["last_egress"])


def test_run_http_check_up(monkeypatch, journal, budget):
    monkeypatch.setattr(service_status, "_probe_http", lambda *a: (True, False))
    status = service_status.run_check(
        "svc-api", auto_iface.ServiceCheckKind.HTTP
    )
    assert status.state == "UP"
    assert _age_seconds(status.timestamp) < 300


def test_run_tcp_check_down(monkeypatch, journal, budget):
    monkeypatch.setattr(service_status, "_probe_tcp", lambda *a: (False, False))
    status = service_status.run_check(
        "svc-loopback", auto_iface.ServiceCheckKind.TCP
    )
    assert status.state == "DOWN"
    assert service_status.get("svc-loopback").state == "DOWN"


def test_run_check_slow_is_degraded(monkeypatch, journal, budget):
    monkeypatch.setattr(service_status, "_probe_http", lambda *a: (True, True))
    status = service_status.run_check(
        "svc-api", auto_iface.ServiceCheckKind.HTTP
    )
    assert status.state == "DEGRADED"


def test_run_check_unhealthy_but_reachable_is_degraded(
    monkeypatch, journal, budget
):
    monkeypatch.setattr(service_status, "_probe_http", lambda *a: (False, False))
    monkeypatch.setattr(service_status, "_probe_tcp", lambda *a: (True, False))
    status = service_status.run_check(
        "svc-api", auto_iface.ServiceCheckKind.HTTP
    )
    assert status.state == "DEGRADED"


def test_container_check_refused_on_network_service(monkeypatch, journal, budget):
    def _boom(*args):
        raise AssertionError("probe executed pre-refusal")

    monkeypatch.setattr(service_status, "_probe_http", _boom)
    monkeypatch.setattr(service_status, "_probe_tcp", _boom)
    with pytest.raises(AutomationError) as excinfo:
        service_status.run_check(
            "svc-api", auto_iface.ServiceCheckKind.CONTAINER_READONLY
        )
    assert _code(excinfo) == "SERVICE_CHECK_REFUSED"
    assert len(journal.calls) == 1
    assert service_status.get("svc-api").state == "UP"


def test_protected_service_refused_pre_exec(monkeypatch, journal, budget):
    def _boom(*args):
        raise AssertionError("probe executed pre-refusal")

    monkeypatch.setattr(service_status, "_probe_http", _boom)
    monkeypatch.setattr(service_status, "_probe_tcp", _boom)
    with pytest.raises(AutomationError) as excinfo:
        service_status.run_check(
            "svc-vault", auto_iface.ServiceCheckKind.HTTP
        )
    assert _code(excinfo) == "SERVICE_CHECK_REFUSED"
    assert len(journal.calls) == 1
    assert service_status.get("svc-vault").state == "DEGRADED"


def test_container_scan_reports_verdict_counts_locations(monkeypatch):
    monkeypatch.setattr(
        service_status,
        "_read_descriptor",
        lambda service_id: {
            "env": {"LEAKED_API_TOKEN": PLACEHOLDER_VALUE, "PORT": "9000"},
            "files": (),
        },
    )
    report = service_status.scan_container("svc-container")
    assert report.verdict == "FINDINGS"
    assert report.findings >= 1
    assert report.checked >= 1
    assert report.locations != ()
    assert all(isinstance(location, str) for location in report.locations)
    assert PLACEHOLDER_VALUE not in repr(report)
    assert all(PLACEHOLDER_VALUE not in location for location in report.locations)


def test_container_scan_clean_by_default():
    report = service_status.scan_container("svc-container")
    assert report.verdict == "CLEAN"
    assert report.findings == 0
    assert report.locations == ()


def test_run_check_observes_budget(monkeypatch, journal, budget):
    monkeypatch.setattr(service_status, "_probe_tcp", lambda *a: (True, False))
    service_status.run_check("svc-loopback", auto_iface.ServiceCheckKind.TCP)
    assert budget.calls == ["svc-loopback"]


# --- service watch: observe plus notify ---

def test_watch_tick_notifies_changes(journal, budget):
    summary = service_watch.tick("proj-a")
    assert isinstance(summary, service_watch.ServiceWatchSummary)
    assert summary.checked == len(service_status.services_for_project("proj-a"))
    assert set(summary.changed) == set(service_status.services_for_project("proj-a"))
    assert len(summary.journal_entry_ids) == len(summary.changed)
    assert len(journal.calls) == len(summary.changed)
    assert _age_seconds(summary.checked_at) < 300


def test_watch_tick_quiet_without_changes(journal, budget):
    service_watch.tick("proj-a")
    before = len(journal.calls)
    summary = service_watch.tick("proj-a")
    assert summary.changed == ()
    assert summary.journal_entry_ids == ()
    assert len(journal.calls) == before


def test_watch_tick_notifies_single_change(monkeypatch, journal, budget):
    service_watch.tick("proj-a")
    before = len(journal.calls)
    monkeypatch.setattr(service_status, "_probe_http", lambda *a: (True, True))
    service_status.run_check("svc-api", auto_iface.ServiceCheckKind.HTTP)
    summary = service_watch.tick("proj-a")
    assert summary.changed == ("svc-api",)
    assert len(journal.calls) == before + 2


def test_watch_tick_unknown_project_is_empty(journal, budget):
    summary = service_watch.tick("proj-missing")
    assert summary.checked == 0
    assert summary.changed == ()
    assert journal.calls == []


# --- apps card: stored facts only ---

def test_apps_card_facts_only(budget):
    card = apps_card.get_apps_card("proj-a")
    assert isinstance(card, auto_iface.AppsCardData)
    assert card.project_id == "proj-a"
    assert card.service_ids == service_status.services_for_project("proj-a")
    assert card.paused is False
    assert _age_seconds(card.generated_at) < 300


def test_apps_card_reflects_pause(monkeypatch, budget):
    monkeypatch.setattr(apps_card, "is_pause_effective", lambda project_id: True)
    card = apps_card.get_apps_card("proj-a")
    assert card.paused is True


# --- P6: every template makes a working automation ---

BUILT_IN_IDS = (
    "tpl-nightly",
    "tpl-healthcheck",
    "tpl-container-audit",
    "tpl-usage-report",
    "tpl-watch-sweep",
    "tpl-outage-drill",
)


def test_builtin_template_ids_exact():
    assert templates.BUILTIN_TEMPLATE_IDS == BUILT_IN_IDS
    assert set(templates.list_templates()) >= set(BUILT_IN_IDS)


@pytest.mark.parametrize("template_id", BUILT_IN_IDS)
def test_each_template_makes_working_automation(template_id, journal):
    template = templates.instantiate("proj-a", template_id)
    assert isinstance(template, auto_iface.AutomationTemplate)
    assert template.template_id == template_id
    assert template.project_id == "proj-a"
    plan = templates.materialize("proj-a", template_id)
    assert plan["template_id"] == template_id
    assert plan["project_id"] == "proj-a"
    assert plan["model"] == "meta/muse-spark-1.3-contributor"
    assert isinstance(plan["steps"], list) and plan["steps"] != []
    for step in plan["steps"]:
        assert step["action"] in templates.ACTION_CATALOG
        assert isinstance(step["outputs"], list) and step["outputs"] != []
        for output in step["outputs"]:
            assert output in templates.ACTION_CATALOG[step["action"]]


def test_instantiate_unknown_template_raises(journal):
    with pytest.raises(AutomationError) as excinfo:
        templates.instantiate("proj-a", "template-missing")
    assert _code(excinfo) == "TEMPLATE_NOT_FOUND"


def test_import_rejects_unknown_action():
    with pytest.raises(ValueError):
        templates.import_template(
            "tpl-test-bad",
            {
                "name": "bad",
                "version": 1,
                "steps": [{"action": "nope", "outputs": ["x"]}],
            },
        )


def test_import_rejects_missing_outputs():
    with pytest.raises(ValueError):
        templates.import_template(
            "tpl-test-bad",
            {
                "name": "bad",
                "version": 1,
                "steps": [{"action": "service.check", "outputs": []}],
            },
        )


def test_imported_template_makes_working_automation(journal):
    templates.import_template(
        "tpl-test-import",
        {
            "name": "test-import",
            "version": 1,
            "description": "test-only imported template",
            "steps": [
                {
                    "action": "service.check",
                    "with": {"service_id": "svc-api"},
                    "outputs": ["service_id", "state"],
                }
            ],
        },
    )
    assert "tpl-test-import" in templates.list_templates()
    template = templates.instantiate("proj-a", "tpl-test-import")
    assert template.name == "test-import"
    plan = templates.materialize("proj-a", "tpl-test-import")
    assert plan["steps"][0]["outputs"] == ["service_id", "state"]
    assert plan["model"] == "meta/muse-spark-1.3-contributor"


def test_model_id_exact():
    assert templates.MODEL_ID == "meta/muse-spark-1.3-contributor"


# --- P4: one outage signal, stop-and-report ---

def test_signal_outage_reports(journal, stopper, budget):
    report = outage.signal_outage(
        "proj-a", "svc-api", "HIGH", "loopback lost"
    )
    assert isinstance(report, auto_iface.OutageReport)
    assert report.project_id == "proj-a"
    assert report.service_id == "svc-api"
    assert report.severity == "HIGH"
    assert report.journal_entry_id == journal.calls[0][5].entry_id
    assert report.journal_entry_id != ""
    assert report.stopped is True
    assert _age_seconds(report.reported_at) < 300


def test_signal_outage_calls_stop_and_journal_once(journal, stopper, budget):
    report = outage.signal_outage(
        "proj-a", "svc-api", "HIGH", "loopback lost"
    )
    assert len(stopper.calls) == 1
    assert len(journal.calls) == 1
    assert stopper.calls[0].project_id == "proj-a"
    assert "svc-api" in stopper.calls[0].reason
    project_id, source, kind, summary, refs, _entry = journal.calls[0]
    assert (project_id, source, kind) == ("proj-a", "automation", "OUTAGE_SIGNAL")
    assert summary == "loopback lost"
    assert report.report_id in refs and "svc-api" in refs


def test_signal_outage_unknown_service_raises(journal, stopper, budget):
    with pytest.raises(AutomationError) as excinfo:
        outage.signal_outage("proj-a", "svc-missing", "HIGH", "s")
    assert _code(excinfo) == "SERVICE_NOT_FOUND"
    assert stopper.calls == []
    assert journal.calls == []


def test_signal_outage_severity_enum_passthrough(journal, stopper, budget):
    report = outage.signal_outage(
        "proj-a",
        "svc-cache",
        auto_iface.OutageSeverity.CRITICAL,
        "cache down",
    )
    assert report.severity == "CRITICAL"
    assert report.stopped is True


# --- routes: thin mapping with token guard ---

@needs_routes
def test_router_covers_http_routes_exactly():
    covered = set()
    for route in routes.router.routes:
        methods = getattr(route, "methods", None) or set()
        for method in methods:
            covered.add((method, route.path))
    assert covered == set(auto_iface.HTTP_ROUTES)
    assert set(routes._HANDLED) == set(auto_iface.ROUTE_ENTRY_POINTS)


@pytest.fixture()
def client(monkeypatch):
    app = FastAPI()
    app.include_router(routes.router)
    monkeypatch.setattr(
        routes, "_auth_hook", lambda token: token == LIVE_TOKEN
    )
    monkeypatch.setattr(routes, "_rate_hook", None)
    monkeypatch.setattr(
        auto_iface, "journal_append_event", FakeJournal().append_event
    )
    monkeypatch.setattr(
        auto_iface, "stop_all_request_stop", FakeStopAll().request_stop
    )
    return TestClient(app)


@needs_routes
def test_route_get_status_open(client):
    response = client.get("/api/v1/services/svc-api/status")
    assert response.status_code == 200
    assert response.json()["service_id"] == "svc-api"


@needs_routes
def test_route_get_card_open(client):
    response = client.get("/api/v1/apps/card", params={"project_id": "proj-a"})
    assert response.status_code == 200
    assert "svc-api" in response.json()["service_ids"]


@needs_routes
def test_route_post_check_with_live_token(client, monkeypatch):
    monkeypatch.setattr(service_status, "_probe_http", lambda *a: (True, False))
    response = client.post(
        "/api/v1/services/svc-api/check",
        json={"check": "HTTP", "session_token": LIVE_TOKEN},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "UP"


@needs_routes
def test_route_post_instantiate_with_live_token(client):
    response = client.post(
        "/api/v1/automations/templates/tpl-nightly/instantiate",
        json={"project_id": "proj-a", "session_token": LIVE_TOKEN},
    )
    assert response.status_code == 200
    assert response.json()["template_id"] == "tpl-nightly"


@needs_routes
def test_route_post_outage_with_live_token(client):
    response = client.post(
        "/api/v1/outage/signal",
        json={
            "project_id": "proj-a",
            "service_id": "svc-api",
            "severity": "HIGH",
            "summary": "loopback lost",
            "session_token": LIVE_TOKEN,
        },
    )
    assert response.status_code == 200
    assert response.json()["stopped"] is True


POST_ROUTES = (
    ("/api/v1/automations/pause", {"paused": True, "reason": "drill"}),
    ("/api/v1/services/svc-api/check", {"check": "HTTP"}),
    ("/api/v1/automations/runs", {"project_id": "proj-a", "template_id": "tpl-nightly"}),
    (
        "/api/v1/automations/triggers/trg-hourly/fire",
        {"project_id": "proj-a"},
    ),
    (
        "/api/v1/automations/templates/tpl-nightly/instantiate",
        {"project_id": "proj-a"},
    ),
    ("/api/v1/automations/runs/run-0001/launch", {"project_id": "proj-a"}),
    ("/api/v1/automations/runs/run-0001/resume", {"project_id": "proj-a"}),
    (
        "/api/v1/outage/signal",
        {
            "project_id": "proj-a",
            "service_id": "svc-api",
            "severity": "HIGH",
            "summary": "loopback lost",
        },
    ),
)


@needs_routes
@pytest.mark.parametrize("path,payload", POST_ROUTES)
def test_post_routes_refuse_without_token(client, path, payload):
    response = client.post(path, json=dict(payload))
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "SESSION_TOKEN_MISSING"


@needs_routes
@pytest.mark.parametrize("path,payload", POST_ROUTES)
def test_post_routes_refuse_with_wrong_token(client, path, payload):
    response = client.post(
        path, json=dict(payload), headers={"x-ui-session-token": "token-wrong"}
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "SESSION_TOKEN_INVALID"

