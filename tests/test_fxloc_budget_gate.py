"""FXLOC C5: budget gate fails closed, never fail-open.

admit_budget_call: gate None raises BudgetBlockedError; unknown
projects raise; unexpected gate errors propagate (never swallowed).
The chat orchestration path streams a budget_stop with plain text and
never invokes the provider. A real gate with a configured project
admits (the fixture pattern neighbours must use).
"""
from __future__ import annotations

import json as _json
import os
import sys

import pytest

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import chat_stream as _chat_stream  # noqa: E402
from agent_si.backend.chat_stream import (  # noqa: E402
    ChatStreamRequest,
    build_bridge,
)
from agent_si.budget.gate import (  # noqa: E402
    BudgetBlockedError,
    BudgetGate,
)
from agent_si.providers.adapters.base import (  # noqa: E402
    AdapterConfig,
    make_secret_ref,
)
from agent_si.providers.adapters.mock_provider import (  # noqa: E402
    MockProviderAdapter,
)
from agent_si.runtime import manager as _manager  # noqa: E402
from agent_si.runtime.devrun import roles as _roles  # noqa: E402

_PROJECT = "fxloc-c5-proj"


@pytest.fixture()
def _no_global_gate():
    prev = getattr(_manager, "_BUDGET_GATE", None)
    _manager.set_budget_gate(None)
    yield
    _manager.set_budget_gate(prev)


def _real_gate(*projects):
    gate = BudgetGate()
    for project in projects:
        gate.configure_project(project, "USD", "1000.00", "900.00",
                               "1000.00")
    return gate


def _mock(canned=("canned one.",)):
    config = AdapterConfig(
        provider_id="mock", instance_id="fxloc-c5-test",
        model="mock-canned",
        secret_ref=make_secret_ref(
            secret_id="mock-secret", provider_id="mock"))
    return MockProviderAdapter(config, transport=None, canned=canned)


def test_admit_with_gate_none_raises(_no_global_gate):
    with pytest.raises(BudgetBlockedError):
        _manager.admit_budget_call(
            None, _PROJECT, "mock", "task-1", "run-1", "admit-run-1-chat")
    with pytest.raises(BudgetBlockedError):
        _roles.admit_role_call(
            None, project_id=_PROJECT, task_id="task-1", run_id="run-1",
            role="chat", provider_id="mock")


def test_admit_unknown_project_raises():
    gate = _real_gate()
    with pytest.raises(BudgetBlockedError):
        _manager.admit_budget_call(
            gate, "fxloc-c5-ghost", "mock", "task-1", "run-1",
            "admit-run-1-chat")


def test_admit_gate_error_propagates():
    class _BoomGate:
        def get_state(self, project_id):
            raise RuntimeError("gate boom")

    with pytest.raises(RuntimeError, match="gate boom"):
        _manager.admit_budget_call(
            _BoomGate(), _PROJECT, "mock", "task-1", "run-1",
            "admit-run-1-chat")


def test_real_gate_admits_configured_project():
    gate = _real_gate(_PROJECT)
    assert _manager.admit_budget_call(
        gate, _PROJECT, "mock", "task-1", "run-1",
        "admit-run-1-chat") is None
    _roles.admit_role_call(
        gate, project_id=_PROJECT, task_id="task-1", run_id="run-1",
        role="chat", provider_id="mock")


def _events(iterator):
    text = b"".join(iterator).decode("utf-8")
    out = []
    for line in text.splitlines():
        if line.startswith("data:"):
            out.append(_json.loads(line[len("data:"):].strip()))
    return out


def test_orchestration_streams_budget_stop_without_gate(
        _no_global_gate, monkeypatch):
    monkeypatch.setattr(
        _chat_stream, "_load_manager_run_task_streamed", lambda: None)
    mock = _mock()
    bridge = build_bridge(provider_adapter=mock)
    request = ChatStreamRequest(
        project=_PROJECT, task="task-c5", message="hello budget",
        actor="tester-c5")
    _stream_id, iterator = bridge.run(request)
    events = _events(iterator)
    kinds = [event.get("type") for event in events]
    assert kinds[0] == "start", kinds
    assert kinds[-1] == "budget_stop", kinds
    terminal = events[-1]
    assert str(terminal.get("reason") or terminal.get("text") or "")
    assert mock.turns_served == 0, "blocked calls never invoke the provider"


def test_orchestration_runs_with_real_gate(_no_global_gate, monkeypatch):
    monkeypatch.setattr(
        _chat_stream, "_load_manager_run_task_streamed", lambda: None)
    prev = getattr(_manager, "_BUDGET_GATE", None)
    _manager.set_budget_gate(_real_gate(_PROJECT))
    try:
        mock = _mock()
        bridge = build_bridge(provider_adapter=mock)
        request = ChatStreamRequest(
            project=_PROJECT, task="task-c5", message="hello budget",
            actor="tester-c5")
        _stream_id, iterator = bridge.run(request)
        kinds = [event.get("type") for event in _events(iterator)]
        assert kinds[0] == "start", kinds
        assert kinds[-1] == "done", kinds
        assert mock.turns_served == 1
    finally:
        _manager.set_budget_gate(prev)
