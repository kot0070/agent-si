"""K05REST served behaviour proofs (rows M-D-D10, M-D-D22, MVP_ACCEPT-50, MVP_ACCEPT-53).

RED start: this file is written before src/agent_si/local/k05rest_a.py exists,
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

from agent_si.local import k05rest_a  # noqa: E402


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(k05rest_a.router)
    return TestClient(app)


def test_d_d10_served() -> None:
    """M-D-D10: refreshed capability knowledge serves only current versions; original untouched."""
    client = _client()

    current = client.post(
        "/k05rest/d-d10/serve",
        json={
            "copies": [
                {"ref": "cap:probe:refresh", "version": 4},
                {"ref": "cap:probe:refresh", "version": 2},
            ],
            "current": {"cap:probe:refresh": 4},
            "requested": [
                {"ref": "cap:probe:refresh", "version": 4},
                {"ref": "cap:probe:refresh", "version": 2},
            ],
        },
    )
    assert current.status_code == 200, current.text
    body = current.json()
    json.dumps(body)
    assert body["served"] == [{"ref": "cap:probe:refresh", "version": 4}]
    assert len(body["refused"]) == 1
    assert body["refused"][0]["ref"] == "cap:probe:refresh"
    assert "versioned stale backup copies are never served as current" in body["refused"][0]["reason"]
    assert body["original_untouched"] is True

    unknown = client.post(
        "/k05rest/d-d10/serve",
        json={
            "copies": [],
            "current": {},
            "requested": [{"ref": "cap:ghost:refresh", "version": 1}],
        },
    )
    assert unknown.status_code == 404, unknown.text
    assert unknown.json()["code"] == "K05REST_A_UNKNOWN_ROW"

    bad = client.post("/k05rest/d-d10/serve", json={"requested": []})
    assert bad.status_code == 422, bad.text
    assert bad.json()["code"] == "K05REST_A_BAD_PAYLOAD"


def test_d_d22_served() -> None:
    """M-D-D22: helper attach runs the passive gate first and refuses when busy."""
    client = _client()

    idle = client.post(
        "/k05rest/d-d22/serve",
        json={"gateway": "gw-idle-1", "passive_ok": True},
    )
    assert idle.status_code == 200, idle.text
    body = idle.json()
    json.dumps(body)
    assert body["allowed"] is True
    assert body["contacted"] is True
    assert body["violation"] is None

    busy = client.post(
        "/k05rest/d-d22/serve",
        json={"gateway": "gw-busy-1", "passive_ok": False},
    )
    assert busy.status_code == 200, busy.text
    body = busy.json()
    json.dumps(body)
    assert body["allowed"] is False
    assert body["contacted"] is False
    assert body["violation"] == "PASSIVE_GATE_REFUSED"

    bad = client.post(
        "/k05rest/d-d22/serve",
        json={"gateway": "  ", "passive_ok": True},
    )
    assert bad.status_code == 422, bad.text
    assert bad.json()["code"] == "K05REST_A_BAD_PAYLOAD"


def test_mvp_accept_50_served() -> None:
    """B0B-UNCOVERED_MVP_ACCEPT-50: SPLIT carries local draft plus cloud verify atomically."""
    client = _client()

    ordered = client.post(
        "/k05rest/mvp-accept-50/serve",
        json={
            "local_draft_ref": "draft-50",
            "cloud_verify_ref": "verify-50",
            "stages": ["local_draft", "cloud_verify"],
            "provenance": ["local", "cloud"],
        },
    )
    assert ordered.status_code == 200, ordered.text
    body = ordered.json()
    json.dumps(body)
    assert body["ordered"] is True
    assert body["dual"] is True

    swapped = client.post(
        "/k05rest/mvp-accept-50/serve",
        json={
            "local_draft_ref": "draft-50",
            "cloud_verify_ref": "verify-50",
            "stages": ["cloud_verify", "local_draft"],
            "provenance": ["local", "cloud"],
        },
    )
    assert swapped.status_code == 422, swapped.text
    assert swapped.json()["code"] == "K05REST_A_VALIDATION_FAILED"

    gap = client.post(
        "/k05rest/mvp-accept-50/serve",
        json={
            "local_draft_ref": "draft-50",
            "cloud_verify_ref": "verify-50",
            "stages": ["local_draft", "cloud_verify"],
            "provenance": ["local"],
        },
    )
    assert gap.status_code == 422, gap.text
    assert gap.json()["code"] == "K05REST_A_VALIDATION_FAILED"

    bad = client.post(
        "/k05rest/mvp-accept-50/serve",
        json={
            "local_draft_ref": "",
            "cloud_verify_ref": "verify-50",
            "stages": ["local_draft", "cloud_verify"],
            "provenance": ["local", "cloud"],
        },
    )
    assert bad.status_code == 422, bad.text
    assert bad.json()["code"] == "K05REST_A_BAD_PAYLOAD"


def test_mvp_accept_53_served() -> None:
    """B0B-UNCOVERED_MVP_ACCEPT-53: verifier input binds the draft hash to the exact draft."""
    client = _client()

    bound = client.post(
        "/k05rest/mvp-accept-53/serve",
        json={
            "draft_ref": "heron-draft",
            "verify_ref": "heron-verify",
            "draft_hash": "heron-hash",
            "known_drafts": ["heron-draft"],
        },
    )
    assert bound.status_code == 200, bound.text
    body = bound.json()
    json.dumps(body)
    assert body["bound"] is True
    assert body["draft_hash"] == "heron-hash"

    unknown = client.post(
        "/k05rest/mvp-accept-53/serve",
        json={
            "draft_ref": "ghost-draft",
            "verify_ref": "heron-verify",
            "draft_hash": "heron-hash",
            "known_drafts": ["heron-draft"],
        },
    )
    assert unknown.status_code == 404, unknown.text
    assert unknown.json()["code"] == "K05REST_A_UNKNOWN_ROW"

    bad = client.post(
        "/k05rest/mvp-accept-53/serve",
        json={
            "draft_ref": "heron-draft",
            "verify_ref": "heron-verify",
            "draft_hash": "",
            "known_drafts": ["heron-draft"],
        },
    )
    assert bad.status_code == 422, bad.text
    assert bad.json()["code"] == "K05REST_A_BAD_PAYLOAD"


def test_k05rest_a_identity_pinned() -> None:
    """Module identity: MODEL_ID exact plus the frozen ERROR_CODES triple."""
    assert k05rest_a.MODEL_ID == "k05rest-a-1"
    assert k05rest_a.ERROR_CODES == (
        "K05REST_A_BAD_PAYLOAD",
        "K05REST_A_VALIDATION_FAILED",
        "K05REST_A_UNKNOWN_ROW",
    )
