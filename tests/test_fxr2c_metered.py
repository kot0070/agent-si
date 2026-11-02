"""FXR2C-3 RED: every model call is admitted, charged and telemetered.

chat_stream._orchestration_events and code_executor AI-kind route through
the same admit + charge + telemetry as devrun roles.invoke_owned, with
the role named. A hard cap holds on each entry: the provider is never
invoked when the budget refuses.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest


def _event_types(events):
    import json as _json

    types = []
    for event in events:
        try:
            text = bytes(event).decode("utf-8").strip()
        except Exception:
            continue
        if text.startswith("data:"):
            text = text[5:].strip()
        try:
            types.append(_json.loads(text))
        except Exception:
            continue
    return types


class _FakeResponse:
    def __init__(self, text="judged"):
        self.output_text = text
        self.mock = True
        self.finish_reason = "stop"
        self.usage = {"input_tokens": 100, "output_tokens": 50}


class _FakeGateway:
    def __init__(self, text="judged"):
        self.calls = []
        self.config = type("Config", (),
                           {"provider_id": "fake-prov",
                            "model": "fake-model"})()
        self._text = text

    def invoke(self, messages):
        self.calls.append(list(messages))
        return _FakeResponse(self._text)


def _gate_with_hard_limit(tmp_path, hard_limit):
    from agent_si.budget.gate import BudgetGate
    from agent_si.runtime import manager as _manager

    gate = BudgetGate(store_dir=str(tmp_path / "ledger"))
    gate.configure_project("fxr2c-m", "USD", hard_limit, hard_limit,
                           hard_limit)
    prev = getattr(_manager, "_BUDGET_GATE", None)
    _manager.set_budget_gate(gate)
    return gate, prev


@pytest.fixture()
def _telemetry_iso(tmp_path):
    from agent_si.telemetry import run_store as _store

    prev = _store.bound_store_dir()
    _store.bind_store_dir(str(tmp_path / "telemetry"))
    try:
        yield
    finally:
        try:
            _store.bind_store_dir(prev)
        except Exception:
            pass


def test_chat_orchestration_hard_cap_blocks_provider(
        tmp_path, _telemetry_iso):
    from agent_si.backend import chat_stream as _chat
    from agent_si.runtime import manager as _manager

    gate, prev = _gate_with_hard_limit(tmp_path, "0.00")
    try:
        gateway = _FakeGateway()
        bridge = _chat.build_bridge(provider_adapter=gateway)
        request = _chat.ChatStreamRequest(
            project="fxr2c-m", task="t", message="hi", actor="user")
        events = list(bridge._orchestration_events(
            "s-1", "run-1", request, {"cancelled": False}))
        assert gateway.calls == [], "provider ran past a hard cap of 0"
        assert any(
            b.get("type") == "error" for b in _event_types(events)), events
    finally:
        _manager.set_budget_gate(prev)


def test_chat_orchestration_meters_role_named(tmp_path, _telemetry_iso):
    from agent_si.backend import chat_stream as _chat
    from agent_si.runtime import manager as _manager
    from agent_si.runtime.devrun import roles as _roles
    from agent_si.telemetry import run_store as _store

    gate, prev = _gate_with_hard_limit(tmp_path, "100.00")
    seen = []
    prev_metered = list(_roles.metered_calls())
    try:
        gateway = _FakeGateway()
        bridge = _chat.build_bridge(provider_adapter=gateway)
        request = _chat.ChatStreamRequest(
            project="fxr2c-m", task="t", message="hi", actor="user")
        events = list(bridge._orchestration_events(
            "s-1", "run-1", request, {"cancelled": False}))
        assert len(gateway.calls) == 1
        assert any(
            b.get("type") == "done" for b in _event_types(events))
        fresh = [c for c in _roles.metered_calls()[len(prev_metered):]]
        assert fresh, "no metered call logged for chat entry"
        assert fresh[0]["role"] == "chat", fresh[0]
        assert fresh[0]["provider"] == "fake-prov"
        seen.append(fresh[0])
        events_store = _store.load_store().get("telemetry_events", [])
        assert any(e.get("event_type") == "PROVIDER_USAGE_REPORTED"
                   and e.get("run_id") == "run-1" for e in events_store)
    finally:
        _manager.set_budget_gate(prev)
    assert seen and seen[0]["role"] == "chat"


def test_code_executor_ai_hard_cap_blocks_provider(
        tmp_path, _telemetry_iso):
    from agent_si.runtime import manager as _manager
    from agent_si.test_runners import code_executor as _exec

    gate, prev = _gate_with_hard_limit(tmp_path, "0.00")
    try:
        gateway = _FakeGateway()
        outcome = _exec.execute_catalog_test(
            test_id="judge-1", kind="AI", intent="is this fine?",
            project_id="fxr2c-m", gateway=gateway, runner_id="r1",
            data_root=str(tmp_path / "data"))
        assert gateway.calls == [], "AI gateway ran past a hard cap of 0"
        assert outcome["status"] == "BLOCKED", outcome
        assert "budget" in str(outcome.get("reason", "")).lower(), outcome
    finally:
        _manager.set_budget_gate(prev)


def test_code_executor_ai_meters_role_named(tmp_path, _telemetry_iso):
    from agent_si.runtime import manager as _manager
    from agent_si.runtime.devrun import roles as _roles
    from agent_si.telemetry import run_store as _store
    from agent_si.test_runners import code_executor as _exec

    gate, prev = _gate_with_hard_limit(tmp_path, "100.00")
    prev_metered = list(_roles.metered_calls())
    try:
        gateway = _FakeGateway("solid pass")
        outcome = _exec.execute_catalog_test(
            test_id="judge-2", kind="AI", intent="is this fine?",
            project_id="fxr2c-m", gateway=gateway, runner_id="r1",
            data_root=str(tmp_path / "data"))
        assert outcome["status"] == "PASS", outcome
        assert len(gateway.calls) == 1
        fresh = [c for c in _roles.metered_calls()[len(prev_metered):]]
        assert fresh, "no metered call logged for AI-test entry"
        assert fresh[0]["role"] == "ai-test", fresh[0]
        events_store = _store.load_store().get("telemetry_events", [])
        assert any(e.get("event_type") == "PROVIDER_USAGE_REPORTED"
                   and e.get("provider") == "fake-prov"
                   for e in events_store)
    finally:
        _manager.set_budget_gate(prev)
