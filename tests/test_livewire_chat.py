"""LIVEWIRE1 chat wire behavior (BE): L0B-08/09/10/11/12 + fixture lock.

RED-first: each defect has a failing test before the fix. After the fix:

- L0B-09: POST {project, message} 200s through the real app; POST {}
  400s with a machine code.
- L0B-10: exactly one `start` + one terminal event per stream, on both
  the manager path (injected run_task_streamed) and the orchestration
  path (mock adapter); the double-`done` path is gone.
- L0B-08: GET /api/v1/budget keeps {project_id, budget{...}} and carries
  a stable machine code on 400/404.
- L0B-11: every error body carries {code, message}; no secret text.
- L0B-12: a configured app with no bound provider answers 200 SSE with
  a terminal NO_PROVIDER_BOUND error event (never a 404); the provider
  bind runs at app start via the K04 public API.
- Fixtures: regenerating all 5 wire files yields byte-identical bytes.

Only the provider boundary uses the sanctioned K04 MockProviderAdapter
(no network, no keys, no token in URL). SecretRef refs only.
"""

import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend import chat_stream as _chat  # noqa: E402
from agent_si.backend.chat_stream import (  # noqa: E402
    ChatStreamRequest,
    bridge_for_app,
    build_bridge,
)
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from agent_si.providers.adapters.base import (  # noqa: E402
    AdapterConfig,
    make_secret_ref,
)
from agent_si.providers.adapters.mock_provider import (  # noqa: E402
    MockProviderAdapter,
)
from agent_si.runtime.manager import RunEvent  # noqa: E402

WIRE_DIR = os.path.join(_WS, "frontend", "src", "api", "wire")

TEST_TOKEN = "livewire-chat-token"
ACTOR = "tester-livewire-chat"
CHAT_PROJECT = "wire-chat-behavior"
CHAT_MESSAGE = "wire behavior hello"
CHAT_CANNED = ("Wire behavior reply one.",)


def _auth(token=TEST_TOKEN, actor=ACTOR):
    headers = {}
    if actor is not None:
        headers["x-actor"] = actor
    if token is not None:
        headers["x-ui-session-token"] = token
    return headers


def _settings(store_dir=None):
    settings = {"testing": True, "ui_session_token": TEST_TOKEN}
    if store_dir is not None:
        settings["store_dir"] = str(store_dir)
    return settings


def _mock_adapter(canned=CHAT_CANNED):
    config = AdapterConfig(
        provider_id="mock",
        instance_id="livewire-behavior",
        model="mock-canned",
        secret_ref=make_secret_ref(
            secret_id="mock-secret", provider_id="mock"),
    )
    return MockProviderAdapter(config, transport=None, canned=canned)


def _apply_chat_limits(project_id):
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": project_id,
        "authority": "livewire-chat-test",
        "reason": "configure test project limits for chat behavior",
        "task_max_steps": 10,
        "chat_max_steps": 10,
    })
    assert outcome.applied, outcome.reason


def setup_function(_func):
    _steplimits._reset_state()


def teardown_function(_func):
    _steplimits._reset_state()


def _stream_body(**overrides):
    body = {"project": CHAT_PROJECT, "message": CHAT_MESSAGE}
    body.update(overrides)
    return body


def _parse_sse(text):
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


def _manager_run(*, fail=None, terminal="done"):
    """Fake M-MANAGER entry: manager-shaped RunEvents, no provider used."""
    def _run(request, **kwargs):
        yield RunEvent(
            event="start", turn=0, subtask_id="sub-001",
            detail="manager run started",
            data={"run_id": "run-wire-1"},
        )
        yield RunEvent(
            event="tool_call", turn=1, subtask_id="sub-001",
            detail="guarded tool call",
            data={},
        )
        if fail is not None:
            raise fail
        yield RunEvent(
            event="turn", turn=1, subtask_id="sub-001",
            detail="turn executed",
            data={"text": "wire manager text"},
        )
        yield RunEvent(
            event=terminal, turn=1, subtask_id="sub-001",
            detail="manager run finished",
            data={"executed": True},
        )
    return _run


# -- L0B-09: chat open shape ----------------------------------------------


def test_chat_open_project_message_200s(tmp_path):
    _apply_chat_limits(CHAT_PROJECT)
    app = create_app(_settings(tmp_path))
    app.state.chat_provider_adapter = _mock_adapter()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/v1/chat/stream", json=_stream_body(), headers=_auth())
    assert resp.status_code == 200, resp.text
    assert resp.headers.get("x-stream-id")
    assert "text/event-stream" in resp.headers.get("content-type", "")


def test_chat_open_empty_body_400s_with_code(tmp_path):
    app = create_app(_settings(tmp_path))
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/api/v1/chat/stream", json={}, headers=_auth())
    assert resp.status_code == 400, resp.text
    body = resp.json().get("detail", resp.json())
    assert body.get("code") == "CHAT_BAD_REQUEST", resp.text
    assert body.get("message"), resp.text


# -- L0B-10: exactly one start + one terminal ------------------------------


def test_orchestration_events_single_start_single_done(tmp_path, monkeypatch):
    _apply_chat_limits(CHAT_PROJECT)
    # Force the orchestration path: no manager entry, no bound provider.
    monkeypatch.setattr(_chat, "_load_manager_run_task_streamed", lambda: None)
    monkeypatch.setattr(_chat, "_load_manager_bound_provider", lambda: None)
    app = create_app(_settings(tmp_path))
    app.state.chat_provider_adapter = _mock_adapter()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/v1/chat/stream", json=_stream_body(), headers=_auth())
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    kinds = [event.get("type") for event in events]
    assert kinds[0] == "start"
    assert kinds.count("start") == 1, kinds
    assert "delta" in kinds, kinds
    assert kinds[-1] == "done", kinds
    assert kinds.count("done") == 1, kinds
    assert events[-1].get("stream_id") == resp.headers["x-stream-id"]


def test_manager_events_single_start_single_done():
    bridge = build_bridge(
        provider_adapter=_mock_adapter(),
        run_task_streamed=_manager_run(),
    )
    request = ChatStreamRequest.from_body(_stream_body(), ACTOR)
    _stream_id, iterator = bridge.run(request)
    events = _parse_sse(b"".join(iterator).decode("utf-8"))
    kinds = [event.get("type") for event in events]
    assert kinds[0] == "start", kinds
    assert kinds.count("start") == 1, kinds
    assert kinds[-1] == "done", kinds
    assert kinds.count("done") == 1, kinds


def test_manager_terminal_without_done_is_not_duplicated():
    for terminal in ("dispatch_rejected", "budget_stop"):
        bridge = build_bridge(
            provider_adapter=_mock_adapter(),
            run_task_streamed=_manager_run(terminal=terminal),
        )
        request = ChatStreamRequest.from_body(_stream_body(), ACTOR)
        _stream_id, iterator = bridge.run(request)
        events = _parse_sse(b"".join(iterator).decode("utf-8"))
        kinds = [event.get("type") for event in events]
        assert kinds.count("start") == 1, (terminal, kinds)
        assert kinds[-1] == terminal, (terminal, kinds)
        assert kinds.count("done") == 0, (terminal, kinds)


def test_manager_midstream_failure_is_one_terminal_error():
    from agent_si.runtime.manager import ProviderUnboundError

    bridge = build_bridge(
        provider_adapter=_mock_adapter(),
        run_task_streamed=_manager_run(
            fail=ProviderUnboundError("no provider adapter bound")),
    )
    request = ChatStreamRequest.from_body(_stream_body(), ACTOR)
    _stream_id, iterator = bridge.run(request)
    events = _parse_sse(b"".join(iterator).decode("utf-8"))
    kinds = [event.get("type") for event in events]
    assert kinds[0] == "start", kinds
    assert kinds[-1] == "error", kinds
    errors = [event for event in events if event.get("type") == "error"]
    assert len(errors) == 1, kinds
    assert errors[0].get("code") == "NO_PROVIDER_BOUND", errors[0]


# -- L0B-08: budget shape kept, codes added --------------------------------


def test_budget_shape_kept_with_defaults(tmp_path):
    _steplimits._reset_state()
    app = create_app(_settings(tmp_path))
    client = TestClient(app, raise_server_exceptions=False)
    created = client.post(
        "/api/v1/projects",
        json={"name": "wire", "folder_ref": "wire-dock"},
        headers=_auth(),
    )
    assert created.status_code == 200, created.text
    pid = created.json()["project"]["project_id"]
    resp = client.get("/api/v1/budget", params={"project_id": pid})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["project_id"] == pid
    budget = payload["budget"]
    assert budget["budget_limit"] == "5.00"
    assert budget["soft_limit"] == "4.00"
    assert budget["hard_limit"] == "5.00"


def test_budget_errors_carry_code(tmp_path):
    app = create_app(_settings(tmp_path))
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/v1/budget", params={"project_id": ""})
    assert resp.status_code == 400, resp.text
    assert resp.json().get("code"), resp.text
    assert resp.json().get("message"), resp.text
    resp = client.get(
        "/api/v1/budget", params={"project_id": "wire-no-such-project"})
    assert resp.status_code == 404, resp.text
    assert resp.json().get("code"), resp.text
    assert resp.json().get("message"), resp.text


# -- L0B-11: every error body carries {code, message} -----------------------


def test_report_404_carries_code(tmp_path):
    app = create_app(_settings(tmp_path))
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get(
        "/api/v1/reports/next-package-nudge",
        params={"package_id": "wire-no-such-pkg"})
    assert resp.status_code == 404, resp.text
    body = resp.json().get("detail", resp.json())
    assert body.get("code"), resp.text
    assert body.get("message"), resp.text


def test_chat_guard_errors_carry_code(tmp_path):
    app = create_app(_settings(tmp_path))
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/api/v1/chat/stream", json=_stream_body())
    assert resp.status_code == 401, resp.text
    assert resp.json()["detail"].get("code"), resp.text
    resp = client.post(
        "/api/v1/chat/stream", json=_stream_body(), headers=_auth())
    assert resp.status_code == 200, resp.text


# -- L0B-12: bind at start; no provider -> NO_PROVIDER_BOUND event ---------


def test_app_start_attempts_k04_provider_bind(tmp_path):
    app = create_app(_settings(tmp_path))
    assert hasattr(app.state, "chat_provider_adapter")
    assert app.state.chat_provider_adapter is None
    bridge = bridge_for_app(app)
    assert bridge is not None


def test_no_provider_stream_is_200_with_coded_error(tmp_path):
    _apply_chat_limits(CHAT_PROJECT)
    app = create_app(_settings(tmp_path))
    assert getattr(app.state, "chat_provider_adapter", None) is None
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/v1/chat/stream", json=_stream_body(), headers=_auth())
    assert resp.status_code == 200, resp.text
    assert resp.headers.get("x-stream-id")
    events = _parse_sse(resp.text)
    kinds = [event.get("type") for event in events]
    assert kinds == ["start", "error"], kinds
    assert events[1].get("code") == "NO_PROVIDER_BOUND", events[1]
    assert events[1].get("message"), events[1]
    assert events[1].get("stream_id") == resp.headers["x-stream-id"]


def test_late_bound_provider_attaches_without_test_help(tmp_path):
    _apply_chat_limits(CHAT_PROJECT)
    app = create_app(_settings(tmp_path))
    bridge = bridge_for_app(app)
    assert getattr(bridge, "_provider_adapter", None) is None
    app.state.chat_provider_adapter = _mock_adapter()
    again = bridge_for_app(app)
    assert again is bridge
    assert getattr(bridge, "_provider_adapter", None) is not None


# -- L0B-13 kept: step-limit error stays one terminal error event -----------


def test_stream_without_limits_ends_with_single_error_event(tmp_path):
    _steplimits._reset_state()
    app = create_app(_settings(tmp_path))
    app.state.chat_provider_adapter = _mock_adapter()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/v1/chat/stream", json=_stream_body(), headers=_auth())
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    assert events and events[0].get("type") == "start"
    errors = [event for event in events if event.get("type") == "error"]
    assert len(errors) == 1
    assert errors[0].get("code")
    assert "no step limits configured for project" in errors[0].get(
        "message", "")
    assert events[-1].get("type") == "error"


# -- fixtures: regeneration is byte-for-byte stable -------------------------


def test_wire_fixtures_byte_stable(tmp_path):
    from test_livewire_wire import build_wire_artifacts

    expected = {}
    for name in ("budget-state.json", "chat-open-request.json",
                 "chat-stream-events.json", "error-body.json",
                 "report-body.json"):
        with open(os.path.join(WIRE_DIR, name), "rb") as handle:
            expected[name] = handle.read()
    regenerated = build_wire_artifacts(tmp_path)
    assert sorted(regenerated) == sorted(expected)
    for name, payload in regenerated.items():
        assert payload == expected[name], (
            "%s is not byte-stable" % name)
