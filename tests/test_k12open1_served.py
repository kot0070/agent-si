"""K12OPEN1 Beacon served through create_app (RED-first, testid k12open1-served).

Drives the K12OPEN1 rows through the real seam app (create_app) with
TestClient: R-350 idea/demo public-text rules (GET rules is open, POST
check needs the USER_WRITE guard) and HC-3 secret/private scan (POST
scan needs the USER_WRITE guard). The real public_text and secretscan
modules back the routes: no fakes.
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

from agent_si.backend import public_text as _public_text  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "k12open1-served-token"
ACTOR = "tester-k12open1"


def _auth(token=TEST_TOKEN, actor=ACTOR):
    headers = {}
    if actor is not None:
        headers["x-actor"] = actor
    if token is not None:
        headers["x-ui-session-token"] = token
    return headers


@pytest.fixture
def client(tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    settings = {"ui_session_token": TEST_TOKEN, "store_dir": str(store)}
    app = create_app(dict(settings))
    return TestClient(app)


# --- R-350: idea/demo public-text rules ---


def test_rules_open_lists_r350_rules(client):
    resp = client.get("/api/v1/public-text/rules")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rules"] == [
        {"code": rule["code"], "message": rule["message"]}
        for rule in _public_text.RULES
    ]
    codes = {rule["code"] for rule in body["rules"]}
    assert _public_text.RULE_SECRET_IN_PUBLIC_TEXT in codes
    assert _public_text.RULE_PRIVATE_PATH_IN_PUBLIC_TEXT in codes


def test_check_clean_idea_ok(client):
    resp = client.post(
        "/api/v1/public-text/check",
        json={"idea_text": "A public demo night showing a garden watering rota."},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "violations": []}


def test_check_secret_idea_violation(client):
    resp = client.post(
        "/api/v1/public-text/check",
        json={"idea_text": "Demo login with api_key = sk-FAKEEXAMPLE0"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    codes = [item["code"] for item in body["violations"]]
    assert _public_text.RULE_SECRET_IN_PUBLIC_TEXT in codes


def test_check_private_path_violation(client):
    resp = client.post(
        "/api/v1/public-text/check",
        json={"idea_text": "Screenshots live under /home/ops/private-demo/shot.png"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    codes = [item["code"] for item in body["violations"]]
    assert _public_text.RULE_PRIVATE_PATH_IN_PUBLIC_TEXT in codes


def test_check_empty_idea_text_400(client):
    for body in ({}, {"idea_text": ""}, {"idea_text": "   "}):
        resp = client.post(
            "/api/v1/public-text/check",
            json=dict(body),
            headers=_auth(),
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == "EMPTY_IDEA_TEXT"


def test_check_guard_401_403(client):
    resp = client.post(
        "/api/v1/public-text/check",
        json={"idea_text": "A public demo night."},
        headers=_auth(actor=None),
    )
    assert resp.status_code == 401, resp.text
    resp = client.post(
        "/api/v1/public-text/check",
        json={"idea_text": "A public demo night."},
        headers=_auth(token="wrong-token"),
    )
    assert resp.status_code == 403, resp.text


# --- HC-3: secret/private scan ---


def test_scan_clean_submission_ok(client):
    resp = client.post(
        "/api/v1/submission/scan",
        json={
            "files": [{"path": "demo/notes.md", "content": "public demo notes"}],
            "notes": "nothing private here",
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "findings": []}


def test_scan_secret_detected(client):
    resp = client.post(
        "/api/v1/submission/scan",
        json={
            "files": [
                {
                    "path": "demo/config.env",
                    "content": "api_key = sk-FAKEEXAMPLE0",
                }
            ],
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    secret_hits = [
        item for item in body["findings"] if item["code"] == "SECRET_DETECTED"
    ]
    assert secret_hits and secret_hits[0]["path"] == "demo/config.env"


def test_scan_private_path(client):
    resp = client.post(
        "/api/v1/submission/scan",
        json={
            "files": [
                {
                    "path": "/home/ops/private-notes/memo.md",
                    "content": "placeholder",
                }
            ],
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    private_hits = [
        item for item in body["findings"] if item["code"] == "PRIVATE_PATH"
    ]
    assert private_hits
    assert private_hits[0]["path"] == "/home/ops/private-notes/memo.md"


def test_scan_empty_submission_400(client):
    for body in ({}, {"files": []}, {"files": [], "notes": "  "}):
        resp = client.post(
            "/api/v1/submission/scan",
            json=dict(body),
            headers=_auth(),
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == "EMPTY_SUBMISSION"


def test_scan_guard_401_403(client):
    payload = {"files": [{"path": "a.md", "content": "hi"}], "notes": "hi"}
    resp = client.post(
        "/api/v1/submission/scan",
        json=dict(payload),
        headers=_auth(actor=None),
    )
    assert resp.status_code == 401, resp.text
    resp = client.post(
        "/api/v1/submission/scan",
        json=dict(payload),
        headers=_auth(token="wrong-token"),
    )
    assert resp.status_code == 403, resp.text
