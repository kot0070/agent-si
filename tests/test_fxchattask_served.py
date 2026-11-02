"""FXCHATTASK served proof: first chat message creates one task row.

Drives the real seam app (create_app + TestClient,
raise_server_exceptions=False) over a real tmp store dir on the real
fs. Only the provider boundary uses the sanctioned K04
MockProviderAdapter (no network, no keys, no token in URL).

  msg1 with project selected -> exactly one task row holding the
    message text, in the k02r3_tasks.jsonl snapshot AND listed by
    GET /api/v1/tasks?project_id=.
  B2 (frozen): every accepted message stores one row; a repeat of the
    same stripped text stores none (same text twice -> one row,
    a different second message -> two rows).
  chat with no project, or an unknown project -> 200, no row.
  task-write failure -> the stream still 200s with one start plus one
    terminal event (never breaks on the write).
  the stored row carries no key or secret text, only the message.
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

from agent_si.backend import chat_stream as _chat  # noqa: E402
from agent_si.backend import read_routes as _reads  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from agent_si.providers.adapters.base import (  # noqa: E402
    AdapterConfig,
    make_secret_ref,
)
from agent_si.providers.adapters.mock_provider import (  # noqa: E402
    MockProviderAdapter,
)

TEST_TOKEN = "fxchattask-token"
ACTOR = "coder-1-fxchattask"
CANNED = ("Canned service reply.",)
MSG1 = "quokka field note: map the north fence line"
MSG2 = "quokka follow-up: also check the south gate"

TASKS_SNAPSHOT = "k02r3_tasks.jsonl"


def _auth(token=TEST_TOKEN, actor=ACTOR):
    return {"x-actor": actor, "x-ui-session-token": token}


def _settings(store_dir=None):
    settings = {"testing": True, "ui_session_token": TEST_TOKEN}
    if store_dir is not None:
        settings["store_dir"] = str(store_dir)
    return settings


def _mock_adapter(canned=CANNED):
    config = AdapterConfig(
        provider_id="mock",
        instance_id="fxchattask-behavior",
        model="mock-canned",
        secret_ref=make_secret_ref(
            secret_id="mock-secret", provider_id="mock"),
    )
    return MockProviderAdapter(config, transport=None, canned=canned)


def _apply_chat_limits(project_id):
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": project_id,
        "authority": "fxchattask-test",
        "reason": "configure test project limits for chat behavior",
        "task_max_steps": 10,
        "chat_max_steps": 10,
    })
    assert outcome.applied, outcome.reason


def setup_function(_func):
    _steplimits._reset_state()


def teardown_function(_func):
    _steplimits._reset_state()


def _served_client(tmp_path, monkeypatch):
    """Real app with the orchestration path forced (manager loaders off)."""
    monkeypatch.setattr(
        _chat, "_load_manager_run_task_streamed", lambda: None)
    monkeypatch.setattr(
        _chat, "_load_manager_bound_provider", lambda: None)
    app = create_app(_settings(tmp_path))
    app.state.chat_provider_adapter = _mock_adapter()
    return TestClient(app, raise_server_exceptions=False), app


def _create_project(client):
    resp = client.post(
        "/api/v1/projects",
        json={"name": "fxchattask", "folder_ref": "dock-fxchattask"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    pid = resp.json()["project"]["project_id"]
    assert pid, resp.text
    return pid


def _parse_sse(text):
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


def _snapshot_rows(tmp_path):
    path = os.path.join(str(tmp_path), TASKS_SNAPSHOT)
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle.read().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _listed_tasks(client, project_id):
    resp = client.get(
        "/api/v1/tasks", params={"project_id": project_id})
    assert resp.status_code == 200, resp.text
    return resp.json()["tasks"]


def _post_chat(client, message, project=None, task=""):
    body = {"message": message}
    if project is not None:
        body["project"] = project
    if task:
        body["task"] = task
    return client.post("/api/v1/chat/stream", json=body, headers=_auth())


# -- R1 first message creates exactly one task row ----------------------


def test_first_message_creates_one_task_row(tmp_path, monkeypatch):
    client, _app = _served_client(tmp_path, monkeypatch)
    pid = _create_project(client)
    _apply_chat_limits(pid)
    resp = _post_chat(client, MSG1, project=pid)
    assert resp.status_code == 200, resp.text
    rows = _snapshot_rows(tmp_path)
    mine = [row for row in rows if row.get("project_id") == pid]
    assert len(mine) == 1, rows
    assert MSG1 in str(mine[0].get("title", "")), mine[0]
    listed = _listed_tasks(client, pid)
    assert len(listed) == 1, listed
    assert listed[0]["task_id"] == mine[0]["task_id"], (listed, mine)
    assert MSG1 in listed[0]["title"], listed[0]


# -- R2/B2 later messages: same stripped text adds none, different adds one -


def test_second_message_follows_b2_dedup_rule(tmp_path, monkeypatch):
    client, _app = _served_client(tmp_path, monkeypatch)
    pid = _create_project(client)
    _apply_chat_limits(pid)
    first = _post_chat(client, MSG1, project=pid)
    assert first.status_code == 200, first.text
    tid = _listed_tasks(client, pid)[0]["task_id"]
    repeat_with_task = _post_chat(client, MSG1, project=pid, task=tid)
    assert repeat_with_task.status_code == 200, repeat_with_task.text
    repeat_bare = _post_chat(client, "  " + MSG1 + "  ", project=pid)
    assert repeat_bare.status_code == 200, repeat_bare.text
    rows = _snapshot_rows(tmp_path)
    mine = [row for row in rows if row.get("project_id") == pid]
    assert len(mine) == 1, rows
    assert len(_listed_tasks(client, pid)) == 1
    second_new = _post_chat(client, MSG2, project=pid)
    assert second_new.status_code == 200, second_new.text
    rows = _snapshot_rows(tmp_path)
    mine = [row for row in rows if row.get("project_id") == pid]
    assert len(mine) == 2, rows
    assert len(_listed_tasks(client, pid)) == 2


# -- R3 no project changes nothing ----------------------------------------


def test_chat_without_project_200s_with_no_row(tmp_path, monkeypatch):
    client, _app = _served_client(tmp_path, monkeypatch)
    resp = _post_chat(client, MSG1)
    assert resp.status_code == 200, resp.text
    rows = _snapshot_rows(tmp_path)
    assert rows == [], rows


def test_chat_unknown_project_200s_with_no_row(tmp_path, monkeypatch):
    client, _app = _served_client(tmp_path, monkeypatch)
    resp = _post_chat(client, MSG1, project="proj-fxchattask-ghost")
    assert resp.status_code == 200, resp.text
    rows = _snapshot_rows(tmp_path)
    assert rows == [], rows


# -- R4 write failure never breaks the stream ------------------------------


def test_task_write_failure_leaves_stream_whole(tmp_path, monkeypatch):
    client, app = _served_client(tmp_path, monkeypatch)
    pid = _create_project(client)
    _apply_chat_limits(pid)
    _projects, tasks = _reads.repos_for(app)

    def _boom(_record):
        raise RuntimeError("fxchattask probe write failure")

    monkeypatch.setattr(tasks, "append", _boom)
    resp = _post_chat(client, MSG1, project=pid)
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    kinds = [event.get("type") for event in events]
    assert kinds[0] == "start", kinds
    assert kinds.count("start") == 1, kinds
    assert kinds[-1] in ("done", "error"), kinds
    rows = _snapshot_rows(tmp_path)
    mine = [row for row in rows if row.get("project_id") == pid]
    assert mine == [], rows


# -- R5 the stored row carries message text only -----------------------------


def test_task_row_holds_message_text_only(tmp_path, monkeypatch):
    client, _app = _served_client(tmp_path, monkeypatch)
    pid = _create_project(client)
    _apply_chat_limits(pid)
    resp = _post_chat(client, MSG1, project=pid)
    assert resp.status_code == 200, resp.text
    listed = _listed_tasks(client, pid)
    assert len(listed) == 1, listed
    row = listed[0]
    assert set(row) == {
        "task_id", "project_id", "title", "status", "created_at",
    }, row
    assert row["title"] == MSG1, row
    assert row["project_id"] == pid, row
