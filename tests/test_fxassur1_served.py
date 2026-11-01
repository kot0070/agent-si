"""FXASSUR1 served assurance: run_assurance delegation + keeper never-500.

RED-first: on the unpatched tree POST /api/v1/assurance/run_assurance
with a valid body answers 500 (the handler calls a missing
``audit_coordinator.run_assurance`` attribute); after the fix the valid
body reaches the real ``assurance.coordinator.run_assurance`` entry
(proven by a wraps spy, never a fake result) and answers 200 with the
real outcome fields, a bad body answers 400 with a code field, and all
four keeper routes never answer 500.
"""

import os
import sys
import uuid
from unittest import mock

import pytest
from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.assurance import coordinator as _coordinator  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "fxassur1-served-token"
ACTOR = "tester-fxassur1"

RUN_ROUTE = "/api/v1/assurance/run_assurance"
TURN_ROUTE = "/api/v1/assurance/audit_served_turn"
FRESH_ROUTE = "/api/v1/assurance/fresh_assurance"
CLOSE_ROUTE = "/api/v1/assurance/close_stage"


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
    return TestClient(app, raise_server_exceptions=False)


def _tag():
    return uuid.uuid4().hex[:12]


def _turn(tag, work=True):
    return {
        "project_id": "fxassur1-p-%s" % tag,
        "task_id": "fxassur1-t-%s" % tag,
        "run_id": "run-fxassur1-%s" % tag,
        "contract_hash": "contract-fxassur1-%s" % tag,
        "work_refs": ["work-fxassur1-%s" % tag] if work else [],
        "artifact_refs": [],
        "evidence_refs": [],
        "producer_session_refs": [],
    }


def _run_body(tag, project_dir):
    body = _turn(tag, work=True)
    body["tool_rows"] = []
    body["project_dir"] = str(project_dir)
    body["task_state"] = None
    body["output_refs"] = []
    body["metric_refs"] = []
    body["accounting_complete"] = False
    body["budget_settled"] = False
    body["resources_released"] = False
    return body


def test_run_assurance_valid_reaches_real_coordinator(client, tmp_path):
    tag = _tag()
    proj = tmp_path / ("proj-%s" % tag)
    proj.mkdir()
    real = _coordinator.run_assurance
    with mock.patch.object(
        _coordinator, "run_assurance", wraps=real
    ) as spy:
        resp = client.post(
            RUN_ROUTE, json=_run_body(tag, proj), headers=_auth()
        )
    assert resp.status_code == 200, resp.text
    assert spy.call_count == 1, spy.call_count
    outcome = resp.json()
    for key in (
        "ok",
        "phase",
        "verification_id",
        "audit_id",
        "finalization_id",
        "status_trail",
        "records",
    ):
        assert key in outcome, outcome
    for step in outcome["records"]:
        assert {"leg", "status", "note"} <= set(step), step


def test_run_assurance_bad_body_400_with_code(client):
    for bad in ({}, {"project_id": "only-fxassur1"}):
        resp = client.post(RUN_ROUTE, json=bad, headers=_auth())
        assert resp.status_code == 400, resp.text
        detail = resp.json().get("detail")
        assert isinstance(detail, dict) and "code" in detail, resp.text


def test_keepers_never_500(client, tmp_path):
    tag = _tag()
    proj = tmp_path / ("proj-%s" % tag)
    proj.mkdir()
    cases = [
        (RUN_ROUTE, _run_body(tag, proj)),
        (RUN_ROUTE, {}),
        (TURN_ROUTE, _turn("keep-%s" % tag)),
        (TURN_ROUTE, {}),
        (FRESH_ROUTE, _turn("fresh-%s" % tag)),
        (FRESH_ROUTE, {}),
        (
            CLOSE_ROUTE,
            {
                "task_id": "t-fxassur1-%s" % tag,
                "scope_id": "s-fxassur1-%s" % tag,
                "audit_id": "a-fxassur1-%s" % tag,
            },
        ),
        (CLOSE_ROUTE, {}),
    ]
    for route, body in cases:
        resp = client.post(route, json=body, headers=_auth())
        assert resp.status_code != 500, (route, body, resp.text)
