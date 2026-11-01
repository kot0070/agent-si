"""K13F1 route tests: amend / finalize-read / stop through create_app.

Drives the three K13F1 routes behind the frozen K02 seam guard: write
routes need x-actor (401) + the UI session token via auth_hook (403);
the finalize-read route is a read (no token). Amend accepts both
amendment classes, mints a new contract version + activation record, and
leaves a RUNNING run bound to the old hash. Stop reaches the real
cancellation entry and persists CANCELLED. Finalize-read round-trips a
record built by the real Finalizer through the real store.
"""

import os
import sys
from dataclasses import asdict, replace

import pytest
from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app
from agent_si.domain import contracts
from agent_si.finalization.finalizer import Finalizer

TEST_TOKEN = "k13f1-routes-token"
ACTOR = "tester-k13f1"

AMEND_PATH = "/api/v1/core/contracts/amend"
STOP_PATH = "/api/v1/core/runs/stop"
FINAL_PATH = "/api/v1/core/finalizations/%s"


def _settings():
    return {"ui_session_token": TEST_TOKEN, "testing": True}


def _headers(token=TEST_TOKEN, actor=ACTOR):
    headers = {}
    if actor is not None:
        headers["x-actor"] = actor
    if token is not None:
        headers["x-ui-session-token"] = token
    return headers


def _make_app():
    return create_app(dict(_settings()))


def _contract_kwargs(**overrides):
    base = dict(
        schema_version="1",
        contract_version=1,
        contract_sequence=1,
        project_id="P1",
        task_id="T1",
        created_by="director",
        priority="P2",
        risk="MEDIUM",
        goal="do the thing",
        requirements=("r1",),
        acceptance_criteria=("a1",),
        inputs=("i1",),
        outputs=("o1",),
        workspace="ws",
        permissions="read",
        tools=("tool1",),
        verification_policy_ref="vp:1",
        audit_policy_ref="ap:1",
        routing_policy_ref="rp:1",
        retry_policy_ref="rtp:1",
        fallback_policy_ref="fbp:1",
        optimization_policy_ref="op:1",
        override_policy_ref="ovp:1",
    )
    base.update(overrides)
    return base


def _seed_contract(app, **overrides):
    """Seed contract v1 + initial activation via the real domain entries."""
    bare = contracts.TaskContract(contract_hash="", **_contract_kwargs(**overrides))
    contract = replace(
        bare, contract_hash=contracts.compute_contract_hash(bare))
    state = app.state.k13f1
    contract_row = asdict(contract)
    contract_row["record_id"] = "P1:T1:%s" % contract.contract_hash
    contract_row["version"] = contract.contract_version
    state.contracts.append(contract_row)
    activation = contracts.activate(
        contract,
        activation_id="act-T1-1",
        activation_sequence=1,
        activation_reason="initial",
        activated_at="t0",
    )
    activation_row = asdict(activation)
    activation_row["record_id"] = activation.activation_id
    activation_row["version"] = activation.activation_sequence
    state.activations.append(activation_row)
    return contract, activation


def _seed_run(app, run_id, contract_hash, status="RUNNING", version=1):
    state = app.state.k13f1
    row = {
        "record_id": run_id,
        "project_id": "P1",
        "version": version,
        "run_id": run_id,
        "task_id": "T1",
        "status": status,
        "contract_hash": contract_hash,
    }
    state.runs.append(row)
    return row


def _seed_finalization(app):
    record = Finalizer.finalize(
        finalization_id="fin-1",
        project_id="P1",
        task_id="T1",
        run_id="run-fin-1",
        task_state="COMPLETED",
        audit_result="PASS",
        output_refs=("art-1",),
        accounting_complete=True,
        budget_settled=True,
        resources_released=True,
        completed_at="t9",
    )
    row = asdict(record)
    row["record_id"] = record.finalization_id
    row["version"] = 1
    app.state.k13f1.finalizations.append(row)
    return record


def test_amend_contract_affecting_new_version_and_activation():
    app = _make_app()
    old, _ = _seed_contract(app)
    resp = TestClient(app).post(
        AMEND_PATH,
        json={"project_id": "P1", "task_id": "T1",
              "fields": {"goal": "do the other thing"},
              "reason": "director note"},
        headers=_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["amendment_class"] == "CONTRACT_AFFECTING"
    assert body["contract_version"] == old.contract_version + 1
    assert body["contract_hash"] != old.contract_hash
    assert body["previous_contract_hash"] == old.contract_hash
    state = app.state.k13f1
    rows = state.activations.list_by({"project_id": "P1", "task_id": "T1"})
    assert len(rows) == 2
    live = contracts.resolve_active(
        [contracts.ContractActivationRecord(
            **{k: r[k] for k in contracts.ContractActivationRecord.__dataclass_fields__ if k in r})
         for r in rows])
    assert live is not None
    assert live.contract_hash == body["contract_hash"]


def test_amend_non_contract_affecting_new_version():
    app = _make_app()
    old, _ = _seed_contract(app)
    resp = TestClient(app).post(
        AMEND_PATH,
        json={"project_id": "P1", "task_id": "T1", "fields": {}},
        headers=_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["amendment_class"] == "NON_CONTRACT_AFFECTING"
    assert body["contract_version"] == old.contract_version + 1


def test_amend_running_run_keeps_old_hash():
    app = _make_app()
    old, _ = _seed_contract(app)
    _seed_run(app, "run-1", old.contract_hash, status="RUNNING")
    resp = TestClient(app).post(
        AMEND_PATH,
        json={"project_id": "P1", "task_id": "T1",
              "fields": {"goal": "changed goal"},
              "active_run_id": "run-1",
              "active_run_status": "RUNNING"},
        headers=_headers(),
    )
    assert resp.status_code == 200
    stored = app.state.k13f1.runs.load("run-1")
    assert stored is not None
    assert stored["contract_hash"] == old.contract_hash
    assert stored["status"] == "RUNNING"


def test_amend_without_actor_is_401():
    app = _make_app()
    _seed_contract(app)
    resp = TestClient(app).post(
        AMEND_PATH,
        json={"project_id": "P1", "task_id": "T1",
              "fields": {"goal": "x"}},
        headers=_headers(actor=None),
    )
    assert resp.status_code == 401


def test_amend_with_wrong_token_is_403():
    app = _make_app()
    _seed_contract(app)
    resp = TestClient(app).post(
        AMEND_PATH,
        json={"project_id": "P1", "task_id": "T1",
              "fields": {"goal": "x"}},
        headers=_headers(token="wrong-token"),
    )
    assert resp.status_code == 403


def test_amend_unknown_task_is_404():
    app = _make_app()
    resp = TestClient(app).post(
        AMEND_PATH,
        json={"project_id": "P1", "task_id": "NOPE",
              "fields": {"goal": "x"}},
        headers=_headers(),
    )
    assert resp.status_code == 404


def test_stop_running_run_cancelled():
    app = _make_app()
    old, _ = _seed_contract(app)
    _seed_run(app, "run-1", old.contract_hash, status="RUNNING")
    resp = TestClient(app).post(
        STOP_PATH,
        json={"project_id": "P1", "run_id": "run-1",
              "reason": "CANCELLED_BY_USER"},
        headers=_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "run-1"
    assert body["from_status"] == "RUNNING"
    assert body["to_status"] == "CANCELLED"
    assert body["reason"] == "CANCELLED_BY_USER"
    stored = app.state.k13f1.runs.load("run-1")
    assert stored is not None
    assert stored["status"] == "CANCELLED"
    assert stored["contract_hash"] == old.contract_hash


def test_stop_without_actor_is_401():
    app = _make_app()
    old, _ = _seed_contract(app)
    _seed_run(app, "run-1", old.contract_hash, status="RUNNING")
    resp = TestClient(app).post(
        STOP_PATH,
        json={"project_id": "P1", "run_id": "run-1",
              "reason": "CANCELLED_BY_USER"},
        headers=_headers(actor=None),
    )
    assert resp.status_code == 401


def test_stop_with_wrong_token_is_403():
    app = _make_app()
    old, _ = _seed_contract(app)
    _seed_run(app, "run-1", old.contract_hash, status="RUNNING")
    resp = TestClient(app).post(
        STOP_PATH,
        json={"project_id": "P1", "run_id": "run-1",
              "reason": "CANCELLED_BY_USER"},
        headers=_headers(token="wrong-token"),
    )
    assert resp.status_code == 403


def test_stop_unknown_run_is_404():
    app = _make_app()
    resp = TestClient(app).post(
        STOP_PATH,
        json={"project_id": "P1", "run_id": "ghost",
              "reason": "CANCELLED_BY_USER"},
        headers=_headers(),
    )
    assert resp.status_code == 404


def test_stop_terminal_run_is_409():
    app = _make_app()
    old, _ = _seed_contract(app)
    _seed_run(app, "run-9", old.contract_hash, status="CANCELLED")
    resp = TestClient(app).post(
        STOP_PATH,
        json={"project_id": "P1", "run_id": "run-9",
              "reason": "CANCELLED_BY_USER"},
        headers=_headers(),
    )
    assert resp.status_code == 409


def test_finalization_read_round_trip():
    app = _make_app()
    record = _seed_finalization(app)
    resp = TestClient(app).get(FINAL_PATH % "fin-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["record_id"] == "fin-1"
    assert body["project_id"] == "P1"
    assert body["task_id"] == "T1"
    assert body["completion_disposition"] == str(
        record.completion_disposition.value)


def test_finalization_read_unknown_is_404():
    app = _make_app()
    resp = TestClient(app).get(FINAL_PATH % "missing")
    assert resp.status_code == 404
