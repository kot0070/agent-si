"""K10ST4 lane A+B: served acceptance, combine-default, competitive audit.

Row M-P4-162 (acceptance): GET /api/v1/release/accept returns the final acceptance
status over Docker plus declared services plus PowerShell, with testid.
Row M-P4-166 (combine): GET /api/v1/release/combine?package_id=<id> combines best
plus KB plus benchmark plus Watcher on DEFAULT, with testid.
Row M-R-COMPET (audit, MGR-B module, frozen F4 API): GET
/api/v1/release/compet/audit returns flow-by-flow claims each with a recorded source
plus snippet, with testid. Loopback TEST data only.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402

TESTID = "k10st4-accept"


def _client():
    app = create_app({"ui_session_token": "k10st4-app-token"})
    return fastapi.testclient.TestClient(app)


def test_k10st4_accept_served():
    client = _client()
    resp = client.get("/api/v1/release/accept")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == TESTID, body
    for key in ("ok", "docker", "services", "powershell"):
        assert key in body, body


def test_k10st4_combine_default_served():
    client = _client()
    resp = client.get("/api/v1/release/combine", params={"package_id": "TEST-PKG-1"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == TESTID, body
    assert body["package_id"] == "TEST-PKG-1", body
    assert body["mode"] == "default", body
    for key in ("best", "kb", "benchmark", "watcher"):
        assert key in body, body


def test_k10st4_compet_audit_served():
    client = _client()
    resp = client.get("/api/v1/release/compet/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == TESTID, body
    flows = body["flows"]
    assert isinstance(flows, list) and flows, body
    for row in flows:
        for key in ("flow", "claim", "source", "snippet"):
            assert key in row and row[key], row
