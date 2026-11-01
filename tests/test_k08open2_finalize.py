"""K08OPEN2 lane B: served record-bound finalization (testid k08open2-finalize).

Row B0B-UNCOVERED_ARCH-641: served finalization binds the exact
VerificationRecord traced to the verification sections (success carries
the verification ref; an absent or mismatched verification record
refuses with an error-code body, never a silent pass).
Row B0B-UNCOVERED_ARCH-642: served finalization binds the exact
AuditRecord owned by the audit sections (success carries audit_ref with
audit_ref.result equal to the record audit_result; an absent or
mismatched audit record refuses with an error-code body).

Behaviour tests through create_app + HTTP client (TestClient) over the
additive K13 finalize-write route; records are built through the real
VerificationRecord / AuditRecord entries and finalized through the real
Finalizer.finalize_with_records. No doubles, no skip/xfail.
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

TEST_TOKEN = "k08open2-finalize-token"
ACTOR = "tester-k08open2-finalize"

FINALIZE_WRITE_PATH = "/api/v1/k13/finalizations"
FINALIZE_READ_PATH = "/api/v1/k13/finalizations/%s"


def _settings():
    return {"ui_session_token": TEST_TOKEN, "testing": True}


def _headers(token=TEST_TOKEN, actor=ACTOR):
    headers = {}
    if actor is not None:
        headers["x-actor"] = actor
    if token is not None:
        headers["x-ui-session-token"] = token
    return headers


def _payload(finalization_id="fin-k08open2-1", **overrides):
    body = {
        "finalization_id": finalization_id,
        "project_id": "P1",
        "task_id": "T1",
        "run_id": "run-1",
        "task_state": "COMPLETED",
        "verification": {
            "verification_id": "v-k08open2-1",
            "contract_hash": "h-k08open2-1",
        },
        "audit": {
            "audit_id": "aud-k08open2-1",
            "contract_hash": "h-k08open2-1",
            "result": "PASS",
        },
        "output_refs": ["art-1"],
        "accounting_complete": True,
        "budget_settled": True,
        "resources_released": True,
    }
    body.update(overrides)
    return body


def _error_code(resp):
    """A refusal carries an error-code body, never a silent pass."""
    assert resp.status_code in (400, 409, 422), resp.text
    detail = resp.json().get("detail")
    assert isinstance(detail, dict) and detail.get("code"), resp.text
    return detail["code"]


# --- row 641 (testid k08open2-finalize) ---


def test_641_finalize_write_binds_exact_verification_record():
    """k08open2-finalize row 641: success carries the exact verification
    ref; an absent or mismatched verification record refuses with an
    error-code body."""
    client = TestClient(create_app(dict(_settings())))

    ok = client.post(
        FINALIZE_WRITE_PATH, json=_payload(), headers=_headers())
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["verification_ref"] == "v-k08open2-1"
    assert body["completion_disposition"] == "VERIFIED_PASS"
    readback = client.get(
        FINALIZE_READ_PATH % "fin-k08open2-1",
        params={"project_id": "P1"},
    )
    assert readback.status_code == 200, readback.text
    assert readback.json()["verification_ref"] == "v-k08open2-1"

    absent = dict(_payload(finalization_id="fin-k08open2-absent"))
    del absent["verification"]
    _error_code(client.post(
        FINALIZE_WRITE_PATH, json=absent, headers=_headers()))

    mismatch = _payload(finalization_id="fin-k08open2-mismatch")
    mismatch["verification_ref"] = "v-some-other-id"
    _error_code(client.post(
        FINALIZE_WRITE_PATH, json=mismatch, headers=_headers()))


# --- row 642 (testid k08open2-finalize) ---


def test_642_finalize_write_binds_exact_audit_record():
    """k08open2-finalize row 642: success carries audit_ref with
    audit_ref.result equal to the record audit_result; an absent or
    mismatched audit record refuses with an error-code body."""
    client = TestClient(create_app(dict(_settings())))

    ok = client.post(
        FINALIZE_WRITE_PATH,
        json=_payload(finalization_id="fin-k08open2-642"),
        headers=_headers(),
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["audit_result"] == "PASS"
    assert body["audit_ref"]["audit_id"] == "aud-k08open2-1"
    assert body["audit_ref"]["result"] == body["audit_result"]

    absent = dict(_payload(finalization_id="fin-k08open2-642-absent"))
    del absent["audit"]
    _error_code(client.post(
        FINALIZE_WRITE_PATH, json=absent, headers=_headers()))

    mismatch = _payload(finalization_id="fin-k08open2-642-mismatch")
    mismatch["audit"] = dict(mismatch["audit"])
    mismatch["audit"]["contract_hash"] = "h-other-hash"
    _error_code(client.post(
        FINALIZE_WRITE_PATH, json=mismatch, headers=_headers()))
