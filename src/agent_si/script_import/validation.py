"""STEP 2 entry: schema plus static validation of facts (G6, SPEC 20/20A).

Untrusted data stays data: override phrasing is refused. Secret material
is refused unless it arrives as an opaque SecretRef pointer; a raw
string under a secret-typed field is refused even without a marker,
including raw smuggled inside a container under that field.
Error results never echo input payloads back.
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


_SECRET_KEY_HINTS: tuple[str, ...] = (
    "secret",
    "token",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "api-key",
    "credential",
    "private_key",
    "privatekey",
    "private-key",
)

_SECRET_REF_PREFIX = "secretref:"


def _is_opaque_handle(value: Any) -> bool:
    """True for SecretRef-scheme strings (G5 opaque handles)."""
    return (
        isinstance(value, str)
        and value.startswith(_SECRET_REF_PREFIX)
        and len(value) > len(_SECRET_REF_PREFIX)
    )


def _holds_nested_raw(value: Any) -> bool:
    """True when a container hides a raw string that is no opaque handle."""
    if _is_secret_pointer(value):
        return False
    if isinstance(value, str):
        return bool(value) and not _is_opaque_handle(value)
    if isinstance(value, dict):
        return any(_holds_nested_raw(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_holds_nested_raw(item) for item in value)
    return False


def _holds_bare_secret(value: Any) -> bool:
    if isinstance(value, str):
        return "secret:" in value
    if isinstance(value, dict):
        if _is_secret_pointer(value):
            return False
        for key, item in value.items():
            if (
                isinstance(key, str)
                and any(hint in key.lower() for hint in _SECRET_KEY_HINTS)
                and isinstance(item, str)
                and item
                and not _is_opaque_handle(item)
            ):
                return True
            if (
                isinstance(key, str)
                and any(hint in key.lower() for hint in _SECRET_KEY_HINTS)
                and isinstance(item, (dict, list, tuple))
                and _holds_nested_raw(item)
            ):
                return True
            if _holds_bare_secret(key) or _holds_bare_secret(item):
                return True
        return False
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
