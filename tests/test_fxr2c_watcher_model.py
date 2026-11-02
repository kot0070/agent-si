"""FXR2C-2 RED: watcher uses its model (served path, fake local transport).

Normal verdict: no row, no call, no load. Abnormal verdict: ONE call to
the configured watcher model for one action + params from the rule's
allowed list; journal names the exact model; budget + telemetry row on
that call; garbage reply falls back to the default; never outside list.
Topbar/status truth: model name, or "Rules only".
"""

import os
import sys

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

TESTID = "fxr2c-watcher"
TOKEN = "fxr2c-token"


def _settings():
    return {"testing": True, "ui_session_token": TOKEN}


def _auth():
    return {"x-ui-session-token": TOKEN}


@pytest.fixture(autouse=True)
def _lane():
    from types import SimpleNamespace as _NS

    class _AllowGate:
        def get_state(self, pid):
            return _NS(hard_limit="1000", spent="0", reserved="0",
                       currency="USD", provider_spend_caps={})

        def compare_and_reserve(self, *args, **kwargs):
            return None

        def release(self, *args, **kwargs):
            return None

    from agent_si.runtime import manager as _manager_home
    _prev_gate = getattr(_manager_home, "_BUDGET_GATE", None)
    _manager_home._BUDGET_GATE = _AllowGate()
    _journal.reset_state()
    _rules.reset_state()
    _engine.reset_state()
    _status.reset_state()
    yield
    try:
        _manager_home._BUDGET_GATE = _prev_gate
    except Exception:
        pass
    _journal.reset_state()
    _rules.reset_state()
    _engine.reset_state()
    _status.reset_state()


class _FakeLocalTransport:
    """Fake local model transport: records calls, answers in-list."""

    def __init__(self, script=None, params=(), usage=None):
        self.calls = []
        self.script = script
        self.params = tuple(params)
        self.usage = dict(usage or {"input_tokens": 10,
                                    "output_tokens": 5})

    def __call__(self, model, rule_id, allowed):
        self.calls.append({"model": model, "rule_id": rule_id,
                           "allowed": list(allowed)})
        script = self.script
        params = tuple(self.params)
        if script is None:
            script, params = allowed[0]
        return {"script": script, "params": params, "usage": dict(self.usage)}


def _configure(transport, **kwargs):
    settings = {"transport": transport, "local_model": "fx-local-1",
                "local_connected": True, "cloud_model": "fx-cloud-1",
                "cloud_connected": False, "cloud_fallback": False}
    settings.update(kwargs)
    _rules.configure_watcher_model(**settings)


def _fresh_project(pid):
    _journal.append_event(pid, "watcher", "SERVICE_STATE", "boot", ())


def test_idle_normal_verdict_no_row_no_call():
    transport = _FakeLocalTransport()
    _configure(transport)
    pid = "fxr2c-idle-1"
    _fresh_project(pid)
    before = list(_journal.stored_rows(pid, "WATCH_DECISION"))
    decision = _rules.evaluate(pid, "rule-tamper")
    assert decision.verdict == _rules.WatchVerdict.ALLOW
    assert transport.calls == [], "idle verdict must make no model call"
    after = list(_journal.stored_rows(pid, "WATCH_DECISION"))
    assert after == before, "idle verdict must write no row"
    assert decision.journal_entry_id == ""


def test_served_idle_evaluate_no_call_no_row():
    transport = _FakeLocalTransport()
    _configure(transport)
    client = TestClient(create_app(_settings()))
    pid = "fxr2c-idle-2"
    _fresh_project(pid)
    before = len(_journal.stored_rows(pid, "WATCH_DECISION"))
    resp = client.post("/api/v1/watcher/rules/rule-tamper/evaluate",
                       json={"project_id": pid}, headers=_auth())
    assert resp.status_code == 200, resp.text
    assert resp.json()["verdict"] == "ALLOW"
    assert transport.calls == []
    assert len(_journal.stored_rows(pid, "WATCH_DECISION")) == before


def test_abnormal_one_call_names_model_and_bills(tmp_path):
    from agent_si.telemetry import run_store as _store

    prev_dir = _store.bound_store_dir()
    _store.bind_store_dir(str(tmp_path / "telemetry"))
    transport = _FakeLocalTransport()
    _configure(transport)
    pid = "fxr2c-abn-1"
    _journal.append_event(pid, "agent-x", "TAMPER_ATTEMPT",
                          "edited log", ("ref-1",))
    decision = _rules.evaluate(pid, "rule-tamper")
    assert decision.verdict == _rules.WatchVerdict.BLOCK
    assert len(transport.calls) == 1, transport.calls
    call = transport.calls[0]
    assert call["model"] == "fx-local-1"
    rows = list(_journal.stored_rows(pid, "WATCH_DECISION"))
    assert len(rows) == 1
    assert "fx-local-1" in rows[0].summary, rows[0].summary
    assert decision.journal_entry_id == rows[0].entry_id
    events = [e for e in _store.load_store().get("telemetry_events", [])
              if e.get("event_type") == "PROVIDER_USAGE_REPORTED"
              and e.get("run_id") == decision.decision_id]
    assert events, "no telemetry row for the watcher model call"
    try:
        pass
    finally:
        try:
            _store.bind_store_dir(prev_dir)
        except Exception:
            pass


def test_garbage_reply_falls_back_to_default():
    transport = _FakeLocalTransport(script="evil-outside-list",
                                    params=("--pwn", "1"))
    _configure(transport)
    pid = "fxr2c-abn-2"
    _journal.append_event(pid, "agent-x", "TAMPER_ATTEMPT",
                          "edited log", ("ref-1",))
    _rules.evaluate(pid, "rule-tamper")
    assert len(transport.calls) == 1
    rows = list(_journal.stored_rows(pid, "WATCH_DECISION"))
    assert len(rows) == 1
    default = _rules.allowed_actions("rule-tamper")[0]
    assert default[0] in rows[0].summary, rows[0].summary


def test_no_model_default_action_journal_line():
    _configure(None)
    pid = "fxr2c-abn-3"
    _journal.append_event(pid, "agent-x", "TAMPER_ATTEMPT",
                          "edited log", ("ref-1",))
    _rules.evaluate(pid, "rule-tamper")
    rows = list(_journal.stored_rows(pid, "WATCH_DECISION"))
    assert len(rows) == 1
    assert "no watcher model: default action" in rows[0].summary


def test_cloud_only_with_fallback_setting():
    local = _FakeLocalTransport()
    cloud = _FakeLocalTransport()
    _rules.configure_watcher_model(
        transport=cloud, local_model="fx-local-1", local_connected=False,
        cloud_model="fx-cloud-9", cloud_connected=True,
        cloud_fallback=False)
    pid = "fxr2c-abn-4"
    _journal.append_event(pid, "agent-x", "TAMPER_ATTEMPT",
                          "edited log", ("ref-1",))
    _rules.evaluate(pid, "rule-tamper")
    assert cloud.calls == [], "cloud must not answer without fallback on"
    rows = list(_journal.stored_rows(pid, "WATCH_DECISION"))
    assert "no watcher model: default action" in rows[0].summary
    _rules.configure_watcher_model(
        transport=cloud, local_model="fx-local-1", local_connected=False,
        cloud_model="fx-cloud-9", cloud_connected=True,
        cloud_fallback=True)
    _journal.append_event(pid, "agent-x", "TAMPER_ATTEMPT",
                          "again", ("ref-2",))
    _rules.evaluate(pid, "rule-tamper")
    assert len(cloud.calls) == 1
    assert cloud.calls[0]["model"] == "fx-cloud-9"
    _ = local


def test_guard_resting_block_is_normal_trigger_is_not():
    transport = _FakeLocalTransport()
    _configure(transport)
    pid = "fxr2c-guard-1"
    _fresh_project(pid)
    decision = _rules.evaluate(pid, "rule-guard")
    assert decision.verdict == _rules.WatchVerdict.BLOCK
    assert transport.calls == [], "resting guard BLOCK must not call"
    assert list(_journal.stored_rows(pid, "WATCH_DECISION")) == []
    assert decision.journal_entry_id == ""
    _journal.append_event(pid, "agent-x", "GUARD_BLOCK",
                          "escape", ("path-1",))
    flagged = _rules.evaluate(pid, "rule-guard")
    assert flagged.verdict == _rules.WatchVerdict.BLOCK
    assert len(transport.calls) == 1
    rows = list(_journal.stored_rows(pid, "WATCH_DECISION"))
    assert len(rows) == 1
    assert "fx-local-1" in rows[0].summary


def test_status_truth_model_name_or_rules_only():
    _configure(_FakeLocalTransport())
    idle = "fxr2c-st-1"
    _fresh_project(idle)
    _rules.evaluate(idle, "rule-tamper")
    assert _status.get(idle).watcher_model == "Rules only"
    hot = "fxr2c-st-2"
    _journal.append_event(hot, "agent-x", "TAMPER_ATTEMPT",
                          "edited log", ("ref-1",))
    _rules.evaluate(hot, "rule-tamper")
    assert _status.get(hot).watcher_model == "fx-local-1"


def test_served_status_carries_watcher_model():
    _configure(_FakeLocalTransport())
    client = TestClient(create_app(_settings()))
    try:
        from types import SimpleNamespace as _NS

        class _AllowGate:
            def get_state(self, pid):
                return _NS(hard_limit="1000", spent="0", reserved="0",
                           currency="USD", provider_spend_caps={})

            def compare_and_reserve(self, *args, **kwargs):
                return None

            def release(self, *args, **kwargs):
                return None

        from agent_si.runtime import manager as _manager_home
        _manager_home._BUDGET_GATE = _AllowGate()
    except Exception:
        pass
    pid = "fxr2c-st-3"
    _journal.append_event(pid, "agent-x", "TAMPER_ATTEMPT",
                          "edited log", ("ref-1",))
    resp = client.post("/api/v1/watcher/rules/rule-tamper/evaluate",
                       json={"project_id": pid}, headers=_auth())
    assert resp.status_code == 200, resp.text
    status = client.get("/api/v1/watcher/status",
                        params={"project_id": pid})
    assert status.status_code == 200, status.text
    assert status.json()["watcher_model"] == "fx-local-1"
