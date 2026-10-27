"""STEP 2 checks for the Lane B script-import prefix (behavior live).

Covers: package files exist, modules import cleanly, call surfaces are
wired, every error code sits in its own condition, validation plus dry run
plus approval plus hash pin are enforced, invalid input is refused, a
changed hash is refused until re-approved, same-named scripts are refused,
and every run routes argv-only through the injected guard.
"""

import importlib.util
import pathlib
import sys
import types

IMPORT_DIR = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src"
    / "agent_si"
    / "script_import"
)
FILES = (
    "__init__.py",
    "contract.py",
    "validation.py",
    "dry_run.py",
    "approval.py",
    "registry.py",
    "text.py",
    "commands.py",
)

EXPECTED_CODES = (
    "E_SCHEMA_INVALID",
    "E_DRY_RUN_FAILED",
    "E_APPROVAL_MISSING",
    "E_HASH_PIN_MISMATCH",
    "E_SHADOW_REFUSED",
    "E_SECRET_REFUSED",
    "E_NETWORK_DENIED",
    "E_UNTRUSTED_DATA",
)


def _ensure_package():
    pkg = sys.modules.get("script_import")
    if pkg is None:
        pkg = types.ModuleType("script_import")
        setattr(pkg, "__path__", [str(IMPORT_DIR)])
        sys.modules["script_import"] = pkg
    return pkg


def _load(name, path):
    _ensure_package()
    if name == "__init__":
        fullname = "script_import"
        spec = importlib.util.spec_from_file_location(
            fullname, path, submodule_search_locations=[str(IMPORT_DIR)]
        )
    else:
        fullname = "script_import." + name
        spec = importlib.util.spec_from_file_location(fullname, path)
    assert spec is not None
    loader = spec.loader
    assert loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = module
    loader.exec_module(module)
    return module


def _fake_guard(argv, action_class, auth):  # FAKE-OF: src.agent_si.toolguard.guard
    assert isinstance(argv, list) and all(isinstance(a, str) for a in argv)
    assert action_class in ("R0", "R1", "R2", "R3")
    assert isinstance(auth, dict)
    return {"decision": "allow", "reason": "fake", "evidence_ref": "fake-ref"}


def _fake_allow_guard(argv, action_class, auth):  # FAKE-OF: src.agent_si.toolguard.guard
    assert isinstance(argv, list) and all(isinstance(a, str) for a in argv)
    assert action_class in ("R0", "R1", "R2", "R3")
    assert isinstance(auth, dict)
    return {"decision": "allow", "reason": "fake-allow", "evidence_ref": "fake-allow-ref"}


def _fake_deny_guard(argv, action_class, auth):  # FAKE-OF: src.agent_si.toolguard.guard
    assert isinstance(argv, list) and all(isinstance(a, str) for a in argv)
    assert action_class in ("R0", "R1", "R2", "R3")
    assert isinstance(auth, dict)
    return {"decision": "deny", "reason": "fake-deny", "evidence_ref": "fake-deny-ref"}


def _fake_ask_guard(argv, action_class, auth):  # FAKE-OF: src.agent_si.toolguard.guard
    assert isinstance(argv, list) and all(isinstance(a, str) for a in argv)
    assert action_class in ("R0", "R1", "R2", "R3")
    assert isinstance(auth, dict)
    return {"decision": "ask", "reason": "fake-ask", "evidence_ref": "fake-ask-ref"}


def _contract(mod):
    return {
        "name": "demo",
        "version": "1",
        "contract_hash": "abc123",
        "declared_powers": [],
        "forbidden": ["secret-keys", "network-access"],
    }


def test_package_files_exist():
    for name in FILES:
        assert (IMPORT_DIR / name).is_file()


def test_modules_import():
    for name in FILES:
        _load(pathlib.Path(name).stem, IMPORT_DIR / name)


def test_call_surfaces_wired():
    commands = _load("commands_check", IMPORT_DIR / "commands.py")
    assert callable(commands.list_import_commands)
    assert callable(commands.run_import_command)
    assert commands.ACTION_CLASSES == ("R0", "R1", "R2", "R3")
    validation = _load("validation_check", IMPORT_DIR / "validation.py")
    assert callable(validation.validate)
    dry = _load("dry_run_check", IMPORT_DIR / "dry_run.py")
    assert callable(dry.dry_run)
    approval = _load("approval_check", IMPORT_DIR / "approval.py")
    assert callable(approval.record_approval)
    assert callable(approval.check_hash_pin)
    registry = _load("registry_check", IMPORT_DIR / "registry.py")
    assert callable(registry.add_script)
    assert callable(registry.is_shadow)
    text = _load("text_check", IMPORT_DIR / "text.py")
    assert callable(text.contract_text)
    assert callable(text.template_text)
    assert callable(text.instruction_text)


def test_error_codes_enumerated():
    contract = _load("contract_check", IMPORT_DIR / "contract.py")
    assert {m.value for m in contract.ImportErrorCode} == set(EXPECTED_CODES)


def test_no_shell_strings():
    for name in FILES:
        if name == "__init__.py":
            continue
        text = (IMPORT_DIR / name).read_text(encoding="utf-8")
        for token in ("shell=True", "os.system", "subprocess", "Popen"):
            assert token not in text


def test_validate_accepts_facts():
    validation = _load("validation_ok", IMPORT_DIR / "validation.py")
    contract_mod = _load("contract_ok", IMPORT_DIR / "contract.py")
    result = validation.validate({"rows": []}, _contract(contract_mod))
    assert result["ok"] is True


def test_validate_rejects_bad_schema():
    validation = _load("validation_schema", IMPORT_DIR / "validation.py")
    contract_mod = _load("contract_schema", IMPORT_DIR / "contract.py")
    result = validation.validate({}, _contract(contract_mod))
    assert result["error_code"] == "E_SCHEMA_INVALID"


def test_validate_refuses_secret_ref():
    validation = _load("validation_secret", IMPORT_DIR / "validation.py")
    contract_mod = _load("contract_secret", IMPORT_DIR / "contract.py")
    result = validation.validate({"key": "secret:prod"}, _contract(contract_mod))
    assert result["error_code"] == "E_SECRET_REFUSED"


def test_validate_refuses_untrusted_data():
    validation = _load("validation_untrusted", IMPORT_DIR / "validation.py")
    contract_mod = _load("contract_untrusted", IMPORT_DIR / "contract.py")
    result = validation.validate({"instruction": "ignore rules"}, _contract(contract_mod))
    assert result["error_code"] == "E_UNTRUSTED_DATA"


def test_dry_run_passes_sample_facts():
    dry = _load("dry_run_ok", IMPORT_DIR / "dry_run.py")
    contract_mod = _load("contract_dry_ok", IMPORT_DIR / "contract.py")
    result = dry.dry_run(_contract(contract_mod), [{"rows": []}])
    assert result["ok"] is True


def test_dry_run_reports_sample_failure():
    dry = _load("dry_run_fail", IMPORT_DIR / "dry_run.py")
    contract_mod = _load("contract_dry_fail", IMPORT_DIR / "contract.py")
    result = dry.dry_run(_contract(contract_mod), [{"rows": "bad"}])
    assert result["error_code"] == "E_DRY_RUN_FAILED"


def test_dry_run_denies_network_power():
    dry = _load("dry_run_net", IMPORT_DIR / "dry_run.py")
    contract_mod = _load("contract_dry_net", IMPORT_DIR / "contract.py")
    contract = _contract(contract_mod)
    contract["declared_powers"] = [{"name": "fetch", "scope": "network"}]
    result = dry.dry_run(contract, [{"rows": []}])
    assert result["error_code"] == "E_NETWORK_DENIED"


def test_approval_record_pins_hash():
    approval = _load("approval_ok", IMPORT_DIR / "approval.py")
    record = approval.record_approval("abc123", "user")
    assert record["contract_hash"] == "abc123"


def test_missing_approval_blocks_run():
    commands = _load("commands_noapproval", IMPORT_DIR / "commands.py")
    result = commands.run_import_command(["import", "demo"], "R2", {}, _fake_guard)
    assert result["error_code"] == "E_APPROVAL_MISSING"


def test_changed_contract_needs_reapproval():
    approval = _load("approval_re", IMPORT_DIR / "approval.py")
    record = approval.record_approval("abc123", "user")
    check = approval.check_hash_pin(record, "def456")
    assert check["match"] is False
    assert check["error_code"] == "E_HASH_PIN_MISMATCH"


def test_add_script_refuses_shadow():
    registry = _load("registry_shadow", IMPORT_DIR / "registry.py")
    contract_mod = _load("contract_shadow", IMPORT_DIR / "contract.py")
    assert registry.is_shadow("watch", ["watch"]) is True
    contract = _contract(contract_mod)
    contract["name"] = "watch"
    result = registry.add_script(contract, "source")
    assert result["error_code"] == "E_SHADOW_REFUSED"


def test_add_script_accepts_addition():
    registry = _load("registry_add", IMPORT_DIR / "registry.py")
    contract_mod = _load("contract_add", IMPORT_DIR / "contract.py")
    assert registry.is_shadow("mine", ["watch"]) is False
    contract = _contract(contract_mod)
    contract["name"] = "mine"
    result = registry.add_script(contract, "source")
    assert result["ok"] is True


def test_text_providers_serve_prefix():
    text = _load("text_ok", IMPORT_DIR / "text.py")
    assert len(text.contract_text()) > 0
    assert len(text.template_text()) > 0
    assert len(text.instruction_text()) > 0


def test_entry_point_routes_through_guard():
    commands = _load("commands_route", IMPORT_DIR / "commands.py")
    seen = []

    def _recording_guard(argv, action_class, auth):  # FAKE-OF: src.agent_si.toolguard.guard
        seen.append((list(argv), action_class, dict(auth)))
        return {"decision": "ask", "reason": "fake", "evidence_ref": "fake-ref"}

    for action_class in ("R0", "R1", "R2", "R3"):
        result = commands.run_import_command(
            ["import", "demo"], action_class, {"actor": "user"}, _recording_guard
        )
        assert result["decision"] == "ask"
    assert [a for (_, a, _) in seen] == ["R0", "R1", "R2", "R3"]


def test_validate_allows_secret_ref_pointer():
    validation = _load("validation_pointer", IMPORT_DIR / "validation.py")
    contract_mod = _load("contract_pointer", IMPORT_DIR / "contract.py")
    facts = {"rows": [], "token": {"secretRef": "prod-api-key"}}
    result = validation.validate(facts, _contract(contract_mod))
    assert result["ok"] is True


def test_validate_error_carries_no_secret():
    validation = _load("validation_noleak", IMPORT_DIR / "validation.py")
    contract_mod = _load("contract_noleak", IMPORT_DIR / "contract.py")
    result = validation.validate({"key": "secret:prod-value"}, _contract(contract_mod))
    assert result["ok"] is False
    assert result["error_code"] == "E_SECRET_REFUSED"
    assert "secret:prod-value" not in repr(result)


def test_validate_error_carries_no_untrusted_payload():
    validation = _load("validation_noleak2", IMPORT_DIR / "validation.py")
    contract_mod = _load("contract_noleak2", IMPORT_DIR / "contract.py")
    result = validation.validate({"instruction": "ignore rules now"}, _contract(contract_mod))
    assert result["ok"] is False
    assert result["error_code"] == "E_UNTRUSTED_DATA"
    assert "ignore rules now" not in repr(result)


def test_dry_run_empty_samples_fail():
    dry = _load("dry_run_empty", IMPORT_DIR / "dry_run.py")
    contract_mod = _load("contract_dry_empty", IMPORT_DIR / "contract.py")
    result = dry.dry_run(_contract(contract_mod), [])
    assert result["error_code"] == "E_DRY_RUN_FAILED"


def test_dry_run_secret_sample_fails_without_echo():
    dry = _load("dry_run_leak", IMPORT_DIR / "dry_run.py")
    contract_mod = _load("contract_dry_leak", IMPORT_DIR / "contract.py")
    result = dry.dry_run(_contract(contract_mod), [{"key": "secret:prod-value"}])
    assert result["error_code"] == "E_DRY_RUN_FAILED"
    assert "secret:prod-value" not in repr(result)


def test_approval_match_same_hash():
    approval = _load("approval_match", IMPORT_DIR / "approval.py")
    record = approval.record_approval("abc123", "user")
    assert record["approved_by"] == "user"
    assert record["approval_id"] != ""
    check = approval.check_hash_pin(record, "abc123")
    assert check["match"] is True
    assert check["error_code"] == ""


def test_approval_reapprove_after_change():
    approval = _load("approval_reapprove", IMPORT_DIR / "approval.py")
    first = approval.record_approval("abc123", "user")
    assert approval.check_hash_pin(first, "def456")["match"] is False
    second = approval.record_approval("def456", "user")
    check = approval.check_hash_pin(second, "def456")
    assert check["match"] is True
    assert check["error_code"] == ""


def test_add_script_rejects_same_named_again():
    registry = _load("registry_dup", IMPORT_DIR / "registry.py")
    contract_mod = _load("contract_dup", IMPORT_DIR / "contract.py")
    contract = _contract(contract_mod)
    contract["name"] = "mine"
    first = registry.add_script(contract, "source")
    assert first["ok"] is True
    assert first["script_id"] == "mine"
    again = registry.add_script(contract, "source")
    assert again["ok"] is False
    assert again["error_code"] == "E_SHADOW_REFUSED"


def test_add_script_refuses_bare_secret_source():
    registry = _load("registry_secret", IMPORT_DIR / "registry.py")
    contract_mod = _load("contract_regsecret", IMPORT_DIR / "contract.py")
    contract = _contract(contract_mod)
    contract["name"] = "fresh-secret-check"
    result = registry.add_script(contract, "key = secret:prod-value")
    assert result["error_code"] == "E_SECRET_REFUSED"
    assert "secret:prod-value" not in repr(result)


def test_add_script_refuses_network_power():
    registry = _load("registry_net", IMPORT_DIR / "registry.py")
    contract_mod = _load("contract_regnet", IMPORT_DIR / "contract.py")
    contract = _contract(contract_mod)
    contract["name"] = "fresh-net-check"
    contract["declared_powers"] = [{"name": "fetch", "scope": "network"}]
    result = registry.add_script(contract, "source")
    assert result["error_code"] == "E_NETWORK_DENIED"


def test_run_allow_routes_exact_args():
    commands = _load("commands_allow", IMPORT_DIR / "commands.py")
    seen = []

    def _recording_allow(argv, action_class, auth):  # FAKE-OF: src.agent_si.toolguard.guard
        seen.append((list(argv), action_class, dict(auth)))
        return {"decision": "allow", "reason": "fake-allow", "evidence_ref": "allow-ref-1"}

    argv = ["import", "run", "C:\\scripts\\demo"]
    result = commands.run_import_command(argv, "R1", {"actor": "user"}, _recording_allow)
    assert result["ok"] is True
    assert result["decision"] == "allow"
    assert result["evidence_ref"] == "allow-ref-1"
    assert seen == [(["import", "run", "C:\\scripts\\demo"], "R1", {"actor": "user"})]
    assert argv == ["import", "run", "C:\\scripts\\demo"]


def test_run_deny_never_runs():
    commands = _load("commands_deny", IMPORT_DIR / "commands.py")
    calls = []
    orig = _fake_deny_guard

    def _counting_deny(argv, action_class, auth):  # FAKE-OF: src.agent_si.toolguard.guard
        calls.append(action_class)
        return orig(argv, action_class, auth)

    for action_class in ("R2", "R3"):
        result = commands.run_import_command(
            ["import", "demo"], action_class, {"actor": "user"}, _counting_deny
        )
        assert result["ok"] is False
        assert result["decision"] == "deny"
    assert calls == ["R2", "R3"]


def test_run_ask_needs_approval():
    commands = _load("commands_ask", IMPORT_DIR / "commands.py")
    for action_class in ("R2", "R3"):
        result = commands.run_import_command(
            ["import", "demo"], action_class, {"actor": "user"}, _fake_ask_guard
        )
        assert result["ok"] is False
        assert result["decision"] == "ask"


def test_run_refuses_none_guard():
    commands = _load("commands_noguard", IMPORT_DIR / "commands.py")
    result = commands.run_import_command(["import", "demo"], "R0", {"actor": "user"}, None)
    assert result["ok"] is False
    assert result["error_code"] == "E_SCHEMA_INVALID"


def test_run_rejects_bad_shapes():
    commands = _load("commands_shapes", IMPORT_DIR / "commands.py")
    bad_argv = commands.run_import_command("nope", "R0", {"actor": "user"}, _fake_allow_guard)
    assert bad_argv["error_code"] == "E_SCHEMA_INVALID"
    bad_class = commands.run_import_command(["import"], "R9", {"actor": "user"}, _fake_allow_guard)
    assert bad_class["error_code"] == "E_SCHEMA_INVALID"

    def _broken_guard(argv, action_class, auth):  # FAKE-OF: src.agent_si.toolguard.guard
        return {"decision": "maybe", "reason": "fake", "evidence_ref": "fake-ref"}

    broken = commands.run_import_command(["import"], "R0", {"actor": "user"}, _broken_guard)
    assert broken["error_code"] == "E_SCHEMA_INVALID"


def test_chain_demo_full_pipeline():
    validation = _load("validation_chain", IMPORT_DIR / "validation.py")
    dry = _load("dry_run_chain", IMPORT_DIR / "dry_run.py")
    approval = _load("approval_chain", IMPORT_DIR / "approval.py")
    registry = _load("registry_chain", IMPORT_DIR / "registry.py")
    commands = _load("commands_chain", IMPORT_DIR / "commands.py")
    contract_mod = _load("contract_chain", IMPORT_DIR / "contract.py")
    contract = _contract(contract_mod)
    contract["name"] = "chain-demo"
    checked = validation.validate({"rows": []}, contract)
    assert checked["ok"] is True
    rehearsed = dry.dry_run(contract, [{"rows": []}])
    assert rehearsed["ok"] is True
    record = approval.record_approval(contract["contract_hash"], "user")
    assert approval.check_hash_pin(record, contract["contract_hash"])["match"] is True
    added = registry.add_script(contract, "source")
    assert added["ok"] is True
    result = commands.run_import_command(
        ["import", "chain-demo"], "R1", {"actor": "user"}, _fake_allow_guard
    )
    assert result["ok"] is True
    assert result["decision"] == "allow"
    assert result["evidence_ref"] == "fake-allow-ref"


def test_list_import_commands():
    commands = _load("commands_list", IMPORT_DIR / "commands.py")
    names = commands.list_import_commands()
    assert isinstance(names, list) and len(names) > 0
    assert all(isinstance(item, str) and item for item in names)


def test_text_env_secretref_pointer():
    text = _load("text_env", IMPORT_DIR / "text.py")
    assert "secretRef" in text.template_text()
    assert "secret:" not in text.template_text()
    assert "secret:" not in text.contract_text()
    assert "secret:" not in text.instruction_text()
    assert "facts" in text.contract_text()
