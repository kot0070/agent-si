"""STEP 2 entry: add script, additions only, shadow refusal (G6).

A user script whose name collides with a standard script name, or with an
already registered script, is refused so it can never shadow trusted
behavior. Error results never echo the submitted source back.
"""

from __future__ import annotations

from typing import Any

from .contract import AddScriptResult, ImportContract

_registered: dict = {}


def reset_registry() -> None:
    _registered.clear()


def is_shadow(script_name: str, standard_names: list[str]) -> bool:
    try:
        return script_name in standard_names
    except TypeError:
        return False


def _denied_power_code(contract: ImportContract) -> str:
    powers = contract.get("declared_powers")
    forbidden = contract.get("forbidden")
    if not isinstance(powers, list) or not isinstance(forbidden, list):
        return ""
    for power in powers:
        if not isinstance(power, dict):
            continue
        text = (str(power.get("name", "")) + " " + str(power.get("scope", ""))).lower()
        if "network" in text and "network-access" in forbidden:
            return "E_NETWORK_DENIED"
        if "secret" in text and "secret-keys" in forbidden:
            return "E_SECRET_REFUSED"
    return ""


def add_script(contract: ImportContract, source_text: str) -> AddScriptResult:
    if not isinstance(contract, dict):
        return {"ok": False, "script_id": "", "error_code": "E_SCHEMA_INVALID"}
    name = contract.get("name")
    digest = contract.get("contract_hash")
    if not isinstance(name, str) or not name:
        return {"ok": False, "script_id": "", "error_code": "E_SCHEMA_INVALID"}
    if not isinstance(digest, str) or not digest:
        return {"ok": False, "script_id": "", "error_code": "E_SCHEMA_INVALID"}
    standard_names = ("watch", "help", "list", "status")
    if name in standard_names or name in _registered:
        return {"ok": False, "script_id": "", "error_code": "E_SHADOW_REFUSED"}
    if isinstance(source_text, str) and "secret:" in source_text:
        return {"ok": False, "script_id": "", "error_code": "E_SECRET_REFUSED"}
    denial = _denied_power_code(contract)
    if denial:
        return {"ok": False, "script_id": "", "error_code": denial}
    _registered[name] = {"contract_hash": digest, "source_text": source_text}
    return {"ok": True, "script_id": name, "error_code": ""}
