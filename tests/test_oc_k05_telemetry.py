"""OC-K05: bench completion feeds telemetry (L2-D06b; rows R-341/M-P4-129).

Served proof over the real create_app + HTTP path (loopback TestClient,
isolated store dir, no keys/network): start a bench run, complete it with
measured rows, and read the bench evidence back from both the results
surface and GET /api/v1/analytics/telemetry totals.
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

TEST_TOKEN = "ock05-token"
ACTOR = "tester-ock05"


def _auth(token=TEST_TOKEN, actor=ACTOR):
    headers = {}
    if actor is not None:
        headers["x-actor"] = actor
    if token is not None:
        headers["x-ui-session-token"] = token
    return headers


def _settings(store_dir):
    return {"testing": True, "ui_session_token": TEST_TOKEN,
            "store_dir": str(store_dir)}


def _rows(model="ock05-model"):
    return [
        {"case_id": "q-001", "kind": "MEASURED", "model_id": model},
        {"case_id": "q-002", "kind": "MEASURED", "model_id": model},
    ]


def test_complete_records_rows_and_bench_telemetry(tmp_path):
    client = TestClient(create_app(_settings(tmp_path)))
    started = client.post(
        "/api/v1/local/bench/runs",
        json={"level": "Quick", "model_id": "ock05-model"},
        headers=_auth(),
    )
    assert started.status_code == 200, started.text
    run_id = started.json()["run_id"]

    done = client.post(
        "/api/v1/local/bench/runs/complete",
        json={"run_id": run_id, "rows": _rows()},
        headers=_auth(),
    )
    assert done.status_code == 200, done.text
    outcome = done.json()
    assert outcome["run_id"] == run_id
    assert outcome["rows"] == 2
    assert len(outcome["metric_ids"]) == 2

    results = client.get(
        "/api/v1/local/bench/results", params={"run_id": run_id})
    assert results.status_code == 200, results.text
    assert len(results.json()) == 2

    telemetry = client.get("/api/v1/analytics/telemetry")
    assert telemetry.status_code == 200, telemetry.text
    totals = telemetry.json()["totals"]
    assert totals.get("bench_runs", 0) >= 1
    assert totals.get("bench_cases", 0) >= 2


def test_complete_without_token_refuses_and_changes_nothing(tmp_path):
    client = TestClient(create_app(_settings(tmp_path)))
    started = client.post(
        "/api/v1/local/bench/runs",
        json={"level": "Quick", "model_id": "ock05-model-unauth"},
        headers=_auth(),
    )
    assert started.status_code == 200, started.text
    run_id = started.json()["run_id"]

    refused = client.post(
        "/api/v1/local/bench/runs/complete",
        json={"run_id": run_id, "rows": _rows("ock05-model-unauth")},
    )
    assert refused.status_code == 401, refused.text
    assert "SESSION_TOKEN_REFUSED" in refused.text

    results = client.get(
        "/api/v1/local/bench/results", params={"run_id": run_id})
    assert results.status_code == 200, results.text
    assert results.json() == []

    telemetry = client.get("/api/v1/analytics/telemetry")
    assert telemetry.status_code == 200, telemetry.text
    totals = telemetry.json()["totals"]
    assert totals.get("bench_runs", 0) == 0
    assert totals.get("bench_cases", 0) == 0

    stopped = client.post(
        "/api/v1/local/bench/runs/stop",
        json={"run_id": run_id},
        headers=_auth(),
    )
    assert stopped.status_code == 200, stopped.text


def test_complete_unknown_run_is_404(tmp_path):
    client = TestClient(create_app(_settings(tmp_path)))
    resp = client.post(
        "/api/v1/local/bench/runs/complete",
        json={"run_id": "run-9999", "rows": _rows()},
        headers=_auth(),
    )
    assert resp.status_code == 404, resp.text


def test_complete_empty_rows_is_400(tmp_path):
    client = TestClient(create_app(_settings(tmp_path)))
    started = client.post(
        "/api/v1/local/bench/runs",
        json={"level": "Quick", "model_id": "ock05-model-empty"},
        headers=_auth(),
    )
    assert started.status_code == 200, started.text
    run_id = started.json()["run_id"]
    resp = client.post(
        "/api/v1/local/bench/runs/complete",
        json={"run_id": run_id, "rows": []},
        headers=_auth(),
    )
    assert resp.status_code == 400, resp.text

    stopped = client.post(
        "/api/v1/local/bench/runs/stop",
        json={"run_id": run_id},
        headers=_auth(),
    )
    assert stopped.status_code == 200, stopped.text
