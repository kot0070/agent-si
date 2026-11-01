"""K05NEXT FalconA served behaviour proofs (rows MVP_ACCEPT-221, MVP_ACCEPT-222, BP05-94, ARCH-367, ARCH-373).

RED start: this file is written before src/agent_si/local/k05next_a.py exists,
so collection fails with a module import error on the unchanged tree.
GREEN: the module provides a FastAPI router; the proof app is built here
in-test (never in product) and driven with TestClient. Entries stay
JSON-serializable.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from agent_si.local import k05next_a  # noqa: E402


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(k05next_a.router)
    return TestClient(app)


def test_mvp_accept_221_served() -> None:
    """B0B-UNCOVERED_MVP_ACCEPT-221: non-running runtimes keep UNKNOWN, grant nothing."""
    client = _client()

    stopped = client.post(
        "/api/v1/local/mvp-accept-221/serve",
        json={"store_ref": "store-ref-221", "running": False, "tiers": ["MEASURED"]},
    )
    assert stopped.status_code == 200, stopped.text
    body = stopped.json()
    json.dumps(body)
    assert body["tier"] == "UNKNOWN"
    assert body["eligible"] is False
    assert body["granted"] == []

    unknown_only = client.post(
        "/api/v1/local/mvp-accept-221/serve",
        json={"store_ref": "store-ref-221", "running": True, "tiers": ["UNKNOWN"]},
    )
    assert unknown_only.status_code == 200, unknown_only.text
    body = unknown_only.json()
    json.dumps(body)
    assert body["tier"] == "UNKNOWN"
    assert body["eligible"] is False
    assert "UNKNOWN_TIER_INELIGIBLE" in body["reason"]
    assert body["granted"] == []

    measured = client.post(
        "/api/v1/local/mvp-accept-221/serve",
        json={"store_ref": "store-ref-221", "running": True, "tiers": ["UNKNOWN", "MEASURED"]},
    )
    assert measured.status_code == 200, measured.text
    body = measured.json()
    json.dumps(body)
    assert body["tier"] == "MEASURED"
    assert body["eligible"] is True

    bad = client.post(
        "/api/v1/local/mvp-accept-221/serve",
        json={"store_ref": "  ", "running": True, "tiers": []},
    )
    assert bad.status_code == 422, bad.text
    assert bad.json()["code"] == "K05NEXT_A_BAD_PAYLOAD"


def test_mvp_accept_222_served() -> None:
    """B0B-UNCOVERED_MVP_ACCEPT-222: evidence-less keys yield no row, local classes stay UNKNOWN."""
    client = _client()

    bare = client.post(
        "/api/v1/local/mvp-accept-222/serve",
        json={"model_id": "k05next-probe", "task_class": "draft", "columns": ["model_id", "task_class"]},
    )
    assert bare.status_code == 200, bare.text
    body = bare.json()
    json.dumps(body)
    assert body["tier"] == "UNKNOWN"
    assert body["row_found"] is False

    evidenced = client.post(
        "/api/v1/local/mvp-accept-222/serve",
        json={
            "model_id": "k05next-probe",
            "task_class": "draft",
            "columns": ["model_id", "task_class", "benchmark_evidence"],
        },
    )
    assert evidenced.status_code == 200, evidenced.text
    body = evidenced.json()
    json.dumps(body)
    assert body["tier"] == "PROXY"
    assert body["row_found"] is True

    bad = client.post(
        "/api/v1/local/mvp-accept-222/serve",
        json={"model_id": "", "task_class": "draft", "columns": []},
    )
    assert bad.status_code == 422, bad.text
    assert bad.json()["code"] == "K05NEXT_A_BAD_PAYLOAD"


def test_bp05_94_served() -> None:
    """B0B-UNCOVERED_BP05-94: prose notes land as PROXY with UNKNOWN freshness and null scores."""
    client = _client()

    stale = client.post(
        "/api/v1/local/bp05-94/serve",
        json={"notes": "agent_ops.db prose note", "fresh_benchmark": False},
    )
    assert stale.status_code == 200, stale.text
    body = stale.json()
    json.dumps(body)
    assert body["tier"] == "PROXY"
    assert body["freshness"] == "UNKNOWN"
    assert body["score"] is None

    fresh = client.post(
        "/api/v1/local/bp05-94/serve",
        json={"notes": "agent_ops.db prose note", "fresh_benchmark": True, "threshold": 85, "shape": "scalar"},
    )
    assert fresh.status_code == 200, fresh.text
    body = fresh.json()
    json.dumps(body)
    assert body["tier"] == "MEASURED"
    assert body["score"] == 85

    unmeasured = client.post(
        "/api/v1/local/bp05-94/serve",
        json={"notes": "agent_ops.db prose note", "fresh_benchmark": True},
    )
    assert unmeasured.status_code == 422, unmeasured.text
    assert unmeasured.json()["code"] == "K05NEXT_A_VALIDATION_FAILED"

    bad = client.post(
        "/api/v1/local/bp05-94/serve",
        json={"notes": " ", "fresh_benchmark": False},
    )
    assert bad.status_code == 422, bad.text
    assert bad.json()["code"] == "K05NEXT_A_BAD_PAYLOAD"


def test_arch_367_served() -> None:
    """B0B-UNCOVERED_ARCH-367: stale versioned copies refused as current, only current rows serve."""
    client = _client()

    mixed = client.post(
        "/api/v1/local/arch-367/serve",
        json={
            "copies": [
                {"ref": "cap:probe:draft", "version": 3},
                {"ref": "cap:probe:draft", "version": 1},
            ],
            "current": {"cap:probe:draft": 3},
            "requested": [
                {"ref": "cap:probe:draft", "version": 3},
                {"ref": "cap:probe:draft", "version": 1},
            ],
        },
    )
    assert mixed.status_code == 200, mixed.text
    body = mixed.json()
    json.dumps(body)
    assert body["served"] == [{"ref": "cap:probe:draft", "version": 3}]
    assert len(body["refused"]) == 1
    assert body["refused"][0]["ref"] == "cap:probe:draft"
    assert "versioned stale backup copies are never served as current" in body["refused"][0]["reason"]

    unknown = client.post(
        "/api/v1/local/arch-367/serve",
        json={
            "copies": [],
            "current": {},
            "requested": [{"ref": "cap:ghost:draft", "version": 1}],
        },
    )
    assert unknown.status_code == 404, unknown.text
    assert unknown.json()["code"] == "K05NEXT_A_UNKNOWN_ROW"

    bad = client.post("/api/v1/local/arch-367/serve", json={"requested": []})
    assert bad.status_code == 422, bad.text
    assert bad.json()["code"] == "K05NEXT_A_BAD_PAYLOAD"


def test_arch_373_served() -> None:
    """B0B-UNCOVERED_ARCH-373: prose notes go only through the labelled PROXY adapter."""
    client = _client()

    adapted = client.post(
        "/api/v1/local/arch-373/serve",
        json={"notes": "prose capability note", "label": "k05next-proxy"},
    )
    assert adapted.status_code == 200, adapted.text
    body = adapted.json()
    json.dumps(body)
    assert body["tier"] == "PROXY"
    assert body["adapter"] == "PROXY"
    assert body["label"] == "k05next-proxy"
    assert body["score"] is None

    unlabelled = client.post(
        "/api/v1/local/arch-373/serve",
        json={"notes": "prose capability note", "label": "  "},
    )
    assert unlabelled.status_code == 422, unlabelled.text
    assert unlabelled.json()["code"] == "K05NEXT_A_VALIDATION_FAILED"

    bad = client.post(
        "/api/v1/local/arch-373/serve",
        json={"notes": "", "label": "k05next-proxy"},
    )
    assert bad.status_code == 422, bad.text
    assert bad.json()["code"] == "K05NEXT_A_BAD_PAYLOAD"


def test_k05next_a_identity_pinned() -> None:
    """Module identity: MODEL_ID exact plus the frozen ERROR_CODES triple."""
    assert k05next_a.MODEL_ID == "k05next-a-1"
    assert k05next_a.ERROR_CODES == (
        "K05NEXT_A_BAD_PAYLOAD",
        "K05NEXT_A_VALIDATION_FAILED",
        "K05NEXT_A_UNKNOWN_ROW",
    )
