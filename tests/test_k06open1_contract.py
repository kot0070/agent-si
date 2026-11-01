"""K06OPEN1 behaviour tests: rows 189/253/254 on the served worker path.

Served path: create_app + TestClient (loopback only, no keys, no
network). One behaviour test per row through the create_app entry.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient

from agent_si.backend.app import create_app

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


# --- R-367: assurance mount (verify, then audit, then close) ---


def test_r367_assurance_finalize_guards_served():
    client = _client()
    resp = client.post("/api/v1/assurance/finalize", json={})
    assert resp.status_code == 401, resp.text
    resp = client.post("/api/v1/assurance/finalize", json={},
                       headers=_auth())
    assert resp.status_code == 400, resp.text
    resp = client.post(
        "/api/v1/assurance/finalize",
        json={
            "project_id": "p",
            "task_id": "no-such-task",
            "run_id": "r",
            "contract_hash": "h",
        },
        headers=_auth(),
    )
    assert resp.status_code == 404, resp.text
    assert "no-such-task" in resp.text


def test_r367_verify_refused_never_audits_served():
    import tempfile

    client = _client()
    project_id = client.post(
        "/api/v1/projects",
        json={"name": "p-r367", "folder_ref": "f-r367"},
        headers=_auth(),
    ).json()["project"]["project_id"]
    task_id = client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "t-r367", "scope": ["s"]},
        headers=_auth(),
    ).json()["task"]["task_id"]
    with tempfile.TemporaryDirectory(prefix="r367-verify-") as project_dir:
        resp = client.post(
            "/api/v1/assurance/finalize",
            json={
                "project_id": project_id,
                "task_id": task_id,
                "run_id": "run-r367",
                "contract_hash": "hash-r367",
                "project_dir": project_dir,
                "work_refs": ["work-r367"],
                "criteria": [{"ac_id": "AC-r367"}],
                "tool_rows": [],
            },
            headers=_auth(),
        )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["ok"] is False
    assert payload["phase"] == "VERIFY_REFUSED"
    assert payload["verification_id"]
    assert payload["audit_id"] is None
    assert payload["verdict"] is None
    turns = client.get(f"/api/v1/tasks/{task_id}/turns")
    assert turns.status_code == 200, turns.text
    assert turns.json()["turns"][0]["action"] == "no-audit"


def test_r367_detected_environment_unknown_not_alarm_served():
    client = _client()
    resp = client.get("/portability/environment")
    assert resp.status_code == 200, resp.text
    page = resp.json()
    assert page["detected"]["alarm"] is False
    assert page["detected"]["state"]["gpu"] == "UNKNOWN"
    assert page["detected"]["state"]["local-ai"] == "UNKNOWN"
    assert set(page["states"].values()) == {"UNKNOWN"}
    check = page["check"]
    assert check["dry_run"] is True
    assert check["status"] == "green"
    assert check["alarm"] is False
    assert all(entry["alarm"] is False for entry in check["checks"])


# --- M-D-D3: port contracts frozen by hash; targets pinned per allow ---


def test_d3_contract_frozen_and_targets_pinned_served():
    client = _client()
    first = client.get("/api/v1/k06/script-contract")
    assert first.status_code == 200, first.text
    second = client.get("/api/v1/k06/script-contract")
    assert second.json() == first.json()
    assert "contract_hash" in first.json()["template_text"]
    refused = client.post(
        "/api/v1/k06/tools/dispatch",
        json={
            "tool": "other",
            "argv": ["other", "run"],
            "action_class": "R0",
            "auth": _auth_r0(),
            "task_authorized": ["status"],
        },
        headers=_auth(),
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "TOOL_NOT_AUTHORIZED"


# --- B0B-UNCOVERED_MVP_ACCEPT-141: env example with SecretRef pointers ---


def test_141_env_example_secretref_pointers_served():
    client = _client()
    payload = client.get("/api/v1/k06/script-contract").json()
    import json as _json

    template, _ = _json.JSONDecoder().raw_decode(
        payload["template_text"])
    pointer = template["env"]["API_KEY"]
    assert set(pointer) == {"secretRef"}
    assert isinstance(pointer["secretRef"], str) and pointer["secretRef"]
    joined = "\n".join(
        [payload["contract_text"], payload["template_text"],
         payload["instruction_text"]]
    )
    assert "secretRef" in joined
    assert "AKIA" not in joined and "sk-live-" not in joined
    seam = client.get("/api/v1/keychain/seam")
    assert seam.status_code == 200, seam.text
    ref = seam.json()["secret_ref"]
    assert isinstance(ref, str) and ref.startswith("secretref:")
