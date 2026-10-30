"""K02OPEN1B rows 101+102: served early-start plus link-check close.

Port of the 6 reference cases (read-only reference stays untouched);
one behaviour test per row via create_app + HTTP client.
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
from agent_si.backend.orchestration.gates import GateAuditLog  # noqa: E402

TEST_TOKEN = "k02open1b-test-token"
TEST_SETTINGS = {"testing": True, "ui_session_token": TEST_TOKEN}


def make_client(**kwargs):
    settings = dict(TEST_SETTINGS)
    app = create_app(settings, **kwargs)
    return app, TestClient(app)


def _auth_headers(token=TEST_TOKEN):
    return {"x-actor": "tester-k02b", "x-ui-session-token": token}


def test_early_start_true_on_resolved_pass_plus_pass_with_overlap_on():
    _, client = make_client()
    log = GateAuditLog()
    gate = log.serve_gate("k02b-early-1", "PASS")
    audit = log.serve_audit("k02b-early-1", "PASS",
                            "sess-k02b-aud-e1", ["sess-k02b-prod-e1"], True)
    resp = client.get("/k02open1b/early-start",
                      params={"gate_ref": gate.gate_id,
                              "audit_ref": audit.audit_id})
    assert resp.status_code == 200
    assert resp.json()["allowed"] is True


def test_early_start_false_otherwise():
    _, client = make_client()
    log = GateAuditLog()
    gate = log.serve_gate("k02b-early-2", "PASS")
    audit = log.serve_audit("k02b-early-2", "PASS",
                            "sess-k02b-aud-e2", ["sess-k02b-prod-e2"], True)
    resp = client.get("/k02open1b/early-start",
                      params={"gate_ref": "gate:k02b-unknown:part-000",
                              "audit_ref": "audit:k02b-unknown:part-000"})
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False
    resp = client.get("/k02open1b/early-start",
                      params={"gate_ref": gate.gate_id,
                              "audit_ref": audit.audit_id,
                              "overlap": "false"})
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False
    log.serve_gate("k02b-early-3", "FAIL")
    audit3 = log.serve_audit("k02b-early-3", "PASS",
                             "sess-k02b-aud-e3", ["sess-k02b-prod-e3"], True)
    resp = client.get("/k02open1b/early-start",
                      params={"gate_ref": "k02b-early-3:gate-001",
                              "audit_ref": audit3.audit_id})
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False


def test_early_start_reads_need_no_token():
    _, client = make_client()
    resp = client.get("/k02open1b/early-start",
                      params={"gate_ref": "gate:k02b-open:part-000",
                              "audit_ref": "audit:k02b-open:part-000"})
    assert resp.status_code == 200


def test_link_check_evidence_on_pass_plus_pass_with_refs():
    _, client = make_client()
    delta = {"delta_id": "delta-k02b-1",
             "scope": ["scope-a"], "blocking": False}
    verdict = {"gate": "PASS", "audit": "PASS",
               "evidence_refs": ["ev-k02b-1"]}
    resp = client.post("/k02open1b/link-check",
                       json={"delta": delta, "verdict": verdict},
                       headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["package_id"] == "delta-k02b-1"
    assert body["gate"] == "PASS"
    assert body["audit"] == "PASS"
    assert "ev-k02b-1" in body["evidence_refs"]
    assert "linkcheck:ok" in body["evidence_refs"]


def test_link_check_joint_failure_evidence():
    _, client = make_client()
    delta = {"delta_id": "delta-k02b-2",
             "scope": ["scope-a"], "blocking": True}
    verdict = {"gate": "FAIL", "audit": "FAIL",
               "evidence_refs": ["ev-k02b-2"]}
    resp = client.post("/k02open1b/link-check",
                       json={"delta": delta, "verdict": verdict},
                       headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["gate"] == "FAIL"
    assert body["audit"] == "FAIL"
    assert "linkcheck:failed:joint" in body["evidence_refs"]


def test_link_check_write_guard():
    _, client = make_client()
    payload = {"delta": {"delta_id": "delta-k02b-3"},
               "verdict": {"gate": "PASS", "audit": "PASS",
                           "evidence_refs": ["ev-k02b-3"]}}
    resp = client.post("/k02open1b/link-check", json=payload)
    assert resp.status_code == 401
    resp = client.post("/k02open1b/link-check", json=payload,
                       headers={"x-actor": "tester-k02b"})
    assert resp.status_code == 403
    resp = client.post("/k02open1b/link-check", json=payload,
                       headers=_auth_headers(token="wrong-token"))
    assert resp.status_code == 403
