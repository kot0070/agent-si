"""FXWATCH served proof: watcher shows it really watches (RED first).

Quiet run: checks rise, model calls 0. Abnormal: alert + journal row +
model call counted. Served status route carries the numbers; real page
uses them. en + uk locale keys exist. Fresh auditor runs the same file.
"""

import os
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from fastapi.testclient import TestClient  # noqa: E402

import pytest  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.watcher import engine as _engine  # noqa: E402
from agent_si.watcher import journal as _journal  # noqa: E402
from agent_si.watcher import rules as _rules  # noqa: E402
from agent_si.watcher import stats as _stats  # noqa: E402
from agent_si.watcher import status as _status  # noqa: E402

TOKEN = "fxwatch-token"


def _settings():
    return {"testing": True, "ui_session_token": TOKEN}


def _auth():
    return {"x-ui-session-token": TOKEN}


def setup_function(_func):
    _journal.reset_state()
    _rules.reset_state()
    _engine.reset_state()
    _status.reset_state()
    _stats.reset_state()


def teardown_function(_func):
    _journal.reset_state()
    _rules.reset_state()
    _engine.reset_state()
    _status.reset_state()
    _stats.reset_state()


# Fail-closed gate needs a real gate: the abnormal path admits the
# watcher model call before invoking the transport. Generous limits,
# all static project ids, restored after (same ordered pattern as the
# C5 neighbours, incl. FXLOC2's fxr2c fixture).
_FXWATCH_GATE_PROJECTS = (
    "fxwatch-quiet-1",
    "fxwatch-hot-1",
    "fxwatch-served-1",
)


@pytest.fixture(autouse=True)
def _fxwatch_real_budget_gate():
    from agent_si.budget.gate import BudgetGate
    from agent_si.runtime import manager as _manager

    prev = _manager._BUDGET_GATE
    gate = BudgetGate()
    for project in _FXWATCH_GATE_PROJECTS:
        gate.configure_project(
            project, "USD", "1000000.00", "900000.00", "1000000.00")
    _manager.set_budget_gate(gate)
    yield
    _manager.set_budget_gate(prev)


class _FakeTransport:
    def __init__(self, usage=None):
        self.calls = []
        self.usage = dict(usage or {"input_tokens": 10, "output_tokens": 5})

    def __call__(self, model, rule_id, allowed):
        self.calls.append({"model": model, "rule_id": rule_id})
        script, params = allowed[0]
        return {"script": script, "params": params,
                "usage": dict(self.usage)}


def _configure(transport):
    _rules.configure_watcher_model(
        transport=transport, local_model="fx-local-1",
        local_connected=True, cloud_model="", cloud_connected=False,
        cloud_fallback=False)


def test_quiet_tick_checks_rise_calls_zero():
    _configure(_FakeTransport())
    pid = "fxwatch-quiet-1"
    _journal.append_event(pid, "watcher", "SERVICE_STATE", "boot", ())
    before = _status.get(pid)
    _engine.tick(pid)
    _engine.tick(pid)
    after = _status.get(pid)
    assert after.checks_done > before.checks_done
    assert after.checks_done >= 4
    assert after.watcher_calls == 0
    assert after.watcher_tokens == 0
    assert after.last_check_at != ""
    assert len(_journal.stored_rows(pid, "WATCH_DECISION")) == 0


def test_abnormal_alert_journal_model_call_counted():
    transport = _FakeTransport({"input_tokens": 10, "output_tokens": 5})
    _configure(transport)
    pid = "fxwatch-hot-1"
    _journal.append_event(pid, "watcher", "SERVICE_STATE", "boot", ())
    _journal.append_event(pid, "agent-x", "TAMPER_ATTEMPT",
                          "edited log", ("ref-1",))
    _engine.tick(pid)
    rows = list(_journal.stored_rows(pid, "WATCH_DECISION"))
    assert rows, "abnormal tick left no WATCH_DECISION row"
    assert len(transport.calls) >= 1
    served = _status.get(pid)
    assert served.alerts_raised >= 1
    assert served.watcher_calls >= 1
    assert served.watcher_tokens == 15
    assert served.last_action != ""
    assert any(rule == "rule-tamper" and count >= 1
               for rule, count in served.rules_fired)


def test_served_status_route_carries_numbers():
    transport = _FakeTransport()
    _configure(transport)
    client = TestClient(create_app(_settings()))
    pid = "fxwatch-served-1"
    _journal.append_event(pid, "watcher", "SERVICE_STATE", "boot", ())
    _engine.tick(pid)
    resp = client.get("/api/v1/watcher/status", params={"project_id": pid})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for field in ("checks_done", "alerts_raised", "last_check_at",
                  "watcher_calls", "watcher_tokens", "watched_runs",
                  "watched_agents", "last_action", "rules_fired"):
        assert field in body, "served status missing %s: %r" % (field, body)
    assert int(body["checks_done"]) >= 2
    assert int(body["watcher_calls"]) == 0
    journal = client.get("/api/v1/watcher/journal",
                         params={"project_id": pid})
    assert journal.status_code == 200


def test_locale_en_uk_not_known_and_rules():
    import json as _json

    for path in (
        os.path.join(_WS, "frontend", "src", "locale", "en.json"),
        os.path.join(_WS, "frontend", "src", "locale", "uk.json"),
    ):
        with open(path, encoding="utf-8") as handle:
            table = _json.load(handle)
        tab = table["watcher"]["tab"]
        assert tab["notKnown"] in ("not known", "невідомо"), path
        for key in ("checks", "alerts", "lastCheck", "modelCalls",
                    "watches", "lastAction", "rulesTitle", "journalTitle",
                    "looksHang", "looksGuard", "looksTamper"):
            assert tab.get(key), "%s missing %s" % (path, key)
        rail = table["shell"]["cards"]["watcher"]
        assert rail["notKnown"] in ("not known", "невідомо"), path
