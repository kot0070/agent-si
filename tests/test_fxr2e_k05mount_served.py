"""FXR2E-4: k05next_a + k05next_b served by create_app (RED-first).

The 10 proof routes work on real state (pure verdicts over the
request payload) and clash with nothing served. k05rest_a stays
test-mounted only: its mvp-accept-50/53 paths duplicate k05next_b's
same-path handlers (different MODEL_ID), so the router is not
mounted; the return names which and why.
"""
import os
import sys

from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agent_si.backend.app import create_app  # noqa: E402

TOKEN = "fxr2e-k05-token"


def _client():
    app = create_app({"testing": True, "ui_session_token": TOKEN})
    return TestClient(app, raise_server_exceptions=False)


def test_k05next_a_served_by_create_app():
    """POST /api/v1/local/mvp-accept-221/serve answers from create_app."""
    client = _client()
    resp = client.post(
        "/api/v1/local/mvp-accept-221/serve",
        json={"store_ref": "ref-fxr2e", "running": True,
              "tiers": ["MEASURED"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["model_id"] == "k05next-a-1"
    assert body["eligible"] is True and body["tier"] == "MEASURED"


def test_k05next_b_served_by_create_app():
    """POST /api/v1/local/arch-352/serve answers from create_app."""
    client = _client()
    resp = client.post(
        "/api/v1/local/arch-352/serve",
        json={"endpoint": "http://127.0.0.1:11434",
              "permission": False})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["contacted"] is False
    assert body["violation"] is True
