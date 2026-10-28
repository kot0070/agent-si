"""STEP 2 entry: schema plus static validation of facts (G6, SPEC 20/20A).

Untrusted data stays data: override phrasing is refused. Secret material
is refused unless it arrives as an opaque SecretRef pointer. Error results
never echo input payloads back.
"""

from __future__ import annotations

from typing import Any

from .contract import ImportContract, ValidationResult


def _is_secret_pointer(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value.keys()) == {"secretRef"}
        and isinstance(value["secretRef"], str)
        and len(value["secretRef"]) > 0
    )


def _holds_bare_secret(value: Any) -> bool:
    if isinstance(value, str):
        return "secret:" in value
    if isinstance(value, dict):
        if _is_secret_pointer(value):
            return False
        return any(
            _holds_bare_secret(key) or _holds_bare_secret(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_holds_bare_secret(item) for item in value)
    return False


def _holds_untrusted(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        markers = (
            "ignore rules",
            "ignore previous",
            "ignore instruction",
            "ignore all",
            "disregard",
            "bypass rules",
            "bypass",
        )
        return any(marker in lowered for marker in markers)
    if isinstance(value, dict):
        if _is_secret_pointer(value):
            return False
        return any(
            _holds_untrusted(key) or _holds_untrusted(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_holds_untrusted(item) for item in value)
    return False


def _schema_ok(facts: Any, contract: Any) -> bool:
    if not isinstance(facts, dict):
        return False
    if "rows" not in facts or not isinstance(facts["rows"], list):
        return False
    if not isinstance(contract, dict):
        return False
    for key in ("name", "version", "contract_hash", "declared_powers", "forbidden"):
        if key not in contract:
            return False
    if not isinstance(contract["declared_powers"], list):
        return False
    if not isinstance(contract["forbidden"], list):
        return False
    return True


def validate(facts: dict[str, Any], contract: ImportContract) -> ValidationResult:
    if _holds_bare_secret(facts):
        return {"ok": False, "error_code": "E_SECRET_REFUSED"}
    if _holds_untrusted(facts):
        return {"ok": False, "error_code": "E_UNTRUSTED_DATA"}
    if not _schema_ok(facts, contract):
        return {"ok": False, "error_code": "E_SCHEMA_INVALID"}
    return {"ok": True, "error_code": ""}
