"""FXAUDITC fresh-audit contract_hash pin over the served route.

Drives ONLY the frozen create_app route POST /api/v1/assurance/fresh-audit
through the real product entries. The submitted contract_hash is compared
against the product-recorded contract_hash pin for the audited run (audit
records of that run_id):

- free-text contract_hash on a run with no pin -> 4xx unknown-hash
- stale contract_hash (pin exists, value differs) -> 4xx stale-hash
- frozen contract_hash (matches the pin) -> minted audit id as today

RED: free-text mints an audit id, so the unknown-hash and stale-hash
cases fail before the pin lands.
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

TEST_TOKEN = "fxauditc-hash-token"
ACTOR = "tester-fxauditc-hash"

UNKNOWN_CODE = "K03WIRE_FRESH_AUDIT_UNKNOWN_HASH"
STALE_CODE = "K03WIRE_FRESH_AUDIT_STALE_HASH"


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


def _tag():
    return uuid.uuid4().hex[:12]


def _turn(tag, run_id, contract_hash):
    return {
        "project_id": "fxauditc-p-%s" % tag,
        "task_id": "fxauditc-t-%s" % tag,
        "run_id": run_id,
        "contract_hash": contract_hash,
        "work_refs": ["work-fxauditc-%s" % tag],
        "artifact_refs": [],
        "evidence_refs": [],
        "producer_session_refs": [],
    }


def _pin_run(client, tag, run_id, contract_hash):
    """Record the product pin for a run through the served-turn route."""
    pinned = client.post(
        "/api/v1/assurance/served-turn",
        json=_turn(tag, run_id, contract_hash),
        headers=_auth(),
    )
    assert pinned.status_code == 200, pinned.text
    assert pinned.json()["audit_id"]
    return pinned.json()["audit_id"]


def test_free_text_contract_hash_is_unknown_hash(client):
    tag = _tag()
    run_id = "run-fxauditc-free-%s" % tag
    resp = client.post(
        "/api/v1/assurance/fresh-audit",
        json=_turn(tag, run_id, "free-text-not-a-pin-%s" % tag),
        headers=_auth(),
    )
    assert 400 <= resp.status_code < 500, resp.text
    assert resp.json()["detail"]["code"] == UNKNOWN_CODE, resp.text


def test_stale_contract_hash_is_stale_hash(client):
    tag = _tag()
    run_id = "run-fxauditc-stale-%s" % tag
    frozen = "frozen-contract-fxauditc-%s" % tag
    _pin_run(client, tag, run_id, frozen)
    resp = client.post(
        "/api/v1/assurance/fresh-audit",
        json=_turn(tag, run_id, "stale-contract-fxauditc-%s" % tag),
        headers=_auth(),
    )
    assert 400 <= resp.status_code < 500, resp.text
    assert resp.json()["detail"]["code"] == STALE_CODE, resp.text


def test_frozen_contract_hash_mints_audit_id(client):
    tag = _tag()
    run_id = "run-fxauditc-frozen-%s" % tag
    frozen = "frozen-contract-fxauditc-%s" % tag
    _pin_run(client, tag, run_id, frozen)
    resp = client.post(
        "/api/v1/assurance/fresh-audit",
        json=_turn(tag, run_id, frozen),
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["audit_id"]
    assert resp.json()["audit_session_ref"]
