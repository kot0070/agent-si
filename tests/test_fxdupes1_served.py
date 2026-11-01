"""FXDUPES1 served dedupe: losers 404, keepers as before, one write/read per store.

Group B losers (k12open2 demo check/scan) are removed: they 404. Their
k12open1 keepers answer as before (byte-identical pure logic). Groups A, C, D,
E are OWNER (DECISIONS.md): both/all members stay served as before, with one
write-then-read round-trip per store lane.
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

from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "fxdupes1-served-token"
ACTOR = "tester-fxdupes1"


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


def _route_paths(app_or_client):
    app = getattr(app_or_client, "app", app_or_client)
    return {getattr(r, "path", "") for r in app.routes if hasattr(r, "path")}


# --- Group B: losers 404 ---


def test_b_demo_check_loser_404(client):
    resp = client.post(
        "/api/v1/demo/public-text/check",
        json={"idea_text": "hello world"},
        headers=_auth(),
    )
    assert resp.status_code == 404, resp.text


def test_b_demo_scan_loser_404(client):
    resp = client.post(
        "/api/v1/demo/submission/scan",
        json={"notes": "hello notes"},
        headers=_auth(),
    )
    assert resp.status_code == 404, resp.text


# --- Group B: keepers as before ---


def test_b_keeper_check_clean(client):
    resp = client.post(
        "/api/v1/public-text/check",
        json={"idea_text": "A public demo night showing a garden watering rota."},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "violations": []}


def test_b_keeper_check_violation(client):
    resp = client.post(
        "/api/v1/public-text/check",
        json={"idea_text": "Demo login with api_key = [REDACTED]"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["violations"] == [
        {
            "code": "SECRET_IN_PUBLIC_TEXT",
            "message": "public idea/demo text must not contain secrets",
        }
    ]


def test_b_keeper_scan_secret(client):
    resp = client.post(
        "/api/v1/submission/scan",
        json={
            "files": [
                {
                    "path": "demo/config.env",
                    "content": "api_key = [REDACTED]",
                }
            ]
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["findings"] == [
        {
            "code": "SECRET_DETECTED",
            "path": "demo/config.env",
            "message": "submission carries a possible secret",
        }
    ]


def test_b_keeper_scan_empty_400(client):
    resp = client.post(
        "/api/v1/submission/scan",
        json={},
        headers=_auth(),
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["code"] == "EMPTY_SUBMISSION"


# --- Group A (OWNER): both lanes stay; one write + one read per lane ---


def test_a_keeper_mark_round_trip(client):
    client.app.state.ledger_for("proj-fx").record_row("pkg-fx-1", 1, 1, 1.0)
    today = datetime.date.today().isoformat()
    resp = client.post(
        "/api/v1/demo/contributions/mark",
        json={"package_id": "pkg-fx-1", "evidence_ref": "ev-fx"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "contribution": {
            "package_id": "pkg-fx-1",
            "evidence_ref": "ev-fx",
            "recorded_at": today,
        }
    }
    resp = client.get("/api/v1/demo/contributions")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "contributions": [
            {
                "package_id": "pkg-fx-1",
                "evidence_ref": "ev-fx",
                "recorded_at": today,
            }
        ]
    }


def test_a_k12open2_lane_round_trip(client):
    today = datetime.date.today().isoformat()
    resp = client.post(
        "/api/v1/contributions",
        json={"package_id": "pkg-fx-2"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "contribution": {
            "package_id": "pkg-fx-2",
            "evidence_ref": None,
            "recorded_at": today,
        }
    }
    resp = client.get("/api/v1/contributions")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "contributions": [
            {
                "package_id": "pkg-fx-2",
                "evidence_ref": None,
                "recorded_at": today,
            }
        ]
    }


# --- Group C (OWNER): both members of each pair stay served ---


def _turn(tag):
    return {
        "run_id": "r-fx-%s" % tag,
        "project_id": "p-fx",
        "task_id": "t-fx",
        "contract_hash": "h-fx",
        "work_refs": ["w1"],
        "artifact_refs": [],
        "evidence_refs": [],
        "producer_session_refs": [],
    }


def test_c1_both_served_turn(client):
    resp = client.post(
        "/api/v1/assurance/audit_served_turn", json=_turn("c1"), headers=_auth()
    )
    assert resp.status_code == 200, resp.text
    assert "audit_id" in resp.json()
    resp = client.post(
        "/api/v1/assurance/served-turn", json=_turn("c1"), headers=_auth()
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["served"] is True
    assert "audit_id" in resp.json()


def test_c2_run_pair_stays_mounted(client):
    # App run_assurance always-500s (wrong entry attr — defect in RETURN);
    # OWNER keeps it mounted: assert mounted, not the 500.
    resp = client.post(
        "/api/v1/assurance/run_assurance", json=_turn("c2"), headers=_auth()
    )
    assert resp.status_code != 404, resp.text
    resp = client.post(
        "/api/v1/assurance/run", json=_turn("c2"), headers=_auth()
    )
    assert resp.status_code == 200, resp.text
    assert "phase" in resp.json()


def test_c3_both_fresh(client):
    resp = client.post(
        "/api/v1/assurance/fresh_assurance", json=_turn("c3"), headers=_auth()
    )
    assert resp.status_code == 200, resp.text
    assert "audit_id" in resp.json()
    # k03wire fresh-audit needs a product-recorded pin; unknown run refuses.
    resp = client.post(
        "/api/v1/assurance/fresh-audit", json=_turn("c3"), headers=_auth()
    )
    assert resp.status_code in (200, 404), resp.text


def test_c4_both_close(client):
    body = {"task_id": "t-fx", "scope_id": "s-fx", "audit_id": "a-fx"}
    resp = client.post(
        "/api/v1/assurance/close_stage", json=dict(body), headers=_auth()
    )
    assert resp.status_code == 200, resp.text
    assert "row_id" in resp.json()
    resp = client.post(
        "/api/v1/assurance/stages/close", json=dict(body), headers=_auth()
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["row_id"] == "t-fx/s-fx/a-fx"


# --- Group D (OWNER): all stay ---


def test_d_reference_doc_stays(client):
    resp = client.get("/api/v1/app/step-limits")
    assert resp.status_code == 200, resp.text
    assert resp.json()["row"] == "B0B-UNCOVERED_ARCH-686"


def test_d_per_project_round_trip(client):
    resp = client.put(
        "/api/v1/projects/p-fx/step-limits",
        json={"task_max_steps": 7, "chat_max_steps": 8},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["task_max_steps"] == 7
    resp = client.get("/api/v1/projects/p-fx/step-limits")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "project_id": "p-fx",
        "task_max_steps": 7,
        "chat_max_steps": 8,
    }


def test_d_app_setter_stays(client):
    resp = client.post(
        "/api/v1/step-limits",
        json={
            "project_id": "p-fx",
            "max_agent_steps": 5,
            "max_chat_steps": 6,
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["max_agent_steps"] == 5


# --- Group E (OWNER): all stay ---


def test_e_app_offload_pair_stays(client):
    resp = client.put(
        "/api/v1/offload-switch",
        json={"project_id": "p-fx", "enabled": True},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["routine_offload_enabled"] is True
    resp = client.post(
        "/api/v1/offload",
        json={"project_id": "p-fx", "routine": "r"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["project_id"] == "p-fx"


def test_e_offload_routes_round_trip(client):
    resp = client.put(
        "/api/v1/projects/p-fx/offload",
        json={"role": "worker", "enabled": True},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is True
    resp = client.get("/api/v1/projects/p-fx/offload", params={"role": "worker"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is True
    resp = client.post(
        "/api/v1/offload/maybe",
        json={"task_id": "t", "role": "worker", "routine": True},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert "handover" in resp.json()
