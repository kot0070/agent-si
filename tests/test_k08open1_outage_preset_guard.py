"""K08OPEN1 watcher lane: outage / preset / guard / watcher-tab payloads.

Row 181 (testid k08open1-outage): one outage means one clear stop-and-report
through the real lane (one real stop_all call + one OUTAGE_SIGNAL row named
STOP_AND_REPORT), never a stop double (a repeated signal adds no rows).
Row 186 (testid k08open1-preset): gap probe, see test_186 below.
Row R-321: a workspace escape detected from stored facts yields alert plus
block through the served app (served rule evaluate -> BLOCK plus one
WATCH_DECISION row, plus the owned from-facts escape guard).
Row R-336: the serving model triple (local-AI default, API cloud fallback,
OFF) governs served rule evaluation: local default evaluates facts, API
falls back to the local evaluation, OFF never blocks.

Behaviour tests through create_app + HTTP client (TestClient); facts are
planted only through real product APIs. No doubles, no skip/xfail.
"""

import os
import sys

from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest  # noqa: E402

import agent_si.watcher.journal as journal  # noqa: E402
import agent_si.watcher.presets as presets  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend import stop_all as stop_home  # noqa: E402

TOKEN = "k08open1-token"
ACTOR = "tester-k08open1"


def _settings(tmp_path):
    return {
        "testing": True,
        "ui_session_token": TOKEN,
        "store_dir": str(tmp_path / "k08open1-store"),
    }


def _auth():
    return {"x-actor": ACTOR, "x-ui-session-token": TOKEN}


@pytest.fixture(autouse=True)
def _reset_lane_state():
    import agent_si.watcher.engine as engine
    import agent_si.watcher.integrity as integrity
    import agent_si.watcher.rules as rules
    import agent_si.watcher.status as status

    journal.reset_state()
    integrity.reset_state()
    rules.reset_state()
    engine.reset_state()
    presets.reset_state()
    status.reset_state()
    stop_home.reset_state()
    yield
    stop_home.reset_state()


def _served_journal(client, project_id, kind):
    resp = client.get(
        "/api/v1/watcher/journal",
        params={"project_id": project_id, "kind": kind},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- row 181 (testid k08open1-outage): one stop-and-report, never a double ---


def test_181_outage_single_stop_and_report_never_double(tmp_path):
    """k08open1-outage: one outage -> exactly one STOP_ALL row plus exactly
    one OUTAGE_SIGNAL row named STOP_AND_REPORT; a repeated signal for the
    same outage adds no further rows (never a stop double). Served legs
    verified through the app journal reads."""
    try:
        from agent_si.watcher import outage as watcher_outage
    except ImportError:
        watcher_outage = None
    assert watcher_outage is not None, (
        "k08open1-outage: watcher outage leg missing: expected "
        "agent_si.watcher.outage.signal_outage to stop once through the "
        "real stop_all lane and report one STOP_AND_REPORT OUTAGE_SIGNAL row"
    )
    client = TestClient(create_app(_settings(tmp_path)))
    pid = "k08open1-outage-p1"
    first = watcher_outage.signal_outage(pid, "svc-a", "outage svc-a down")
    assert first.stopped is True
    stop_rows = _served_journal(client, pid, "STOP_ALL")
    assert len(stop_rows) == 1
    outage_rows = _served_journal(client, pid, "OUTAGE_SIGNAL")
    assert len(outage_rows) == 1
    stored = journal.stored_rows(pid, "OUTAGE_SIGNAL")
    assert len(stored) == 1
    assert "STOP_AND_REPORT" in stored[0].summary
    second = watcher_outage.signal_outage(pid, "svc-a", "outage svc-a down")
    assert second.stopped is False
    assert len(_served_journal(client, pid, "STOP_ALL")) == 1
    assert len(_served_journal(client, pid, "OUTAGE_SIGNAL")) == 1


# --- row 186 (testid k08open1-preset): served-leg gap probe, NOT-DONE ---


def test_186_route_gap_create_does_not_seed(tmp_path):
    """k08open1-preset gap probe (NOT-DONE waits-for-pkg): a project created
    through the served create_project leg gets NO default watcher preset,
    because console_projects_write.create_project runs
    _project_defaults.ensure_project_defaults but never
    presets.ensure_seeded
    (src/agent_si/backend/console_projects_write.py:130), and no
    watcher-owned hook runs on that path (zero seed/preset refs in
    src/agent_si/backend). A watcher-side hook would corrupt frozen
    journal-count semantics, so the fix sits outside owned files."""
    client = TestClient(create_app(_settings(tmp_path)))
    resp = client.post(
        "/api/v1/projects",
        json={"name": "k08open1-fresh", "folder_ref": "dock-k08open1"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    pid = resp.json()["project"]["project_id"]
    assert presets.installed_cards(pid) == ()


# --- row R-321: escape from facts yields alert plus block, served ---


def test_r321_escape_from_facts_alerts_and_blocks(tmp_path):
    """R-321: stored TAMPER_ATTEMPT facts make the served rule evaluate yield
    BLOCK (block) plus one WATCH_DECISION row (alert); the owned from-facts
    escape guard blocks outside paths and allows inside paths."""
    try:
        from agent_si.watcher import guard as watcher_guard
    except ImportError:
        watcher_guard = None
    assert watcher_guard is not None, (
        "R-321: watcher from-facts escape guard missing: expected "
        "agent_si.watcher.guard.check_escape to alert plus block workspace "
        "escapes detected from stored facts"
    )
    client = TestClient(create_app(_settings(tmp_path)))
    pid = "k08open1-r321-p1"
    journal.append_event(
        pid, "agent-x", "TAMPER_ATTEMPT",
        "write outside workspace", ("/outside/evil.txt",),
    )
    resp = client.post(
        "/api/v1/watcher/rules/rule-tamper/evaluate",
        json={"project_id": pid, "session_token": TOKEN},
        headers={"x-ui-session-token": TOKEN},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["verdict"] == "BLOCK"
    decisions = _served_journal(client, pid, "WATCH_DECISION")
    assert len(decisions) == 1
    block = watcher_guard.check_escape(pid, "/outside/evil.txt", "/ws/proj")
    assert block.allowed is False
    assert block.reason != ""
    assert len(journal.stored_rows(pid, "GUARD_BLOCK")) == 1
    calm = watcher_guard.check_escape(pid, "/ws/proj/notes.txt", "/ws/proj")
    assert calm.allowed is True
    assert len(journal.stored_rows(pid, "GUARD_BLOCK")) == 1


# --- row R-336: serving model triple governs served evaluation ---


def test_r336_model_default_fallback_off_served(tmp_path):
    """R-336: local-AI default, API cloud fallback, OFF. Served rule
    evaluation follows the card model: local (default) evaluates stored
    facts, API falls back to the local evaluation, OFF never blocks. The
    Watcher tab data deps (status + journal) stay served."""
    import dataclasses

    import agent_si.watcher.rules as rules

    assert rules.MODELS == ("local", "API", "OFF")
    assert rules.describe("rule-tamper").model == "local"
    client = TestClient(create_app(_settings(tmp_path)))
    pid = "k08open1-r336-p1"
    journal.append_event(
        pid, "agent-x", "TAMPER_ATTEMPT", "escape probe", ("evil-path",),
    )
    status_resp = client.get(
        "/api/v1/watcher/status", params={"project_id": pid}
    )
    assert status_resp.status_code == 200, status_resp.text
    journal_resp = client.get(
        "/api/v1/watcher/journal", params={"project_id": pid}
    )
    assert journal_resp.status_code == 200, journal_resp.text

    def _eval():
        resp = client.post(
            "/api/v1/watcher/rules/rule-tamper/evaluate",
            json={"project_id": pid, "session_token": TOKEN},
            headers={"x-ui-session-token": TOKEN},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    assert _eval()["verdict"] == "BLOCK"
    card = rules.describe("rule-tamper")
    try:
        rules.RULES["rule-tamper"] = dataclasses.replace(card, model="API")
        assert _eval()["verdict"] == "BLOCK"
        rows = journal.stored_rows(pid, "WATCH_DECISION")
        assert "API->local" in rows[-1].summary
        rules.RULES["rule-tamper"] = dataclasses.replace(card, model="OFF")
        assert _eval()["verdict"] == "ALLOW"
        rows = journal.stored_rows(pid, "WATCH_DECISION")
        assert "OFF" in rows[-1].summary
    finally:
        rules.RULES["rule-tamper"] = card
    assert len(_served_journal(client, pid, "WATCH_DECISION")) == 3
