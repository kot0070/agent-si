"""PLANB X5 (DEFECT-34): one run leaves one history row.

The client sends its run id in the x-run-id header; the route puts it on the
request and the server turn writes under it, so the client's own write
upserts the same row (before: two rows per run, listed twice on reopen).
"""

import dataclasses
import os
import sys
from types import SimpleNamespace

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_WS, os.path.join(_WS, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from agent_si.backend import chat_history as _hist  # noqa: E402
from agent_si.backend import chat_stream as _cs  # noqa: E402


def _app():
    state = SimpleNamespace(
        chat_history_turns={}, chat_history_hydrated=True,
        k02r3_store_dir=None)
    return SimpleNamespace(state=state)


def test_clean_client_run_id_accepts_plain_tokens_only():
    assert _cs.clean_client_run_id("chat-stream-1793784688764-1") == (
        "chat-stream-1793784688764-1")
    assert _cs.clean_client_run_id("  abc_1.2  ") == "abc_1.2"
    for bad in ("", None, 5, "has space", "../x", "a" * 81, "-lead"):
        assert _cs.clean_client_run_id(bad) == ""


def test_request_field_defaults_empty_and_body_cannot_set_it():
    request = _cs.ChatStreamRequest.from_body(
        {"project": "p", "message": "hi", "run_id": "body-id"}, "a")
    assert request.client_run_id == ""
    assert dataclasses.replace(
        request, client_run_id="c-1").client_run_id == "c-1"


def test_server_turn_and_client_write_are_one_row_executed_sticky():
    from agent_si.backend.chat_stream import ChatStreamRequest, build_bridge
    from agent_si.providers.adapters.base import (
        AdapterConfig, make_secret_ref)
    from agent_si.providers.adapters.mock_provider import (
        MockProviderAdapter)
    from agent_si.runtime.manager import RunEvent

    def fake_run(request, **kwargs):
        yield RunEvent(event="turn", turn=1, subtask_id="s", detail="t",
                       data={"text": "Director: plan\n"})
        yield RunEvent(event="done", turn=2, subtask_id="s", detail="d",
                       data={"executed": True})

    config = AdapterConfig(
        provider_id="mock", instance_id="x5", model="mock-canned",
        secret_ref=make_secret_ref(secret_id="mock-secret",
                                   provider_id="mock"))
    bridge = build_bridge(
        provider_adapter=MockProviderAdapter(
            config, transport=None, canned=("x",)),
        run_task_streamed=fake_run)
    app = _app()
    bridge._app = app
    request = dataclasses.replace(
        ChatStreamRequest.from_body(
            {"project": "x5-proj", "message": "build it"}, "x5-actor"),
        client_run_id="chat-stream-9-1")
    _sid, iterator = bridge.run(request)
    b"".join(iterator)
    # the client's own writes of the same run (running at send, terminal)
    _hist.record_turn(app, "x5-proj", "build it", "", status="running",
                      run_id="chat-stream-9-1")
    _hist.record_turn(app, "x5-proj", "build it", "Director: plan\n",
                      status="ok", run_id="chat-stream-9-1", executed=True)
    turns = _hist.list_turns(app, "x5-proj")
    assert len(turns) == 1
    assert turns[0]["run_id"] == "chat-stream-9-1"
    assert turns[0]["status"] == "ok" and turns[0]["executed"] is True
    # a late server write must not clear the executed mark
    _hist.record_turn(app, "x5-proj", "build it", "Director: plan\n",
                      status="ok", run_id="chat-stream-9-1")
    assert _hist.list_turns(app, "x5-proj")[0]["executed"] is True


def test_without_a_client_id_the_server_still_uses_its_own_run_id():
    from agent_si.backend.chat_stream import ChatStreamRequest, build_bridge
    from agent_si.providers.adapters.base import (
        AdapterConfig, make_secret_ref)
    from agent_si.providers.adapters.mock_provider import (
        MockProviderAdapter)
    from agent_si.runtime.manager import RunEvent

    def fake_run(request, **kwargs):
        yield RunEvent(event="done", turn=1, subtask_id="s", detail="d",
                       data={"executed": True})

    config = AdapterConfig(
        provider_id="mock", instance_id="x5b", model="mock-canned",
        secret_ref=make_secret_ref(secret_id="mock-secret",
                                   provider_id="mock"))
    bridge = build_bridge(
        provider_adapter=MockProviderAdapter(
            config, transport=None, canned=("x",)),
        run_task_streamed=fake_run)
    app = _app()
    bridge._app = app
    request = ChatStreamRequest.from_body(
        {"project": "x5b", "message": "m"}, "a")
    _sid, iterator = bridge.run(request)
    b"".join(iterator)
    turns = _hist.list_turns(app, "x5b")
    assert len(turns) == 1 and len(turns[0]["run_id"]) == 32


def test_route_header_names_the_stored_turn_and_client_write_merges(
        tmp_path, monkeypatch):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import test_fxchattask_served as served

    served.setup_function(None)
    try:
        client, _app = served._served_client(tmp_path, monkeypatch)
        pid = served._create_project(client)
        served._apply_chat_limits(pid)
        headers = dict(served._auth())
        headers["x-run-id"] = "chat-stream-5-1"
        resp = client.post(
            "/api/v1/chat/stream",
            json={"message": "one row please", "project": pid},
            headers=headers)
        assert resp.status_code == 200, resp.text
        shown = client.get(
            "/api/v1/chat/history", params={"project_id": pid}).json()
        assert [t["run_id"] for t in shown["turns"]] == ["chat-stream-5-1"]
        client.post(
            "/api/v1/chat/history",
            json={"project_id": pid, "user_text": "one row please",
                  "assistant_text": "x", "status": "ok",
                  "run_id": "chat-stream-5-1", "executed": True},
            headers=served._auth())
        after = client.get(
            "/api/v1/chat/history", params={"project_id": pid}).json()
        assert len(after["turns"]) == 1
        assert after["turns"][0]["executed"] is True
        # a bad header is ignored: the server keeps its own id
        bad = dict(served._auth())
        bad["x-run-id"] = "not ok!"
        client.post(
            "/api/v1/chat/stream",
            json={"message": "second", "project": pid}, headers=bad)
        ids = [t["run_id"] for t in client.get(
            "/api/v1/chat/history", params={"project_id": pid}
        ).json()["turns"]]
        assert len(ids) == 2 and "not ok!" not in ids
    finally:
        served.teardown_function(None)
