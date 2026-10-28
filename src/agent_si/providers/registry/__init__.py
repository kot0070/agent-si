"""Provider registry package: registration plus lookup plus health views.

Merges the DELTA-1 leftover-keys row into the served tables
idempotently on import (B2 budget precedent; DELTA-1-row-only; safe
under either import order — the merge never rebinds or replaces the
served ROUTES table object, it only extends the served tables).
"""

from .contracts import (
    FRESH_BLOCKED_REASON,
    SECRET_REF_FIELDS,
    STATUS_BLOCKED,
    STATUS_READY,
    TRANSPORT_LITELLM_BACKED,
    TRANSPORT_LOCAL,
    TRANSPORT_OPENAI_COMPATIBLE,
    TRANSPORT_TYPES,
    ProviderContract,
    SecretRef,
    TransportDescriptor,
    coerce_secret_ref,
    make_secret_ref,
    reject_inline_key_material,
)
from .health import (
    MEASURED,
    NOT_MEASURED,
    MODEL_STATUSES,
    PROVIDER_STATUSES,
    ModelHealth,
    ModelHealthLog,
    ProviderHealth,
    ProviderHealthLog,
)
from .presets import META_CATALOGUE, PRESET_KEYS, PRESETS, build_config, get_preset
from . import provider_routes as _provider_routes_module
from .provider_routes import ROUTES as _provider_routes
from .registry import ProviderRegistry
from agent_si.backend import pools_routes as _pools_routes
from .usage import (
    METRIC_MEASURED,
    METRIC_UNAVAILABLE,
    UNPERMITTED,
    USAGE_METRICS,
    USAGE_STATES,
    LocalProbeNotPermitted,
    UsageSupport,
    UsageSupportLog,
)

__all__ = [
    "FRESH_BLOCKED_REASON",
    "SECRET_REF_FIELDS",
    "STATUS_BLOCKED",
    "STATUS_READY",
    "TRANSPORT_LITELLM_BACKED",
    "TRANSPORT_LOCAL",
    "TRANSPORT_OPENAI_COMPATIBLE",
    "TRANSPORT_TYPES",
    "ProviderContract",
    "SecretRef",
    "TransportDescriptor",
    "coerce_secret_ref",
    "make_secret_ref",
    "reject_inline_key_material",
    "MEASURED",
    "NOT_MEASURED",
    "MODEL_STATUSES",
    "PROVIDER_STATUSES",
    "ModelHealth",
    "ModelHealthLog",
    "ProviderHealth",
    "ProviderHealthLog",
    "META_CATALOGUE",
    "PRESET_KEYS",
    "PRESETS",
    "build_config",
    "get_preset",
    "ProviderRegistry",
    "METRIC_MEASURED",
    "METRIC_UNAVAILABLE",
    "UNPERMITTED",
    "USAGE_METRICS",
    "USAGE_STATES",
    "LocalProbeNotPermitted",
    "UsageSupport",
    "UsageSupportLog",
]


#: Served-table keys this package merges on import. DELTA-1 only: the
#: five frozen provider rows keep their existing owners and hosts.
_LEFTOVER_ROUTE_KEYS = frozenset({("get", "/api/v1/providers/leftover-keys")})


def _leftover_served(ctx, query, body):
    """Serve the leftover row over a bare lane context (pre-merge mirror).

    Same shape as the pools owner's served adapter for this endpoint;
    the leftover handler never reads the models port, so a bare
    ProviderCtx behaves exactly like the owner's adapted one (reads
    fall back to the query app_prefix; unbound stores stay unbound).
    Used only while the owner's merge has not run yet (its helper is
    unavailable); the post-merge path reuses the owner's helper.
    """
    pctx = _provider_routes_module.ProviderCtx()
    return _provider_routes_module.leftover_keys(pctx, query or {}, body)


def _extend_served_dispatch(fn) -> None:
    """Add the leftover row to the served dispatch tables (extend only).

    Never rebinds or replaces any served table object: dict entries
    only, setdefault so an existing entry always wins.
    """
    key = ("get", "/api/v1/providers/leftover-keys")
    base = getattr(_pools_routes, "_DISPATCH_BASE", None)
    if base is not None:
        base.setdefault(key, fn)
    dispatch = getattr(_pools_routes, "_DISPATCH", None)
    if dispatch is not None:
        dispatch.setdefault(key, fn)


def _mount_leftover_route() -> None:
    """Merge the DELTA-1 leftover-keys row into the served tables (idempotent).

    B2 budget precedent. Only the DELTA-1 row is eligible (it must be
    present in the lane's own table and missing from the served one),
    so repeated imports and either import order stay safe. The
    owner's served ROUTES table object is never rebound or replaced
    once the owner's merge has run: the row is then extended into the
    served dispatch/legacy tables only. While the owner's merge has
    not run yet (this package imported first inside the owner's own
    import), the row is staged in ROUTES content so the owner's
    imminent merge carries it to the served tables itself (the owner
    re-derives ROUTES from its frozen set at that point). Either way
    both import orders serve the frozen rows plus the leftover row.
    """
    key = ("get", "/api/v1/providers/leftover-keys")
    have = {(str(method).lower(), str(path))
            for method, path, _name, _fn in _pools_routes.ROUTES}
    if key in have:
        _extend_served_dispatch(_leftover_served)
        return
    eligible = [row for row in _provider_routes
                if (str(row[0]).lower(), str(row[1])) in _LEFTOVER_ROUTE_KEYS
                and (str(row[0]).lower(), str(row[1])) not in have]
    if not eligible:
        return
    if getattr(_pools_routes, "_D9_MERGED", False):
        adapter = getattr(_pools_routes, "_provider_served", None)
        if adapter is not None:
            fn = adapter("leftover_keys",
                         _provider_routes_module.leftover_keys, write=False)
        else:
            fn = _leftover_served
        _extend_served_dispatch(fn)
        legacy = getattr(_pools_routes, "_LEGACY_ROUTES", None)
        if legacy is not None and key not in {
                (str(m).lower(), str(p)) for m, p, _, _ in legacy}:
            _pools_routes._LEGACY_ROUTES = tuple(legacy) + (
                ("get", "/api/v1/providers/leftover-keys",
                 "leftover_keys", fn),)
        return
    _pools_routes.ROUTES = tuple(_pools_routes.ROUTES) + (
        ("get", "/api/v1/providers/leftover-keys",
         "leftover_keys", _leftover_served),)


_mount_leftover_route()
