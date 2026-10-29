"""K06 Lane A toolguard -- G5 SecretRef.

A SecretRef is an opaque string only: it carries a scheme prefix
plus a random token, and the raw secret value never appears in it,
in logs, in telemetry, in reports, in prompts or in artifacts.
The module keeps an internal-only registry of issued tokens (no
raw values); there is deliberately no lookup returning a secret.
Pointer checks plus key-hint redaction keep raw material out of
logs, telemetry, reports and records.
"""

from __future__ import annotations

import os
from typing import Any

SecretRef = str

_PREFIX = "secretref:"

_ISSUED: dict[str, bool] = {}

REDACTED_SECRET_MARKER: str = "SecretRef(redacted)"

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


def make_secret_ref(
    ref: str,
) -> SecretRef:
    """Mint an opaque reference for ``ref`` without keeping ``ref``.

    The returned string holds only the scheme prefix and fresh
    random material, so the raw value is absent from it. Only the
    random token is registered internally, never the raw value.
    """
    if not isinstance(ref, str) or not ref:
        raise ValueError("a non-empty secret reference is required")
    token = os.urandom(16).hex()
    while token in _ISSUED:
        token = os.urandom(16).hex()
    _ISSUED[token] = True
    return SecretRef(_PREFIX + token)


def is_secret_ref(
    value: object,
) -> bool:
    """True only for strings in the SecretRef scheme."""
    return (
        isinstance(value, str)
        and value.startswith(_PREFIX)
        and len(value) > len(_PREFIX)
    )


def is_secret_pointer(
    value: object,
) -> bool:
    """True for opaque handles: SecretRef strings or pointer mappings.

    A pointer mapping carries exactly one ``secretRef`` key with a
    non-empty string handle. Anything else, including a raw string
    under a secret-typed key, is not an opaque handle.
    """
    if is_secret_ref(value):
        return True
    return (
        isinstance(value, dict)
        and set(value.keys()) == {"secretRef"}
        and isinstance(value["secretRef"], str)
        and len(value["secretRef"]) > 0
    )


def _holds_nested_raw(
    value: Any,
) -> bool:
    """True when a container hides a raw string that is no opaque handle.

    Pointer mappings and SecretRef-scheme strings are opaque handles,
    never raw material; any other non-empty string smuggled inside a
    container under a secret-typed key is raw secret material.
    """
    if is_secret_pointer(value):
        return False
    if isinstance(value, str):
        return bool(value) and not is_secret_ref(value)
    if isinstance(value, dict):
        return any(_holds_nested_raw(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_holds_nested_raw(item) for item in value)
    return False


def find_raw_secret(
    value: Any,
    path: str = "value",
) -> str | None:
    """Return the location of raw secret material, or None when clean.

    Secret-typed keys (secret, token, password, credential, api key
    and kin, hyphen-spelled twins included) must hold opaque handles,
    never raw strings -- directly or nested inside a container. The
    walk recurses through mappings and sequences; the first offending
    location is reported as a dotted path.
    """
    if isinstance(value, dict):
        if is_secret_pointer(value):
            return None
        for key, item in value.items():
            if (
                isinstance(key, str)
                and any(hint in key.lower() for hint in _SECRET_KEY_HINTS)
                and isinstance(item, str)
                and item
                and not is_secret_ref(item)
            ):
                return f"{path}.{key}"
            if (
                isinstance(key, str)
                and any(hint in key.lower() for hint in _SECRET_KEY_HINTS)
                and isinstance(item, (dict, list, tuple))
                and _holds_nested_raw(item)
            ):
                return f"{path}.{key}"
            if isinstance(item, (dict, list, tuple)):
                hit = find_raw_secret(item, f"{path}.{key}")
                if hit is not None:
                    return hit
        return None
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            hit = find_raw_secret(item, f"{path}[{index}]")
            if hit is not None:
                return hit
        return None
    return None


def redact_value(
    value: Any,
) -> Any:
    """Redact secret-typed values to opaque markers, keeping shape.

    Secret-typed keys resolve to ``SecretRef(redacted)``; mappings
    and sequences keep their structure with redaction applied
    recursively. Opaque handles pass through untouched.
    """
    if isinstance(value, dict):
        if is_secret_pointer(value):
            return value
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            if is_secret_pointer(item):
                redacted[key] = item
            elif isinstance(key, str) and any(
                hint in key.lower() for hint in _SECRET_KEY_HINTS
            ):
                redacted[key] = REDACTED_SECRET_MARKER
            else:
                redacted[key] = redact_value(item)
        return redacted
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    return value
