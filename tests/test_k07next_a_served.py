# K07NEXT split A: 8 backend-boundary rows over create_app + REAL HTTP.
# One test per row: 163, 162, 168, 242, 248, R-316, R-317, R-318.
# The boundary module agent_si.http.k07next is mounted onto the real
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

TEST_TOKEN = "k07next-solo-token"
BASE_SETTINGS = {
    "testing": True,
    "ui_session_token": TEST_TOKEN,
    "secret_store": "memory",
}


def _load_boundary():
    try:
        from agent_si.http import k07next as module
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


def test_row163_adopted_decision_served(served):
    status, payload = _get(served, "/api/v1/app/adopted-decision")
    assert status == 200, payload
    assert payload == {
        "row": "163",
        "decision": "adopted-system",
        "recorded_in": "docs/reports/K07.md",
        "surfaces": ["settings-layout", "card-kit", "localbench-tab"],
        "endpoint_style": "ENDPOINTS registry strings, never hardcoded URLs",
        "new_locale_keys": 0,
    }


def test_row162_drive_comfort_served(served):
    status, payload = _get(served, "/api/v1/app/drive-comfort")
    assert status == 200, payload
    assert payload == {
        "row": "162",
        "aspect": "comfort",
        "status": "judged-in-drive",
        "run": "row-166-run",
        "sign_off": "in-repo",
    }


def test_row168_design_signoff_served(served):
    status, payload = _get(served, "/api/v1/app/design-signoff")
    assert status == 200, payload
    assert payload == {
        "row": "168",
        "aspect": "design-and-clarity",
        "status": "signed-off-in-drive",
        "new_visual_language": False,
    }


def test_row242_display_labels_served(served):
    status, payload = _get(served, "/api/v1/app/display-labels")
    assert status == 200, payload
    assert payload == {
        "row": "242",
        "rule": "no-raw-ids-as-primary-content",
        "labels": [
            {"id": "projects.list.title", "label": "Projects"},
            {"id": "tasks.list.title", "label": "Tasks"},
            {"id": "agents.live.title", "label": "Live agents"},
            {"id": "shell.sidebar.chat", "label": "Chat"},
        ],
    }


def test_row248_card_parity_served(served):
    status, payload = _get(served, "/api/v1/app/card-parity")
    assert status == 200, payload
    assert payload == {
        "row": "248",
        "pattern": "card",
        "languages": ["en", "uk"],
        "surfaces": [
            "settings-layout",
            "localbench-tab",
            "agents-live-view",
            "projects-view",
        ],
    }


def test_row_r316_edit_guard_served(served):
    status, payload = _get(served, "/api/v1/app/edit-guard")
    assert status == 200, payload
    assert payload == {
        "row": "R-316",
        "guard": "dirty-guarded-edit",
        "late_load_keeps_user_edits": True,
        "fields": ["role", "mode", "provider", "model"],
    }


def test_row_r317_agents_panel_served(served):
    from agent_si.backend import agents_live as live

    live.clear_live_rows()
    try:
        live.record_live_row("k07next-r317", {
            "agent": "worker",
            "scope": "p9",
            "deliverable": "x",
            "status": "running",
        })
        status, payload = _get(served, "/api/v1/app/agents-panel")
        assert status == 200, payload
        assert payload["row"] == "R-317"
        assert payload["mapping"] == {
            "who": "agent",
            "where": "scope",
            "result": "deliverable",
            "state": "status",
        }
        frozen = {
            "agent": "worker",
            "scope": "p9",
            "deliverable": "x",
            "status": "running",
        }
        matches = [
            row for row in payload["agents"]
            if all(row.get(key) == value
                   for key, value in frozen.items())
        ]
        assert matches, payload["agents"]
        for field in live.LIVE_EXTRA_FIELDS:
            assert field in matches[0], (field, matches[0])
    finally:
        live.clear_live_rows()


def test_row_r318_inspector_panel_state_served(served):
    status, payload = _get(
        served, "/api/v1/app/inspector-panel-state")
    assert status == 200, payload
    assert payload == {
        "row": "R-318",
        "panel": "inspector_panel_state",
        "visible": True,
        "sections": ["live-agents", "run-detail"],
    }
