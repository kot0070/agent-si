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
