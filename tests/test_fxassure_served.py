"""FXASSURE served regression: run_assurance forwards criteria to verify_run.

RED-first: on the drifted tree coordinator.run_assurance calls
checker.verify_run with audit-leg keywords (artifact_refs, evidence_refs,
work_refs, producer_session_refs, task_state), so POST
/api/v1/assurance/run_assurance answers 200 VERIFY_REFUSED with
"verification raised TypeError: verify_run() got an unexpected keyword
argument". After the fix the same POST carries criteria to the real
checker: an empty criteria list is refused at verify (nothing to verify,
no audit, no TypeError text), and a criterion naming missing
evidence fails closed at verify (VERIFY_REFUSED with a refusal note,
still no TypeError text).
"""

import os
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "fxassure-served-token"
ACTOR = "tester-fxassure"

RUN_ROUTE = "/api/v1/assurance/run_assurance"


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


def _run_body(tag, project_dir, criteria):
    return {
        "project_id": "fxassure-p-%s" % tag,
        "task_id": "fxassure-t-%s" % tag,
        "run_id": "run-fxassure-%s" % tag,
        "contract_hash": "contract-fxassure-%s" % tag,
        "project_dir": str(project_dir),
        "tool_rows": [],
        "criteria": criteria,
        "work_refs": ["work-fxassure-%s" % tag],
        "artifact_refs": [],
        "evidence_refs": [],
        "producer_session_refs": [],
        "task_state": None,
        "output_refs": [],
        "metric_refs": [],
        "accounting_complete": False,
        "budget_settled": False,
        "resources_released": False,
    }


def test_empty_criteria_refused_at_verify_without_typeerror(client, tmp_path):
    tag = _tag()
    proj = tmp_path / ("proj-%s" % tag)
    proj.mkdir()
    resp = client.post(
        RUN_ROUTE, json=_run_body(tag, proj, []), headers=_auth()
    )
    assert resp.status_code == 200, resp.text
    assert "TypeError" not in resp.text, resp.text
    assert "unexpected keyword" not in resp.text, resp.text
    outcome = resp.json()
    assert outcome["phase"] == "VERIFY_REFUSED", outcome
    assert outcome["audit_id"] is None, outcome
    assert outcome["status_trail"] == ["RUNNING", "VERIFYING", "FAILED"], outcome
    for step in outcome["records"]:
        assert "TypeError" not in step["note"], step


def test_missing_evidence_criterion_fails_closed_at_verify(
    client, tmp_path
):
    tag = _tag()
    proj = tmp_path / ("proj-%s" % tag)
    proj.mkdir()
    criteria = [
        {
            "ac_id": "ac-fxassure-%s" % tag,
            "evidence_required": True,
            "evidence_refs": ["missing-ev-fxassure-%s" % tag],
            "severity": "HIGH",
            "verification_method": "grounded-evidence",
        },
    ]
    resp = client.post(
        RUN_ROUTE, json=_run_body(tag, proj, criteria), headers=_auth()
    )
    assert resp.status_code == 200, resp.text
    assert "TypeError" not in resp.text, resp.text
    assert "unexpected keyword" not in resp.text, resp.text
    outcome = resp.json()
    assert outcome["phase"] == "VERIFY_REFUSED", outcome
    assert outcome["status_trail"] == [
        "RUNNING", "VERIFYING", "FAILED",
    ], outcome
    notes = " | ".join(step["note"] for step in outcome["records"])
    assert "verification refused" in notes, outcome
