# K07NEXT5 split B: 4 frontend rows over the REAL HttpApiClient.
# One test per row: 111-UI, R-341-UI, B0B-UNCOVERED_ARCH-526,
# B0B-UNCOVERED_MVP_ACCEPT-199.
# Row-to-route assignment (manager frozen list; row semantics live in the
# kit BUILD_PLAN coverage table): each row is proven as one K07-owned
# screen in frontend/src/k07next5/ reading one served k07next5 backend
# route through the REAL HttpApiClient, with the network stand-in
# quoting that route's server-shaped schema. The boundary module is
# mounted onto create_app() here (app.py untouched) so every quoted
# schema is the live served answer, fetched over REAL HTTP:
#   111-UI                  -> POST /api/v1/app/local-ai/decision-update
#                              (local_ai_decision_update) + GET
#                              /api/v1/app/local-ai/view (local_ai_view)
#   R-341-UI                -> GET /api/v1/app/bench/tab (bench_tab)
#   B0B-UNCOVERED_ARCH-526  -> GET /api/v1/app/local-ai/settings-view
#                              (local_ai_settings_view)
#   B0B-UNCOVERED_MVP_ACCEPT-199 -> GET
#                              /api/v1/app/provider-health/transitions
#                              (provider_health_transitions)
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
import urllib.parse
import urllib.request

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.abspath(os.path.join(_HERE, ".."))
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
if _WS not in sys.path:
    sys.path.insert(0, _WS)

TEST_TOKEN = "k07next5-solo-token-b"
BASE_SETTINGS = {
    "testing": True,
    "ui_session_token": TEST_TOKEN,
    "secret_store": "memory",
}

FRONT = os.path.join(_WS, "frontend", "src", "k07next5")
SUITES = os.path.join(FRONT, "__tests__")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


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
    assert "k07next5Api" in screen
    assert "../../api/client" in suite
    assert "ApiClientProvider" in suite
    assert "fakeApiClient" not in screen.lower()
    assert "fakeApiClient" not in suite.lower()
    assert route_path in suite
    assert quote_token in suite


def test_row_111ui_local_ai_decision_served(served):
    _check_wiring("LocalAiDecisionCard.tsx",
                  "k07next5-111ui-local-ai-decision.test.tsx",
                  "/api/v1/app/local-ai/decision-update",
                  "SERVED_DECISION")
    body = {"project_key": "k07next5-b",
            "patch": {"model_id": "k07next5-b-model"},
            "statement": "k07next5 adopt model",
            "reason": "k07next5 proof",
            "authority": "ui"}
    status, payload = _post(
        served, "/api/v1/app/local-ai/decision-update", body)
    assert status == 200, payload
    assert payload["row"] == "111-UI"
    assert payload["decision_id"].startswith("dec-")
    assert payload["config"]["project_key"] == "k07next5-b"
    assert payload["config"]["model_id"] == "k07next5-b-model"
    view_status, view = _get(
        served, "/api/v1/app/local-ai/view?project_key=k07next5-b")
    assert view_status == 200, view
    assert view["row"] == "111-UI"
    assert view["title_key"] == "settings.localAi.title"
    assert view["config"]["model_id"] == "k07next5-b-model"


def test_row_r341ui_bench_tab_served(served):
    _check_wiring("BenchSettingsTab.tsx",
                  "k07next5-r341ui-bench-tab.test.tsx",
                  "/api/v1/app/bench/tab", "SERVED_BENCH_TAB")
    query = urllib.parse.urlencode(
        {"model_id": "k07next5-bench-b", "level": "Quick",
         "pc_in_use": "1"})
    status, payload = _get(served, "/api/v1/app/bench/tab?" + query)
    assert status == 200, payload
    assert payload["row"] == "R-341-UI"
    estimate = payload["estimate"]
    assert estimate["model_id"] == "k07next5-bench-b"
    assert estimate["level"] == "Quick"
    assert estimate["minutes_min"] >= 5.0
    assert estimate["minutes_max"] >= estimate["minutes_min"]
    codes = [warning["code"] for warning in payload["warnings"]]
    assert "BENCH_DURATION" in codes
    assert "BENCH_PC_IN_USE" in codes
    assert payload["scan"] == []
    assert isinstance(payload["results"], list)
    assert isinstance(payload["history"], list)
    assert isinstance(payload["gateway"]["reachable"], bool)
    idle_query = urllib.parse.urlencode(
        {"model_id": "k07next5-bench-b", "level": "Quick"})
    idle_status, idle = _get(
        served, "/api/v1/app/bench/tab?" + idle_query)
    assert idle_status == 200, idle
    idle_codes = [warning["code"] for warning in idle["warnings"]]
    assert idle_codes == ["BENCH_DURATION"]


def test_row_arch526_local_ai_view_served(served):
    _check_wiring("LocalAiViewCard.tsx",
                  "k07next5-arch526-local-ai-view.test.tsx",
                  "/api/v1/app/local-ai/settings-view",
                  "SERVED_LOCAL_AI_VIEW")
    status, payload = _get(
        served,
        "/api/v1/app/local-ai/settings-view?project_key=proj-a")
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


def test_row_mvpaccept199_provider_outage_served(served):
    _check_wiring("ProviderOutageCard.tsx",
                  "k07next5-mvpaccept199-provider-outage.test.tsx",
                  "/api/v1/app/provider-health/transitions",
                  "SERVED_TRANSITIONS")
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
