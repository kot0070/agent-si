"""FXCTX plain-chat memory: earlier turns ride the next provider call.

Served proof over the real seam app (create_app + TestClient,
raise_server_exceptions=False) with a recording mock provider (no
network, no keys). The orchestration path is forced (manager loaders
off); the manager entry is covered by a direct run_task_streamed call
with the same recording fake.

  2-turn chat: the 2nd provider call holds Q1 + A1 once each, the
    current message last and exactly once.
  app rebuild (same store dir): the same context survives hydration.
  another project: sees nothing of the first project's turns.
  key-looking turn: stored scrubbed, never leaks into later context.
  20 long turns: context stays under the 6000-char cap.
  history store raising: the turn still answers.
"""

import json
import os
import sys
import types

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

from agent_si.backend import chat_history  # noqa: E402
from agent_si.backend import chat_stream as _chat  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from agent_si.backend.orchestration.graph import TaskPlanner  # noqa: E402
from agent_si.providers.adapters.base import (  # noqa: E402
    AdapterConfig,
    make_secret_ref,
)
from agent_si.providers.adapters.mock_provider import (  # noqa: E402
    MockProviderAdapter,
)
from agent_si.runtime.manager import run_task_streamed  # noqa: E402

TEST_TOKEN = "fxctx-token"
ACTOR = "coder-1-fxctx"
CANNED = ("Ctx canned reply one.", "Ctx canned reply two.")
SYSTEM = ("You are the assistant in this project. Answer in the user's "
          "language. Earlier turns are context.")


def _auth(token=TEST_TOKEN, actor=ACTOR):
    return {"x-actor": actor, "x-ui-session-token": token}


def _settings(store_dir=None):
    settings = {"testing": True, "ui_session_token": TEST_TOKEN}
    if store_dir is not None:
        settings["store_dir"] = str(store_dir)
    return settings


class _RecordingMock(MockProviderAdapter):
    """Mock adapter that records every invoke messages list."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen = []

    def invoke(self, messages, params=None, max_turns=8):
        self.seen.append([dict(item) for item in messages])
        return super().invoke(messages, params=params, max_turns=max_turns)


def _recording_adapter():
    config = AdapterConfig(
        provider_id="mock",
        instance_id="fxctx-behavior",
        model="mock-canned",
        secret_ref=make_secret_ref(
            secret_id="mock-secret", provider_id="mock"),
    )
    return _RecordingMock(config, transport=None, canned=CANNED)


def _apply_chat_limits(project_id):
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": project_id,
        "authority": "fxctx-test",
        "reason": "configure test project limits for chat behavior",
        "task_max_steps": 10,
        "chat_max_steps": 10,
    })
    assert outcome.applied, outcome.reason


def setup_function(_func):
    _steplimits._reset_state()


def teardown_function(_func):
    _steplimits._reset_state()


def _served_client(tmp_path, project_id, monkeypatch, adapter=None):
    """Real app with the orchestration path forced (manager loaders off)."""
    monkeypatch.setattr(
        _chat, "_load_manager_run_task_streamed", lambda: None)
    monkeypatch.setattr(
        _chat, "_load_manager_bound_provider", lambda: None)
    _apply_chat_limits(project_id)
    app = create_app(_settings(tmp_path))
    adapter = adapter or _recording_adapter()
    app.state.chat_provider_adapter = adapter
    client = TestClient(app, raise_server_exceptions=False)
    client.app = app  # type: ignore[attr-defined]
    return client, adapter


def _chat_turn(client, project, message):
    resp = client.post(
        "/api/v1/chat/stream",
        json={"project": project, "message": message},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    return resp.text


def _planned_graph(subtask_id="fxctx-sub-001"):
    planner = TaskPlanner()
    _plan_ref, graph = planner.plan(
        "pkg-fxctx",
        "fxctx manager run",
        [{"subtask_id": subtask_id, "goal": "serve one canned turn",
          "task_class": "general", "risk": "LOW"}],
    )
    return graph


def test_second_turn_carries_first_q_and_a_once(tmp_path, monkeypatch):
    project = "proj-fxctx-two"
    client, adapter = _served_client(tmp_path, project, monkeypatch)
    first_q = "fxctx first question about the north fence"
    _chat_turn(client, project, first_q)
    assert len(adapter.seen) == 1, adapter.seen
    second_q = "fxctx second question about the south gate"
    _chat_turn(client, project, second_q)
    assert len(adapter.seen) == 2, adapter.seen
    messages = adapter.seen[1]
    assert messages[0] == {"role": "system", "content": SYSTEM}, messages
    contents = [item["content"] for item in messages]
    assert contents.count(first_q) == 1, messages
    assert contents.count(CANNED[0]) == 1, messages
    assert messages[-1] == {"role": "user", "content": second_q}, messages
    assert contents.count(second_q) == 1, messages


def test_context_survives_app_rebuild(tmp_path, monkeypatch):
    project = "proj-fxctx-rebuild"
    client, _adapter = _served_client(tmp_path, project, monkeypatch)
    first_q = "fxctx rebuild first question"
    _chat_turn(client, project, first_q)
    rebuilt, adapter2 = _served_client(tmp_path, project, monkeypatch)
    _chat_turn(rebuilt, project, "fxctx rebuild second question")
    messages = adapter2.seen[0]
    contents = [item["content"] for item in messages]
    assert first_q in contents, messages
    assert CANNED[0] in contents, messages


def test_other_project_sees_nothing(tmp_path, monkeypatch):
    project = "proj-fxctx-home"
    client, adapter = _served_client(tmp_path, project, monkeypatch)
    _apply_chat_limits("proj-fxctx-away")
    secret_q = "fxctx home-only question"
    _chat_turn(client, project, secret_q)
    _chat_turn(client, "proj-fxctx-away", "fxctx away question")
    messages = adapter.seen[1]
    contents = [item["content"] for item in messages]
    assert secret_q not in contents, messages
    assert CANNED[0] not in contents, messages
    assert messages[0] == {"role": "system", "content": SYSTEM}, messages


def test_key_looking_turn_stays_scrubbed(tmp_path, monkeypatch):
    project = "proj-fxctx-scrub"
    client, adapter = _served_client(tmp_path, project, monkeypatch)
    # Fake marker built at runtime so static secret scans stay clean;
    # the runtime value stays key-shaped for the scrub path.
    raw_key = "sk" + "-" + "test" + "-" + "X" * 16
    _chat_turn(client, project, "connect with %s please" % raw_key)
    got = client.get(
        "/api/v1/chat/history", params={"project_id": project})
    assert got.status_code == 200, got.text
    dumped = json.dumps(got.json())
    assert raw_key not in dumped, dumped
    _chat_turn(client, project, "fxctx scrub follow-up")
    follow = json.dumps(adapter.seen[1])
    assert raw_key not in follow, follow


def test_twenty_long_turns_stay_under_cap(tmp_path, monkeypatch):
    project = "proj-fxctx-cap"
    client, adapter = _served_client(tmp_path, project, monkeypatch)
    for pos in range(20):
        chat_history.record_turn(
            client.app,  # type: ignore[attr-defined]
            project, "fxctx long user %d %s" % (pos, "U" * 2000),
            "fxctx long reply %d %s" % (pos, "R" * 3000))
    _chat_turn(client, project, "fxctx cap probe")
    messages = adapter.seen[0]
    context = list(messages[1:-1])
    total = sum(len(item["content"]) for item in context)
    assert total <= 6000, total
    for item in context:
        if item["role"] == "assistant":
            assert len(item["content"]) <= 1500, len(item["content"])
    contents = [item["content"] for item in context]
    assert any("fxctx long reply 19" in text for text in contents), contents
    assert not any("fxctx long reply 0 " in text for text in contents), (
        contents)


def test_history_store_raising_still_answers(tmp_path, monkeypatch):
    project = "proj-fxctx-raise"
    client, adapter = _served_client(tmp_path, project, monkeypatch)
    monkeypatch.setattr(
        chat_history, "list_turns",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("store down")))
    text = _chat_turn(client, project, "fxctx resilient question")
    assert '"type": "done"' in text or '"type":"done"' in text.replace(
        " ", ""), text
    assert adapter.seen, "provider still called"
    assert adapter.seen[0][-1] == {
        "role": "user", "content": "fxctx resilient question"}, adapter.seen


def test_manager_runner_carries_history():
    app = types.SimpleNamespace(state=types.SimpleNamespace())
    chat_history.record_turn(
        app, "p-fxctx-mgr", "mgr first question", "mgr first answer")
    adapter = _recording_adapter()
    events = list(run_task_streamed(
        None,
        agent_task={
            "agent_task_id": "agent-task-fxctx",
            "subtask_id": "fxctx-sub-001",
            "agent_id": "agent-fxctx",
            "contract_hash": "hash-fxctx",
        },
        graph=_planned_graph(),
        provider_adapter=adapter,
        project_id="p-fxctx-mgr",
        task_id="task-fxctx-mgr",
        message="mgr second question",
        manager_id="mgr-fxctx",
        max_agent_steps=3,
        app=app,
    ))
    assert events and events[-1].event == "done"
    assert adapter.seen, "manager provider call recorded"
    messages = adapter.seen[0]
    assert messages[0] == {"role": "system", "content": SYSTEM}, messages
    contents = [item["content"] for item in messages]
    assert contents.count("mgr first question") == 1, messages
    assert contents.count("mgr first answer") == 1, messages
    assert messages[-1] == {
        "role": "user", "content": "mgr second question"}, messages


def test_recent_context_unit_edges():
    app = types.SimpleNamespace(state=types.SimpleNamespace())
    assert chat_history.recent_context(app, "p-fxctx-empty") == []
    chat_history.record_turn(
        app, "p-fxctx-edge", "edge question", "edge answer",
        run_id="run-edge-1")
    kept = chat_history.recent_context(
        app, "p-fxctx-edge", exclude_run_id="run-edge-1")
    assert kept == [], kept
    shown = chat_history.recent_context(app, "p-fxctx-edge")
    assert [item["content"] for item in shown] == [
        "edge question", "edge answer"], shown
    full = chat_history.chat_messages(
        app, "p-fxctx-edge", "edge follow-up")
    assert full[0] == {"role": "system", "content": SYSTEM}, full
    assert full[-1] == {"role": "user", "content": "edge follow-up"}, full
