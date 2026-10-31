"""K12CON1 contributions ledger served through create_app (RED-first).

Drives POST/GET /api/v1/contributions through the real seam app
(create_app) with TestClient: POST needs x-actor (401) + the UI session
token via auth_hook (403); GET is open. The real in-process ledger
module backs the routes: no fakes.
"""

import os
import re
import sys
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "k12con1-served-token"
ACTOR = "tester-k12con1"


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


def _pkg():
    return "pkg-%s" % uuid.uuid4().hex[:12]


def test_post_round_trip_keeps_package_evidence_date(client):
    package_id = _pkg()
    resp = client.post(
        "/api/v1/contributions",
        json={"package_id": package_id,
              "evidence_ref": "ev-1",
              "recorded_at": "2026-10-01"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    entry = resp.json()["contribution"]
    assert entry == {"package_id": package_id,
                     "evidence_ref": "ev-1",
                     "recorded_at": "2026-10-01"}

    resp = client.get("/api/v1/contributions")
    assert resp.status_code == 200, resp.text
    rows = resp.json()["contributions"]
    assert entry in rows


def test_post_defaults_recorded_at_to_today(client):
    package_id = _pkg()
    resp = client.post(
        "/api/v1/contributions",
        json={"package_id": package_id, "evidence_ref": "ev-2"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    recorded = resp.json()["contribution"]["recorded_at"]
    assert recorded == date.today().isoformat()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", recorded)


def test_duplicate_package_id_refused_named_code(client):
    package_id = _pkg()
    resp = client.post(
        "/api/v1/contributions",
        json={"package_id": package_id, "evidence_ref": "ev-3"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        "/api/v1/contributions",
        json={"package_id": package_id, "evidence_ref": "ev-3-again"},
        headers=_auth(),
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "DUPLICATE_PACKAGE_ID"


def test_empty_package_id_refused(client):
    for bad in ("", "   "):
        resp = client.post(
            "/api/v1/contributions",
            json={"package_id": bad, "evidence_ref": "ev-4"},
            headers=_auth(),
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == "EMPTY_PACKAGE_ID"
    resp = client.post(
        "/api/v1/contributions",
        json={"evidence_ref": "ev-4-missing"},
        headers=_auth(),
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["code"] == "EMPTY_PACKAGE_ID"


def test_post_unauth_no_actor_401(client):
    resp = client.post(
        "/api/v1/contributions",
        json={"package_id": _pkg(), "evidence_ref": "ev-5"},
        headers=_auth(actor=None),
    )
    assert resp.status_code == 401, resp.text


def test_post_unauth_bad_token_403(client):
    resp = client.post(
        "/api/v1/contributions",
        json={"package_id": _pkg(), "evidence_ref": "ev-6"},
        headers=_auth(token="wrong-token"),
    )
    assert resp.status_code == 403, resp.text


def test_get_open_and_keeps_record_order(client):
    first, second = _pkg(), _pkg()
    for pid in (first, second):
        resp = client.post(
            "/api/v1/contributions",
            json={"package_id": pid, "evidence_ref": "ev-%s" % pid},
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
    resp = client.get("/api/v1/contributions")
    assert resp.status_code == 200, resp.text
    rows = resp.json()["contributions"]
    ids = [row["package_id"] for row in rows]
    assert ids.index(first) < ids.index(second)
