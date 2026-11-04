"""PLANB W4: the Watcher runs on the model pinned on the watcher role.

Served path: PUT /api/v1/roles/pools (role watcher, the route the role
editor uses), then POST /api/v1/watcher/rules/{id}/evaluate makes one real
model call through the role's adapter; GET /api/v1/watcher/status then
names the model and counts the call plus tokens. Fake only at the model
adapter seam.
"""

import os
import sys
from types import SimpleNamespace

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest
from fastapi.testclient import TestClient

from agent_si.backend.app import create_app
from agent_si.watcher import engine as _engine
from agent_si.watcher import journal as _journal
from agent_si.watcher import rules as _rules
from agent_si.watcher import status as _status

PROJECT = "planb-w4"
TOKEN = "planb-w4-token"
HEADERS = {"x-ui-session-token": TOKEN, "x-actor": "ui"}


@pytest.fixture(autouse=True)
def _lane():
    from agent_si.runtime import manager as _manager

    _journal.reset_state()
    _rules.reset_state()
    _engine.reset_state()
    _status.reset_state()
    prev = _manager._BUDGET_GATE
    yield
    _manager.set_budget_gate(prev)
    _journal.reset_state()
    _rules.reset_state()
    _engine.reset_state()
    _status.reset_state()


class _Adapter:
    def __init__(self, reply):
        self.reply = reply
        self.seen = []

    def invoke(self, messages, params=None):
        self.seen.append(messages)
        return SimpleNamespace(
            output_text=self.reply,
            usage={"input_tokens": 40, "output_tokens": 3})


class _Factory:
    def __init__(self, reply):
        self.adapter = _Adapter(reply)
        self.built = []

    def __call__(self, role, provider, model):
        self.built.append((role, provider, model))
        return self.adapter

    def connected_providers(self):
        return ["ollama"]


def _client(factory, tmp_path):
    app = create_app({"testing": True, "ui_session_token": TOKEN,
                      "store_dir": str(tmp_path)})
    app.state.devrun_adapter_factory = factory
    from agent_si.runtime import manager as _manager

    _manager._BUDGET_GATE.configure_project(
        PROJECT, "USD", "1000000.00", "900000.00", "1000000.00")
    return TestClient(app)


def _pin_watcher(client):
    resp = client.put("/api/v1/roles/pools", headers=HEADERS, json={
        "project_id": PROJECT, "role": "watcher", "mode": "PINNED",
        "provider": "ollama", "model": "ollama/muse-glimmer:30b",
        "pool": [], "strategy": "AUTO"})
    assert resp.status_code == 200, resp.text


def _abnormal():
    _journal.append_event(PROJECT, "watcher", "SERVICE_STATE", "boot", ())
    _journal.append_event(PROJECT, "watcher", "GUARD_BLOCK", "blocked", ())


def _status_of(client):
    resp = client.get("/api/v1/watcher/status",
                      params={"project_id": PROJECT})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_pinned_watcher_makes_one_real_call_and_card_shows_it(tmp_path):
    factory = _Factory('{"pick": 1}')
    client = _client(factory, tmp_path)
    _pin_watcher(client)
    _abnormal()
    assert _status_of(client)["watcher_model"] == "Rules only"
    resp = client.post("/api/v1/watcher/rules/rule-guard/evaluate",
                       json={"project_id": PROJECT}, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert len(factory.adapter.seen) == 1
    assert factory.built == [("watcher", "ollama", "ollama/muse-glimmer:30b")]
    body = _status_of(client)
    assert body["watcher_model"] == "muse-glimmer:30b"
    assert body["watcher_calls"] == 1
    assert body["watcher_tokens"] == 43
    rows = _journal.stored_rows(PROJECT, "WATCH_DECISION")
    assert "model=muse-glimmer:30b action=signal-higher-level" in \
        rows[-1].summary


def test_garbage_reply_still_counts_and_uses_default_action(tmp_path):
    factory = _Factory("no json here")
    client = _client(factory, tmp_path)
    _pin_watcher(client)
    _abnormal()
    resp = client.post("/api/v1/watcher/rules/rule-guard/evaluate",
                       json={"project_id": PROJECT}, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = _status_of(client)
    assert body["watcher_calls"] == 1 and body["watcher_tokens"] == 43
    assert "garbage reply" in _journal.stored_rows(
        PROJECT, "WATCH_DECISION")[-1].summary


def test_no_pin_means_rules_only_and_no_call(tmp_path):
    factory = _Factory('{"pick": 0}')
    client = _client(factory, tmp_path)
    _abnormal()
    resp = client.post("/api/v1/watcher/rules/rule-guard/evaluate",
                       json={"project_id": PROJECT}, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert factory.adapter.seen == []
    body = _status_of(client)
    assert body["watcher_model"] == "Rules only"
    assert body["watcher_calls"] == 0


