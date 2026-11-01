"""K06H1 behaviour: TaskContract chain + SecretRef-only + zero raw bytes.

Row 252: an R1 action executes only with an unbroken TaskContract
authorization chain end to end (guard -> belt -> action record).
Row 20A-a: TaskContract/Manager/Agent paths carry SecretRef handles,
never raw secrets. Row 20A-b: logs, telemetry, reports and records
hold zero raw-secret bytes.

Every raw value below is made inside this test only; no real key,
no owner store, no machine path appears here.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent_si.domain import contracts as domain_contracts  # noqa: E402
from agent_si.portability import merge as port_merge  # noqa: E402
from agent_si.script_import import validation as si_validation  # noqa: E402
from agent_si.services import commands as svc_commands  # noqa: E402
from agent_si.toolguard import actions, guard, permissions, secrets  # noqa: E402
from agent_si.worker_tools import ToolRegistry, guarded_dispatch  # noqa: E402

# Tests-only raw stand-in. Never a real credential.
RAW_SECRET = "K06H1-RAW-9f2c7e4a1b5d8f0a3c6e"


def _import_contract():
    return {
        "name": "k06h1-demo",
        "version": "1",
        "contract_hash": "k06h1-hash",
        "declared_powers": [],
        "forbidden": ["secret-keys", "network-access"],
    }


def _valid_task_contract() -> domain_contracts.TaskContract:
    base = domain_contracts.TaskContract(
        schema_version="1",
        contract_version=1,
        contract_sequence=1,
        project_id="k06h1-project",
        task_id="k06h1-task",
        goal="Run the K06H1 tool-belt chain",
        workspace="project-workspace",
        permissions="R1",
    )
    digest = domain_contracts.compute_contract_hash(base)
    return dataclasses.replace(base, contract_hash=digest)


def _tampered_task_contract(
    valid: domain_contracts.TaskContract,
) -> domain_contracts.TaskContract:
    return dataclasses.replace(valid, goal="Tampered goal without approval")


def _belt_auth(contract) -> dict:
    return {
        "subject": "worker",
        "scopes": ["tools:exec"],
        "contract": contract,
        "task": "k06h1-task",
    }


class _EchoEntryPoint:
    name = "echo"
    action_class = "R1"

    def load(self):
        def _impl(argv, action_class, auth):
            return {
                "ok": True,
                "argv": list(argv),
                "action_class": action_class,
                "pid": 4242,
                "output": {"words": list(argv)},
            }

        return _impl


def _echo_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(_EchoEntryPoint())
    return registry


# --- Row 252: TaskContract authorization chain unbroken end to end ---


def test_252_valid_contract_chain_executes_end_to_end():
    contract = _valid_task_contract()
    verdict = guard.evaluate(["echo", "hello"], "R1", _belt_auth(contract))
    assert verdict["decision"] == "allow"
    decision = permissions.check_permission(
        "R1", {"contract": contract}, generated=False
    )
    assert decision.get("ok") is True
    result = guarded_dispatch(
        ["echo", "hello"], "R1", _belt_auth(contract),
        tool="echo", registry=_echo_registry(),
    )
    assert result["ok"] is True
    assert result["output"] == {"words": ["echo", "hello"]}


def test_252_tampered_contract_chain_broken_denies():
    broken = _tampered_task_contract(_valid_task_contract())
    decision = permissions.check_permission(
        "R1", {"contract": broken}, generated=False
    )
    assert decision.get("error") == permissions.ERR_CONTRACT_CHAIN_BROKEN
    verdict = guard.evaluate(["echo", "hello"], "R1", _belt_auth(broken))
    assert verdict["decision"] == "deny"
    with pytest.raises(PermissionError):
        guarded_dispatch(
            ["echo", "hello"], "R1", _belt_auth(broken),
            tool="echo", registry=_echo_registry(),
        )


def test_252_missing_contract_denies():
    decision = permissions.check_permission("R1", {}, generated=False)
    assert decision.get("error") == permissions.ERR_R1_CONTRACT_REQUIRED
    with pytest.raises(PermissionError):
        guarded_dispatch(
            ["echo", "hello"], "R1", {"subject": "worker"},
            tool="echo", registry=_echo_registry(),
        )


def test_252_forged_token_with_provider_key_refuses():
    record = actions.build_action_record(
        action_id="k06h1-a1",
        idempotency_key="k06h1-k1",
        authorization_ref="forged-bad-token",
        attempt=1,
        status="pending",
    )
    with pytest.raises(PermissionError):
        actions.verify_provider_or_prior_state(
            record=record,
            provider_key="k06h1-provider-key",
            prior_state=None,
        )
    with pytest.raises(PermissionError):
        actions.record_attempt(record=record, status="done")


def test_252_valid_authorization_ref_verifies_and_records():
    record = actions.build_action_record(
        action_id="k06h1-a1",
        idempotency_key="k06h1-k1",
        authorization_ref="k06h1-auth-token",
        attempt=1,
        status="pending",
    )
    assert actions.verify_provider_or_prior_state(
        record=record, provider_key="k06h1-provider-key", prior_state=None
    ) == {"ok": True}
    progressed = actions.record_attempt(record=record, status="done")
    assert progressed["attempt"] == 2
    assert progressed["status"] == "done"
    assert record["attempt"] == 1


# --- Row 20A-a: SecretRef handles, never raw secrets ---


def test_20a_facts_with_secret_typed_raw_refused():
    facts = {"rows": [], "env": {"API_KEY": RAW_SECRET}}
    result = si_validation.validate(facts, _import_contract())
    assert result["error_code"] == "E_SECRET_REFUSED"


def test_20a_secret_pointer_facts_still_accepted():
    ref = secrets.make_secret_ref(ref="k06h1-pointer")
    assert secrets.is_secret_ref(ref) is True
    pointed = {"rows": [], "env": {"API_KEY": {"secretRef": "k06h1-key"}}}
    assert si_validation.validate(pointed, _import_contract())["ok"] is True
    schemed = {"rows": [], "env": {"API_KEY": ref}}
    assert si_validation.validate(schemed, _import_contract())["ok"] is True


def test_20a_belt_auth_with_raw_secret_refused():
    auth = dict(_belt_auth("contract-1"))
    auth["api_key"] = RAW_SECRET
    with pytest.raises(PermissionError):
        guarded_dispatch(
            ["echo", "hello"], "R1", auth,
            tool="echo", registry=_echo_registry(),
        )


def test_20a_services_auth_with_raw_secret_refused_before_guard():
    seen = []

    def _recording_guard(argv, action_class, auth):
        seen.append((list(argv), action_class, dict(auth)))
        return {
            "decision": "allow",
            "reason": "probe",
            "evidence_ref": "probe-ref",
        }

    result = svc_commands.run_command(
        ["status"], "R0",
        {"user": "tester", "api_token": RAW_SECRET},
        guard_evaluate=_recording_guard,
    )
    assert result.get("error") == "E_BAD_AUTH"
    assert seen == []
    belted = svc_commands.run_declared_service_via_belt(
        ["status"], "R0",
        {"user": "tester", "api_token": RAW_SECRET},
        registry=_echo_registry(),
    )
    assert belted.get("error") == "E_BAD_AUTH"


def test_20a_secret_ref_values_travel_cleanly():
    ref = secrets.make_secret_ref(ref="k06h1-pointer")
    seen = []

    def _recording_guard(argv, action_class, auth):
        seen.append(dict(auth))
        return {
            "decision": "allow",
            "reason": "probe",
            "evidence_ref": "probe-ref",
        }

    result = svc_commands.run_command(
        ["status"], "R0",
        {"user": "tester", "api_token": ref},
        guard_evaluate=_recording_guard,
    )
    assert result["decision"] == "allow"
    assert len(seen) == 1


# --- Row 20A-b: zero raw-secret bytes in reports and records ---


def test_20b_merged_environment_redacts_secret_typed_raw():
    merged = port_merge.merge_project_environment(
        "k06h1-project",
        {"status": "KNOWN", "api_key": RAW_SECRET},
    )
    assert RAW_SECRET not in repr(merged)
    assert "SecretRef(redacted)" in repr(merged)


def test_20b_refusals_carry_no_raw_bytes():
    facts = {"rows": [], "env": {"API_KEY": RAW_SECRET}}
    refused = si_validation.validate(facts, _import_contract())
    assert refused["ok"] is False
    assert RAW_SECRET not in repr(refused)
    svc_refused = svc_commands.run_command(
        ["status"], "R0",
        {"user": "tester", "api_token": RAW_SECRET},
        guard_evaluate=lambda argv, action_class, auth: {
            "decision": "allow",
            "reason": "probe",
            "evidence_ref": "probe-ref",
        },
    )
    assert RAW_SECRET not in repr(svc_refused)


def test_20b_secret_ref_outputs_hold_no_raw_bytes():
    ref = secrets.make_secret_ref(ref="k06h1-pointer")
    assert RAW_SECRET not in repr(ref)
    assert secrets.is_secret_ref(RAW_SECRET) is False
    redacted = secrets.redact_value({"env": {"API_KEY": RAW_SECRET}})
    assert RAW_SECRET not in repr(redacted)
    result = guarded_dispatch(
        ["echo", "hello"], "R1",
        {
            "subject": "worker",
            "scopes": ["tools:exec"],
            "contract": "contract-1",
            "api_key": ref,
        },
        tool="echo",
        registry=_echo_registry(),
    )
    assert result["ok"] is True
    assert RAW_SECRET not in repr(result)


# --- K06REST CODER-1: chat seam served proofs (loopback TEST data only) ---
#
# Row map (lane task): 253/189/254 secretref via secretscan;
# R-313/R-315 chat adapter; R-365 chat stream guard. Every test below
# drives a served route (create_app + TestClient) or the real belt seam;
# every raw value is made inside the test, never a real credential.

K06REST_TOKEN = "k06rest-coder1-loopback-token"
K06REST_ACTOR = "tester-k06rest-coder1"

# Tests-only raw stand-ins. Never real credentials. K06REST_RAW keeps the
# documented scanner shape (contiguous key material, no separator inside).
K06REST_RAW = "sk-K06RESTTESTONLY12345678"
K06REST_RAW_TWO = "AKIAK06RESTTESTONLY1234"


def _k06rest_settings():
    return {"testing": True, "ui_session_token": K06REST_TOKEN}


def _k06rest_headers():
    return {"x-actor": K06REST_ACTOR, "x-ui-session-token": K06REST_TOKEN}


def _k06rest_client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from agent_si.backend.app import create_app

    monkeypatch.setenv(
        "AGENT_SI_SESSION_STORE", str(tmp_path / "k06rest-sessions"))
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    app = create_app(_k06rest_settings())
    return app, TestClient(app)


def test_k06rest_189_contract_texts_served_secretref_only(
        monkeypatch, tmp_path) -> None:
    """Row 189 via GET /api/v1/tools/script-contract: texts carry secretRef."""
    _, client = _k06rest_client(monkeypatch, tmp_path)
    resp = client.get("/api/v1/tools/script-contract")
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    joined = "\n".join(
        [payload["contract_text"], payload["template_text"],
         payload["instruction_text"]])
    assert "secretRef" in joined
    assert "AKIA" not in joined and "sk-live-" not in joined


def test_k06rest_253_acceptance_run_filed_and_listed(
        monkeypatch, tmp_path) -> None:
    """Row 253 via POST+GET /api/v1/tools/services/acceptance: run filed."""
    _, client = _k06rest_client(monkeypatch, tmp_path)
    resp = client.post(
        "/api/v1/tools/services/acceptance",
        json={
            "service": "status",
            "argv": ["status"],
            "action_class": "R0",
            "auth": {"subject": "worker", "task": "k06rest-task"},
        },
        headers=_k06rest_headers(),
    )
    assert resp.status_code == 200, resp.text
    run = resp.json()
    assert run["run_id"].startswith("acceptance-")
    assert run["ok"] is True
    assert run["evidence_refs"]
    listed = client.get("/api/v1/tools/services/acceptance")
    assert listed.status_code == 200, listed.text
    assert any(
        r["run_id"] == run["run_id"] for r in listed.json()["runs"])


def test_k06rest_253_raw_secret_auth_refused_and_unfiled(
        monkeypatch, tmp_path) -> None:
    """Row 253 secretref guard: raw auth refused (400), nothing filed."""
    _, client = _k06rest_client(monkeypatch, tmp_path)
    resp = client.post(
        "/api/v1/tools/services/acceptance",
        json={
            "service": "status",
            "argv": ["status"],
            "action_class": "R0",
            "auth": {"subject": "worker", "task": "k06rest-task",
                     "api_token": K06REST_RAW},
        },
        headers=_k06rest_headers(),
    )
    assert resp.status_code == 400, resp.text
    assert K06REST_RAW not in resp.text
    listed = client.get("/api/v1/tools/services/acceptance")
    assert listed.json()["runs"] == []


def test_k06rest_254_install_record_view_names_unknown(
        monkeypatch, tmp_path) -> None:
    """Row 254 via POST+GET /api/v1/tools/installs: view names unknown."""
    _, client = _k06rest_client(monkeypatch, tmp_path)
    resp = client.post(
        "/api/v1/tools/installs",
        json={
            "tool": "ruff",
            "version": "0.8.0",
            "status": "granted",
            "source": "install-ask",
            "verified": True,
        },
        headers=_k06rest_headers(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["tool"] == "ruff"
    view = client.get("/api/v1/tools/installs", params={"tool": "ruff"})
    assert view.status_code == 200, view.text
    assert view.json()["records"][0]["version"] == "0.8.0"
    unknown = client.get("/api/v1/tools/installs", params={"tool": "nope"})
    assert unknown.status_code == 200, unknown.text
    assert unknown.json()["records"] == []
    assert unknown.json()["unknown_tool"] == "nope"


def test_k06rest_secretref_scan_blocks_raw_served(
        monkeypatch, tmp_path) -> None:
    """Rows 253/189/254 via POST /api/v1/submission/scan: raw blocked."""
    from agent_si.backend import secretscan as k06rest_secretscan

    _, client = _k06rest_client(monkeypatch, tmp_path)
    blocked = client.post(
        "/api/v1/submission/scan",
        json={"files": [{"path": "a.txt",
                         "content": "key " + K06REST_RAW}]},
        headers=_k06rest_headers(),
    )
    assert blocked.status_code == 200, blocked.text
    body = blocked.json()
    assert body["ok"] is False
    assert body["findings"]
    assert body["findings"][0]["code"] == "SECRET_DETECTED"
    assert K06REST_RAW not in repr(body["findings"])
    clean = client.post(
        "/api/v1/submission/scan",
        json={"files": [{"path": "a.txt", "content": "nothing here"}]},
        headers=_k06rest_headers(),
    )
    assert clean.status_code == 200, clean.text
    assert clean.json() == {"ok": True, "findings": []}
    assert k06rest_secretscan.scan_files(
        [{"path": "a.txt", "content": "nothing here"}]) == []


def test_k06rest_r313_approval_card_roundtrip_and_restart(
        monkeypatch, tmp_path) -> None:
    """R-313 via POST /asks + approve + GET /sessions after restart."""
    from fastapi.testclient import TestClient

    from agent_si.backend.app import create_app

    _, client = _k06rest_client(monkeypatch, tmp_path)
    created = client.post(
        "/asks",
        json={
            "kind": "approval",
            "summary": "Approve the lane demo plan?",
            "options": [{"option_id": "yes", "label": "Yes"},
                        {"option_id": "no", "label": "No"}],
        },
        headers=_k06rest_headers(),
    )
    assert created.status_code == 200, created.text
    card = created.json()
    assert card["kind"] == "approval"
    assert [o["option_id"] for o in card["options"]] == ["yes", "no"]
    decided = client.post(
        "/asks/" + card["ask_id"] + "/approve",
        json={"option_id": "yes", "resume_token": card["resume_token"]},
        headers=_k06rest_headers(),
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["approved_option_id"] == "yes"
    forged = client.post(
        "/asks/" + card["ask_id"] + "/approve",
        json={"option_id": "yes",
              "resume_token": "resume-forged-k06rest-test-only"},
        headers=_k06rest_headers(),
    )
    assert forged.status_code in (401, 403)
    restarted = TestClient(create_app(_k06rest_settings()))
    sessions = restarted.get("/sessions")
    assert sessions.status_code == 200, sessions.text
    assert card["ask_id"] in [
        s["session_id"] for s in sessions.json()["sessions"]]


def test_k06rest_r313_secret_ref_card_never_echoes_value(
        monkeypatch, tmp_path) -> None:
    """R-313 secretref: approval payload carries refs, never values."""
    _, client = _k06rest_client(monkeypatch, tmp_path)
    created = client.post(
        "/asks",
        json={
            "kind": "approval",
            "summary": "Needs a secret?",
            "options": [{"option_id": "y", "label": "Y"}],
            "secret_ref": "ref-k06rest-only",
        },
        headers=_k06rest_headers(),
    )
    assert created.status_code == 200, created.text
    assert set(created.json().keys()) == {
        "ask_id", "kind", "summary", "options", "resume_token"}


def test_k06rest_r315_chat_tool_runs_via_belt_and_refuses_raw() -> None:
    """R-315 via chat_adapter.run_chat_tool through the real belt.

    Fail-closed refusal for raw-secret auth is the documented
    E_BAD_AUTH dict (services/commands.py refuses before the guard
    runs), never a success value and never a tool execution.
    """
    import agent_si.backend.chat_adapter as k06rest_chat_adapter
    from agent_si.worker_tools.registry import ToolRegistry

    calls: list = []

    class _K06RestStatusEntryPoint:
        name = "status"
        action_class = "R0"

        def load(self):
            def _impl(argv, action_class, auth):
                calls.append((list(argv), action_class, dict(auth)))
                return {"ok": True, "argv": list(argv),
                        "action_class": action_class, "pid": 4242,
                        "output": {"words": list(argv)}}

            return _impl

    registry = ToolRegistry()
    registry.register(_K06RestStatusEntryPoint())
    auth = {"subject": "worker", "task": "k06rest-task",
            "contract": "contract-k06rest"}
    via = k06rest_chat_adapter.run_chat_tool(
        ["status"], "R0", auth, registry=registry)
    assert via["ok"] is True
    assert isinstance(via["pid"], int) and via["pid"] > 0
    assert len(calls) == 1
    raw_auth = dict(auth)
    raw_auth["api_token"] = K06REST_RAW_TWO
    refused = k06rest_chat_adapter.run_chat_tool(
        ["status"], "R0", raw_auth, registry=registry)
    assert refused == {"error": "E_BAD_AUTH"}
    assert K06REST_RAW_TWO not in repr(refused)
    assert len(calls) == 1


def test_k06rest_r365_stream_guards_and_dispatch_refused() -> None:
    """R-365 via POST /api/v1/chat/stream guards plus dispatch guard."""
    import os as k06rest_os

    import pytest as k06rest_pytest

    from agent_si.backend.chat_stream import build_bridge
    from agent_si.backend.orchestration.graph import (
        AgentTask,
        DispatchRejected,
        SubtaskGraph,
    )
    from agent_si.providers.adapters.base import (
        AdapterConfig,
        make_secret_ref,
    )
    from agent_si.providers.adapters.mock_provider import (
        MockProviderAdapter,
    )

    k06rest_os.environ["AGENT_SI_SECRET_STORE"] = "memory"
    from fastapi.testclient import TestClient

    from agent_si.backend.app import create_app

    client = TestClient(create_app(_k06rest_settings()))
    assert client.post(
        "/api/v1/chat/stream", json={"message": "hi"}).status_code == 401
    assert client.post(
        "/api/v1/chat/stream", json={"message": "   "},
        headers=_k06rest_headers()).status_code == 400
    absent = client.post(
        "/api/v1/chat/stream", json={"message": "hi"},
        headers=_k06rest_headers())
    assert absent.status_code == 404
    assert absent.json()["detail"]["code"] == "MANAGER_STREAM_ABSENT"
    mock = MockProviderAdapter(
        AdapterConfig(
            provider_id="mock", instance_id="k06rest-365",
            model="mock-canned",
            secret_ref=make_secret_ref(
                secret_id="mock-secret", provider_id="mock")),
        transport=None, canned=("Mock reply one.",))
    bridge = build_bridge(provider_adapter=mock)
    from agent_si.backend.chat_stream import ChatStreamRequest

    request = ChatStreamRequest.from_body(
        {"message": "hello"}, K06REST_ACTOR)
    bare = AgentTask(
        agent_task_id="agent-task-1", subtask_id="", agent_id="agent-1",
        contract_hash="hash-1")
    with k06rest_pytest.raises(DispatchRejected):
        bridge.run(request, agent_task=bare, graph=SubtaskGraph())
    assert mock.turns_served == 0


def test_k06rest_r365_mock_stream_carries_refs_never_values(
        monkeypatch, tmp_path) -> None:
    """R-365 via POST /api/v1/chat/stream: refs in, never values out."""
    from agent_si.backend.orchestration import steplimits as k06rest_limits
    from agent_si.providers.adapters.base import (
        AdapterConfig,
        make_secret_ref,
    )
    from agent_si.providers.adapters.mock_provider import (
        MockProviderAdapter,
    )

    k06rest_limits._reset_state()
    try:
        k06rest_limits.apply_steplimit_config_change({
            "project_id": "proj-k06rest-365",
            "authority": "k06rest-coder1",
            "reason": "served stream proof",
            "task_max_steps": 10,
            "chat_max_steps": 10,
        })
        app, client = _k06rest_client(monkeypatch, tmp_path)
        app.state.chat_provider_adapter = MockProviderAdapter(
            AdapterConfig(
                provider_id="mock", instance_id="k06rest-365",
                model="mock-canned",
                secret_ref=make_secret_ref(
                    secret_id="mock-secret", provider_id="mock")),
            transport=None, canned=("Mock reply one.",))
        resp = client.post(
            "/api/v1/chat/stream",
            json={"project": "proj-k06rest-365", "task": "t-k06rest",
                  "message": "hello", "secret_refs": [K06REST_RAW]},
            headers=_k06rest_headers(),
        )
        assert resp.status_code == 200, resp.text
        assert "text/event-stream" in resp.headers.get("content-type", "")
        assert K06REST_RAW not in resp.text
        assert '"done"' in resp.text
    finally:
        k06rest_limits._reset_state()
