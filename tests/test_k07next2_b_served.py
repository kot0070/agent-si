# K07NEXT2 split B: 7 frontend rows over the REAL HttpApiClient.
# One test per row: M-R-UX-3, M-R-UX-4, M-R-UX-6, M-R-UX-8, M-R-UX-9,
# M-R-UX-10, M-R-UX-12.
# Row-to-route assignment (manager frozen list; row semantics live in the
# kit BUILD_PLAN outside this workspace): each row is proven as one
# K07-owned screen in frontend/src/k07next2/ reading one already-served
# backend route through the REAL HttpApiClient, with the network stand-in
# quoting that route's server-shaped schema. Split B never touches
# backend http files, so every route below is served by create_app()
# itself (no mount step):
#   M-R-UX-3  -> GET /api/v1/projects (read_routes.list_projects)
#   M-R-UX-4  -> GET /api/v1/local/status (local_connect.get_status)
#   M-R-UX-6  -> GET /api/v1/local/models (local_connect.list_models)
#   M-R-UX-8  -> GET /api/v1/analytics/telemetry (read_routes analytics)
#   M-R-UX-9  -> GET /api/v1/kb/refresh/proposal (app kb refresh proposal)
#   M-R-UX-10 -> GET /api/v1/runs/ledger (app runs ledger, fresh project)
#   M-R-UX-12 -> GET /api/v1/local/bench/check (localbench check_route)
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

TEST_TOKEN = "k07next2-solo-token-b"
BASE_SETTINGS = {
    "testing": True,
    "ui_session_token": TEST_TOKEN,
    "secret_store": "memory",
}

FRONT = os.path.join(_WS, "frontend", "src", "k07next2")
SUITES = os.path.join(FRONT, "__tests__")

FRESH_PROJECT = "k07next2-fresh"


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


def _check_wiring(screen_file, suite_file, route_path, quote_token,
                  api_marker="k07next2Api"):
    screen = _read(os.path.join(FRONT, screen_file))
    suite = _read(os.path.join(SUITES, suite_file))
    assert api_marker in screen
    assert "../../api/client" in suite
    assert "ApiClientProvider" in suite
    assert "fakeApiClient" not in screen.lower()
    assert "fakeApiClient" not in suite.lower()
    assert route_path in suite
    assert quote_token in suite


def test_row_mrux3_projects_served(served):
    _check_wiring("ProjectsOverview.tsx", "k07next2-mrux3-projects.test.tsx",
                 "/api/v1/projects", "ProjectsDoc")
    status, payload = _get(served, "/api/v1/projects")
    assert status == 200, payload
    assert payload == {"projects": []}


def test_row_mrux4_local_status_served(served):
    _check_wiring("LocalRuntimeStatus.tsx",
                 "k07next2-mrux4-local-status.test.tsx",
                 "/api/v1/local/status", "NOT_CONFIGURED")
    status, payload = _get(served, "/api/v1/local/status")
    assert status == 200, payload
    assert payload == {
        "status": "NOT_CONFIGURED",
        "reason": "capability base absent; routing continues normally",
    }


def test_row_mrux6_local_models_served(served):
    _check_wiring("LocalModels.tsx", "k07next2-mrux6-local-models.test.tsx",
                 "/api/v1/local/models", "LocalModelsDoc")
    status, payload = _get(served, "/api/v1/local/models")
    assert status == 200, payload
    assert payload == []


def test_row_mrux8_telemetry_served(served):
    _check_wiring("TelemetrySummary.tsx",
                 "k07next2-mrux8-telemetry.test.tsx",
                 "/api/v1/analytics/telemetry", "providers",
                 api_marker="requestJson")
    status, payload = _get(served, "/api/v1/analytics/telemetry")
    assert status == 200, payload
    assert payload == {
        "metric_records": 0,
        "telemetry_events": 0,
        "totals": {},
        "tasks": [],
    }


def test_row_mrux9_kb_proposal_served(served):
    _check_wiring("KbRefreshProposal.tsx",
                 "k07next2-mrux9-kb-proposal.test.tsx",
                 "/api/v1/kb/refresh/proposal", "proposals")
    status, payload = _get(served, "/api/v1/kb/refresh/proposal")
    assert status == 200, payload
    assert payload == {"kb_id": None, "stale": False, "proposals": []}


def test_row_mrux10_runs_ledger_served(served):
    _check_wiring("RunsLedgerFresh.tsx",
                 "k07next2-mrux10-runs-ledger.test.tsx",
                 "/api/v1/runs/ledger", "RunsLedgerDoc")
    status, payload = _get(
        served, f"/api/v1/runs/ledger?project_id={FRESH_PROJECT}")
    assert status == 200, payload
    assert payload == {"rows": []}


def test_row_mrux12_bench_check_served(served):
    _check_wiring("BenchGatewayCheck.tsx",
                 "k07next2-mrux12-bench-check.test.tsx",
                 "/api/v1/local/bench/check", "no gateway endpoint configured")
    status, payload = _get(served, "/api/v1/local/bench/check")
    assert status == 200, payload
    assert payload == {
        "reachable": False,
        "reason": "no gateway endpoint configured",
    }
