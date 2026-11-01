# K07NEXT5 split A: 4 backend-boundary rows over create_app + REAL HTTP.
# One test per row: 111-UI, R-341-UI, ARCH-526, MVP_ACCEPT-199.
# The boundary module agent_si.http.k07next5 is mounted onto the real
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
import urllib.parse
import urllib.request

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.abspath(os.path.join(_HERE, ".."))
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

TEST_TOKEN = "k07next5-solo-token"
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
        from agent_si.http import k07next5 as module
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


def test_row_111_local_ai_decision_write_served(served):
    created_status, created = _post(
        served, "/api/v1/app/local-ai/decision-update",
        {"project_key": "k07next5-a",
         "patch": {"model_id": "k07next5-model"},
         "statement": "k07next5 adopt model",
         "reason": "k07next5 proof",
         "authority": "ui"})
    assert created_status == 200, created
    assert created["row"] == "111-UI"
    assert created["decision_id"].startswith("dec-")
    assert created["config"]["model_id"] == "k07next5-model"
    updated_status, updated = _post(
        served, "/api/v1/app/local-ai/decision-update",
        {"project_key": "k07next5-a",
         "patch": {"endpoint_url": "http://127.0.0.1:11434"},
         "statement": "k07next5 point endpoint",
         "reason": "k07next5 proof",
         "authority": "ui"})
    assert updated_status == 200, updated
    assert updated["config"]["endpoint_url"] == "http://127.0.0.1:11434"
    assert updated["config"]["model_id"] == "k07next5-model"
    status, payload = _get(
        served, "/api/v1/app/local-ai/view?project_key=k07next5-a")
    assert status == 200, payload
    assert payload["row"] == "111-UI"
    assert payload["title_key"] == "settings.localAi.title"
    assert payload["config"]["model_id"] == "k07next5-model"
    bare = dict(WRITE_HEADERS)
    del bare["x-ui-session-token"]
    denied, _ = _post(
        served, "/api/v1/app/local-ai/decision-update",
        {"project_key": "k07next5-a", "patch": {},
         "statement": "s", "reason": "r", "authority": "ui"},
        headers=bare)
    assert denied == 403, denied
    missing_status, missing = _post(
        served, "/api/v1/app/local-ai/decision-update",
        {"project_key": "k07next5-a", "patch": {}})
    assert missing_status == 400, missing
    assert missing["detail"] == "decision record fields are required"


def test_row_r341_bench_tab_served(served):
    query = urllib.parse.urlencode(
        {"model_id": "k07next5-bench", "level": "Quick", "pc_in_use": "1"})
    status, payload = _get(served, "/api/v1/app/bench/tab?" + query)
    assert status == 200, payload
    assert payload["row"] == "R-341-UI"
    estimate = payload["estimate"]
    assert estimate["minutes_min"] >= 5.0
    assert estimate["minutes_max"] >= estimate["minutes_min"]
    codes = [warning["code"] for warning in payload["warnings"]]
    assert "BENCH_DURATION" in codes
    assert "BENCH_PC_IN_USE" in codes
    assert payload["scan"] == []
    assert payload["results"] == []
    assert payload["results_by_model"] == {}
    assert isinstance(payload["history"], list)
    assert isinstance(payload["gateway"]["reachable"], bool)
    idle_query = urllib.parse.urlencode(
        {"model_id": "k07next5-bench", "level": "Quick"})
    idle_status, idle = _get(served, "/api/v1/app/bench/tab?" + idle_query)
    assert idle_status == 200, idle
    idle_codes = [warning["code"] for warning in idle["warnings"]]
    assert idle_codes == ["BENCH_DURATION"]


def test_row_arch526_settings_view_served(served):
    status, payload = _get(
        served, "/api/v1/app/local-ai/settings-view?project_key=proj-a")
    assert status == 200, payload
    assert payload["row"] == "B0B-UNCOVERED_ARCH-526"
    assert payload["title_key"] == "settings.localAi.title"
    assert payload["purpose_key"] == "settings.localAi.purpose"
    config = payload["config"]
    assert config["endpoint_url"].startswith("http")
    assert config["model_id"]
    assert config["permission_scope"]
    assert payload["endpoint_url"] == config["endpoint_url"]
    assert isinstance(payload["models"], list)
    missing_status, _ = _get(
        served, "/api/v1/app/local-ai/settings-view?project_key=nope")
    assert missing_status == 404, missing_status


def test_row_mvp199_provider_health_transitions_served(served):
    status, payload = _get(
        served, "/api/v1/app/provider-health/transitions")
    assert status == 200, payload
    assert payload["row"] == "B0B-UNCOVERED_MVP_ACCEPT-199"
    assert payload["transitions"] == ["UP", "DEGRADED", "DOWN", "DOWN"]
    assert payload["rows"] == [
        {"registry": "ONLINE", "service": "UP", "reason": ""},
        {"registry": "DEGRADED", "service": "DEGRADED", "reason": ""},
        {"registry": "OFFLINE", "service": "DOWN", "reason": ""},
        {"registry": "UNKNOWN", "service": "DOWN",
         "reason": "unknown-health"},
    ]
