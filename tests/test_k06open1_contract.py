"""K06OPEN1 behaviour tests: rows 189/253/254 on the served worker path.

Served path: create_app + TestClient (loopback only, no keys, no
network). One behaviour test per row through the create_app entry.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "k06open1-loopback-token"
ACTOR = "tester-k06open1"


def _settings():
    return {"testing": True, "ui_session_token": TEST_TOKEN}


def _auth():
    return {"x-actor": ACTOR, "x-ui-session-token": TEST_TOKEN}


def _client():
    return TestClient(create_app(_settings()))


def _auth_r0():
    return {"subject": "worker", "task": "task-1"}


# --- row 189: contract + template + instruction text in UI/docs ---


def test_189_contract_template_instruction_served():
    client = _client()
    resp = client.get("/api/v1/k06/script-contract")
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    contract = payload["contract_text"]
    template = payload["template_text"]
    instruction = payload["instruction_text"]
    assert "facts" in contract and "result" in contract
    assert "declared_power" in contract or "declared power" in contract
    assert "secret-keys" in contract and "network-access" in contract
    assert "secretRef" in template
    assert "contract_hash" in template
    assert instruction
    assert "dry run" in instruction or "dry-run" in instruction


def test_189_texts_carry_refs_never_raw_values():
    client = _client()
    payload = client.get("/api/v1/k06/script-contract").json()
    joined = "\n".join(
        [payload["contract_text"], payload["template_text"],
         payload["instruction_text"]]
    )
    assert "secretRef" in joined
    assert "AKIA" not in joined and "sk-live-" not in joined


# --- row 253: declared-services acceptance run filed ---


def test_253_acceptance_run_filed_through_real_belt():
    client = _client()
    resp = client.post(
        "/api/v1/k06/services/acceptance",
        json={
            "service": "status",
            "argv": ["status"],
            "action_class": "R0",
            "auth": _auth_r0(),
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    run = resp.json()
    assert run["run_id"].startswith("acceptance-")
    assert run["service"] == "status"
    assert run["ok"] is True
    assert run["evidence_refs"]
    listed = client.get("/api/v1/k06/services/acceptance")
    assert listed.status_code == 200, listed.text
    runs = listed.json()["runs"]
    assert any(r["run_id"] == run["run_id"] for r in runs)


def test_253_unknown_service_refused_without_filing():
    client = _client()
    resp = client.post(
        "/api/v1/k06/services/acceptance",
        json={
            "service": "nope",
            "argv": ["nope"],
            "action_class": "R0",
            "auth": _auth_r0(),
        },
        headers=_auth(),
    )
    assert resp.status_code == 400, resp.text
    listed = client.get("/api/v1/k06/services/acceptance")
    assert listed.json()["runs"] == []


# --- row 254: install-record view test ---


def test_254_install_record_view():
    client = _client()
    resp = client.post(
        "/api/v1/k06/installs",
        json={
            "tool": "ruff",
            "version": "0.8.0",
            "status": "granted",
            "source": "install-ask",
            "verified": True,
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["tool"] == "ruff"
    view = client.get("/api/v1/k06/installs", params={"tool": "ruff"})
    assert view.status_code == 200, view.text
    assert view.json()["records"][0]["version"] == "0.8.0"


def test_254_unknown_tool_named_in_view():
    client = _client()
    view = client.get("/api/v1/k06/installs", params={"tool": "nope"})
    assert view.status_code == 200, view.text
    assert view.json()["records"] == []
    assert view.json()["unknown_tool"] == "nope"
