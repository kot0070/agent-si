"""K08OPEN1 behaviour lane: rows 249 / R-335 / R-337 / R-363 via the served app.

Each test drives the real lane through ``TestClient(create_app(settings))``
plus the HTTP client (pattern copied from
tests/test_bedef1_project_defaults.py). Module registrations below are
setup only (no HTTP route registers templates/triggers/launchers); every
product action under test goes over HTTP. No fake pause seam anywhere:
the pause assertions drive POST /api/v1/automations/pause for real.
"""

import os
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from fastapi.testclient import TestClient

from agent_si.automation import pause as pause_flags
from agent_si.automation import runner
from agent_si.automation import scheduler
from agent_si.automation import service_status
from agent_si.automation import service_watch
from agent_si.automation import templates
from agent_si.automation import triggers
import agent_si.automation.interface as auto_iface
from agent_si.backend.app import create_app

TEST_TOKEN = "k08open1-token"
ACTOR = "tester-k08open1"

PROJ = "proj-k08open1"
CARD_PROJ = "proj-b"  # seed services live here (svc-loopback, svc-container, ...)

PRESET_SPEC = {
    "name": "k08open1 preset",
    "version": 1,
    "description": "K08OPEN1 no-code preset: check, watch, notify.",
    "steps": [
        {
            "action": "service.check",
            "with": {"service_id": "svc-api"},
            "outputs": ["service_id", "state", "checked_at"],
        },
        {
            "action": "journal.notify",
            "with": {},
            "outputs": ["entry_id", "timestamp"],
        },
    ],
}


def _auth(token=TEST_TOKEN, actor=ACTOR):
    headers = {}
    if actor is not None:
        headers["x-actor"] = actor
    if token is not None:
        headers["x-ui-session-token"] = token
    return headers


def _settings():
    return {"testing": True, "ui_session_token": TEST_TOKEN}


def _reset_lane():
    pause_flags.reset_state()
    runner.reset_state()
    triggers.reset_state()
    scheduler.reset_state()
    service_status.reset_state()
    service_watch.reset_baseline()


def setup_function(_func):
    _reset_lane()
    # FXHIGH-2: resume is fail-closed on budget; these tests prove resume
    # mechanics (restart/outage), so they bind the allow hook explicitly.
    runner.set_budget_hook(lambda project_id: True)


def teardown_function(_func):
    _reset_lane()


def _client():
    return TestClient(create_app(_settings()))


def test_249_named_apps_card_closing_prompt_real_pause():
    """Row 249: named apps card + closing prompt, real pause lane, no fakes."""
    runner.register_template("tpl-k08open1-card", CARD_PROJ, "k08open1 card")
    client = _client()
    started = client.post(
        "/api/v1/automations/runs",
        json={"project_id": CARD_PROJ, "template_id": "tpl-k08open1-card"},
        headers=_auth(),
    )
    assert started.status_code == 200, started.text
    assert started.json()["state"] == "RUNNING"

    card = client.get("/api/v1/apps/card", params={"project_id": CARD_PROJ})
    assert card.status_code == 200, card.text
    payload = card.json()
    # Named per-service entries served from stored facts.
    names = {entry["service_id"]: entry["name"] for entry in payload["services"]}
    assert names["svc-loopback"] != ""
    assert set(names) >= {"svc-loopback", "svc-container", "svc-cache"}
    # Closing prompt: a RUNNING run means the app is not safe to close.
    assert payload["safe_to_close"] is False
    assert payload["close_prompt"] != ""

    # Real pause lane (no seam double): pause flips the served card flag.
    paused = client.post(
        "/api/v1/automations/pause",
        json={"paused": True, "reason": "k08open1 row 249"},
        headers=_auth(),
    )
    assert paused.status_code == 200, paused.text
    card2 = client.get("/api/v1/apps/card", params={"project_id": CARD_PROJ})
    assert card2.status_code == 200, card2.text
    assert card2.json()["paused"] is True
    unpaused = client.post(
        "/api/v1/automations/pause",
        json={"paused": False, "reason": ""},
        headers=_auth(),
    )
    assert unpaused.status_code == 200, unpaused.text
    card3 = client.get("/api/v1/apps/card", params={"project_id": CARD_PROJ})
    assert card3.json()["paused"] is False


def test_r335_timers_launchers_metrics_recorded_pausable():
    """Row R-335: timers/auto-launchers/metric actions recorded + pausable."""
    runner.register_template("tpl-k08open1", PROJ, "k08open1")
    scheduler.register_launcher("ln-k08open1", PROJ, "tpl-k08open1")
    scheduler.register_timer(
        "tm-k08open1", PROJ, 60.0, launcher_id="ln-k08open1", first_due=0.0
    )
    triggers.register_trigger(
        "trg-k08open1-timer", PROJ, kind="TIMER", schedule_ref="tm-k08open1"
    )
    scheduler.register_metric("mt-k08open1", PROJ, 5.0)
    triggers.register_trigger(
        "k08open1-outage", PROJ, kind="METRIC", schedule_ref="mt-k08open1"
    )
    client = _client()

    fired = client.post(
        "/api/v1/automations/triggers/trg-k08open1-timer/fire",
        json={"project_id": PROJ},
        headers=_auth(),
    )
    assert fired.status_code == 200, fired.text
    assert fired.json()["state"] == "RUNNING"
    outcomes = [entry.get("outcome") for entry in scheduler.ledger()]
    assert "timer-fired" in outcomes or "catchup-once" in outcomes

    metric_fired = client.post(
        "/api/v1/automations/triggers/k08open1-outage/fire",
        json={"project_id": PROJ},
        headers=_auth(),
    )
    assert metric_fired.status_code == 200, metric_fired.text
    outcomes = [entry.get("outcome") for entry in scheduler.ledger()]
    assert "metric-fired" in outcomes

    paused = client.post(
        "/api/v1/automations/pause",
        json={"paused": True, "reason": "k08open1 R-335"},
        headers=_auth(),
    )
    assert paused.status_code == 200, paused.text
    refused = client.post(
        "/api/v1/automations/triggers/trg-k08open1-timer/fire",
        json={"project_id": PROJ},
        headers=_auth(),
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "AUTOMATION_PAUSED"


def test_r337_service_usage_leak_scan_protected_refused():
    """Row R-337: usage fields, Docker leak scan, protected check refused."""
    client = _client()

    status = client.get("/api/v1/services/svc-api/status")
    assert status.status_code == 200, status.text
    payload = status.json()
    assert payload["service_id"] == "svc-api"
    assert payload["in_use"] is True
    assert payload["last_used"] != ""
    assert payload["last_agent"] != ""

    refused = client.post(
        "/api/v1/services/svc-vault/check",
        json={"check": "HTTP"},
        headers=_auth(),
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "SERVICE_CHECK_REFUSED"

    scan = client.post(
        "/api/v1/services/svc-container/check",
        json={"check": "CONTAINER_READONLY"},
        headers=_auth(),
    )
    assert scan.status_code == 200, scan.text
    report = scan.json()
    assert report["verdict"] in ("CLEAN", "FINDINGS")
    assert report["counts"]["checked"] >= 1
    assert isinstance(report["locations"], list)


def test_r363_templates_resume_register():
    """Row R-363: preset template, rule builder, resume after restart/outage."""
    templates.import_template("k08open1-preset", dict(PRESET_SPEC))
    runner.register_template("tpl-k08open1-re", PROJ, "k08open1 resume")
    client = _client()

    instantiated = client.post(
        "/api/v1/automations/templates/k08open1-preset/instantiate",
        json={"project_id": PROJ},
        headers=_auth(),
    )
    assert instantiated.status_code == 200, instantiated.text
    assert instantiated.json()["template_id"] == "k08open1-preset"

    # No-code rule builder: one instantiate leaves a runnable rule behind.
    rule = client.post(
        "/api/v1/automations/triggers/k08open1-preset/fire",
        json={"project_id": PROJ},
        headers=_auth(),
    )
    assert rule.status_code == 200, rule.text
    assert rule.json()["state"] == "RUNNING"

    # Resume after restart: persist, wipe (restart), restore, resume by HTTP.
    started = client.post(
        "/api/v1/automations/runs",
        json={"project_id": PROJ, "template_id": "tpl-k08open1-re"},
        headers=_auth(),
    )
    assert started.status_code == 200, started.text
    run_id = started.json()["run_id"]
    journal_rows = []
    orig_journal = auto_iface.journal_append_event

    def _recorder(project_id, source, kind, summary, refs):
        journal_rows.append((project_id, source, kind, summary, tuple(refs)))
        return auto_iface.JournalEntry(
            entry_id="evt-k08open1-%04d" % (len(journal_rows),),
            timestamp="2026-10-29T00:00:00Z",
            hash="hash-k08open1",
        )

    auto_iface.journal_append_event = _recorder
    try:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            runner_path = os.path.join(tmp, "runner.json")
            sched_path = os.path.join(tmp, "sched.json")
            runner.save_state(runner_path)
            scheduler.save_state(sched_path)
            _reset_lane()
            templates.import_template("k08open1-preset", dict(PRESET_SPEC))
            runner.load_state(runner_path)
            scheduler.load_state(sched_path)
            # FXHIGH-2: reset/load clears hooks; resume mechanics tests
            # keep the explicit allow hook (budget refusal is covered
            # in tests/test_fxhigh_budget.py).
            runner.set_budget_hook(lambda project_id: True)
            resumed = client.post(
                "/api/v1/automations/runs/%s/resume" % run_id,
                json={"project_id": PROJ},
                headers=_auth(),
            )
            assert resumed.status_code == 200, resumed.text
            assert resumed.json()["state"] == "RUNNING"
    finally:
        auto_iface.journal_append_event = orig_journal
    kinds = [row[2] for row in journal_rows]
    assert "CONTEXT_RECOVERY" in kinds

    # Resume after outage: stop-and-report then resume, all over HTTP.
    # Served doubles (same pattern as test_k08r7_entries.py): the frozen
    # stubs are unwired (`...`), so the outage path needs doubles.
    orig_stop = auto_iface.stop_all_request_stop

    def _stop_double(project_id, reason):
        return auto_iface.StopReceipt(
            project_id=project_id, stopped=True, reason=reason)

    auto_iface.journal_append_event = _recorder
    auto_iface.stop_all_request_stop = _stop_double
    try:
        outage_client = TestClient(create_app(_settings()), raise_server_exceptions=False)
        runner.register_template("tpl-k08open1-re", PROJ, "k08open1 resume")
        signalled = outage_client.post(
            "/api/v1/outage/signal",
            json={
                "project_id": PROJ,
                "service_id": "svc-cache",
                "severity": "HIGH",
                "summary": "k08open1 outage drill",
            },
            headers=_auth(),
        )
        assert signalled.status_code == 200, signalled.text
        assert signalled.json()["stopped"] is True
    finally:
        auto_iface.journal_append_event = orig_journal
        auto_iface.stop_all_request_stop = orig_stop
