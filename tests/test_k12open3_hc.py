"""K12OPEN3 Beacon served through create_app (RED-first, testid k12open3-hc).

Drives the K12OPEN3 rows HC-2 (contribution marks) and HC-3 (submission
finalize over the real secretscan) through the real seam app
(create_app) with TestClient. Accepted packages are set up only via
app.state.ledger_for on the real app; the real secretscan module backs
the finalize gate: no fakes. TEST loopback data only, never real
secrets.
"""

import datetime
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

from agent_si.backend import secretscan as _secretscan  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402

TESTID = "k12open3-hc"
TEST_TOKEN = "k12open3-hc-token"
ACTOR = "tester-k12open3"
PROJECT = "k12open3-hc-project"


def _auth(token=TEST_TOKEN, actor=ACTOR):
    headers = {}
    if actor is not None:
        headers["x-actor"] = actor
    if token is not None:
        headers["x-ui-session-token"] = token
    return headers


@pytest.fixture
def setup(tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    settings = {"ui_session_token": TEST_TOKEN, "store_dir": str(store)}
    app = create_app(dict(settings))
    return app, TestClient(app)


def _accept(app, package_id):
    return app.state.ledger_for(PROJECT).record_row(package_id, 1, 1, 1.0)


def test_helpers_importable_and_pure(setup):
    app, client = setup
    from agent_si.backend.app import contributions_mark, secret_scan_gate

    assert callable(contributions_mark)
    assert callable(secret_scan_gate)
    store = {}
    record = contributions_mark(store, "pkg-direct")
    assert record == {
        "package_id": "pkg-direct",
        "evidence_ref": None,
        "recorded_at": datetime.date.today().isoformat(),
    }
    assert store == {"pkg-direct": record}
    assert secret_scan_gate(
        [{"path": "notes/demo.md", "content": "public demo notes"}], None
    ) == []


def test_mark_round_trip_and_get_order(setup):
    app, client = setup
    _accept(app, "pkg-a")
    _accept(app, "pkg-b")
    today = datetime.date.today().isoformat()
    resp = client.post(
        "/api/v1/demo/contributions/mark",
        json={"package_id": "pkg-a", "evidence_ref": "ev-a"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "contribution": {
            "package_id": "pkg-a",
            "evidence_ref": "ev-a",
            "recorded_at": today,
        }
    }
    resp = client.post(
        "/api/v1/demo/contributions/mark",
        json={"package_id": "pkg-b", "evidence_ref": "ev-b"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    resp = client.get("/api/v1/demo/contributions")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "contributions": [
            {"package_id": "pkg-a", "evidence_ref": "ev-a",
             "recorded_at": today},
            {"package_id": "pkg-b", "evidence_ref": "ev-b",
             "recorded_at": today},
        ]
    }


def test_mark_default_recorded_at_today(setup):
    app, client = setup
    _accept(app, "pkg-c")
    _accept(app, "pkg-c2")
    resp = client.post(
        "/api/v1/demo/contributions/mark",
        json={"package_id": "pkg-c"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["contribution"]["recorded_at"] == (
        datetime.date.today().isoformat()
    )
    resp = client.post(
        "/api/v1/demo/contributions/mark",
        json={"package_id": "pkg-c2", "recorded_at": "2026-01-02"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["contribution"]["recorded_at"] == "2026-01-02"


def test_mark_duplicate_409(setup):
    app, client = setup
    _accept(app, "pkg-d")
    resp = client.post(
        "/api/v1/demo/contributions/mark",
        json={"package_id": "pkg-d", "evidence_ref": "ev-d"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        "/api/v1/demo/contributions/mark",
        json={"package_id": "pkg-d", "evidence_ref": "ev-d2"},
        headers=_auth(),
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "DUPLICATE_CONTRIBUTION"
    assert "message" in resp.json()


def test_mark_empty_id_400(setup):
    app, client = setup
    for payload in ({}, {"package_id": ""}, {"package_id": "   "}):
        resp = client.post(
            "/api/v1/demo/contributions/mark",
            json=dict(payload),
            headers=_auth(),
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == "EMPTY_PACKAGE_ID"


def test_mark_unaccepted_404(setup):
    app, client = setup
    resp = client.post(
        "/api/v1/demo/contributions/mark",
        json={"package_id": "pkg-never", "evidence_ref": "ev-x"},
        headers=_auth(),
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == "PACKAGE_NOT_ACCEPTED"


def test_finalize_clean_records_mark(setup):
    app, client = setup
    _accept(app, "pkg-e")
    resp = client.post(
        "/api/v1/demo/submission/finalize",
        json={
            "package_id": "pkg-e",
            "files": [
                {"path": "notes/demo.md", "content": "public demo notes"}
            ],
            "notes": "nothing private here",
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["contribution"]["package_id"] == "pkg-e"
    assert body["contribution"]["recorded_at"] == (
        datetime.date.today().isoformat()
    )
    resp = client.get("/api/v1/demo/contributions")
    assert resp.status_code == 200, resp.text
    ids = [item["package_id"] for item in resp.json()["contributions"]]
    assert "pkg-e" in ids


def test_finalize_dirty_blocked_409(setup):
    app, client = setup
    _accept(app, "pkg-f")
    resp = client.post(
        "/api/v1/demo/submission/finalize",
        json={
            "package_id": "pkg-f",
            "files": [
                {
                    "path": "demo/config.env",
                    "content": "api_key = hunter2-demo-value",
                }
            ],
        },
        headers=_auth(),
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["code"] == "SECRET_SCAN_BLOCKED"
    assert "message" in body
    codes = [item["code"] for item in body["findings"]]
    assert _secretscan.SECRET_DETECTED in codes
    resp = client.get("/api/v1/demo/contributions")
    assert resp.status_code == 200, resp.text
    ids = [item["package_id"] for item in resp.json()["contributions"]]
    assert "pkg-f" not in ids


def test_finalize_empty_submission_400(setup):
    app, client = setup
    _accept(app, "pkg-g")
    for payload in (
        {"package_id": "pkg-g"},
        {"package_id": "pkg-g", "files": []},
        {"package_id": "pkg-g", "files": [], "notes": "  "},
    ):
        resp = client.post(
            "/api/v1/demo/submission/finalize",
            json=dict(payload),
            headers=_auth(),
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == "EMPTY_SUBMISSION"


def test_write_guards_on_both_posts(setup):
    app, client = setup
    _accept(app, "pkg-h")
    mark_payload = {"package_id": "pkg-h", "evidence_ref": "ev-h"}
    finalize_payload = {
        "package_id": "pkg-h",
        "files": [{"path": "notes/demo.md", "content": "public demo notes"}],
        "notes": "nothing private here",
    }
    for path, payload in (
        ("/api/v1/demo/contributions/mark", mark_payload),
        ("/api/v1/demo/submission/finalize", finalize_payload),
    ):
        resp = client.post(
            path, json=dict(payload), headers=_auth(actor=None)
        )
        assert resp.status_code == 401, resp.text
        assert resp.json()["code"] == "ACTOR_MISSING"
        assert "message" in resp.json()
        resp = client.post(
            path, json=dict(payload), headers=_auth(token="wrong-token")
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["code"] == "FORBIDDEN"
        assert "message" in resp.json()
