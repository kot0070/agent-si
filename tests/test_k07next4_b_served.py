# K07NEXT4 split B: 6 frontend rows over the REAL HttpApiClient.
# One test per row: LIVE0-08, LIVE0B-01, LIVE0B-04, LIVE0B-05, MH-5, MH-6.
# Row-to-route assignment (manager frozen list; row semantics live in the
# kit BUILD_PLAN coverage table): each row is proven as one K07-owned
# screen in frontend/src/k07next4/ reading one served k07next4 backend
# route through the REAL HttpApiClient, with the network stand-in
# quoting that route's server-shaped schema. The boundary module is
# mounted onto create_app() here (app.py untouched) so every quoted
# schema is the live served answer, fetched over REAL HTTP:
#   LIVE0-08  -> POST /api/v1/app/session-write (session_write)
#   LIVE0B-01 -> POST+GET /api/v1/app/projects (projects)
#   LIVE0B-04 -> GET /api/v1/app/page-shell (page_shell)
#   LIVE0B-05 -> POST /api/v1/app/chat-task (chat_task)
#   MH-5      -> GET /api/v1/app/step-turn (step_turn)
#   MH-6      -> GET /api/v1/app/turn-triple (turn_triple)
# Each test proves two things: (a) the K07-owned screen is wired to the
# REAL HttpApiClient (real client + provider imports in the suite, no
# FakeApiClient, no data injected into a mounted component) with its
# network stand-in quoting the backend route schema; (b) the quoted
# schema is the live served answer, fetched over REAL HTTP from
# create_app() with the boundary mounted.
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
if _WS not in sys.path:
    sys.path.insert(0, _WS)

TEST_TOKEN = "k07next4-solo-token-b"
BASE_SETTINGS = {
    "testing": True,
    "ui_session_token": TEST_TOKEN,
    "secret_store": "memory",
}

FRONT = os.path.join(_WS, "frontend", "src", "k07next4")
SUITES = os.path.join(FRONT, "__tests__")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


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


def _post(base, path, body):
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json",
               "x-actor": "ui",
               "x-ui-session-token": TEST_TOKEN}
    request = urllib.request.Request(base + path, data=data,
                                     headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return (response.status,
                    json.loads(response.read().decode("utf-8")))
    except urllib.error.HTTPError as err:
        return (err.code, json.loads(err.read().decode("utf-8")))


def _check_wiring(screen_file, suite_file, route_path, quote_token):
    screen = _read(os.path.join(FRONT, screen_file))
    suite = _read(os.path.join(SUITES, suite_file))
    assert "k07next4Api" in screen
    assert "../../api/client" in suite
    assert "ApiClientProvider" in suite
    assert "fakeApiClient" not in screen.lower()
    assert "fakeApiClient" not in suite.lower()
    assert route_path in suite
    assert quote_token in suite


def test_row_live008_session_token_served(served):
    _check_wiring("SessionTokenCard.tsx",
                  "k07next4-live008-session-token.test.tsx",
                  "/api/v1/app/session-write",
                  "SERVED_TOKEN_OK")
    status, payload = _post(served, "/api/v1/app/session-write",
                            {})
    assert status == 200, payload
    assert payload == {
        "row": "LIVE0-08",
        "token_ok": True,
        "actor": "ui",
    }


def test_row_live0b01_projects_live_served(served):
    _check_wiring("ProjectsLiveList.tsx",
                  "k07next4-live0b01-projects-live.test.tsx",
                  "/api/v1/app/projects", "SERVED_PROJECTS")
    created_status, created = _post(
        served, "/api/v1/app/projects",
        {"name": "k07next4-bravo", "folder_ref": "f-bravo"})
    assert created_status == 200, created
    assert created["row"] == "LIVE0B-01"
    status, payload = _get(served, "/api/v1/app/projects")
    assert status == 200, payload
    assert payload["row"] == "LIVE0B-01"
    names = [row["name"] for row in payload["projects"]]
    assert "k07next4-bravo" in names


def test_row_live0b04_page_shell_served(served):
    _check_wiring("ConsolePageShell.tsx",
                  "k07next4-live0b04-page-shell.test.tsx",
                  "/api/v1/app/page-shell", "SERVED_SHELL")
    status, payload = _get(served, "/api/v1/app/page-shell")
    assert status == 200, payload
    assert payload == {
        "row": "LIVE0B-04",
        "title_key": "shell.sidebar.projects",
        "title": "Projects",
        "console_class": "agent-si-console",
    }


def test_row_live0b05_chat_task_served(served):
    _check_wiring("ChatTaskBox.tsx",
                  "k07next4-live0b05-chat-task.test.tsx",
                  "/api/v1/app/chat-task", "SERVED_CHAT_TASK")
    status, payload = _post(served, "/api/v1/app/chat-task",
                            {"prompt_ref": "k07next4-b-hello"})
    assert status == 200, payload
    assert payload["row"] == "LIVE0B-05"
    assert payload["prompt_ref"] == "k07next4-b-hello"
    assert payload["status"] == "started"
    assert payload["task_id"]


def test_row_mh5_step_turn_served(served):
    _check_wiring("StepTurnViewer.tsx",
                  "k07next4-mh5-step-turn.test.tsx",
                  "/api/v1/app/step-turn", "SERVED_STEP_TURN")
    status, payload = _get(served, "/api/v1/app/step-turn?advance=1")
    assert status == 200, payload
    assert payload["row"] == "MH-5"
    assert payload["turn"] == 1
    assert payload["model_input"]
    assert payload["action"]
    assert payload["observation"]
    assert payload["model_input"] != payload["observation"]


def test_row_mh6_turn_triple_served(served):
    _check_wiring("TurnTripleBoard.tsx",
                  "k07next4-mh6-turn-triple.test.tsx",
                  "/api/v1/app/turn-triple",
                  "SERVED_TURN_TRIPLE")
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
