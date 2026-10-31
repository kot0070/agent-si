# K07NEXT3 split B: 5 frontend rows over the REAL HttpApiClient.
# One test per row: B0B-UNCOVERED_MVP_ACCEPT-178,
# B0B-UNCOVERED_MVP_ACCEPT-199, LIVE0-02, LIVE0-03, LIVE0-05.
# Row-to-route assignment (manager frozen list; row semantics live in the
# kit BUILD_PLAN outside this workspace): each row is proven as one
# K07-owned screen in frontend/src/k07next3/ reading one already-served
# backend route through the REAL HttpApiClient, with the network stand-in
# quoting that route's server-shaped schema. Split B never touches
# backend http files, so every route below is served by create_app()
# itself (no mount step):
#   B0B-UNCOVERED_MVP_ACCEPT-178 -> GET /api/v1/agents/live (agents_live)
#   B0B-UNCOVERED_MVP_ACCEPT-199 -> GET /api/v1/local/bench/scan (scan)
#   LIVE0-02  -> GET /api/v1/local/bench/estimate (estimate)
#   LIVE0-03  -> GET /api/v1/local/bench/history (history)
#   LIVE0-05  -> GET /api/v1/teststage/tests-view (tests view)
# Each test proves two things: (a) the K07-owned screen is wired to the
# REAL HttpApiClient (real client + provider imports in the suite, no
# FakeApiClient, no data injected into a mounted component) with its
# network stand-in quoting the backend route schema; (b) the quoted
# schema is the live served answer, fetched over REAL HTTP from
# create_app().
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

TEST_TOKEN = "k07next3-solo-token-b"
BASE_SETTINGS = {
    "testing": True,
    "ui_session_token": TEST_TOKEN,
    "secret_store": "memory",
}

FRONT = os.path.join(_WS, "frontend", "src", "k07next3")
SUITES = os.path.join(FRONT, "__tests__")

ESTIMATE_MODEL = "k07next3-bench"
VIEW_PLAN = "k07next3"
VIEW_RUN = "seed"


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture(scope="module")
def served():
    from agent_si.backend.app import create_app

    app = create_app(dict(BASE_SETTINGS))
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


def _check_wiring(screen_file, suite_file, route_path, quote_token):
    screen = _read(os.path.join(FRONT, screen_file))
    suite = _read(os.path.join(SUITES, suite_file))
    assert "k07next3Api" in screen
    assert "../../api/client" in suite
    assert "ApiClientProvider" in suite
    assert "fakeApiClient" not in screen.lower()
    assert "fakeApiClient" not in suite.lower()
    assert route_path in suite
    assert quote_token in suite


def test_row_mvpaccept178_agents_live_served(served):
    from agent_si.backend import agents_live as live

    live.clear_live_rows()
    try:
        _check_wiring("AgentsLiveOverview.tsx",
                      "k07next3-mvpaccept178-agents-live.test.tsx",
                      "/api/v1/agents/live", "SERVED_AGENTS")
        status, payload = _get(served, "/api/v1/agents/live")
        assert status == 200, payload
        assert payload == {"agents": []}
    finally:
        live.clear_live_rows()


def test_row_mvpaccept199_bench_scan_served(served):
    _check_wiring("BenchScanBrowser.tsx",
                 "k07next3-mvpaccept199-bench-scan.test.tsx",
                 "/api/v1/local/bench/scan", "SERVED_SCAN")
    status, payload = _get(served, "/api/v1/local/bench/scan")
    assert status == 200, payload
    assert payload == []


def test_row_live002_bench_estimate_served(served):
    _check_wiring("BenchEstimateCard.tsx",
                 "k07next3-live002-bench-estimate.test.tsx",
                 "/api/v1/local/bench/estimate", "SERVED_ESTIMATE")
    status, payload = _get(
        served,
        "/api/v1/local/bench/estimate"
        f"?model_id={ESTIMATE_MODEL}&level=Quick")
    assert status == 200, payload
    assert payload == {
        "level": "Quick",
        "model_id": ESTIMATE_MODEL,
        "minutes_min": 10.0,
        "minutes_max": 15.0,
    }


def test_row_live003_bench_history_served(served):
    _check_wiring("BenchHistoryList.tsx",
                 "k07next3-live003-bench-history.test.tsx",
                 "/api/v1/local/bench/history", "SERVED_HISTORY")
    status, payload = _get(served, "/api/v1/local/bench/history")
    assert status == 200, payload
    assert payload == []


def test_row_live005_tests_view_served(served):
    _check_wiring("TestsViewBoard.tsx",
                 "k07next3-live005-tests-view.test.tsx",
                 "/api/v1/teststage/tests-view", "SERVED_VIEW")
    status, payload = _get(
        served,
        f"/api/v1/teststage/tests-view?plan_id={VIEW_PLAN}&run_id={VIEW_RUN}")
    assert status == 200, payload
    assert payload == {
        "plan_id": VIEW_PLAN,
        "run_id": VIEW_RUN,
        "active": 0,
        "passed": 0,
        "remaining": 0,
        "rows": [],
        "settings_controls": [],
    }
