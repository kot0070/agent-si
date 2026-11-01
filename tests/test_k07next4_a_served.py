# K07NEXT4 split A: 6 backend-boundary rows over create_app + REAL HTTP.
# One test per row: LIVE0-08, LIVE0B-01, LIVE0B-04, LIVE0B-05, MH-5, MH-6.
# The boundary module agent_si.http.k07next4 is mounted onto the real
# seam app (app.py untouched); a uvicorn server on 127.0.0.1 serves it
# in-process and every assertion below drives that socket via urllib
# (no route mocks, no TestClient). RED shape: with the boundary module
# absent the fixture mounts nothing and each test sees an honest 404.
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.abspath(os.path.join(_HERE, ".."))
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

TEST_TOKEN = "k07next4-solo-token"
BASE_SETTINGS = {
    "testing": True,
    "ui_session_token": TEST_TOKEN,
    "secret_store": "memory",
}

WRITE_HEADERS = {
    "Content-Type": "application/json",
    "x-actor": "ui",
    "x-ui-session-token": TEST_TOKEN,
}


def _load_boundary():
    try:
        from agent_si.http import k07next4 as module
    except Exception:
        return None
    return module


@pytest.fixture(scope="module")
def served():
    from agent_si.backend.app import create_app

    boundary = _load_boundary()
    app = create_app(dict(BASE_SETTINGS))
    if boundary is not None:
        boundary.mount(app)
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=0,
                            log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if getattr(server, "started", False):
            break
        time.sleep(0.05)
    assert getattr(server, "started", False), "uvicorn never started"
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=15)


def _get(base, path):
    request = urllib.request.Request(base + path, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return (response.status,
                    json.loads(response.read().decode("utf-8")))
    except urllib.error.HTTPError as err:
        return (err.code, json.loads(err.read().decode("utf-8")))


def _post(base, path, body, headers=None):
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        base + path, data=data,
        headers=headers or dict(WRITE_HEADERS), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return (response.status,
                    json.loads(response.read().decode("utf-8")))
    except urllib.error.HTTPError as err:
        return (err.code, json.loads(err.read().decode("utf-8")))


def test_row_live008_session_write_served(served):
    status, payload = _post(served, "/api/v1/app/session-write",
                            {})
    assert status == 200, payload
    assert payload == {
        "row": "LIVE0-08",
        "token_ok": True,
        "actor": "ui",
    }
    bare = dict(WRITE_HEADERS)
    del bare["x-ui-session-token"]
    denied, _ = _post(served, "/api/v1/app/session-write", {},
                      headers=bare)
    assert denied == 403, denied


def test_row_live0b01_projects_live_served(served):
    created_status, created = _post(
        served, "/api/v1/app/projects",
        {"name": "k07next4-alpha", "folder_ref": "f-alpha"})
    assert created_status == 200, created
    assert created["row"] == "LIVE0B-01"
    project = created["project"]
    assert project["name"] == "k07next4-alpha"
    assert project["project_id"]
    status, payload = _get(served, "/api/v1/app/projects")
    assert status == 200, payload
    assert payload["row"] == "LIVE0B-01"
    names = [row["name"] for row in payload["projects"]]
    assert "k07next4-alpha" in names


def test_row_live0b04_page_shell_served(served):
    status, payload = _get(served, "/api/v1/app/page-shell")
    assert status == 200, payload
    assert payload == {
        "row": "LIVE0B-04",
        "title_key": "shell.sidebar.projects",
        "title": "Projects",
        "console_class": "agent-si-console",
    }


def test_row_live0b05_chat_task_served(served):
    status, payload = _post(served, "/api/v1/app/chat-task",
                            {"prompt_ref": "k07next4-hello"})
    assert status == 200, payload
    assert payload["row"] == "LIVE0B-05"
    assert payload["prompt_ref"] == "k07next4-hello"
    assert payload["status"] == "started"
    assert payload["task_id"]


def test_row_mh5_step_turn_served(served):
    status, payload = _get(served, "/api/v1/app/step-turn?advance=1")
    assert status == 200, payload
    assert payload["row"] == "MH-5"
    assert payload["turn"] == 1
    assert payload["model_input"]
    assert payload["action"]
    assert payload["observation"]
    assert payload["model_input"] != payload["observation"]


def test_row_mh6_turn_triple_served(served):
    status, payload = _get(served, "/api/v1/app/turn-triple")
    assert status == 200, payload
    assert payload["row"] == "MH-6"
    assert len(payload["turns"]) >= 1
    triple = payload["turns"][0]
    assert triple["plan"]
    assert triple["action"]
    assert triple["observation"]
    assert payload["used"] >= 1
    assert payload["limit"] == 10000
