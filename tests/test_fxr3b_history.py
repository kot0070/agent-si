"""FXR3B served proof: disconnect reason passes through the history row.

A page reload or window close ends the run on the server; the served
history annotates the still-running turn with the recorded reason, so
the UI can name it instead of showing a bare UNKNOWN. Best effort:
unknown state reads as an empty reason, never a crash.
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

TEST_TOKEN = "fxr3b-served-token"
ACTOR = "coder-1-fxr3b"
PROJECT = "p-disc"


def _auth(token=TEST_TOKEN, actor=ACTOR):
    return {"x-actor": actor, "x-ui-session-token": token}


def _settings(store_dir):
    return {"testing": True, "ui_session_token": TEST_TOKEN,
            "store_dir": str(store_dir)}


def _client(store_dir):
    app = create_app(_settings(store_dir))
    return TestClient(app, raise_server_exceptions=False)


def _write_run_row(store_dir, summary, ended_at):
    path = os.path.join(str(store_dir), "devrun_runs.jsonl")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "project": PROJECT,
            "run_id": "r-dead",
            "summary": summary,
            "ended_at": ended_at,
            "started_at": "2026-01-01T00:00:00Z",
        }) + "\n")


def _running_turn(client):
    resp = client.post(
        "/api/v1/chat/history",
        json={"project_id": PROJECT, "user_text": "do it",
              "assistant_text": "half", "status": "running",
              "run_id": "r-live"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text


def test_disconnect_reason_passes_through_running_turn(tmp_path):
    client = _client(tmp_path)
    _running_turn(client)
    _write_run_row(
        tmp_path, "run ended (client disconnect: children reaped)",
        "2999-01-01T00:00:00Z")
    got = client.get("/api/v1/chat/history",
                     params={"project_id": PROJECT})
    assert got.status_code == 200, got.text
    turns = got.json()["turns"]
    assert len(turns) == 1, turns
    assert "client disconnect" in turns[0]["run_end_reason"], turns


def test_no_record_means_empty_reason(tmp_path):
    client = _client(tmp_path)
    _running_turn(client)
    got = client.get("/api/v1/chat/history",
                     params={"project_id": PROJECT})
    assert got.status_code == 200, got.text
    assert got.json()["turns"][0]["run_end_reason"] == "", got.text


def test_older_disconnect_does_not_mislabel(tmp_path):
    client = _client(tmp_path)
    _running_turn(client)
    _write_run_row(
        tmp_path, "run ended (client disconnect: children reaped)",
        "2000-01-01T00:00:00Z")
    got = client.get("/api/v1/chat/history",
                     params={"project_id": PROJECT})
    assert got.status_code == 200, got.text
    assert got.json()["turns"][0]["run_end_reason"] == "", got.text
