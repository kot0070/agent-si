"""K06 Lane A toolguard -- G5 SecretRef.

A SecretRef is an opaque string only: it carries a scheme prefix
plus a random token, and the raw secret value never appears in it,
in logs, in telemetry, in reports, in prompts or in artifacts.
The module keeps an internal-only registry of issued tokens (no
raw values); there is deliberately no lookup returning a secret.
"""

from __future__ import annotations

import os

SecretRef = str

_PREFIX = "secretref:"

_ISSUED: dict[str, bool] = {}


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
