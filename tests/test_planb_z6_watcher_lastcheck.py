"""PLANB Z6 (DEFECT-42): the Watcher page read "Last check: No checks yet"
after Evaluate while Model calls and the journal row already existed.

Cause: only the engine tick recorded a check; the Evaluate route ran the
rule (journal row, model call) and recorded none. Contract: one Evaluate is
one check: checks_done +1, last_check_at set, alert counted when the rule
fired. The engine tick keeps counting once per card (no double count).
"""
import os
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_WS, os.path.join(_WS, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.watcher import engine as _engine  # noqa: E402
from agent_si.watcher import journal as _journal  # noqa: E402
from agent_si.watcher import rules as _rules  # noqa: E402
from agent_si.watcher import stats as _stats  # noqa: E402
from agent_si.watcher import status as _status  # noqa: E402

TOKEN = "planb-z6-token"
PID = "planb-z6-1"


def _reset():
    _journal.reset_state()
    _rules.reset_state()
    _engine.reset_state()
    _status.reset_state()
    _stats.reset_state()


def setup_function(_f):
    _reset()


def teardown_function(_f):
    _reset()


@pytest.fixture(autouse=True)
def _gate():
    from agent_si.budget.gate import BudgetGate
    from agent_si.runtime import manager as _manager

    prev = _manager._BUDGET_GATE
    gate = BudgetGate()
    gate.configure_project(PID, "USD", "1000000.00", "900000.00", "1000000.00")
    _manager.set_budget_gate(gate)
    yield
    _manager.set_budget_gate(prev)


class _Transport:
    def __call__(self, model, rule_id, allowed):
        script, params = allowed[0]
        return {"script": script, "params": params,
                "usage": {"input_tokens": 10, "output_tokens": 5}}


def _client():
    _rules.configure_watcher_model(
        transport=_Transport(), local_model="z6-local-1",
        local_connected=True, cloud_model="", cloud_connected=False,
        cloud_fallback=False)
    return TestClient(create_app({"testing": True, "ui_session_token": TOKEN}))


def _status_body(client):
    resp = client.get("/api/v1/watcher/status", params={"project_id": PID})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_evaluate_with_model_call_records_a_check():
    client = _client()
    _journal.append_event(PID, "watcher", "SERVICE_STATE", "boot", ())
    _journal.append_event(PID, "agent-x", "TAMPER_ATTEMPT", "edited log", ("ref-1",))
    assert _status_body(client)["last_check_at"] == ""
    resp = client.post("/api/v1/watcher/rules/rule-tamper/evaluate",
                       json={"project_id": PID},
                       headers={"x-ui-session-token": TOKEN})
    assert resp.status_code == 200, resp.text
    body = _status_body(client)
    assert body["watcher_calls"] >= 1, body
    assert body["last_check_at"] != "", body
    assert body["checks_done"] == 1, body
    assert body["alerts_raised"] == 1, body


def test_quiet_evaluate_records_a_check_without_alert():
    client = _client()
    _journal.append_event(PID, "watcher", "SERVICE_STATE", "boot", ())
    resp = client.post("/api/v1/watcher/rules/rule-tamper/evaluate",
                       json={"project_id": PID},
                       headers={"x-ui-session-token": TOKEN})
    assert resp.status_code == 200, resp.text
    body = _status_body(client)
    assert body["last_check_at"] != "", body
    assert body["checks_done"] == 1 and body["alerts_raised"] == 0, body


def test_engine_tick_still_counts_once_per_card():
    _client()
    _journal.append_event(PID, "watcher", "SERVICE_STATE", "boot", ())
    before = _status.get(PID).checks_done
    tick = _engine.tick(PID)
    assert _status.get(PID).checks_done == before + len(tick.fired)
