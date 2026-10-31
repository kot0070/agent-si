"""K09-B served proofs (rows R-361 / M-P2-74 / B0B-BP05-43 / LIVE0-06).

Stock create_app + TestClient, TEST data only. All fixtures, fakes and
state-reset live in this file. Requires CODER-A's mount
(`app.include_router(k09b_router)` adjacent to the kb mount); until the
mount lands these tests 404 (predicted RED, not a defect).
"""

import os
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from fastapi.testclient import TestClient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from src.agent_si.kb import telemetry as _telemetry  # noqa: E402

TEST_TOKEN = "k09b-served-test-token"
TEST_SETTINGS = {"testing": True, "ui_session_token": TEST_TOKEN}
FIX = os.path.join(_WS, "tests", "fixtures", "k09b")


def make_client():
    app = create_app(dict(TEST_SETTINGS))
    return app, TestClient(app, raise_server_exceptions=False)


def reset_telemetry():
    _telemetry._records.clear()


def test_r361_telemetry_lists_stored_records():
    reset_telemetry()
    _telemetry.record_hit("dev", "agent-1", 100, 0.02)
    _telemetry.record_miss("dev", "agent-1", 50, 0.01)
    _telemetry.record_web_fallback("dev", "agent-1", 25, 0.005)
    _, client = make_client()
    resp = client.get("/api/v1/kb/telemetry")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert isinstance(rows, list)
    assert [r["kind"] for r in rows] == ["hit", "miss", "web_fallback"]
    assert rows[0]["role"] == "dev"
    assert rows[0]["agent"] == "agent-1"
    assert (rows[0]["tokens"], rows[2]["tokens"]) == (100, 25)


def test_m_p2_74_savings_reports_stored_records():
    reset_telemetry()
    _telemetry.record_hit("dev", "agent-2", 100, 0.02)
    _telemetry.record_miss("dev", "agent-2", 50, 0.01)
    _telemetry.record_web_fallback("dev", "agent-2", 25, 0.005)
    _, client = make_client()
    resp = client.get("/api/v1/kb/savings")
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert isinstance(report, dict)
    assert report["hits"] == 1
    assert report["misses"] == 1
    assert report["web_fallbacks"] == 1
    assert report["tokens"] == 175
    assert abs(report["cost"] - 0.035) < 1e-9


def test_b0b_bp05_43_validate_reports_code():
    _, client = make_client()
    good = client.post(
        "/api/v1/kb/validate", json={"kb_dir": os.path.join(FIX, "good")})
    assert good.status_code == 200, good.text
    assert good.json()["ok"] is True
    assert good.json()["error_code"] is None
    bad = client.post(
        "/api/v1/kb/validate",
        json={"kb_dir": os.path.join(FIX, "no-manifest")})
    assert bad.status_code == 200, bad.text
    assert bad.json()["ok"] is False
    assert bad.json()["error_code"] == "KB_MANIFEST_MISSING"
    empty = client.post("/api/v1/kb/validate", json={})
    assert empty.status_code == 200, empty.text
    assert empty.json()["ok"] is False


def test_live0_06_live_lists_rows():
    _, client = make_client()
    resp = client.get("/api/v1/k09b/live")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "served": True,
        "rows": ["R-361", "M-P2-74", "B0B-BP05-43", "LIVE0-06"],
    }
