"""Leftover-key served access: per-entry confirm plus session token.

Adapters-side seam for M-P4-147 (explicit confirm per entry and behind
session token, kit BUILD_PLAN row 1438): transport-level adaptation
only. The refusal rules themselves live in
``agent_si.providers.registry.provider_api`` (``CONFIRM_REQUIRED`` /
``TOKEN_REQUIRED`` under rule ``M-P4-147``) and are never restated
here; this module only shapes served input so the registry decision
sees it: string confirms from served query strings are coerced with
the lane's own truth table, and the per-entry session token travels
in the served params (query/body ``session_token``, ``token`` alias).

The token is read from the served params ONLY, never from the
server-side context handle: the app write guard already
authenticates the caller from the ``x-ui-session-token`` header (it
binds ``ctx.session_token`` on every write), so consulting the
context here would make TOKEN_REQUIRED unreachable over HTTP. The
header session authenticates the caller; the per-entry params token
authorizes the delete. Neither is logged, echoed, or stored here.

Standard library only: no machine paths, no secrets, no vendor or
model defaults.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: Served truth table for an explicit per-entry confirm. Mirrors the
#: lane's own query-boolean reading
#: (``provider_routes._as_bool``): the strings a served query string
#: can carry for True. Anything else is left for the registry, which
#: refuses non-True confirms with CONFIRM_REQUIRED.
TRUTHY_CONFIRM_STRINGS = frozenset({"1", "true", "yes", "on"})

#: Confirm keys the served surface accepts, most explicit first. The
#: registry handler reads ``confirmed`` first with ``confirm`` as the
#: alias; the same order applies here so coercion never reorders the
#: decision.
CONFIRM_KEYS = ("confirmed", "confirm")


def served_true(value: Any) -> bool:
    """Lane truth reading for served string flags (never a rule)."""
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY_CONFIRM_STRINGS
    return bool(value)


def coerce_entry_confirm(params: Mapping[str, Any]) -> dict:
    """Copy ``params`` with string confirms coerced to booleans.

    Only string values under :data:`CONFIRM_KEYS` are rewritten (via
    :func:`served_true`); every other value passes through untouched
    so the registry still decides non-True confirms itself.
    """
    merged = dict(params)
    for key in CONFIRM_KEYS:
        if key in merged and isinstance(merged[key], str):
            merged[key] = served_true(merged[key])
    return merged


def bind_served_params(query: Any, body: Any) -> dict:
    """Merge served query plus body, then coerce the per-entry confirm.

    Mirrors the lane handler's own query-plus-body merge (query first,
    body overriding) and coerces string confirms; the per-entry
    session token stays exactly where the caller put it (query/body
    ``session_token``, ``token`` alias) so the lane handler decides
    TOKEN_REQUIRED itself. Returns a fresh dict; inputs are never
    mutated.
    """
    merged: dict = dict(query or {})
    if isinstance(body, Mapping):
        merged.update(body)
    return coerce_entry_confirm(merged)
