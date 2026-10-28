"""K02R4 manager: streamed run_task_streamed plus agents-live rows.

Proves the four contract points against the real chain (guarded
dispatch, turn budget, SDK retries 0, live-row sink) with the K04
MockProviderAdapter at the provider boundary only: no network, no
keys, no token in URL. Reads need no token.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import agents_live  # noqa: E402
from agent_si.backend.agents_live import live_rows  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration.graph import TaskPlanner  # noqa: E402
from agent_si.backend.orchestration.steplimits import (  # noqa: E402
    apply_steplimit_config_change,
)
from agent_si.backend.runtime_manager import (  # noqa: E402
    RunEvent,
    run_task_streamed,
)
from agent_si.providers.adapters.base import (  # noqa: E402
    AdapterConfig,
    make_secret_ref,
)
from agent_si.providers.adapters.mock_provider import (  # noqa: E402
    MockProviderAdapter,
)
from agent_si.runtime.manager import (  # noqa: E402
    ProviderUnboundError,
    bound_provider_adapter,
)
from agent_si.sdk_adapter.sdk_adapter import (  # noqa: E402
    OpenAIAgentsSDKAdapter,
    SdkClientConfig,
    SdkClientConfigError,
)

TEST_TOKEN = "k02r4-manager-token"
TEST_SETTINGS = {"testing": True, "ui_session_token": TEST_TOKEN}


def _mock_adapter(canned=None):
    config = AdapterConfig(
        provider_id="mock",
        instance_id="k02r4-manager-test",
        model="mock-canned",
        secret_ref=make_secret_ref(
            secret_id="mock-secret", provider_id="mock"),
    )
    if canned is None:
        return MockProviderAdapter(config, transport=None)
    return MockProviderAdapter(config, transport=None, canned=canned)


class _ContinueMock(MockProviderAdapter):
    """Mock that asks for another turn (finish continue, still mock)."""

    def invoke(self, messages, params=None, max_turns=8):
        response = super().invoke(messages, params=params,
                                   max_turns=max_turns)
        response.finish_reason = "continue"
        return response


def _planned_graph(subtask_id="k02r4-sub-001"):
    planner = TaskPlanner()
    _plan_ref, graph = planner.plan(
        "pkg-k02r4",
        "k02r4 manager run",
        [{"subtask_id": subtask_id, "goal": "serve one canned turn",
          "task_class": "general", "risk": "LOW"}],
    )
    return graph


def _agent_task(subtask_id="k02r4-sub-001"):
    return {
        "agent_task_id": "agent-task-k02r4",
        "subtask_id": subtask_id,
        "agent_id": "agent-k02r4",
        "contract_hash": "hash-k02r4",
    }


def _configure_budget(project_id, task_max_steps):
    outcome = apply_steplimit_config_change({
        "project_id": project_id,
        "task_max_steps": task_max_steps,
        "chat_max_steps": task_max_steps,
        "authority": "M-MANAGER-CONT",
        "reason": "K02R4 manager budget test",
    })
    assert outcome.applied, outcome.reason


def _terminal(events):
    assert events, "a streamed run always ends with a terminal event"
    return events[-1]


# -- budget caps turns ------------------------------------------------------


def test_budget_caps_turns():
    project_id = "k02r4-budget"
    _configure_budget(project_id, 2)
    agents_live.clear_live_rows()
    mock = _ContinueMock(
        _mock_adapter().config, transport=None,
        canned=("turn one.", "turn two.", "turn three."),
    )
    events = list(run_task_streamed(
        None,
        agent_task=_agent_task(),
        graph=_planned_graph(),
        provider_adapter=mock,
        project_id=project_id,
        task_id="task-k02r4-budget",
        message="keep going",
        manager_id="mgr-k02r4",
    ))
    assert all(isinstance(event, RunEvent) for event in events)
    terminal = _terminal(events)
    assert terminal.event == "budget_stop"
    turns = [event for event in events if event.event == "turn"]
    assert len(turns) == 2
    assert [event.turn for event in turns] == [1, 2]
    assert mock.turns_served == 2
    assert terminal.data["budget"] == 2
    assert terminal.data["turns"] == 2


# -- SDK layer retries 0 ----------------------------------------------------


def test_sdk_retries_zero_at_client_layer():
    agents_live.clear_live_rows()
    mock = _mock_adapter(canned=("Mock manager reply.",))
    events = list(run_task_streamed(
        None,
        agent_task=_agent_task(),
        graph=_planned_graph(),
        provider_adapter=mock,
        project_id="k02r4-sdk",
        task_id="task-k02r4-sdk",
        message="hello manager",
        manager_id="mgr-k02r4",
        max_agent_steps=3,
    ))
    terminal = _terminal(events)
    assert terminal.event == "done"
    turns = [event for event in events if event.event == "turn"]
    assert len(turns) == 1
    assert turns[0].data["client_max_retries"] == 0
    assert turns[0].data["mock"] is True
    assert mock.turns_served == 1
    with pytest.raises(SdkClientConfigError):
        OpenAIAgentsSDKAdapter(
            client_config=SdkClientConfig(max_retries=1))


# -- streamed events reach the live rows ------------------------------------


def test_streamed_events_reach_live_rows_and_route():
    agents_live.clear_live_rows()
    mock = _mock_adapter(canned=("Mock live reply.",))
    events = list(run_task_streamed(
        None,
        agent_task=_agent_task(),
        graph=_planned_graph(),
        provider_adapter=mock,
        project_id="k02r4-live",
        task_id="task-k02r4-live",
        message="hello live",
        manager_id="mgr-k02r4",
        max_agent_steps=3,
    ))
    assert _terminal(events).event == "done"
    assert len(events) > 1
    kinds = {event.event for event in events}
    assert {"start", "turn", "done"} <= kinds
    payload = live_rows()
    assert set(payload) == {"agents"}
    rows = {row["scope"]: row for row in payload["agents"]}
    assert rows, "a real streamed run records live rows"
    assert "agent-k02r4" in {row["agent"] for row in rows.values()}
    app = create_app(dict(TEST_SETTINGS))
    client = TestClient(app)
    resp = client.get("/api/v1/agents/live")
    assert resp.status_code == 200
    served = {row["scope"]: row for row in resp.json()["agents"]}
    assert served, "the live route serves rows from a real streamed run"
    assert "agent-k02r4" in {row["agent"] for row in served.values()}


# -- a subtask-less task never executes -------------------------------------


def test_subtaskless_task_never_executes():
    agents_live.clear_live_rows()
    mock = _mock_adapter()
    bare = {
        "agent_task_id": "agent-task-bare",
        "agent_id": "agent-k02r4",
        "contract_hash": "hash-k02r4",
    }
    events = list(run_task_streamed(
        None,
        agent_task=bare,
        graph=_planned_graph(),
        provider_adapter=mock,
        project_id="k02r4-dispatch",
        task_id="task-k02r4-dispatch",
        message="must not run",
        manager_id="mgr-k02r4",
        max_agent_steps=3,
    ))
    assert len(events) == 1
    assert events[0].event == "dispatch_rejected"
    assert mock.turns_served == 0
    unplanned = _agent_task(subtask_id="not-planned")
    events = list(run_task_streamed(
        None,
        agent_task=unplanned,
        graph=_planned_graph(),
        provider_adapter=mock,
        project_id="k02r4-dispatch",
        task_id="task-k02r4-dispatch",
        message="must not run",
        manager_id="mgr-k02r4",
        max_agent_steps=3,
    ))
    assert len(events) == 1
    assert events[0].event == "dispatch_rejected"
    assert mock.turns_served == 0
    assert bound_provider_adapter() is None
    with pytest.raises(ProviderUnboundError):
        list(run_task_streamed(
            None,
            agent_task=_agent_task(),
            graph=_planned_graph(),
            provider_adapter=None,
            project_id="k02r4-dispatch",
            task_id="task-k02r4-dispatch",
            message="must not run",
            manager_id="mgr-k02r4",
            max_agent_steps=3,
        ))


# -- assurance hook fires before execution ----------------------------------


def test_assurance_hook_fires_before_execution():
    agents_live.clear_live_rows()
    order = []

    def _hook(call):
        order.append(("hook", call["turn"], call["decision_id"]))
        return True

    mock = _mock_adapter(canned=("Mock hook reply.",))
    real_invoke = mock.invoke

    def _watched_invoke(messages, params=None, max_turns=8):
        order.append(("invoke", mock.turns_served))
        return real_invoke(messages, params=params, max_turns=max_turns)

    mock.invoke = _watched_invoke
    events = list(run_task_streamed(
        None,
        agent_task=_agent_task(),
        graph=_planned_graph(),
        provider_adapter=mock,
        project_id="k02r4-hook",
        task_id="task-k02r4-hook",
        message="hello hook",
        manager_id="mgr-k02r4",
        max_agent_steps=3,
        assurance_hook=_hook,
    ))
    assert _terminal(events).event == "done"
    assert order[0][0] == "hook"
    assert order[1] == ("invoke", 0)
    tool_calls = [event for event in events if event.event == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0].data["decision_id"]
    assert tool_calls[0].data["retry_policy_ref"] == "retry:default"
    assert _terminal(events).data["assurance_calls"] == 1
