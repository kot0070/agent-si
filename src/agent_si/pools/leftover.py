"""Leftover-key served finder: list own entries, guarded per-entry delete.

Pools-side seam for M-P4-144 through M-P4-148 (kit BUILD_PLAN rows
1435-1439): the served ``GET /api/v1/providers/leftover-keys`` route
bound to the served context. Every rule, code and status lives in
``agent_si.providers.registry.provider_api`` (``LEFTOVER_RULES`` plus
``list_leftover_keys`` / ``request_delete_entry``) and in the lane's
``provider_routes.leftover_keys`` handler; this module only binds the
served ports and delegates:

- finder (M-P4-144): the served credential store is bound as the
  read view, so the list shows product-prefixed entries; the DELETE
  row is registered here too, so user-click deletes reach the lane;
- names plus dates only (M-P4-145): the lane handler projects each
  entry to ``{"name", "last_used_at"}``; other entries are untouched;
- live-linked protection (M-P4-146): the live set is left unbound so
  the lane derives it from the provider side, read-only;
- confirm plus token (M-P4-147): served string confirms are coerced
  and the per-entry session token stays in the served params via
  :mod:`agent_si.adapters.leftover_access` (params only, never the
  header-bound context handle, so TOKEN_REQUIRED stays reachable;
  never logged, never echoed);
- audit (M-P4-148): the served audit sink is bound, so success is
  logged by entry name through the registry call.

The session token travels as a handle only. Standard library plus
in-repo ports only: no machine paths, no secrets, no vendor or model
defaults.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Tuple

from agent_si.adapters import leftover_access as _access
from agent_si.providers.registry import provider_routes as _routes

#: Served leftover-keys route this seam binds.
LEFTOVER_ROUTE = "/api/v1/providers/leftover-keys"
LEFTOVER_KEY = ("get", LEFTOVER_ROUTE)

#: Served per-entry delete on the same route (user-click delete,
#: M-P4-144): the legacy served tables carry one row per method, so
#: the delete binds its own key to the same handler.
LEFTOVER_DELETE_KEY = ("delete", LEFTOVER_ROUTE)

#: Rule ids this seam serves, from the registry's verbatim map (never
#: restated here so the wording cannot drift).
RULE_IDS = ("M-P4-144", "M-P4-145", "M-P4-146", "M-P4-147", "M-P4-148")


def rule_ids() -> Tuple[str, ...]:
    """Rule ids served here, cross-checked against the registry map."""
    from agent_si.providers.registry.provider_api import LEFTOVER_RULES

    missing = [rule for rule in RULE_IDS if rule not in LEFTOVER_RULES]
    if missing:
        raise ValueError(
            "leftover seam rule ids missing from registry: %s"
            % sorted(missing)
        )
    return RULE_IDS


def _credential_store(ctx: Any) -> Any:
    """Served credential store behind the leftover namespace."""
    for attr in ("store_view", "credential_store"):
        store = getattr(ctx, attr, None)
        if store is not None:
            return store
    return None


def _mutable_store(ctx: Any) -> Any:
    """Mutable served store deletes act on."""
    for attr in ("store", "store_view", "credential_store"):
        store = getattr(ctx, attr, None)
        if store is not None and hasattr(store, "__delitem__"):
            return store
    store = getattr(ctx, "store", None)
    if store is None:
        store = getattr(ctx, "credential_store", None)
    return store


def _audit_sink(ctx: Any) -> Any:
    """Served audit sink deletes are logged to, by entry name."""
    for attr in ("audit_sink", "audit"):
        sink = getattr(ctx, attr, None)
        if sink is not None:
            return sink
    facade = getattr(ctx, "provider_facade", None)
    return getattr(facade, "_audit", None)


def leftover_keys_served(ctx: Any, query: Any, body: Any) -> Tuple[int, Dict]:
    """Serve the leftover row over the served pools routing context.

    Binds the served credential store and audit sink, leaves the live
    set for the provider side, then delegates the whole call to the
    lane handler (rules, codes and statuses stay there verbatim).
    The per-entry session token is NOT taken from the context: the
    app write guard already authenticates the caller from the header,
    so the delete authorizes from the served params only.
    """
    params = _access.bind_served_params(query, body)
    facade = getattr(ctx, "provider_facade", None)
    pctx = _routes.ProviderCtx(
        facade=facade,
        # The leftover handler never reads the models port.
        models={},
        app_prefix=getattr(ctx, "app_prefix", None),
        store_view=_credential_store(ctx),
        store=_mutable_store(ctx),
        audit_sink=_audit_sink(ctx),
        live_provider_ids=getattr(ctx, "live_provider_ids", None),
    )
    return _routes.leftover_keys(pctx, params, None)


def _served_tables() -> Any:
    """Backend served tables, imported late to keep import order safe."""
    from agent_si.backend import pools_routes as _pools_routes

    return _pools_routes


def mount_leftover_served() -> Callable:
    """Bind the served leftover rows to this seam's handler (idempotent).

    Dispatch entries are assigned on the existing table objects and
    the legacy rows carry this handler, so both import orders and
    repeated imports serve the bound finder: GET lists own-prefix
    entries (M-P4-144/145) and DELETE removes one entry per explicit
    confirm plus session token (M-P4-144/146/147/148). The frozen
    ROUTES table object is never touched: that table holds the lane's
    frozen rows only. Returns the bound handler.
    """
    tables = _served_tables()
    base = getattr(tables, "_DISPATCH_BASE", None)
    if base is not None:
        base[LEFTOVER_KEY] = leftover_keys_served
        base[LEFTOVER_DELETE_KEY] = leftover_keys_served
    dispatch = getattr(tables, "_DISPATCH", None)
    if dispatch is not None:
        dispatch[LEFTOVER_KEY] = leftover_keys_served
        dispatch[LEFTOVER_DELETE_KEY] = leftover_keys_served
    legacy = getattr(tables, "_LEGACY_ROUTES", None)
    if legacy is not None:
        rows = list(legacy)
        have = set()
        for index, row in enumerate(rows):
            try:
                method, path = row[0], row[1]
            except (IndexError, TypeError):
                continue
            if str(path) != LEFTOVER_ROUTE:
                continue
            lowered = str(method).lower()
            if lowered == "get":
                rows[index] = ("get", LEFTOVER_ROUTE, "leftover_keys",
                               leftover_keys_served)
                have.add("get")
            elif lowered == "delete":
                rows[index] = ("delete", LEFTOVER_ROUTE,
                               "leftover_keys_delete",
                               leftover_keys_served)
                have.add("delete")
        if "get" not in have:
            rows.append(("get", LEFTOVER_ROUTE, "leftover_keys",
                         leftover_keys_served))
        if "delete" not in have:
            rows.append(("delete", LEFTOVER_ROUTE, "leftover_keys_delete",
                         leftover_keys_served))
        tables._LEGACY_ROUTES = tuple(rows)
    return leftover_keys_served


mount_leftover_served()

__all__ = [
    "LEFTOVER_DELETE_KEY",
    "LEFTOVER_KEY",
    "LEFTOVER_ROUTE",
    "RULE_IDS",
    "leftover_keys_served",
    "mount_leftover_served",
    "rule_ids",
]
