"""K12R1 R-350 served through create_app (RED-first, testid k12r1-served).

Drives idea+presentation+demo texts through the served public-text
routes plus the submission scan route on the real seam app
(create_app) with TestClient: GET rules is open, POST check and POST
scan need the USER_WRITE guard (401 missing x-actor, 403 bad token;
every refusal body carries {code, message}). The real public_text
and secretscan modules back the routes: no fakes.
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

TEST_TOKEN = "k12r1-served-token"
ACTOR = "tester-k12r1"


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


# --- R-350: rules table ---


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


# --- R-350: idea+presentation+demo texts ---


def test_check_clean_idea_ok(client):
    resp = client.post(
        "/api/v1/public-text/check",
        json={"idea_text": "A public demo night showing a garden watering rota."},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "violations": []}


def test_check_secret_in_presentation_only_violation(client):
    resp = client.post(
        "/api/v1/public-text/check",
        json={
            "idea_text": "A public demo night showing a garden watering rota.",
            "presentation": "Login uses api_key: hunter2value for the demo.",
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert [item["code"] for item in body["violations"]] == [
        _public_text.RULE_SECRET_IN_PUBLIC_TEXT
    ]


def test_check_private_path_in_video_demo_only_violation(client):
    resp = client.post(
        "/api/v1/public-text/check",
        json={
            "idea_text": "A public demo night showing a garden watering rota.",
            "video_demo": "Clips live under /home/ops/private-demo/shot.png",
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert [item["code"] for item in body["violations"]] == [
        _public_text.RULE_PRIVATE_PATH_IN_PUBLIC_TEXT
    ]


def test_check_two_rule_break_yields_two_violations(client):
    resp = client.post(
        "/api/v1/public-text/check",
        json={
            "idea_text": (
                "Login uses api_key: hunter2value; "
                "clips live under /home/ops/private-demo/shot.png"
            ),
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert [item["code"] for item in body["violations"]] == [
        _public_text.RULE_SECRET_IN_PUBLIC_TEXT,
        _public_text.RULE_PRIVATE_PATH_IN_PUBLIC_TEXT,
    ]


def test_check_blank_idea_text_400(client):
    for body in ({}, {"idea_text": ""}, {"idea_text": "   "}):
        resp = client.post(
            "/api/v1/public-text/check",
            json=dict(body),
            headers=_auth(),
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == "EMPTY_IDEA_TEXT"
        assert resp.json()["message"]


def test_check_guard_401_403_carry_code_message(client):
    resp = client.post(
        "/api/v1/public-text/check",
        json={"idea_text": "A public demo night."},
        headers=_auth(actor=None),
    )
    assert resp.status_code == 401, resp.text
    assert resp.json()["code"]
    assert resp.json()["message"]
    resp = client.post(
        "/api/v1/public-text/check",
        json={"idea_text": "A public demo night."},
        headers=_auth(token="wrong-token"),
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"]
    assert resp.json()["message"]


# --- R-350: submission scan ---


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


def test_scan_flagged_files_and_notes_findings(client):
    resp = client.post(
        "/api/v1/submission/scan",
        json={
            "files": [
                {
                    "path": "demo/config.env",
                    "content": "login uses api_key: hunter2value",
                },
                {
                    "path": "/home/ops/private-notes/memo.md",
                    "content": "placeholder",
                },
            ],
            "notes": "token: hunter2notes",
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    by_path = {}
    for item in body["findings"]:
        by_path.setdefault(item["path"], []).append(item["code"])
        assert item["message"]
    assert "SECRET_DETECTED" in by_path.get("demo/config.env", [])
    assert "PRIVATE_PATH" in by_path.get("/home/ops/private-notes/memo.md", [])
    assert "SECRET_DETECTED" in by_path.get("notes", [])


def test_scan_notes_only_finding(client):
    resp = client.post(
        "/api/v1/submission/scan",
        json={"files": [], "notes": "login uses api_key: hunter2value"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["findings"]
    assert all(item["path"] == "notes" for item in body["findings"])


def test_scan_empty_submission_400(client):
    for body in ({}, {"files": []}, {"files": [], "notes": "  "}):
        resp = client.post(
            "/api/v1/submission/scan",
            json=dict(body),
            headers=_auth(),
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == "EMPTY_SUBMISSION"
        assert resp.json()["message"]


def test_scan_guard_401_403_carry_code_message(client):
    payload = {"files": [{"path": "a.md", "content": "hi"}], "notes": "hi"}
    resp = client.post(
        "/api/v1/submission/scan",
        json=dict(payload),
        headers=_auth(actor=None),
    )
    assert resp.status_code == 401, resp.text
    assert resp.json()["code"]
    assert resp.json()["message"]
    resp = client.post(
        "/api/v1/submission/scan",
        json=dict(payload),
        headers=_auth(token="wrong-token"),
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"]
    assert resp.json()["message"]
