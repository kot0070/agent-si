"""FXCHATHIST Part 2 served proof: chat history durability across restart.

Drives the real seam app (create_app + TestClient,
raise_server_exceptions=False) over a real tmp store dir on the real
fs. No provider, no network, no keys; the history path has no provider
boundary at all (fake only at the provider, of which this route uses
none).

  POST /api/v1/chat/history turns rehydrate on a NEW app bound to the
  same store dir (restart persistence), oldest-first.
  turns stay per-project isolated through the real routes.
  an unknown project reads back empty (no invented turns).
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

TEST_TOKEN = "fxchathist-wire-token"
ACTOR = "coder-1-fxchathist-wire"

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
    return TestClient(app, raise_server_exceptions=False)


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


def test_history_survives_restart_oldest_first(tmp_path):
    first = _served_client(tmp_path)
    for user_text, assistant_text in [
        ("wire question one", "wire answer one"),
        ("wire question two", "wire answer two"),
    ]:
        resp = first.post(
            "/api/v1/chat/history",
            json={
                "project_id": "p-wire-1",
                "user_text": user_text,
                "assistant_text": assistant_text,
            },
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
    # A restart binds a NEW app to the same store dir: turns rehydrate.
    second = _served_client(tmp_path)
    got = second.get(
        "/api/v1/chat/history", params={"project_id": "p-wire-1"})
    assert got.status_code == 200, got.text
    turns = got.json()["turns"]
    assert [t["user_text"] for t in turns] == [
        "wire question one",
        "wire question two",
    ], turns
    assert [t["assistant_text"] for t in turns] == [
        "wire answer one",
        "wire answer two",
    ], turns
    assert all(t["time"] for t in turns), turns
    assert all(t["project_id"] == "p-wire-1" for t in turns), turns


def test_history_stays_per_project_through_real_routes(tmp_path):
    client = _served_client(tmp_path)
    for project_id in ("p-wire-a", "p-wire-b"):
        resp = client.post(
            "/api/v1/chat/history",
            json={
                "project_id": project_id,
                "user_text": f"hello {project_id}",
                "assistant_text": f"hi {project_id}",
            },
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
    for project_id in ("p-wire-a", "p-wire-b"):
        got = client.get(
            "/api/v1/chat/history", params={"project_id": project_id})
        assert got.status_code == 200, got.text
        turns = got.json()["turns"]
        assert len(turns) == 1, turns
        assert turns[0]["user_text"] == f"hello {project_id}", turns
    rows = _snapshot_rows(tmp_path)
    assert {row["project_id"] for row in rows} == {
        "p-wire-a", "p-wire-b"}, rows


def test_history_unknown_project_reads_empty(tmp_path):
    client = _served_client(tmp_path)
    got = client.get(
        "/api/v1/chat/history", params={"project_id": "p-wire-missing"})
    assert got.status_code == 200, got.text
    assert got.json()["turns"] == [], got.text
