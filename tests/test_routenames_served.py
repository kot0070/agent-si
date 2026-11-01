"""ROUTENAMES served proof: 10 sample renamed routes answer, old ones 404.

One route per package domain (k03 qa, k07 app, k10 release, k12 demo,
k13 core): the new /api/v1/<domain>/* path answers 200 through the
real create_app app (TestClient), and the old lane-named path answers
404 (no aliases). The 5 DEDUPE-DIFF variant tails (ruling 03:25) are
covered below: /api/v1/qa/sourcing_gate{,/scoped,/basic} and
/api/v1/qa/semantic_security{,/lenient}.
"""
import os
import sys
from dataclasses import asdict

from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.finalization.finalizer import Finalizer  # noqa: E402
from agent_si.http import k07next as _k07_boundary  # noqa: E402

TEST_TOKEN = "routenames-served-token"
ACTOR = "tester-routenames"


def _settings(**overrides):
    base = {"ui_session_token": TEST_TOKEN, "testing": True,
            "secret_store": "memory"}
    base.update(overrides)
    return base


def _headers(token=TEST_TOKEN, actor=ACTOR):
    headers = {}
    if actor is not None:
        headers["x-actor"] = actor
    if token is not None:
        headers["x-ui-session-token"] = token
    return headers


def _client(tmp_path=None, monkeypatch=None):
    if tmp_path is not None and monkeypatch is not None:
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))
        monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    app = create_app(dict(_settings()))
    _k07_boundary.mount(app)
    return TestClient(app), app


def test_routename_k03_qa_registry_gate(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/v1/qa/registry_gate",
        json={"provider_id": "provider-routenames",
              "model": "meta/muse-spark-1.3-auditor",
              "implementer_model_ids": ["meta/muse-spark-1.3-contributor"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["disposition"] == "BLOCKED"
    old = client.post(
        "/api/v1/k03rest/registry_gate",
        json={"provider_id": "provider-routenames",
              "model": "meta/muse-spark-1.3-auditor",
              "implementer_model_ids": ["meta/muse-spark-1.3-contributor"]},
    )
    assert old.status_code == 404, old.text


def test_routename_k07_app_adopted_decision(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    resp = client.get("/api/v1/app/adopted-decision")
    assert resp.status_code == 200, resp.text
    assert resp.json()["row"] == "163"
    old = client.get("/api/v1/k07next/adopted-decision")
    assert old.status_code == 404, old.text


def test_routename_k10_release_accept(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    resp = client.get("/api/v1/release/accept")
    assert resp.status_code == 200, resp.text
    assert resp.json()["testid"] == "k10st4-accept"
    old = client.get("/k10/accept")
    assert old.status_code == 404, old.text


def test_routename_k12_demo_public_text(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/v1/demo/public-text/check",
        json={"idea_text": "A public demo night showing a garden rota."},
        headers=_headers(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "violations": []}
    old = client.post(
        "/api/v1/k12open2/public-text/check",
        json={"idea_text": "A public demo night showing a garden rota."},
        headers=_headers(),
    )
    assert old.status_code == 404, old.text


def test_routename_k13_core_finalization_read(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    record = Finalizer.finalize(
        finalization_id="fin-routenames",
        project_id="P1",
        task_id="T1",
        run_id="run-fin-rn",
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
    resp = client.get("/api/v1/core/finalizations/fin-routenames")
    assert resp.status_code == 200, resp.text
    assert resp.json()["record_id"] == "fin-routenames"
    old = client.get("/api/v1/k13/finalizations/fin-routenames")
    assert old.status_code == 404, old.text


def _gate_body():
    return {"implementer_model_ids": ["meta/muse-spark-1.3-contributor"],
            "task_class": "served-turn", "minimum_level": "L2"}


def test_routename_k03_qa_sourcing_gate(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/qa/sourcing_gate", json=_gate_body())
    assert resp.status_code == 200, resp.text
    assert resp.json()["disposition"] == "BLOCKED"
    old = client.post(
        "/api/v1/k03next/sourcing_gate", json=_gate_body())
    assert old.status_code == 404, old.text


def test_routename_k03_qa_sourcing_gate_scoped(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/v1/qa/sourcing_gate/scoped", json=_gate_body())
    assert resp.status_code == 200, resp.text
    assert resp.json()["disposition"] == "BLOCKED"
    old = client.post(
        "/api/v1/k03next2/sourcing_gate", json=_gate_body())
    assert old.status_code == 404, old.text


def test_routename_k03_qa_sourcing_gate_basic(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/v1/qa/sourcing_gate/basic", json=_gate_body())
    assert resp.status_code == 200, resp.text
    assert resp.json()["disposition"] == "BLOCKED"
    old = client.post(
        "/api/v1/k03rest/sourcing_gate", json=_gate_body())
    assert old.status_code == 404, old.text


def test_routename_k03_qa_semantic_security(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    body = {"criterion_refs": ["crit-routenames"],
            "evidence_refs": ["ev-routenames"]}
    resp = client.post("/api/v1/qa/semantic_security", json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["verdict"] == "PASS"
    old = client.post("/api/v1/k03next/semantic_security", json=body)
    assert old.status_code == 404, old.text


def test_routename_k03_qa_semantic_security_lenient(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/qa/semantic_security/lenient", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["verdict"] == "FAIL"
    old = client.post("/api/v1/k03rest/semantic_security", json={})
    assert old.status_code == 404, old.text
