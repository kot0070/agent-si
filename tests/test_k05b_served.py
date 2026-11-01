"""K05NEXT FalconB served proofs (tests/test_k05b_served).

Five rows served on the FastAPI router owned by
src/agent_si/local/k05next_b.py, mounted on an app built inside this
file (no product mount edits). One test per row, plus pins for the
frozen ERROR_CODES tuple and MODEL_ID.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_si.local import k05next_b

_LOCAL_ENDPOINT = "http://127.0.0.1:11434"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(k05next_b.router)
    return TestClient(app)


def test_arch_352_served() -> None:
    """B0B-UNCOVERED_ARCH-352: permission gates local contact; refusal is a violation."""
    client = _client()
    permitted = client.post(
        "/k05next/arch-352/serve",
        json={"endpoint": _LOCAL_ENDPOINT, "permission": True},
    )
    assert permitted.status_code == 200, permitted.text
    permitted_body = permitted.json()
    assert permitted_body["contacted"] is True
    assert permitted_body["violation"] is False
    refused = client.post(
        "/k05next/arch-352/serve",
        json={"endpoint": _LOCAL_ENDPOINT, "permission": False},
    )
    assert refused.status_code == 200, refused.text
    refused_body = refused.json()
    assert refused_body["contacted"] is False
    assert refused_body["violation"] is True
    assert "UNPERMITTED_CONTACT" in refused_body["reason"]
    bad = client.post(
        "/k05next/arch-352/serve",
        json={"endpoint": "", "permission": True},
    )
    assert bad.status_code == 422, bad.text
    assert "K05NEXT_B_BAD_PAYLOAD" in bad.text
    outside = client.post(
        "/k05next/arch-352/serve",
        json={"endpoint": "http://127.0.0.1:9999", "permission": True},
    )
    assert outside.status_code == 404, outside.text
    assert "K05NEXT_B_UNKNOWN_ROW" in outside.text


def test_bp05_65_served() -> None:
    """B0B-UNCOVERED_BP05-65: unmet preconditions record GATEWAY_BUSY, refuse contact."""
    client = _client()
    met = client.post(
        "/k05next/bp05-65/serve",
        json={"gateway": "gateway-idle-1", "preconditions_met": True},
    )
    assert met.status_code == 200, met.text
    met_body = met.json()
    assert met_body["contacted"] is True
    assert met_body["violation_recorded"] is False
    unmet = client.post(
        "/k05next/bp05-65/serve",
        json={"gateway": "gateway-busy-1", "preconditions_met": False},
    )
    assert unmet.status_code == 200, unmet.text
    unmet_body = unmet.json()
    assert unmet_body["contacted"] is False
    assert unmet_body["violation_recorded"] is True
    assert unmet_body["violation"] == "GATEWAY_BUSY"
    bad = client.post(
        "/k05next/bp05-65/serve",
        json={"gateway": "", "preconditions_met": False},
    )
    assert bad.status_code == 422, bad.text
    assert "K05NEXT_B_BAD_PAYLOAD" in bad.text


def test_bp05_92_served() -> None:
    """B0B-UNCOVERED_BP05-92: tiers derive from recorded evidence; bare labels never admit."""
    client = _client()
    measured = client.post(
        "/k05next/bp05-92/serve",
        json={"evidence": [{"kind": "measured", "ref": "store-ref-measured-1"}]},
    )
    assert measured.status_code == 200, measured.text
    measured_body = measured.json()
    assert measured_body["tier"] == "MEASURED"
    assert measured_body["eligible"] is True
    proxy = client.post(
        "/k05next/bp05-92/serve",
        json={"evidence": [{"kind": "proxy", "ref": "store-ref-proxy-1"}]},
    )
    assert proxy.status_code == 200, proxy.text
    proxy_body = proxy.json()
    assert proxy_body["tier"] == "PROXY"
    assert proxy_body["eligible"] is False
    unknown = client.post("/k05next/bp05-92/serve", json={"evidence": []})
    assert unknown.status_code == 200, unknown.text
    unknown_body = unknown.json()
    assert unknown_body["tier"] == "UNKNOWN"
    assert unknown_body["eligible"] is False
    bare = client.post("/k05next/bp05-92/serve", json={"evidence": ["measured"]})
    assert bare.status_code == 200, bare.text
    assert bare.json()["eligible"] is False
    bad = client.post("/k05next/bp05-92/serve", json={"evidence": "measured"})
    assert bad.status_code == 422, bad.text
    assert "K05NEXT_B_BAD_PAYLOAD" in bad.text


def test_mvp_accept_50_served() -> None:
    """B0B-UNCOVERED_MVP_ACCEPT-50: SPLIT carries draft plus verify with verify before audit."""
    client = _client()
    good = client.post(
        "/k05next/mvp-accept-50/serve",
        json={
            "local_draft_ref": "draft-ref-k05b-1",
            "cloud_verify_ref": "verify-ref-k05b-1",
            "draft_hash": "draft-hash-k05b-1",
        },
    )
    assert good.status_code == 200, good.text
    good_body = good.json()
    assert good_body["route"] == "SPLIT"
    assert good_body["stages"] == ["local_draft", "cloud_verify"]
    assert good_body["verify_before_audit"] is True
    provenance = good_body["provenance"]
    assert provenance["local_draft_ref"] == "draft-ref-k05b-1"
    assert provenance["cloud_verify_ref"] == "verify-ref-k05b-1"
    assert provenance["draft_hash"] == "draft-hash-k05b-1"
    duplicated = client.post(
        "/k05next/mvp-accept-50/serve",
        json={
            "local_draft_ref": "same-ref",
            "cloud_verify_ref": "same-ref",
            "draft_hash": "draft-hash-k05b-1",
        },
    )
    assert duplicated.status_code == 422, duplicated.text
    assert "K05NEXT_B_VALIDATION_FAILED" in duplicated.text
    empty = client.post(
        "/k05next/mvp-accept-50/serve",
        json={
            "local_draft_ref": "",
            "cloud_verify_ref": "verify-ref-k05b-1",
            "draft_hash": "draft-hash-k05b-1",
        },
    )
    assert empty.status_code == 422, empty.text
    assert "K05NEXT_B_VALIDATION_FAILED" in empty.text


def test_mvp_accept_53_served() -> None:
    """B0B-UNCOVERED_MVP_ACCEPT-53: verifier input binds the draft hash."""
    client = _client()
    bound = client.post(
        "/k05next/mvp-accept-53/serve",
        json={
            "local_draft_ref": "draft-ref-k05b-1",
            "cloud_verify_ref": "verify-ref-k05b-1",
            "draft_hash": "draft-hash-k05b-1",
            "verifier_input_hash": "draft-hash-k05b-1",
        },
    )
    assert bound.status_code == 200, bound.text
    bound_body = bound.json()
    assert bound_body["bound"] is True
    assert bound_body["trace"] == "draft-hash-k05b-1"
    loose = client.post(
        "/k05next/mvp-accept-53/serve",
        json={
            "local_draft_ref": "draft-ref-k05b-1",
            "cloud_verify_ref": "verify-ref-k05b-1",
            "draft_hash": "draft-hash-k05b-1",
            "verifier_input_hash": "other-hash",
        },
    )
    assert loose.status_code == 200, loose.text
    loose_body = loose.json()
    assert loose_body["bound"] is False
    assert loose_body["trace"] is None
    bad = client.post(
        "/k05next/mvp-accept-53/serve",
        json={
            "local_draft_ref": "draft-ref-k05b-1",
            "cloud_verify_ref": "verify-ref-k05b-1",
            "draft_hash": "",
            "verifier_input_hash": "",
        },
    )
    assert bad.status_code == 422, bad.text
    assert "K05NEXT_B_BAD_PAYLOAD" in bad.text


def test_error_code_bad_payload_pinned() -> None:
    assert "K05NEXT_B_BAD_PAYLOAD" in k05next_b.ERROR_CODES


def test_error_code_validation_failed_pinned() -> None:
    assert "K05NEXT_B_VALIDATION_FAILED" in k05next_b.ERROR_CODES


def test_error_code_unknown_row_pinned() -> None:
    assert "K05NEXT_B_UNKNOWN_ROW" in k05next_b.ERROR_CODES


def test_model_id_pinned() -> None:
    assert k05next_b.MODEL_ID == "k05next-b-1"
