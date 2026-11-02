"""K02R4 engine: chat SSE stream + cancel over a Manager run (M-ENGINE).

Drives POST /api/v1/chat/stream and POST /api/v1/chat/cancel through the
real seam app (create_app) with TestClient. The provider boundary alone is
the K04 MockProviderAdapter (canned, mock=true): no network, no keys, no
token in URL. SecretRef refs only.

Covers: stream emits model-driven events via mock; cancel ends a live
stream (second cancel for the same id is an honest 404); bad stream
bodies are 400 while the token/actor guard keeps its 401/403/429 shape;
a subtask-less AgentTask never executes at the chat boundary.
"""

import json
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

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.chat_stream import (  # noqa: E402
    ChatStreamRequest,
    bridge_for_app,
)
from agent_si.backend.orchestration.graph import (  # noqa: E402
    AgentTask,
    DispatchRejected,
    SubtaskGraph,
)
from agent_si.providers.adapters.base import (  # noqa: E402
    AdapterConfig,
    make_secret_ref,
)
from agent_si.providers.adapters.mock_provider import (  # noqa: E402
    MockProviderAdapter,
)
from agent_si.backend.orchestration import steplimits as _k02r5_steplimits  # noqa: E402

TEST_TOKEN = "k02r4-engine-token"
TEST_SETTINGS = {"testing": True, "ui_session_token": TEST_TOKEN}
ACTOR = "tester-k02r4"

CANNED = ("Mock engine reply one.", "Mock engine reply two.")


# -- FXLOC C5: real budget gate (fail-closed product gate) --------------------
@pytest.fixture(autouse=True)
def _fxloc_real_budget_gate():
    """Fail-closed gate needs a real gate: generous limits, restored after."""
    from agent_si.budget.gate import BudgetGate
    from agent_si.runtime import manager as _mgr

    prev = _mgr._BUDGET_GATE
    gate = BudgetGate()
    gate.configure_project(
        "proj-k02r4", "USD", "1000000.00", "900000.00", "1000000.00")
    _mgr.set_budget_gate(gate)
    yield
    _mgr.set_budget_gate(prev)


# K02R5-Sable: per-project step limits for the streamed mock test (R-349
# honest refusal, NO product default; reset before/after for isolation).
@pytest.fixture(autouse=True)
def _k02r5_configured_step_limits():
    _k02r5_steplimits._reset_state()
    outcome = _k02r5_steplimits.apply_steplimit_config_change({
        "project_id": "proj-k02r4",
        "authority": "k02r5-engine-test",
        "reason": "configure test project limits for mock stream",
        "task_max_steps": 10,
        "chat_max_steps": 10,
    })
    assert outcome.applied, outcome.reason
    yield
    _k02r5_steplimits._reset_state()


def _auth(token=TEST_TOKEN, actor=ACTOR):
    headers = {}
    if actor is not None:
        headers["x-actor"] = actor
    if token is not None:
        headers["x-ui-session-token"] = token
    return headers


def _mock_adapter(canned=CANNED):
    config = AdapterConfig(
        provider_id="mock",
        instance_id="k02r4-test",
        model="mock-canned",
        secret_ref=make_secret_ref(
            secret_id="mock-secret", provider_id="mock"),
    )
    return MockProviderAdapter(config, transport=None, canned=canned)


def _client_with_mock(canned=CANNED):
    mock = _mock_adapter(canned)
    app = create_app(dict(TEST_SETTINGS))
    app.state.chat_provider_adapter = mock
    return app, TestClient(app), mock


def _stream_body(**overrides):
    body = {
        "project": "proj-k02r4",
        "task": "task-k02r4",
        "message": "hello engine",
        "profile": "profile:default",
        "pool": "pool:default",
    }
    body.update(overrides)
    return body


def _sse_events(resp):
    assert "text/event-stream" in resp.headers.get("content-type", "")
    return _parse_sse_bytes([resp.text.encode("utf-8")])


def _parse_sse_bytes(chunks):
    text = b"".join(chunks).decode("utf-8")
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


# -- stream emits model-driven events via mock ------------------------------


def test_stream_emits_model_driven_events_via_mock():
    _app, client, mock = _client_with_mock()
    resp = client.post(
        "/api/v1/chat/stream", json=_stream_body(), headers=_auth())
    assert resp.status_code == 200, resp.text
    assert resp.headers.get("x-stream-id")
    events = _sse_events(resp)
    kinds = [event.get("type") for event in events]
    assert kinds[0] == "start"
    assert "delta" in kinds
    assert kinds[-1] == "done"
    deltas = [event for event in events if event.get("type") == "delta"]
    assert deltas[0]["text"] == CANNED[0]
    assert deltas[0]["stream_id"] == resp.headers["x-stream-id"]
    done = events[-1]
    assert done["mock"] is True
    assert done["executed"] is True
    assert mock.turns_served == 1


def test_stream_request_validation_only():
    request = ChatStreamRequest.from_body(_stream_body(), ACTOR)
    assert request.message == "hello engine"
    assert request.actor == ACTOR
    with pytest.raises(ValueError):
        ChatStreamRequest.from_body({"message": "  "}, ACTOR)
    with pytest.raises(ValueError):
        ChatStreamRequest.from_body([], ACTOR)


# -- cancel ends a live stream, then the id is unknown ----------------------


def test_cancel_ends_live_stream_then_unknown():
    app, client, mock = _client_with_mock()
    bridge = bridge_for_app(app)
    request = ChatStreamRequest.from_body(_stream_body(), ACTOR)
    stream_id, iterator = bridge.run(request)
    resp = client.post(
        "/api/v1/chat/cancel",
        json={"stream_id": stream_id},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "stream_id": stream_id}
    tail = _parse_sse_bytes(list(iterator))
    assert mock.turns_served == 0
    assert tail and tail[0]["type"] == "start"
    assert tail[-1]["type"] == "cancelled"
    assert "delta" not in [event.get("type") for event in tail]
    resp = client.post(
        "/api/v1/chat/cancel",
        json={"stream_id": stream_id},
        headers=_auth(),
    )
    assert resp.status_code == 404


def test_cancel_unknown_is_404_and_empty_is_400():
    _app, client, _mock = _client_with_mock()
    resp = client.post(
        "/api/v1/chat/cancel",
        json={"stream_id": "no-such-stream"},
        headers=_auth(),
    )
    assert resp.status_code == 404
    assert client.post(
        "/api/v1/chat/cancel", json={}, headers=_auth()).status_code == 400
    resp = client.post(
        "/api/v1/chat/cancel",
        json={"stream_id": "  "},
        headers=_auth(),
    )
    assert resp.status_code == 400


# -- bad stream bodies are 400; guard shape unchanged -----------------------


def test_stream_bad_request_rejected_400():
    _app, client, _mock = _client_with_mock()
    assert client.post(
        "/api/v1/chat/stream", json={}, headers=_auth()).status_code == 400
    resp = client.post(
        "/api/v1/chat/stream",
        json=_stream_body(message="   "),
        headers=_auth(),
    )
    assert resp.status_code == 400


def test_stream_guard_shapes_unchanged():
    _app, client, _mock = _client_with_mock()
    assert client.post("/api/v1/chat/stream").status_code == 401
    resp = client.post(
        "/api/v1/chat/stream",
        json=_stream_body(),
        headers={"x-actor": ACTOR},
    )
    assert resp.status_code == 403
    resp = client.post(
        "/api/v1/chat/stream",
        json=_stream_body(),
        headers=_auth(token="wrong-token"),
    )
    assert resp.status_code == 403


def test_stream_rate_limit_shape_unchanged():
    app = create_app(dict(TEST_SETTINGS), rate_hook=lambda key: False)
    app.state.chat_provider_adapter = _mock_adapter()
    client = TestClient(app)
    resp = client.post(
        "/api/v1/chat/stream", json=_stream_body(), headers=_auth())
    assert resp.status_code == 429


def test_absent_engine_without_provider_is_honest_404():
    app = create_app(dict(TEST_SETTINGS))
    client = TestClient(app)
    resp = client.post(
        "/api/v1/chat/stream", json=_stream_body(), headers=_auth())
    assert resp.status_code == 404


# -- dispatch boundary: subtask-less AgentTask never executes ---------------


def test_subtaskless_agent_task_never_executes_at_boundary():
    _app, _client, mock = _client_with_mock()
    from agent_si.backend.chat_stream import build_bridge

    bridge = build_bridge(provider_adapter=mock)
    request = ChatStreamRequest.from_body(_stream_body(), ACTOR)
    bare = AgentTask(
        agent_task_id="agent-task-1",
        subtask_id="",
        agent_id="agent-1",
        contract_hash="hash-1",
    )
    with pytest.raises(DispatchRejected):
        bridge.run(request, agent_task=bare, graph=SubtaskGraph())
    assert mock.turns_served == 0
    planned = SubtaskGraph()
    with pytest.raises(DispatchRejected):
        bridge.run(request, agent_task=bare, graph=planned)
    assert mock.turns_served == 0


# -- K02NEXT2 CODER-B served proof (orchestration rows) ----------------------

_K02NEXT2_PROJ = "proj-k02next2-b"


def test_k02next2_row_m_p1_28_routine_handoff_switch_and_record():
    from agent_si.backend.orchestration import offload as offload_mod

    offload_mod._reset_state()
    try:
        project = _K02NEXT2_PROJ + "-p1-28"
        assert offload_mod.routine_offload_enabled(project) is False
        with pytest.raises(offload_mod.OffloadDisabled):
            offload_mod.serve_routine_handoff(
                {"project_id": project, "routine": "nightly-docs"})
        assert offload_mod.handovers_for(project) == []
        switched = offload_mod.switch(project, True)
        assert switched == {
            "project_id": project, "routine_offload_enabled": True}
        handed = offload_mod.serve_routine_handoff(
            {"project_id": project, "routine": "nightly-docs"})
        assert handed["project_id"] == project
        assert handed["routine"] == "nightly-docs"
        assert handed["by"] == "manager"
        assert offload_mod.handovers_for(project) == [
            {"routine": "nightly-docs",
             "at": handed["at"], "by": "manager"}]
        with pytest.raises(ValueError):
            offload_mod.serve_routine_handoff(
                {"project_id": project, "routine": "   "})
        with pytest.raises(ValueError):
            offload_mod.serve_routine_handoff({"project_id": project})
        with pytest.raises(ValueError):
            offload_mod.serve_routine_handoff(["not-a-mapping"])
    finally:
        offload_mod._reset_state()


def test_k02next2_row_m_p1_33_audit_model_strong_only_when_needed():
    from agent_si.backend.orchestration import teamcard as teamcard_mod

    before = len(teamcard_mod.AUDIT_CHOICE_LOG)
    try:
        strong = teamcard_mod.serve_audit_model_choice(
            {"part_id": "part-high", "risk": "high"})
        assert strong["strength"] == "strong"
        assert strong["part_id"] == "part-high"
        assert strong["logged"] == before + 1
        standard = teamcard_mod.serve_audit_model_choice(
            {"part_id": "part-low", "risk": "low"})
        assert standard["strength"] == "standard"
        assert standard["logged"] == before + 2
        assert teamcard_mod.AUDIT_CHOICE_LOG[before].part_id == "part-high"
        assert teamcard_mod.AUDIT_CHOICE_LOG[before].strength == "strong"
        assert teamcard_mod.AUDIT_CHOICE_LOG[before + 1].strength == "standard"
        with pytest.raises(ValueError):
            teamcard_mod.serve_audit_model_choice(
                {"part_id": "  ", "risk": "high"})
        with pytest.raises(ValueError):
            teamcard_mod.serve_audit_model_choice({"part_id": "part-x"})
        with pytest.raises(ValueError):
            teamcard_mod.serve_audit_model_choice("not-a-mapping")
    finally:
        del teamcard_mod.AUDIT_CHOICE_LOG[before:]


def test_k02next2_row_m_p1_42_no_provisional_director_default():
    from agent_si.backend.orchestration import graph as graph_mod

    assert graph_mod.DIRECTOR_RUNTIME is None
    served = graph_mod.serve_director_control(
        {"director": "director:explicit-1"})
    assert served["director"] == "director:explicit-1"
    assert served["live_runtime"] is None
    assert served["control_plane"]["director.route"] == "graph.route_task"
    for target in served["control_plane"].values():
        assert "." in target
    with pytest.raises(graph_mod.DirectorControlOnly):
        graph_mod.serve_director_control({"director": "provisional"})
    with pytest.raises(graph_mod.DirectorControlOnly):
        graph_mod.serve_director_control({"director": "   "})
    with pytest.raises(ValueError):
        graph_mod.serve_director_control({"director": 7})
    with pytest.raises(ValueError):
        graph_mod.serve_director_control(["not-a-mapping"])


def test_k02next2_row_m_d_d13_worker_inputs_shared_and_authorized_only():
    from agent_si.backend.orchestration import split as split_mod
    from agent_si.backend.orchestration import teamcard as teamcard_mod

    listed = "ARTIFACT_REF:pkg-d13/shared-a"
    served = split_mod.serve_worker_inputs({
        "worker_id": "worker-1",
        "authorized_refs": [listed, "artifact://pkg-d13/shared-b"],
        "requested_refs": [
            listed,
            "artifact://pkg-d13/shared-b",
            "artifact://pkg-d13/not-listed",
        ],
    })
    assert served["worker_id"] == "worker-1"
    assert served["context"] == teamcard_mod.worker_context() == {}
    assert served["inputs"] == [
        listed, "artifact://pkg-d13/shared-b"]
    assert "artifact://pkg-d13/not-listed" not in served["inputs"]
    with pytest.raises(ValueError):
        split_mod.serve_worker_inputs({
            "worker_id": "worker-1",
            "authorized_refs": [listed],
            "requested_refs": ["raw-inline-secret"],
        })
    with pytest.raises(ValueError):
        split_mod.serve_worker_inputs({
            "worker_id": "  ",
            "authorized_refs": [],
            "requested_refs": [],
        })
    with pytest.raises(ValueError):
        split_mod.serve_worker_inputs("not-a-mapping")
