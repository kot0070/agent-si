"""FXCHATHIST Part 1 served proof: chat turns persist per project.

Drives the real seam app (create_app + TestClient,
raise_server_exceptions=False) over a real tmp store dir on the real
fs. No provider, no network, no keys.

  POST /api/v1/chat/history (token-guarded USER write) stores one turn
    {project_id, user text, assistant text, time} and returns it.
  GET /api/v1/chat/history?project_id= retrieves turns oldest-first.
  401 without x-actor, 403 on a bad token (write guard only).
  the data-dir snapshot holds user/assistant/time rows only: extra
    body fields (key/secret material) are never stored.
  secret-shaped text is stored redacted through the redaction helper.
"""

import json
import os
import sys

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

TEST_TOKEN = "fxchathist-token"
ACTOR = "coder-1-fxchathist"

HISTORY_SNAPSHOT = "chat_history.jsonl"


def _auth(token=TEST_TOKEN, actor=ACTOR):
    return {"x-actor": actor, "x-ui-session-token": token}


def _settings(store_dir=None):
    settings = {"testing": True, "ui_session_token": TEST_TOKEN}
    if store_dir is not None:
        settings["store_dir"] = str(store_dir)
    return settings


def _served_client(tmp_path):
    app = create_app(_settings(tmp_path))
    return TestClient(app, raise_server_exceptions=False), app


def _snapshot_rows(tmp_path):
    path = os.path.join(str(tmp_path), HISTORY_SNAPSHOT)
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle.read().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def test_history_roundtrip_stores_and_retrieves_turns(tmp_path):
    client, _app = _served_client(tmp_path)
    first = client.post(
        "/api/v1/chat/history",
        json={
            "project_id": "p-hist-1",
            "user_text": "quokka hello: map the north fence",
            "assistant_text": "quokka reply: fence mapped",
        },
        headers=_auth(),
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["project_id"] == "p-hist-1", body
    assert body["user_text"] == "quokka hello: map the north fence", body
    assert body["assistant_text"] == "quokka reply: fence mapped", body
    assert body["time"], body
    second = client.post(
        "/api/v1/chat/history",
        json={
            "project_id": "p-hist-1",
            "user_text": "quokka follow-up: check the south gate",
            "assistant_text": "quokka reply: gate checked",
        },
        headers=_auth(),
    )
    assert second.status_code == 200, second.text
    got = client.get(
        "/api/v1/chat/history", params={"project_id": "p-hist-1"})
    assert got.status_code == 200, got.text
    turns = got.json()["turns"]
    assert [t["user_text"] for t in turns] == [
        "quokka hello: map the north fence",
        "quokka follow-up: check the south gate",
    ], turns
    assert all(t["time"] for t in turns), turns
    assert all(t["project_id"] == "p-hist-1" for t in turns), turns


def test_history_write_guard_rejects_missing_actor_and_bad_token(tmp_path):
    client, _app = _served_client(tmp_path)
    payload = {
        "project_id": "p-hist-1",
        "user_text": "hi",
        "assistant_text": "hello",
    }
    no_actor = client.post(
        "/api/v1/chat/history",
        json=payload,
        headers={"x-ui-session-token": TEST_TOKEN},
    )
    assert no_actor.status_code == 401, no_actor.text
    bad_token = client.post(
        "/api/v1/chat/history", json=payload, headers=_auth(token="wrong"))
    assert bad_token.status_code == 403, bad_token.text
    got = client.get(
        "/api/v1/chat/history", params={"project_id": "p-hist-1"})
    assert got.status_code == 200, got.text
    assert got.json()["turns"] == [], got.text


def test_history_snapshot_holds_only_turn_fields(tmp_path):
    client, _app = _served_client(tmp_path)
    resp = client.post(
        "/api/v1/chat/history",
        json={
            "project_id": "p-hist-1",
            "user_text": "plain question",
            "assistant_text": "plain answer",
            "api_key": "sk-should-never-persist",
            "secret": "shh-should-never-persist",
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    rows = _snapshot_rows(tmp_path)
    assert len(rows) == 1, rows
    assert set(rows[0].keys()) == {
        "project_id", "user_text", "assistant_text", "time"}, rows
    dumped = json.dumps(rows)
    assert "sk-should-never-persist" not in dumped, rows
    assert "shh-should-never-persist" not in dumped, rows


def test_history_redacts_secret_shaped_text(tmp_path):
    client, _app = _served_client(tmp_path)
    resp = client.post(
        "/api/v1/chat/history",
        json={
            "project_id": "p-hist-1",
            "user_text": "connect with api_key: abc123def",
            "assistant_text": "noted, token: xyz789",
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "abc123def" not in body["user_text"], body
    assert "xyz789" not in body["assistant_text"], body
    rows = _snapshot_rows(tmp_path)
    dumped = json.dumps(rows)
    assert "abc123def" not in dumped, rows
    assert "xyz789" not in dumped, rows


def test_history_needs_project_id(tmp_path):
    client, _app = _served_client(tmp_path)
    resp = client.post(
        "/api/v1/chat/history",
        json={"user_text": "hi", "assistant_text": "hello"},
        headers=_auth(),
    )
    assert resp.status_code == 400, resp.text
    missing = client.get("/api/v1/chat/history")
    assert missing.status_code == 400, missing.text
