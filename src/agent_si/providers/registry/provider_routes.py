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
from . import provider_model_lists as _model_lists
from .contracts import SECRET_REF_FIELDS, TRANSPORT_LOCAL
from .presets import get_preset
from .provider_api import (
    CONFIRM_REQUIRED,
    CREDENTIAL_ENTRY_MISSING,
    LIVE_LINKED,
    NOT_FOUND,
    NOT_OWN_PREFIX,
    PROVIDER_CONFLICT_CODE,
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
                 live_provider_ids: Any = None,
                 credential_store: Any = None,
                 model_state_dir: Any = None, http_get: Any = None,
                 kb_rows: Any = None,
                 local_models: Any = None) -> None:
        self.facade = facade if facade is not None else _default_facade
        self.models: Dict[str, list] = dict(models or {})
        self.app_prefix = app_prefix
        self.store_view = store_view
        self.store = store
        self.audit_sink = audit_sink
        self.live_provider_ids = live_provider_ids
        self.local_models = local_models
        # FXPROVBE ports (all optional; unbound keeps the legacy read):
        # credential_store resolves the stored key at refresh time,
        # model_state_dir persists merged lists + ticks beside
        # provider_connections.json, http_get is the FAKE network seam,
        # kb_rows carries catalog rows with price fields for the merge,
        # local_models maps a local provider id to its attached
        # runtime's real model names (None when nothing attached).
        self.credential_store = credential_store
        self.model_state_dir = model_state_dir
        self.http_get = http_get
        self.kb_rows = kb_rows


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


def _view_payload(view: Any, error: Any = None) -> Dict[str, Any]:
    # K04BIND1: error only when a verbatim failure reason exists (keeps
    # the D9 exact-set shape for the healthy path).
    payload = {
        "provider_id": view.provider_id,
        "type": view.type,
        "base_url": view.base_url,
        "health": view.health,
        "evidenced": bool(view.evidenced),
    }
    if error is not None and isinstance(error, str) and error:
        payload["error"] = error
    return payload


def _facade_error(facade: Any, provider_id: str) -> Any:
    # K04BIND1: read the verbatim failure reason without touching secrets.
    try:
        getter = getattr(facade, "get_provider_error", None)
        if callable(getter):
            return getter(provider_id)
    except Exception:
        pass
    return None


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


def _secret_value_gone(ctx: ProviderCtx, view: Any) -> bool:
    """True when the view's key value is provably gone (FXSTORE).

    The providers list is the card truth: a connected provider whose
    value is gone (sibling window disconnected, memory-isolated
    restart without a re-save) is dropped so the card shows Connect,
    not Disconnect. Reads resolve one value through ``get_secret``
    first (KeyError or an empty value means gone); any other read
    failure means the store is unreadable, so the row stays (fail
    open: the chat path says the store cannot be read). No store on
    the ctx, or a view without a secret id (local runtimes), keeps the
    legacy row. Values never travel: only presence is probed.
    """
    try:
        store = getattr(ctx, "credential_store", None)
    except Exception:
        return False
    if store is None:
        return False
    try:
        secret_id = getattr(getattr(view, "secret_ref", None),
                            "secret_id", "")
    except Exception:
        return False
    if not isinstance(secret_id, str) or not secret_id:
        return False
    probe = getattr(store, "get_secret", None)
    if callable(probe):
        try:
            value = probe(secret_id)
        except KeyError:
            return True
        except Exception:
            return False
        if isinstance(value, Mapping):
            try:
                value = value.get("value")
            except Exception:
                return False
        return not (isinstance(value, str) and value)
    checker = getattr(store, "has", None)
    if callable(checker):
        try:
            return not checker(secret_id)
        except Exception:
            return False
    return False


def list_providers(ctx: ProviderCtx, query, body) -> Tuple[int, Dict]:
    """List provider matrix rows (ids and health only, never key material)."""
    only = _as_bool((query or {}).get("only_evidenced", False))
    try:
        views = ctx.facade.list_providers(only)
    except ValueError as exc:
        return 400, {"error": str(exc)}
    # K04BIND1: surface the verbatim evidence-failure reason (no secret).
    # FXSTORE: drop rows whose key value is provably gone (the card
    # shows Connect, not Disconnect); unreadable stores keep the row.
    rows = []
    for view in views:
        if _secret_value_gone(ctx, view):
            continue
        rows.append(_view_payload(
            view, _facade_error(ctx.facade, view.provider_id)))
    return 200, {"providers": rows}


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
        message = str(exc)
        if message.startswith(PROVIDER_CONFLICT_CODE + ":"):
            return 400, {"code": PROVIDER_CONFLICT_CODE,
                         "message": message.split(":", 1)[1].strip()}
        return 400, {"error": message}
    _refresh_best_effort(ctx, preset["provider_id"], view, model)
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
    _model_lists.drop_state(
        getattr(ctx, "model_state_dir", None), provider_id)
    return 200, {"removed": True, "provider_id": provider_id}


def _kb_rows_for(ctx: ProviderCtx, provider_id: str) -> list:
    """Catalog rows with price fields for one provider, best effort."""
    rows = getattr(ctx, "kb_rows", None)
    if isinstance(rows, list) and rows:
        return [r for r in rows
                if isinstance(r, Mapping)
                and str(r.get("provider_id", "") or "") == provider_id]
    out = []
    for model, kb in _model_entries(ctx.models.get(provider_id)):
        fields: Any = None
        if isinstance(kb, Mapping):
            fields = kb.get("fields")
        out.append({"provider_id": provider_id,
                    "model_id": model,
                    "fields": fields if isinstance(fields, Mapping) else {}})
    return out


def _merged_for(ctx: ProviderCtx, provider_id: str) -> Tuple[list, Any, Any]:
    """Merged display rows plus stored state and KB rows for one provider."""
    kb_rows = _kb_rows_for(ctx, provider_id)
    state = _model_lists.load_state(
        getattr(ctx, "model_state_dir", None), provider_id)
    if state is not None and isinstance(state.get("models"), list):
        return ([dict(m) for m in state["models"]
                 if isinstance(m, Mapping)], state, kb_rows)
    return (_model_lists.merge_model_rows(provider_id, [], kb_rows),
            None, kb_rows)


def _preset_transport(provider_id: str) -> Any:
    try:
        return get_preset(provider_id).get("transport")
    except KeyError:
        return None


def _is_local_provider(provider_id: str, view: Any = None) -> bool:
    """Local runtimes keep their existing list: never a cloud fetch."""
    if _preset_transport(provider_id) == TRANSPORT_LOCAL:
        return True
    base = ""
    try:
        base = getattr(view, "base_url", "") or ""
    except Exception:
        base = ""
    return isinstance(base, str) and base.startswith("http://localhost")


#: Provider ids served off the attached local runtime (never a cloud
#: fetch): the real names come from the runtime itself, never a
#: placeholder. any-openai-compatible rides the same loopback rule.
LOCAL_PROVIDER_IDS = ("ollama", "lm-studio", "any-openai-compatible")


def _local_runtime_names(ctx: ProviderCtx, provider_id: str) -> Any:
    """Real model names for a local provider id, or None when unserved.

    None means the local lane serves nothing for this id right now
    (no reader port or no attached runtime): callers keep the legacy
    404. A list (possibly empty) means the runtime answered, so the
    routes answer too, never a placeholder.
    """
    reader = getattr(ctx, "local_models", None)
    if not callable(reader):
        return None
    try:
        names = reader(provider_id)
    except Exception:
        return None
    if names is None:
        return None
    out = []
    for name in names:
        text = str(name or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _local_rows(ctx: ProviderCtx, provider_id: str,
                names: list) -> Tuple[list, list, list]:
    """Merged display rows plus tick list and KB rows for local names."""
    kb_rows = _kb_rows_for(ctx, provider_id)
    try:
        state_enabled = _model_lists.load_enabled(
            getattr(ctx, "model_state_dir", None), provider_id)
    except Exception:
        state_enabled = None
    enabled = [str(i) for i in state_enabled
               if isinstance(i, str) and i] \
        if isinstance(state_enabled, list) else []
    ticked = {_model_lists.canonical_model_id(provider_id, i)
              for i in enabled}
    rows = []
    for name in names:
        ident = _model_lists.canonical_model_id(provider_id, name)
        hit = _model_lists.resolve_kb_row(kb_rows, provider_id, ident)
        kb_known = isinstance(hit, Mapping)
        fields = None
        if kb_known and isinstance(hit.get("fields"), Mapping):
            fields = dict(hit.get("fields"))
        rows.append({
            "model": name,
            "enabled": ident in ticked,
            "in_base": kb_known,
            "kb": fields,
            "id": ident,
            "name": name,
            "wire_id": _model_lists.wire_model_id(ident),
            "price": None,
            "kb_known": kb_known,
            "listed": True,
        })
    return rows, enabled, kb_rows


def _refresh_best_effort(ctx: ProviderCtx, provider_id: str,
                         view: Any, default_model: Any) -> None:
    """Refresh after a good connect; failure never breaks the connect."""
    if getattr(ctx, "model_state_dir", None) is None:
        return
    if _is_local_provider(provider_id, view):
        return
    try:
        secret_id = getattr(getattr(view, "secret_ref", None),
                            "secret_id", "")
        key_value = _model_lists.read_secret_value(
            getattr(ctx, "credential_store", None), secret_id)
        try:
            base_url = getattr(view, "base_url", "")
        except Exception:
            base_url = ""
        _model_lists.refresh_with_join(
            provider_id, base_url, key_value,
            _kb_rows_for(ctx, provider_id),
            transport=_preset_transport(provider_id),
            http_get=getattr(ctx, "http_get", None),
            store_dir=getattr(ctx, "model_state_dir", None),
            default_model=default_model)
    except Exception:
        pass


def provider_models(ctx: ProviderCtx, query, body) -> Tuple[int, Dict]:
    """Model rows for one provider: merged live + KB list with ticks.

    ``{provider_id, models: [{id, name, price, kb_known, ...}],
    source, enabled}``. Legacy row keys stay (``model`` is the id,
    ``enabled`` is ticked, ``in_base`` is kb_known, ``kb`` the fields).
    GET never performs network I/O: it reads the last stored list, or
    the catalog rows when nothing was ever stored. Local provider ids
    (LOCAL_PROVIDER_IDS) the facade never registered answer off the
    attached runtime's real names instead (a loopback read, possibly
    zero rows), never a placeholder.
    """
    query = query or {}
    provider_id = query.get("id")
    if not provider_id:
        return 400, {"error": "provider id is required"}
    try:
        view = ctx.facade.get_provider(provider_id)
    except ValueError as exc:
        return 400, {"error": str(exc)}
    if view is None:
        # R2 local branch: a local provider id the facade never
        # registered still answers off the attached runtime's real
        # names (possibly zero rows), never a placeholder and never a
        # cloud fetch. Nothing attached means the legacy 404.
        if provider_id in LOCAL_PROVIDER_IDS:
            names = _local_runtime_names(ctx, provider_id)
            if names is not None:
                rows, enabled, _kb_rows = _local_rows(
                    ctx, provider_id, names)
                return 200, {"provider_id": provider_id,
                             "models": rows, "source": "local",
                             "enabled": enabled}
        return 404, {"error": "unknown provider %r" % (provider_id,)}
    merged, state, _kb_rows = _merged_for(ctx, provider_id)
    verbatim: Dict[str, str] = {}
    for row in _kb_rows:
        if isinstance(row, Mapping):
            mid = row.get("model_id", "")
            if isinstance(mid, str) and mid:
                verbatim.setdefault(
                    _model_lists.canonical_model_id(provider_id, mid), mid)
    for model, _kb in _model_entries(ctx.models.get(provider_id)):
        verbatim.setdefault(
            _model_lists.canonical_model_id(provider_id, model), model)
    if state is not None and isinstance(state.get("enabled"), list):
        enabled = [str(i) for i in state["enabled"]
                   if isinstance(i, str) and i]
        source = str(state.get("source", "provider") or "provider")
    else:
        enabled = []
        source = "catalog"
    wanted = query.get("query")
    rows = []
    for item in merged:
        ident = str(item.get("id", "") or "")
        if wanted and wanted not in ident:
            continue
        ticked = ident in enabled
        fields = None
        if item.get("kb_known"):
            hit = _model_lists.resolve_kb_row(_kb_rows, provider_id, ident)
            if isinstance(hit, Mapping) and isinstance(
                    hit.get("fields"), Mapping):
                fields = dict(hit["fields"])
        rows.append({
            "model": verbatim.get(ident, ident),
            "enabled": ticked,
            "in_base": bool(item.get("kb_known", False)),
            "kb": fields,
            "id": ident,
            "name": str(item.get("name", "") or ""),
            "wire_id": _model_lists.wire_model_id(ident),
            "price": item.get("price"),
            "kb_known": bool(item.get("kb_known", False)),
            "listed": bool(item.get("listed", False)),
        })
    return 200, {"provider_id": provider_id, "models": rows,
                 "source": source, "enabled": enabled}


def refresh_provider_models(ctx: ProviderCtx, query,
                            body) -> Tuple[int, Dict]:
    """POST refresh: fetch the live list, merge, store, return it."""
    query = query or {}
    provider_id = query.get("id")
    if not provider_id:
        return 400, {"error": "provider id is required"}
    try:
        view = ctx.facade.get_provider(provider_id)
    except ValueError as exc:
        return 400, {"error": str(exc)}
    if view is None:
        # R2 local branch: refresh re-reads the attached runtime's
        # real names (a loopback read, never a pull); nothing attached
        # means the legacy 404.
        if provider_id in LOCAL_PROVIDER_IDS:
            names = _local_runtime_names(ctx, provider_id)
            if names is not None:
                rows, enabled, _kb_rows = _local_rows(
                    ctx, provider_id, names)
                return 200, {"provider_id": provider_id, "models": [
                    {"id": str(m.get("id", "") or ""),
                     "name": str(m.get("name", "") or ""),
                     "price": m.get("price"),
                     "kb_known": bool(m.get("kb_known", False))}
                    for m in rows], "source": "local",
                    "enabled": enabled}
        return 404, {"error": "unknown provider %r" % (provider_id,)}
        merged, state, _kb_rows = _merged_for(ctx, provider_id)
        enabled = []
        if state is not None and isinstance(state.get("enabled"), list):
            enabled = [str(i) for i in state["enabled"]
                       if isinstance(i, str) and i]
        return 200, {"provider_id": provider_id, "models": [
            {"id": str(m.get("id", "") or ""),
             "name": str(m.get("name", "") or ""),
             "price": m.get("price"),
             "kb_known": bool(m.get("kb_known", False))}
            for m in merged], "source": "catalog", "enabled": enabled}
    try:
        secret_id = getattr(getattr(view, "secret_ref", None),
                            "secret_id", "")
        key_value = _model_lists.read_secret_value(
            getattr(ctx, "credential_store", None), secret_id)
    except _model_lists.LiveModelsError as exc:
        return 409, {"error": str(exc)}
    try:
        base_url = getattr(view, "base_url", "")
    except Exception:
        base_url = ""
    try:
        state = _model_lists.refresh_with_join(
            provider_id, base_url, key_value,
            _kb_rows_for(ctx, provider_id),
            transport=_preset_transport(provider_id),
            http_get=getattr(ctx, "http_get", None),
            store_dir=getattr(ctx, "model_state_dir", None))
    except _model_lists.LiveModelsError as exc:
        return 502, {"error": str(exc)}
    return 200, {"provider_id": provider_id, "models": [
        {"id": str(m.get("id", "") or ""),
         "name": str(m.get("name", "") or ""),
         "price": m.get("price"),
         "kb_known": bool(m.get("kb_known", False))}
        for m in state["models"]],
        "source": state.get("source", "provider"),
        "enabled": state.get("enabled", [])}


def put_provider_models(ctx: ProviderCtx, query, body) -> Tuple[int, Dict]:
    """PUT ticks: persist the enabled subset; ids must be known merged."""
    query = query or {}
    provider_id = query.get("id")
    if not provider_id:
        return 400, {"error": "provider id is required"}
    try:
        view = ctx.facade.get_provider(provider_id)
    except ValueError as exc:
        return 400, {"error": str(exc)}
    if view is None:
        # R2 local branch: ticks persist against the runtime's real
        # names. An empty tick list clears the stored ticks (legacy
        # allow), so Use-for-agents never needs a PUT first.
        if provider_id in LOCAL_PROVIDER_IDS:
            names = _local_runtime_names(ctx, provider_id)
            if names is None:
                return 404, {
                    "error": "unknown provider %r" % (provider_id,)}
            if not isinstance(body, Mapping):
                return 400, {
                    "error": "models save needs a JSON object body"}
            hit = _find_raw_secret(body)
            if hit:
                return 400, {"error": "raw secret material refused at %s "
                                      "(pass model ids, never raw)" % hit}
            ids = body.get("ids")
            if not isinstance(ids, list):
                return 400, {"error": "models save needs an ids list"}
            rows, _prev_enabled, _kb_rows = _local_rows(
                ctx, provider_id, names)
            known = {str(m.get("id", "") or "") for m in rows}
            enabled = []
            for ident in ids:
                if not isinstance(ident, str) or not ident.strip():
                    return 400, {
                        "error": "model ids must be non-empty strings"}
                canonical = _model_lists.canonical_model_id(
                    provider_id, ident.strip())
                if canonical not in known:
                    return 400, {"error": "unknown model %r for provider %r "
                                          "(ticks must be known to the "
                                          "served list)" % (ident,
                                                             provider_id)}
                if canonical not in enabled:
                    enabled.append(canonical)
            if not enabled:
                _model_lists.drop_state(
                    getattr(ctx, "model_state_dir", None), provider_id)
            else:
                previous = {
                    "provider_id": provider_id, "models": rows,
                    "source": "local",
                    "updated_at": _model_lists._utcnow(),
                    "enabled": enabled}
                if getattr(ctx, "model_state_dir", None) is not None:
                    _model_lists.save_state(
                        getattr(ctx, "model_state_dir", None),
                        provider_id, previous)
            return 200, {"ok": True, "provider_id": provider_id,
                         "enabled": enabled}
        return 404, {"error": "unknown provider %r" % (provider_id,)}
    if not isinstance(body, Mapping):
        return 400, {"error": "models save needs a JSON object body"}
    hit = _find_raw_secret(body)
    if hit:
        return 400, {"error": "raw secret material refused at %s "
                              "(pass model ids, never raw)" % hit}
    ids = body.get("ids")
    if not isinstance(ids, list):
        return 400, {"error": "models save needs an ids list"}
    merged, state, _kb_rows = _merged_for(ctx, provider_id)
    known = {str(m.get("id", "") or "") for m in merged}
    enabled = []
    for ident in ids:
        if not isinstance(ident, str) or not ident.strip():
            return 400, {"error": "model ids must be non-empty strings"}
        canonical = _model_lists.canonical_model_id(
            provider_id, ident.strip())
        if canonical not in known:
            return 400, {"error": "unknown model %r for provider %r "
                                  "(ticks must be known to the merged "
                                  "list)" % (ident, provider_id)}
        if canonical not in enabled:
            enabled.append(canonical)
    previous = dict(state) if isinstance(state, Mapping) else {
        "provider_id": provider_id, "models": merged,
        "source": "catalog",
        "updated_at": _model_lists._utcnow()}
    previous["enabled"] = enabled
    if getattr(ctx, "model_state_dir", None) is not None:
        _model_lists.save_state(
            getattr(ctx, "model_state_dir", None), provider_id, previous)
    return 200, {"ok": True, "provider_id": provider_id,
                 "enabled": enabled}


def chat_models(ctx: ProviderCtx, query, body) -> Tuple[int, Dict]:
    """Enabled models only: the server's tick list is the routing truth.

    Providers with a stored tick list contribute only ticked models
    (canonical compare, so ``meta/x`` and ``x`` are one model);
    providers without one keep the legacy read (every KB row).
    """
    query = query or {}
    try:
        views = ctx.facade.list_providers(True)
    except ValueError as exc:
        return 400, {"error": str(exc)}
    ticks = _model_lists.enabled_map(
        getattr(ctx, "model_state_dir", None),
        [getattr(v, "provider_id", "") for v in views])
    rows = []
    for view in views:
        pid = getattr(view, "provider_id", "")
        allowed = ticks.get(pid) if isinstance(pid, str) else None
        wanted = None
        if allowed is not None:
            wanted = {_model_lists.canonical_model_id(pid, i)
                      for i in allowed}
        for model, _kb in _model_entries(ctx.models.get(pid)):
            if wanted is not None and \
                    _model_lists.canonical_model_id(pid, model) not in wanted:
                continue
            rows.append({"provider_id": pid, "model": model})
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
    "refresh_provider_models",
    "put_provider_models",
    "chat_models",
    "leftover_keys",
    "match",
    "mount",
]
