"""D9 provider HTTP surface over the D10 facade (K04 lane A1 owned).

Five frozen routes plus the HD-approved DELTA-1 addition (lowercase
method strings, mirroring ``agent_si.backend.pools_routes``
conventions):

- GET /api/v1/providers (list; secret ids only, matrix-row shape)
- POST /api/v1/providers/connect (key-only connect: the preset fills
  id/type/base URL, the body supplies model plus key ref)
- POST /api/v1/providers/{id}/disconnect (clean removal incl. store entry)
- GET /api/v1/providers/{id}/models (model rows with checkbox state)
- GET /api/v1/chat/models (enabled models only)
- GET /api/v1/providers/leftover-keys (DELTA-1: own-namespace entries,
  names plus dates only; per-entry delete behind explicit confirm
  plus session token, audit-logged by entry name)

Handlers are pure ``(ctx, query, body) -> (status, payload)`` over a small
:class:`ProviderCtx` holding the D10 facade module (or a matching
object) plus an optional models port. Raw key material is refused
before anything else; ValueError maps to 4xx (unknown provider to 404,
missing store entry to 409, anything else to 400). Standard library
only at top level: no import of ``backend.pools_routes`` or of
``providers.adapters``. Wiring into the app host stays with the pools
routes owner (HANDOFF); :func:`mount` uses the same wrapper shape.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from . import facades as _default_facade
from .presets import get_preset
from .contracts import SECRET_REF_FIELDS
from .provider_api import (
    CONFIRM_REQUIRED,
    CREDENTIAL_ENTRY_MISSING,
    LIVE_LINKED,
    NOT_FOUND,
    NOT_OWN_PREFIX,
    TOKEN_REQUIRED,
    list_leftover_keys,
    request_delete_entry,
)


SECRET_KEY_HINTS = ("secret", "api_key", "apikey", "token", "password",
                    "passwd", "credential", "private_key")


class ProviderCtx:
    """Server-side context: the D10 facade plus the models port.

    ``facade`` is the D10 facade module (or any object with the same
    five functions); ``models`` maps provider ids to model entries,
    each either a model-id string or a ``{"model": ..., "kb": ...}``
    mapping (the KB row comes from the KB owner when supplied).

    DELTA-1 leftover ports (all optional; only the leftover-keys
    handler reads them): ``app_prefix`` is the app's own namespace
    (e.g. ``"app:"``); ``store_view`` is a read mapping of leftover
    entry name to a mapping carrying ``last_used_at``; ``store`` is
    the mutable leftover mapping deletes act on (defaults to
    ``store_view`` when it supports item deletion); ``audit_sink``
    receives ``append(record)`` on every successful delete;
    ``live_provider_ids`` names live-linked entries that are never
    deletable (defaults to the facade's provider ids, both bare and
    prefixed).
    """

    def __init__(self, facade: Any = None, models: Any = None,
                 app_prefix: Any = None, store_view: Any = None,
                 store: Any = None, audit_sink: Any = None,
                 live_provider_ids: Any = None) -> None:
        self.facade = facade if facade is not None else _default_facade
        self.models: Dict[str, list] = dict(models or {})
        self.app_prefix = app_prefix
        self.store_view = store_view
        self.store = store
        self.audit_sink = audit_sink
        self.live_provider_ids = live_provider_ids


def _is_id_only_ref(value: Any) -> bool:
    """True for id-only SecretRef handles (never raw key material)."""
    keys = set(value)
    return bool(keys) and keys <= set(SECRET_REF_FIELDS)


def _find_raw_secret(value: Any, path: str = "body") -> Optional[str]:
    if isinstance(value, Mapping):
        if _is_id_only_ref(value):
            return None
        for key, item in value.items():
            lowered = str(key).lower()
            if any(hint in lowered for hint in SECRET_KEY_HINTS):
                return "%s.%s" % (path, key)
            hit = _find_raw_secret(item, "%s.%s" % (path, key))
            if hit:
                return hit
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hit = _find_raw_secret(item, "%s[%d]" % (path, index))
            if hit:
                return hit
    return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _view_payload(view: Any) -> Dict[str, Any]:
    return {
        "provider_id": view.provider_id,
        "type": view.type,
        "base_url": view.base_url,
        "health": view.health,
        "evidenced": bool(view.evidenced),
    }


def _model_entries(raw: Any) -> List[Tuple[str, Any]]:
    entries: List[Tuple[str, Any]] = []
    for item in raw or []:
        if isinstance(item, Mapping):
            model = item.get("model")
            kb = item.get("kb")
        else:
            model, kb = item, None
        if isinstance(model, str) and model:
            entries.append((model, kb))
    return entries


def list_providers(ctx: ProviderCtx, query, body) -> Tuple[int, Dict]:
    """List provider matrix rows (ids and health only, never key material)."""
    only = _as_bool((query or {}).get("only_evidenced", False))
    try:
        views = ctx.facade.list_providers(only)
    except ValueError as exc:
        return 400, {"error": str(exc)}
    return 200, {"providers": [_view_payload(view) for view in views]}


def connect_provider(ctx: ProviderCtx, query, body) -> Tuple[int, Dict]:
    """Key-only connect: preset fills id/type/base URL, body gives model+ref."""
    body = body or {}
    hit = _find_raw_secret(body)
    if hit:
        return 400, {"error": "raw secret material refused at %s "
                              "(pass a SecretRef handle, never raw)" % hit}
    preset_id = body.get("preset_id")
    if not preset_id:
        return 400, {"error": "preset_id is required"}
    try:
        preset = get_preset(preset_id)
    except KeyError:
        return 400, {"error": "unknown preset %r" % (preset_id,)}
    model = body.get("model")
    if not isinstance(model, str) or not model:
        return 400, {"error": "model is required: presets never bake one in"}
    key_ref = body.get("key_ref")
    if key_ref is None:
        return 400, {"error": "key_ref is required"}
    descriptor = {
        "provider_id": preset["provider_id"],
        "type": preset["provider_type"],
        "base_url": preset["base_url"],
        "model": model,
    }
    try:
        view = ctx.facade.register_provider(descriptor, key_ref)
    except ValueError as exc:
        return 400, {"error": str(exc)}
    return 200, {"provider": view.describe()}


def disconnect_provider(ctx: ProviderCtx, query, body) -> Tuple[int, Dict]:
    """Disconnect cleanly, including the credential-store entry."""
    query = query or {}
    body = body or {}
    provider_id = query.get("id", body.get("provider_id"))
    if not provider_id:
        return 400, {"error": "provider id is required"}
    try:
        ctx.facade.remove_provider(provider_id)
    except ValueError as exc:
        message = str(exc)
        if "unknown provider" in message:
            return 404, {"error": message}
        if CREDENTIAL_ENTRY_MISSING in message:
            return 409, {"error": message}
        return 400, {"error": message}
    return 200, {"removed": True, "provider_id": provider_id}


def provider_models(ctx: ProviderCtx, query, body) -> Tuple[int, Dict]:
    """Model rows for one provider, with checkbox state and search filter."""
    query = query or {}
    provider_id = query.get("id")
    if not provider_id:
        return 400, {"error": "provider id is required"}
    try:
        view = ctx.facade.get_provider(provider_id)
    except ValueError as exc:
        return 400, {"error": str(exc)}
    if view is None:
        return 404, {"error": "unknown provider %r" % (provider_id,)}
    wanted = query.get("query")
    rows = []
    for model, kb in _model_entries(ctx.models.get(provider_id)):
        if wanted and wanted not in model:
            continue
        rows.append({
            "model": model,
            "enabled": bool(view.evidenced),
            "in_base": True,
            "kb": kb,
        })
    return 200, {"provider_id": provider_id, "models": rows}


def chat_models(ctx: ProviderCtx, query, body) -> Tuple[int, Dict]:
    """Enabled models only: evidenced providers' base-list models."""
    query = query or {}
    try:
        views = ctx.facade.list_providers(True)
    except ValueError as exc:
        return 400, {"error": str(exc)}
    rows = []
    for view in views:
        for model, _kb in _model_entries(ctx.models.get(view.provider_id)):
            rows.append({"provider_id": view.provider_id, "model": model})
    return 200, {"project_id": query.get("project_id", "p1"),
                 "models": rows}


def _first(value: Any, default: Any = None) -> Any:
    """Unwrap a singleton query list (hosts collapse them; be liberal)."""
    if isinstance(value, list):
        return value[0] if value else default
    return value


def _live_entry_names(ctx: ProviderCtx, app_prefix: str) -> Any:
    """Live-linked entry names a delete must never remove (M-P4-146)."""
    explicit = getattr(ctx, "live_provider_ids", None)
    if explicit is not None:
        return explicit
    live = set()
    try:
        views = ctx.facade.list_providers(False)
    except Exception:
        return live
    for view in views or []:
        provider_id = getattr(view, "provider_id", None)
        if isinstance(provider_id, str) and provider_id:
            live.add(provider_id)
            if app_prefix:
                live.add("%s%s" % (app_prefix, provider_id))
    return live


def leftover_keys(ctx: ProviderCtx, query, body) -> Tuple[int, Dict]:
    """DELTA-1 leftover-key surface: list own entries; guarded per-entry delete.

    Without a ``name`` param this is a read (no token needed): 200 with
    ``{"entries": [{"name": ..., "last_used_at": ...}]}`` holding only
    the app-namespace prefix entries, names plus dates only.

    With a ``name`` param this is a per-entry delete: explicit confirm
    (``confirmed``/``confirm`` boolean True) plus a session token
    (``session_token``/``token``) are enforced at this handler;
    token-less deletes are refused with 401 (ruling 5), live-linked
    entries are never deletable, and success is audit-logged by entry
    name. The session token travels as a handle only: it is never
    stored, never logged, and never echoed in any payload.
    """
    query = query or {}
    params = dict(query)
    if isinstance(body, Mapping):
        params.update(body)
    app_prefix = getattr(ctx, "app_prefix", None)
    if app_prefix is None:
        app_prefix = _first(params.get("app_prefix"))
    if not isinstance(app_prefix, str) or not app_prefix:
        return 400, {"error": "app_prefix is required: leftover keys "
                              "live under the app's own namespace"}
    if params.get("name") is None:
        store_view = getattr(ctx, "store_view", None)
        if store_view is None:
            store_view = getattr(ctx, "store", None)
        if store_view is None:
            store_view = {}
        try:
            return 200, list_leftover_keys(store_view, app_prefix)
        except ValueError as exc:
            return 400, {"error": str(exc)}
        except (TypeError, AttributeError) as exc:
            return 400, {"error": "bad leftover store view: %s" % (exc,)}
    name = _first(params.get("name"))
    if not isinstance(name, str) or not name:
        return 400, {"error": "entry name is required"}
    if _first(params.get("confirmed", params.get("confirm", False))) is not True:
        return 400, {"error": "explicit confirm is required per entry",
                     "code": CONFIRM_REQUIRED, "rule": "M-P4-147",
                     "entry": name}
    token = _first(params.get("session_token"))
    if token is None:
        token = _first(params.get("token"))
    if not isinstance(token, str) or not token:
        return 401, {"error": "session token is required for leftover "
                              "deletes (token-less writes refused)",
                     "code": TOKEN_REQUIRED, "rule": "M-P4-147",
                     "entry": name}
    store = getattr(ctx, "store", None)
    if store is None:
        candidate = getattr(ctx, "store_view", None)
        if candidate is not None and hasattr(candidate, "__delitem__"):
            store = candidate
    if store is None:
        return 500, {"error": "leftover store unbound: bind a mutable "
                              "store on ctx for deletes"}
    audit_sink = (getattr(ctx, "audit_sink", None)
                  or getattr(ctx, "audit", None)
                  or getattr(getattr(ctx, "facade", None), "_audit", None))
    if audit_sink is None:
        return 500, {"error": "audit sink unbound: deletes must be "
                              "audit-logged by entry name"}
    reason = _first(params.get("reason"), "user-confirmed-cleanup")
    if not isinstance(reason, str) or not reason:
        reason = "user-confirmed-cleanup"
    outcome = request_delete_entry(
        store, audit_sink, name=name, app_prefix=app_prefix,
        confirmed=True, session_token=token,
        live_provider_ids=_live_entry_names(ctx, app_prefix),
        reason=reason)
    if outcome.get("removed"):
        return 200, outcome
    reason_code = outcome.get("reason")
    message = {
        NOT_OWN_PREFIX: "entry is outside the app namespace",
        NOT_FOUND: "no such leftover entry",
        LIVE_LINKED: "live-linked entries are never deletable",
        CONFIRM_REQUIRED: "explicit confirm is required per entry",
        TOKEN_REQUIRED: "session token is required for leftover deletes",
    }.get(reason_code, "leftover delete refused")
    status = {
        NOT_OWN_PREFIX: 403,
        NOT_FOUND: 404,
        LIVE_LINKED: 409,
        CONFIRM_REQUIRED: 400,
        TOKEN_REQUIRED: 401,
    }.get(reason_code, 400)
    payload = dict(outcome)
    payload["error"] = "%s: %s" % (message, name)
    payload["code"] = reason_code
    return status, payload


ROUTES: Tuple[Tuple[str, str, str, Callable], ...] = (
    ("get", "/api/v1/providers", "list_providers", list_providers),
    ("post", "/api/v1/providers/connect", "connect_provider",
     connect_provider),
    ("post", "/api/v1/providers/{id}/disconnect", "disconnect_provider",
     disconnect_provider),
    ("get", "/api/v1/providers/{id}/models", "provider_models",
     provider_models),
    ("get", "/api/v1/chat/models", "chat_models", chat_models),
    ("get", "/api/v1/providers/leftover-keys", "leftover_keys",
     leftover_keys),
)

_DISPATCH = {(method, path): fn for method, path, _name, fn in ROUTES}


def match(method: str, path: str) -> Tuple[Any, Dict[str, str]]:
    """Match a request to a handler, filling ``{id}`` template params.

    Exact entries match first; ``{id}`` segments match exactly one path
    part. Returns ``(handler, params)`` or ``(None, {})``.
    """
    key = (str(method).lower(), path)
    if key in _DISPATCH:
        return _DISPATCH[key], {}
    for (route_method, route_path), fn in _DISPATCH.items():
        if route_method != key[0]:
            continue
        want = route_path.split("/")
        got = path.split("/")
        if len(want) != len(got):
            continue
        params: Dict[str, str] = {}
        ok = True
        for w, g in zip(want, got):
            if w == "{id}":
                if not g:
                    ok = False
                    break
                params["id"] = g
            elif w != g:
                ok = False
                break
        if ok:
            return fn, params
    return None, {}


def mount(app, ctx: ProviderCtx):
    """Register every provider route on a `.get`/`.post` host.

    The host calls handlers as ``handler(query, body)`` where query is a
    string-keyed mapping and body is the parsed JSON object (or None).
    Returns the app for chaining.
    """
    for method, path, _name, fn in ROUTES:
        registrar = getattr(app, method)

        def wrapper(query=None, body=None, _fn=fn):
            return _fn(ctx, query or {}, body)

        registrar(path)(wrapper)
    return app


__all__ = [
    "ProviderCtx",
    "ROUTES",
    "list_providers",
    "connect_provider",
    "disconnect_provider",
    "provider_models",
    "chat_models",
    "leftover_keys",
    "match",
    "mount",
]
