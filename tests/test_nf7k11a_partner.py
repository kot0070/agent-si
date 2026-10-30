"""NF7K11A R-353 partner integration + R-354 Keychain seam (testid nf7k11a-partner).

Behaviour goes through the served build entry (create_app + HTTP client,
loopback TEST data only). No doubles on the production path.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.toolguard import secrets as _secrets  # noqa: E402

TESTID = "nf7k11a-partner"
TEST_TOKEN = "nf7k11a-partner-token"
TEST_SETTINGS = {"testing": True, "ui_session_token": TEST_TOKEN}


@pytest.fixture
def client():
    app = create_app(dict(TEST_SETTINGS))
    with TestClient(app) as tc:
        yield tc


def test_nf7k11a_partner_served(client):
    """R-353: partner integration record served behind the secret-store protocol."""
    assert TESTID == "nf7k11a-partner"
    record = _secrets.partner_integration_record()
    assert isinstance(record, dict)
    assert record.get("testid") == TESTID
    resp = client.get("/api/v1/partner/integration")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("testid") == TESTID
    assert body.get("partner_id") == record.get("partner_id")
    ref = body.get("secret_ref")
    assert isinstance(ref, str) and _secrets.is_secret_ref(ref), body
    assert body.get("source") == "secret_store"
    assert _secrets.find_raw_secret(body) is None, body
    assert "value" not in body, body
    assert TESTID in resp.text


def test_nf7k11a_keychain_served(client):
    """R-354: macOS Keychain path behind the same seam (loopback TEST data only)."""
    assert TESTID == "nf7k11a-partner"
    seam = _secrets.keychain_secret_seam()
    assert isinstance(seam, dict)
    assert seam.get("testid") == TESTID
    resp = client.get("/api/v1/keychain/seam")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("testid") == TESTID
    assert body.get("backend") in ("keychain", "loopback-test"), body
    ref = body.get("secret_ref")
    assert isinstance(ref, str) and _secrets.is_secret_ref(ref), body
    assert body.get("source") == "secret_store"
    assert _secrets.find_raw_secret(body) is None, body
    assert "value" not in body, body


def test_nf7k11a_protocol_hides_raw(client):
    """Both served records stay opaque: redaction keeps shape, raw absent."""
    for path in ("/api/v1/partner/integration", "/api/v1/keychain/seam"):
        resp = client.get(path)
        assert resp.status_code == 200, (path, resp.text)
        body = resp.json()
        cleaned = _secrets.redact_value(dict(body))
        assert _secrets.find_raw_secret(cleaned) is None, (path, cleaned)
        assert "secretref:" in resp.text
