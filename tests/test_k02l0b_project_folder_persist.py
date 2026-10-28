"""K02L0B project folder round-trip + restart persistence (L0B-02/L0B-03).

L0B-02: the folder_ref accepted by POST /api/v1/projects is stored and
returned by POST, GET list and GET one (stripped, same name the UI sent).
L0B-03: projects survive an app restart on the same store_dir: create a
project, rebuild the app via create_app on the SAME store_dir, and GET
/api/v1/projects still lists it with its folder.
"""

import os
import sys

from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "k02l0b-folder-token"
ACTOR = "tester-k02l0b"


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


def test_folder_ref_round_trips_through_post_and_gets():
    client = TestClient(create_app(_settings()))
    resp = client.post(
        "/api/v1/projects",
        json={"name": "harbor", "folder_ref": "  dock-7 "},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    created = resp.json()["project"]
    assert created["name"] == "harbor"
    assert created["folder_ref"] == "dock-7"
    pid = created["project_id"]

    resp = client.get("/api/v1/projects")
    assert resp.status_code == 200
    assert resp.json() == {"projects": [created]}

    resp = client.get(f"/api/v1/projects/{pid}")
    assert resp.status_code == 200
    assert resp.json() == {"project": created}


def test_projects_survive_rebuild_on_same_store_dir(tmp_path):
    first = TestClient(create_app(_settings(tmp_path)))
    resp = first.post(
        "/api/v1/projects",
        json={"name": "harbor", "folder_ref": "shed-3"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    created = resp.json()["project"]
    assert created["folder_ref"] == "shed-3"

    second = TestClient(create_app(_settings(tmp_path)))
    resp = second.get("/api/v1/projects")
    assert resp.status_code == 200
    assert resp.json() == {"projects": [created]}
