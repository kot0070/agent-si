"""FXASK2 served plumbing: the approval event carries the held tool's id.

The install hold's tool identity is the guarded call's tool_name
(src/agent_si/sdk_adapter/tool_guard.py:152 park); the chat approval
event and the manager (task-run) held-done payload forward it as
``tool_id`` so the window answers POST /api/v1/permissions/check
once per tool. Holds that name no tool carry no tool_id field.
"""

import json
import os
import sys
from types import SimpleNamespace

import pytest

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.chat_stream import (  # noqa: E402
    ChatStreamRequest,
    ManagerSdkBridge,
    _manager_event_payload,
)
from agent_si.runtime.manager import RunEvent  # noqa: E402
from agent_si.sdk_adapter.orchestration_interface import (  # noqa: E402
    OrchestrationInterface,
    TurnResult,
)

TOOL = "helper-tool"


def _payloads(chunks):
    events = []
    for chunk in chunks:
        text = chunk.decode("utf-8")
        for line in text.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:"):].strip()))
    return events


def _request():
    return ChatStreamRequest(
        project="p-1", task="t-1", message="please install the helper",
        actor="tester",
    )


def test_turn_result_tool_id_defaults_empty():
    result = TurnResult(
        run_id="r", output_ref="o", executed=False,
        approval_requested=True, treated_as_data=False,
    )
    assert result.tool_id == ""


def test_manager_payload_forwards_tool_id_only_when_present():
    with_tool = _manager_event_payload(
        "s", "r",
        RunEvent(event="done", turn=1, subtask_id="s", detail="held", data={
            "executed": False, "approval_requested": True,
            "reason": "parked", "tool_id": TOOL}),
    )
    assert with_tool["tool_id"] == TOOL
    assert with_tool["approval_requested"] is True
    without_tool = _manager_event_payload(
        "s", "r",
        RunEvent(event="done", turn=1, subtask_id="s", detail="held", data={
            "executed": False, "approval_requested": True,
            "reason": "parked"}),
    )
    assert "tool_id" not in without_tool


def test_orchestration_approval_event_carries_tool_id(monkeypatch):
    held = TurnResult(
        run_id="r", output_ref="", executed=False,
        approval_requested=True, treated_as_data=False,
        reason="APPROVAL_WAITING", tool_id=TOOL,
    )
    monkeypatch.setattr(
        OrchestrationInterface, "run_turn", lambda self, req: held)
    provider = SimpleNamespace(
        invoke=lambda messages: (_ for _ in ()).throw(AssertionError(
            "provider must not run on a held turn")),
        config=SimpleNamespace(provider_id="p", model="m"),
    )
    bridge = ManagerSdkBridge(provider_adapter=provider)
    events = _payloads(list(bridge._orchestration_events(
        "srv", "r", _request(), {"cancelled": False})))
    approvals = [e for e in events if e.get("type") == "approval"]
    assert len(approvals) == 1
    assert approvals[0]["tool_id"] == TOOL


def test_orchestration_approval_event_omits_missing_tool_id(monkeypatch):
    held = TurnResult(
        run_id="r", output_ref="", executed=False,
        approval_requested=True, treated_as_data=True,
        reason="B-001 hold",
    )
    monkeypatch.setattr(
        OrchestrationInterface, "run_turn", lambda self, req: held)
    provider = SimpleNamespace(
        invoke=lambda messages: (_ for _ in ()).throw(AssertionError(
            "provider must not run on a held turn")),
        config=SimpleNamespace(provider_id="p", model="m"),
    )
    bridge = ManagerSdkBridge(provider_adapter=provider)
    events = _payloads(list(bridge._orchestration_events(
        "srv", "r", _request(), {"cancelled": False})))
    approvals = [e for e in events if e.get("type") == "approval"]
    assert len(approvals) == 1
    assert "tool_id" not in approvals[0]


def test_manager_held_run_sse_carries_tool_id():
    held = RunEvent(
        event="done", turn=1, subtask_id="s",
        detail="run held: APPROVAL_WAITING",
        data={"turns": 1, "run_id": "r", "output_ref": "",
              "executed": False, "approval_requested": True,
              "reason": "APPROVAL_WAITING", "tool_id": TOOL},
    )

    def fake_run_task_streamed(request, **kwargs):
        yield held

    bridge = ManagerSdkBridge()
    events = _payloads(list(bridge._manager_events(
        "srv", "r", _request(), {"cancelled": False},
        fake_run_task_streamed)))
    dones = [e for e in events if e.get("type") == "done"]
    assert len(dones) == 1
    assert dones[0]["tool_id"] == TOOL
    assert dones[0]["approval_requested"] is True
