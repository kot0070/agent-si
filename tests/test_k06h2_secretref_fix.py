"""K06H2 behaviour: remaining RED rows on top of the sealed K06H1 work.

Row 252: an R1/R2/R3 action runs only with a real TaskContract
authorization claim end to end; a non-contract scalar or sequence
claim (int, float, bool, bytes, list, tuple) breaks the chain and
must refuse with ERR_CONTRACT_CHAIN_BROKEN (guard -> belt -> record).
Row 20A-a: TaskContract/Manager/Agent paths carry SecretRef handles,
never raw secrets -- including raw smuggled inside a container under
a secret-typed key, and raw under hyphen-spelled secret keys.
Row 20A-b: logs, telemetry, reports and records hold zero raw-secret
bytes -- hyphen-spelled secret keys (api-key, private-key) redact
and detect exactly like their underscored twins.

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
from agent_si.script_import import validation as si_validation  # noqa: E402
from agent_si.services import commands as svc_commands  # noqa: E402
from agent_si.toolguard import guard, permissions, secrets  # noqa: E402
from agent_si.worker_tools import ToolRegistry, guarded_dispatch  # noqa: E402

# Tests-only raw stand-ins. Never real credentials.
RAW_SECRET = "K06H2-RAW-7d3b1f9a2c4e6a0b8d5f"
RAW_TWO = "K06H2-RAW-c41e08b6d5a29f3e7b10c"


def _import_contract():
    return {
        "name": "k06h2-demo",
        "version": "1",
        "contract_hash": "k06h2-hash",
        "declared_powers": [],
        "forbidden": ["secret-keys", "network-access"],
    }


def _valid_task_contract() -> domain_contracts.TaskContract:
    base = domain_contracts.TaskContract(
        schema_version="1",
        contract_version=1,
        contract_sequence=1,
        project_id="k06h2-project",
        task_id="k06h2-task",
        goal="Run the K06H2 tool-belt chain",
        workspace="project-workspace",
        permissions="R1",
    )
    digest = domain_contracts.compute_contract_hash(base)
    return dataclasses.replace(base, contract_hash=digest)


def _belt_auth(contract) -> dict:
    return {
        "subject": "worker",
        "scopes": ["tools:exec"],
        "contract": contract,
        "task": "k06h2-task",
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


# --- Row 252: non-contract claims break the authorization chain ---


def test_252_scalar_contract_claim_refused():
    claims = [12345, 3.14, True, ["c1"], ("c1",), b"c1"]
    for claim in claims:
        decision = permissions.check_permission(
            "R1", {"contract": claim}, generated=False
        )
        assert decision.get("error") == permissions.ERR_CONTRACT_CHAIN_BROKEN
    r2 = permissions.check_permission(
        "R2", {"contract": 12345, "director_record": "d1"}, generated=False
    )
    assert r2.get("error") == permissions.ERR_CONTRACT_CHAIN_BROKEN
    r3 = permissions.check_permission(
        "R3", {"contract": 12345, "user_record": "u1"}, generated=False
    )
    assert r3.get("error") == permissions.ERR_CONTRACT_CHAIN_BROKEN


def test_252_scalar_contract_denied_end_to_end():
    auth = _belt_auth(12345)
    verdict = guard.evaluate(["echo", "hello"], "R1", auth)
    assert verdict["decision"] == "deny"
    with pytest.raises(PermissionError):
        guarded_dispatch(
            ["echo", "hello"], "R1", auth,
            tool="echo", registry=_echo_registry(),
        )


# --- Row 20A-a: raw secrets smuggled in containers never propagate ---


def test_20a_nested_raw_facts_refused():
    nested = {"rows": [], "env": {"API_KEY": {"nested": RAW_SECRET}}}
    assert si_validation.validate(nested, _import_contract())["error_code"] == (
        "E_SECRET_REFUSED"
    )
    listed = {"rows": [], "env": {"API_KEY": [RAW_SECRET]}}
    assert si_validation.validate(listed, _import_contract())["error_code"] == (
        "E_SECRET_REFUSED"
    )
    deep = {"rows": [], "env": {"API_KEY": {"outer": {"inner": RAW_TWO}}}}
    assert si_validation.validate(deep, _import_contract())["error_code"] == (
        "E_SECRET_REFUSED"
    )


def test_20a_nested_raw_belt_refused():
    auth = dict(_belt_auth("contract-2"))
    auth["api_key"] = {"nested": RAW_SECRET}
    with pytest.raises(PermissionError):
        guarded_dispatch(
            ["echo", "hello"], "R1", auth,
            tool="echo", registry=_echo_registry(),
        )
    auth_list = dict(_belt_auth("contract-2"))
    auth_list["api_key"] = [RAW_SECRET]
    with pytest.raises(PermissionError):
        guarded_dispatch(
            ["echo", "hello"], "R1", auth_list,
            tool="echo", registry=_echo_registry(),
        )


def test_20a_nested_raw_services_refused_before_guard():
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
        {"user": "tester", "api_token": {"nested": RAW_SECRET}},
        guard_evaluate=_recording_guard,
    )
    assert result.get("error") == "E_BAD_AUTH"
    assert seen == []
    belted = svc_commands.run_declared_service_via_belt(
        ["status"], "R0",
        {"user": "tester", "api_token": [RAW_SECRET]},
        registry=_echo_registry(),
    )
    assert belted.get("error") == "E_BAD_AUTH"


def test_20a_hyphen_raw_refused_at_entries():
    hyphen = {"rows": [], "env": {"api-key": RAW_SECRET}}
    assert si_validation.validate(hyphen, _import_contract())["error_code"] == (
        "E_SECRET_REFUSED"
    )
    auth = dict(_belt_auth("contract-2"))
    auth["private-key"] = RAW_TWO
    with pytest.raises(PermissionError):
        guarded_dispatch(
            ["echo", "hello"], "R1", auth,
            tool="echo", registry=_echo_registry(),
        )
    seen = []

    def _recording_guard(argv, action_class, auth):
        seen.append(dict(auth))
        return {
            "decision": "allow",
            "reason": "probe",
            "evidence_ref": "probe-ref",
        }

    refused = svc_commands.run_command(
        ["status"], "R0",
        {"user": "tester", "x-api-key": RAW_TWO},
        guard_evaluate=_recording_guard,
    )
    assert refused.get("error") == "E_BAD_AUTH"
    assert seen == []


def test_20a_nested_handles_still_accepted():
    ref = secrets.make_secret_ref(ref="k06h2-pointer")
    assert secrets.is_secret_ref(ref) is True
    pointed = {"rows": [], "env": {"API_KEY": {"secretRef": "k06h2-key"}}}
    assert si_validation.validate(pointed, _import_contract())["ok"] is True
    listed_handle = {"rows": [], "env": {"API_KEY": [ref]}}
    assert si_validation.validate(listed_handle, _import_contract())["ok"] is True
    counted = {"rows": [], "env": {"token_count": 5}}
    assert si_validation.validate(counted, _import_contract())["ok"] is True
    empty = {"rows": [], "env": {"API_KEY": {}}}
    assert si_validation.validate(empty, _import_contract())["ok"] is True
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
    belted = guarded_dispatch(
        ["echo", "hello"], "R1",
        {**_belt_auth("contract-2"), "api_key": {"secretRef": "k06h2-key"}},
        tool="echo", registry=_echo_registry(),
    )
    assert belted["ok"] is True


# --- Row 20A-b: zero raw-secret bytes in reports and records ---


def test_20b_hyphen_keys_redacted():
    redacted = secrets.redact_value({"api-key": RAW_SECRET})
    assert RAW_SECRET not in repr(redacted)
    assert "SecretRef(redacted)" in repr(redacted)
    redacted_private = secrets.redact_value({"env": {"private-key": RAW_TWO}})
    assert RAW_TWO not in repr(redacted_private)
    assert "SecretRef(redacted)" in repr(redacted_private)


def test_20b_hyphen_detector_flags():
    hit = secrets.find_raw_secret({"env": {"api-key": RAW_SECRET}})
    assert hit is not None
    assert RAW_SECRET not in hit
    nested_hit = secrets.find_raw_secret({"env": {"API_KEY": {"nested": RAW_TWO}}})
    assert nested_hit is not None
    assert RAW_TWO not in nested_hit


def test_20b_hyphen_facts_refused_without_bytes():
    refused = si_validation.validate(
        {"rows": [], "env": {"api-key": RAW_SECRET}}, _import_contract()
    )
    assert refused["ok"] is False
    assert refused["error_code"] == "E_SECRET_REFUSED"
    assert RAW_SECRET not in repr(refused)


def test_20b_plain_keys_still_redacted():
    redacted = secrets.redact_value({"env": {"API_KEY": RAW_SECRET}})
    assert RAW_SECRET not in repr(redacted)
    assert "SecretRef(redacted)" in repr(redacted)
    assert secrets.find_raw_secret({"env": {"API_KEY": RAW_SECRET}}) is not None
