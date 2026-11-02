"""K02R3 project/task routes + chat cancel through create_app (M-ROUTES).

Drives every K02R3 endpoint through the real seam app (create_app) with
TestClient: reads need no token; USER writes (POST/PUT/DELETE/cancel)
return 401 with no x-actor and 403 with a wrong x-ui-session-token, and
refused writes never reach storage. Unknown ids give an honest 404.
Chat cancel answers an honest 404 for any stream_id: the seam chat entry
keeps no live-stream registry, so no stream can name a live run.
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

from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "k02r3-routes-token"
TEST_SETTINGS = {"testing": True, "ui_session_token": TEST_TOKEN}
ACTOR = "tester-k02r3"


def _auth(token=TEST_TOKEN, actor=ACTOR):
    headers = {}
    if actor is not None:
        headers["x-actor"] = actor
    if token is not None:
        headers["x-ui-session-token"] = token
    return headers


@pytest.fixture
def client():
    app = create_app(dict(TEST_SETTINGS))
    return TestClient(app)


def _create_project(client, name="harbor", folder="folder"):
    resp = client.post(
        "/api/v1/projects",
        json={"name": name, "folder_ref": folder},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["project"]


# -- reads need no token ------------------------------------------------


def test_list_projects_empty_without_token(client):
    resp = client.get("/api/v1/projects")
    assert resp.status_code == 200
    assert resp.json() == {"projects": []}


def test_project_lifecycle_shapes(client):
    created = _create_project(client)
    # SH-05: the working-folder health rides every project shape.
    assert set(created) == {
        "project_id", "name", "folder_ref", "created_at",
        "folder_ok", "folder_path"}
    assert created["name"] == "harbor"
    assert created["folder_ref"] == "folder"
    pid = created["project_id"]

    resp = client.get("/api/v1/projects")
    assert resp.status_code == 200
    assert resp.json() == {"projects": [created]}

    resp = client.get(f"/api/v1/projects/{pid}")
    assert resp.status_code == 200
    assert resp.json() == {"project": created}

    resp = client.put(
        f"/api/v1/projects/{pid}",
        json={"name": "harbor-2"},
        headers=_auth(),
    )
    assert resp.status_code == 200
    renamed = resp.json()["project"]
    assert renamed["project_id"] == pid
    assert renamed["name"] == "harbor-2"

    resp = client.delete(
        f"/api/v1/projects/{pid}", headers=_auth())
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    assert client.get(f"/api/v1/projects/{pid}").status_code == 404
    assert client.get("/api/v1/projects").json() == {"projects": []}


def test_put_null_name_is_noop(client):
    created = _create_project(client, name="keep")
    pid = created["project_id"]
    resp = client.put(
        f"/api/v1/projects/{pid}",
        json={"name": None},
        headers=_auth(),
    )
    assert resp.status_code == 200
    assert resp.json()["project"]["name"] == "keep"


def test_unknown_project_ids_are_404(client):
    assert client.get("/api/v1/projects/nope").status_code == 404
    assert client.put(
        "/api/v1/projects/nope",
        json={"name": "x"},
        headers=_auth(),
    ).status_code == 404
    assert client.delete(
        "/api/v1/projects/nope", headers=_auth()).status_code == 404
    assert client.post(
        "/api/v1/projects/nope/tasks",
        json={"title": "t", "scope": []},
        headers=_auth(),
    ).status_code == 404
    assert client.get("/api/v1/tasks/nope").status_code == 404


def test_bad_bodies_are_400(client):
    pid = _create_project(client)["project_id"]
    assert client.post(
        "/api/v1/projects",
        json={"name": "", "folder_ref": "f"},
        headers=_auth(),
    ).status_code == 400
    assert client.post(
        "/api/v1/projects",
        json={"name": "n"},
        headers=_auth(),
    ).status_code == 400
    assert client.put(
        f"/api/v1/projects/{pid}",
        json={"name": ""},
        headers=_auth(),
    ).status_code == 400
    assert client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "", "scope": []},
        headers=_auth(),
    ).status_code == 400
    assert client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "t"},
        headers=_auth(),
    ).status_code == 400


# -- USER-write guard: 401 / 403, refused writes never store -----------


def test_writes_need_actor(client):
    pid = _create_project(client)["project_id"]
    assert client.post(
        "/api/v1/projects", json={"name": "n", "folder_ref": "f"}
    ).status_code == 401
    assert client.put(
        f"/api/v1/projects/{pid}", json={"name": "n"}
    ).status_code == 401
    assert client.delete(
        f"/api/v1/projects/{pid}").status_code == 401
    assert client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "t", "scope": []},
    ).status_code == 401
    assert client.post(
        f"/api/v1/tasks?project_id={pid}",
        json={"title": "t", "scope": []},
    ).status_code == 401
    assert client.post(
        "/api/v1/chat/cancel", json={"stream_id": "s"}
    ).status_code == 401


def test_writes_refuse_bad_token(client):
    pid = _create_project(client)["project_id"]
    bad = _auth(token="wrong-token")
    assert client.post(
        "/api/v1/projects",
        json={"name": "n", "folder_ref": "f"},
        headers=bad,
    ).status_code == 403
    assert client.put(
        f"/api/v1/projects/{pid}",
        json={"name": "n"},
        headers=bad,
    ).status_code == 403
    assert client.delete(
        f"/api/v1/projects/{pid}", headers=bad
    ).status_code == 403
    assert client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "t", "scope": []},
        headers=bad,
    ).status_code == 403
    assert client.post(
        "/api/v1/chat/cancel",
        json={"stream_id": "s"},
        headers=bad,
    ).status_code == 403


def test_refused_writes_never_reach_storage(client):
    assert client.post(
        "/api/v1/projects", json={"name": "ghost", "folder_ref": "g"}
    ).status_code == 401
    assert client.post(
        "/api/v1/projects",
        json={"name": "ghost", "folder_ref": "g"},
        headers=_auth(token="wrong-token"),
    ).status_code == 403
    assert client.get("/api/v1/projects").json() == {"projects": []}

    pid = _create_project(client, name="steady")["project_id"]
    assert client.put(
        f"/api/v1/projects/{pid}", json={"name": "hijacked"}
    ).status_code == 401
    resp = client.get(f"/api/v1/projects/{pid}")
    assert resp.json()["project"]["name"] == "steady"


# -- tasks through both create paths ------------------------------------


def test_task_lifecycle_shapes(client):
    pid = _create_project(client)["project_id"]

    resp = client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "chart the harbor", "scope": ["scope-a"]},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    first = resp.json()["task"]
    assert set(first) == {
        "task_id", "project_id", "title", "status", "created_at"}
    assert first["project_id"] == pid
    assert first["status"] == "CREATED"

    resp = client.post(
        f"/api/v1/tasks?project_id={pid}",
        json={"title": "light the beacon", "scope": []},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    second = resp.json()["task"]

    resp = client.get(f"/api/v1/tasks?project_id={pid}")
    assert resp.status_code == 200
    assert resp.json() == {"tasks": [first, second]}

    resp = client.get(f"/api/v1/tasks/{first['task_id']}")
    assert resp.status_code == 200
    assert resp.json() == {"task": first}

    assert client.get("/api/v1/tasks").status_code == 400
    assert client.get(
        "/api/v1/tasks?project_id=nope").status_code == 404
    assert client.post(
        "/api/v1/tasks",
        json={"title": "t", "scope": []},
        headers=_auth(),
    ).status_code == 400


# -- chat cancel: guarded, honest 404 (no live-stream registry) ---------


def test_chat_cancel_guarded_and_honest_404(client):
    resp = client.post(
        "/api/v1/chat/cancel",
        json={"stream_id": "stream-1"},
        headers=_auth(),
    )
    assert resp.status_code == 404

    resp = client.post(
        "/api/v1/chat/cancel", json={}, headers=_auth())
    assert resp.status_code == 400
    resp = client.post(
        "/api/v1/chat/cancel", json={"stream_id": " "}, headers=_auth()
    )
    assert resp.status_code == 400
