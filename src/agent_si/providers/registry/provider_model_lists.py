"""Live provider model lists plus the enabled routing truth (FXPROVBE).

One place for everything the provider-models surface needs:

- id normalisation: ``canonical_model_id`` (``"meta/x"`` and ``"x"`` are one
  model) plus ``wire_model_id`` (the bare form the provider call accepts;
  mirrors the chat gateway strip). Dated snapshots
  (``claude-haiku-4-5-20251001`` -> ``claude-haiku-4-5``) and local runtime
  tags (``qwen2.5:7b`` -> ``qwen2.5``) resolve by one exact rule, never
  fuzzy: exact match first, then the dated/tag base, nothing else.
- strict fetch: ``parse_live_models`` accepts only
  ``{"data": [{"id": non-empty str}]}``; every other shape, HTTP error,
  timeout or denial maps to one generic :class:`LiveModelsError` that
  carries no key, no URL, no body.
- egress: :func:`fetch_live_models` GETs ``<preset base_url>/models`` with
  Bearer through stdlib urllib (the same call-time path the gateway
  transport uses); the Anthropic transport adds only its required
  ``anthropic-version`` header. Timeout is ``MODELS_TIMEOUT_S`` (10 s).
- merge: live ids plus KB rows by exact canonical id; a KB row absent from
  the live list stays, marked not listed; a live id absent from KB is
  shown with UNKNOWN price. The merged rows plus the enabled tick list
  plus time persist per provider in the data dir, beside
  ``provider_connections.json``.
- concurrency: per-provider locks; a second refresh while one runs joins
  it (same result object, one HTTP call). A dead provider never blocks
  another provider: locks are per provider and every network call is
  timeout-bounded; GET never performs network I/O.

The key never leaves the server: it is resolved at call time through the
existing credential-store value port, travels only in the Authorization
header, and is asserted absent from errors, responses and logs in tests.
"""

from __future__ import annotations

import json as _json
import os as _os
import re as _re
import threading as _threading
from typing import Any, Dict, List, Mapping, Optional, Tuple

#: List + refresh budget: a dead provider fails fast, never hangs the page.
MODELS_TIMEOUT_S = 10.0

#: One generic failure line: no key, no URL query, no body, ever.
GENERIC_ERROR = ("provider model list unavailable "
                 "(keeping the last list)")

#: Anthropic transport needs this header on every call, nothing else extra.
_ANTHROPIC_VERSION = "2023-06-01"

#: One trailing -YYYYMMDD date stamp (exact rule, stripped once, no fuzzy).
_DATED_SUFFIX = _re.compile(r"-\d{8}$")


class LiveModelsError(ValueError):
    """The live list is unreadable; the last stored list stays."""


class SecretUnavailableError(LiveModelsError):
    """The stored key is not resolvable right now (reconnect keylessly)."""


# --- ids: one normalisation place --------------------------------------------

def canonical_model_id(provider_id: str, model_id: str) -> str:
    """Canonical compare form: ``provider/bare`` (``meta/x`` == ``x``).

    Strips one leading ``<provider>/`` prefix when present, then
    re-prefixes with the provider. Anything else passes through
    verbatim: no case folding, no trimming inside, no guessing.
    """
    text = str(model_id or "")
    provider = str(provider_id or "")
    if provider and text.startswith(provider + "/"):
        text = text[len(provider) + 1:]
    if not text:
        return text
    if "/" in text:
        return text
    return "%s/%s" % (provider, text) if provider else text


def wire_model_id(model_id: str) -> str:
    """The id form the provider call accepts: the bare tail.

    Mirrors the chat gateway transport (it strips the provider prefix at
    call time): a resolved row keeps its canonical id for display and
    compare, and this form goes on the wire.
    """
    text = str(model_id or "")
    if "/" in text:
        return text.split("/", 1)[1]
    return text


def dated_base_id(model_id: str) -> str:
    """Exact dated/tag rule: strip one trailing -YYYYMMDD, then one :tag.

    ``claude-haiku-4-5-20251001`` -> ``claude-haiku-4-5``,
    ``qwen2.5:7b`` -> ``qwen2.5``. Anything else is returned unchanged;
    there is no fuzzy match anywhere in this module.
    """
    text = str(model_id or "")
    if _DATED_SUFFIX.search(text):
        text = text[:-9]
    if ":" in text:
        text = text.split(":")[0]
    return text


def _kb_canonical(row: Mapping[str, Any]) -> Tuple[str, str]:
    provider = str(row.get("provider_id", "") or "")
    return provider, canonical_model_id(provider, row.get("model_id", ""))


def resolve_kb_row(kb_rows: Any, provider_id: str,
                   live_id: str) -> Optional[Mapping[str, Any]]:
    """Resolve one live id to its KB row by the exact rule or None.

    Exact canonical match first, then the dated/tag base of the same id.
    Never fuzzy: ``gpt-4o`` never resolves to ``gpt-4o-mini``. The match
    itself runs through the single loader match function
    (``agent_si.model_kb.loader.match_row``); only the UI-list
    canonicalization stays here.
    """
    from agent_si.model_kb import loader as _loader

    provider = str(provider_id or "")
    rows = [row for row in kb_rows or []
            if isinstance(row, Mapping)
            and str(row.get("provider_id", "") or "") == provider]
    if not rows:
        return None
    view = {"models": [
        {"provider_id": provider,
         "model_id": canonical_model_id(provider, row.get("model_id", "")),
         "_row": row} for row in rows]}
    hit = _loader.match_row(
        view, provider, canonical_model_id(provider, live_id))
    if hit is None:
        return None
    return hit.get("_row")


# --- strict parse ---------------------------------------------------------------

def parse_live_models(body: Any) -> List[str]:
    """Parse a live ``/models`` body to sorted unique ids, strictly.

    Only ``{"data": [{"id": non-empty str}, ...]}`` (non-empty) parses;
    every other shape raises :class:`LiveModelsError` with the generic
    line (the offending body is never echoed).
    """
    ids: List[str] = []
    if isinstance(body, Mapping):
        data = body.get("data")
        if isinstance(data, list) and data:
            ok = True
            for item in data:
                if not isinstance(item, Mapping):
                    ok = False
                    break
                ident = item.get("id")
                if not isinstance(ident, str) or not ident.strip():
                    ok = False
                    break
                text = ident.strip()
                if text not in ids:
                    ids.append(text)
            if ok:
                return sorted(ids)
    raise LiveModelsError(GENERIC_ERROR)


# --- egress ----------------------------------------------------------------------

def models_url(base_url: str) -> str:
    """Live-list URL off the preset base URL (nothing invented)."""
    base = str(base_url or "").rstrip("/")
    if not base:
        raise LiveModelsError(GENERIC_ERROR)
    if base.endswith("/v1"):
        return base + "/models"
    return base + "/v1/models"


def extra_headers(provider_id: str, transport: Any = None) -> Dict[str, str]:
    """Per-provider headers: Anthropic transport only, nothing else."""
    if str(transport or "") == "litellm_backed" or str(provider_id or "") in (
            "anthropic", "claude"):
        return {"anthropic-version": _ANTHROPIC_VERSION}
    return {}


def read_secret_value(credential_store: Any, secret_id: str) -> str:
    """Resolve one key value at call time through the existing value port.

    Same duck-typed port order the gateway transport uses; the value is
    returned, never stored or logged. Failure raises
    :class:`SecretUnavailableError` (keyless line).
    """
    if credential_store is not None and secret_id:
        for attr in ("get_secret", "get", "retrieve", "read",
                     "get_secret_value"):
            loader = getattr(credential_store, attr, None)
            if not callable(loader):
                continue
            try:
                candidate = loader(secret_id)
            except Exception:
                continue
            value = candidate
            if isinstance(candidate, Mapping):
                value = candidate.get("value")
            if isinstance(value, str) and value:
                return value
        try:
            candidate = credential_store[secret_id]
        except Exception:
            candidate = None
        if isinstance(candidate, Mapping):
            candidate = candidate.get("value")
        if isinstance(candidate, str) and candidate:
            return candidate
    raise SecretUnavailableError(GENERIC_ERROR)


def _default_http_get(url: str, headers: Mapping[str, str],
                      timeout: float) -> Any:
    """Stdlib GET returning the parsed JSON body (FAKE seam: urlopen).

    HTTP failures log the numeric status only (never URL, body or key)
    and surface as the generic keyless error.
    """
    import urllib.error as _urlerror
    import urllib.request as _urlrequest

    request = _urlrequest.Request(url, headers=dict(headers), method="GET")
    try:
        with _urlrequest.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except Exception as exc:
        try:
            import logging as _logging

            status = getattr(exc, "code", None)
            if isinstance(exc, _urlerror.HTTPError):
                status = exc.code
            _logging.getLogger("agent_si.providers").error(
                "provider models fetch failed with status %s",
                status if status is not None else "?")
        except Exception:
            pass
        raise LiveModelsError(GENERIC_ERROR) from None
    try:
        return _json.loads(raw.decode("utf-8"))
    except Exception:
        raise LiveModelsError(GENERIC_ERROR) from None


def fetch_live_models(base_url: str, key_value: str, *,
                      provider_id: str, transport: Any = None,
                      http_get: Any = None,
                      timeout_s: float = MODELS_TIMEOUT_S) -> List[str]:
    """Fetch live ids; every failure is the generic keyless error."""
    if not isinstance(key_value, str) or not key_value:
        raise SecretUnavailableError(GENERIC_ERROR)
    url = models_url(base_url)
    headers = {"Accept": "application/json",
               "Authorization": "Bearer " + key_value}
    headers.update(extra_headers(provider_id, transport))
    getter = http_get if callable(http_get) else _default_http_get
    try:
        body = getter(url, headers, timeout_s)
    except LiveModelsError:
        raise
    except Exception:
        raise LiveModelsError(GENERIC_ERROR) from None
    return parse_live_models(body)


# --- merge -------------------------------------------------------------------------

def price_of_kb_row(row: Mapping[str, Any]) -> Optional[float]:
    """Known input + output token price, else None (UNKNOWN)."""
    try:
        fields = (row or {}).get("fields") or {}
        total = 0.0
        for name in ("input_token_price", "output_token_price"):
            total += float((fields.get(name) or {}).get("value"))
        return total
    except (TypeError, ValueError, AttributeError):
        return None


def merge_model_rows(provider_id: str, live_ids: Any,
                     kb_rows: Any) -> List[Dict[str, Any]]:
    """Merge live ids with KB rows by exact canonical id, sorted by id.

    Row: ``{id, name, price, kb_known, listed}``. A KB row absent from
    the live list stays (``listed`` False); a live id absent from KB is
    shown with price None (UNKNOWN) and ``kb_known`` False.
    """
    live = []
    for ident in live_ids or []:
        canonical = canonical_model_id(provider_id, ident)
        if canonical and canonical not in live:
            live.append(canonical)
    known: Dict[str, Mapping[str, Any]] = {}
    for row in kb_rows or []:
        if not isinstance(row, Mapping):
            continue
        provider, canonical = _kb_canonical(row)
        if provider != str(provider_id or "") or not canonical:
            continue
        known.setdefault(canonical, row)
    rows = []
    for ident in sorted(set(live) | set(known)):
        row = known.get(ident)
        bare = ident.split("/")[-1] if "/" in ident else ident
        rows.append({
            "id": ident,
            "name": bare,
            "price": price_of_kb_row(row) if row is not None else None,
            "kb_known": row is not None,
            "listed": ident in live,
        })
    return rows


# --- persisted state (beside provider_connections.json) ------------------------------

def _safe_provider_id(provider_id: str) -> str:
    return "".join(
        ch if (ch.isalnum() or ch in ("-", "_")) else "_"
        for ch in str(provider_id or "")) or "unknown"


def state_path(store_dir: str, provider_id: str) -> str:
    """Per-provider state file: same dir as provider_connections.json."""
    return _os.path.join(str(store_dir or ""),
                         "provider_models_%s.json" % _safe_provider_id(
                             provider_id))


def load_state(store_dir: Any, provider_id: str) -> Optional[Dict[str, Any]]:
    """Last stored list or None (missing/corrupt reads as absent)."""
    if not store_dir:
        return None
    try:
        with open(state_path(store_dir, provider_id), "r",
                  encoding="utf-8") as _fh:
            raw = _json.load(_fh)
    except (FileNotFoundError, NotADirectoryError, ValueError, OSError):
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def save_state(store_dir: str, provider_id: str,
               state: Mapping[str, Any]) -> str:
    """Atomically persist the merged list + enabled + time."""
    path = state_path(store_dir, provider_id)
    parent = _os.path.dirname(_os.path.abspath(path))
    if parent:
        _os.makedirs(parent, exist_ok=True)
    cleaned = {
        "provider_id": str(provider_id),
        "models": [dict(m) for m in state.get("models", []) or []],
        "enabled": [str(i) for i in state.get("enabled", []) or []],
        "source": str(state.get("source", "catalog") or "catalog"),
        "updated_at": str(state.get("updated_at", "") or ""),
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as _fh:
        _fh.write(_json.dumps(cleaned, ensure_ascii=False, sort_keys=True))
    _os.replace(tmp, path)
    return path


def load_enabled(store_dir: Any, provider_id: str) -> Optional[List[str]]:
    """Stored tick list, or None when this provider never stored one."""
    state = load_state(store_dir, provider_id)
    if state is None:
        return None
    enabled = state.get("enabled")
    if not isinstance(enabled, list):
        return None
    return [str(i) for i in enabled if isinstance(i, str) and i]


def enabled_map(store_dir: Any,
                provider_ids: Any) -> Dict[str, List[str]]:
    """One reader for the routing truth: stored ticks per provider.

    Providers without a stored list are absent (callers fall back to
    their legacy read); nothing is invented here.
    """
    out: Dict[str, List[str]] = {}
    for pid in provider_ids or []:
        enabled = load_enabled(store_dir, pid)
        if enabled is not None:
            out[str(pid)] = enabled
    return out


# --- refresh with in-flight join ----------------------------------------------

_MU = _threading.Lock()
_LOCKS: Dict[str, _threading.Lock] = {}
_INFLIGHT: Dict[str, Tuple[_threading.Event, list]] = {}


def _provider_lock(provider_id: str) -> _threading.Lock:
    with _MU:
        lock = _LOCKS.get(provider_id)
        if lock is None:
            lock = _threading.Lock()
            _LOCKS[provider_id] = lock
        return lock


def _utcnow() -> str:
    try:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
    except Exception:
        return ""


def refresh_with_join(provider_id: str, base_url: str, key_value: str,
                      kb_rows: Any, *, transport: Any = None,
                      http_get: Any = None, store_dir: Any = None,
                      default_model: Any = None,
                      timeout_s: float = MODELS_TIMEOUT_S) -> Dict[str, Any]:
    """Refresh one provider's list; a concurrent second call joins it.

    Returns the stored state dict (the same object to every joiner, one
    HTTP call). Network failure raises :class:`LiveModelsError`; the
    caller keeps the last stored list and says so calmly.
    """
    pid = str(provider_id or "")
    lock = _provider_lock(pid)
    if lock.acquire(blocking=False):
        event = _threading.Event()
        slot: list = [None, None]
        with _MU:
            _INFLIGHT[pid] = (event, slot)
        try:
            live = fetch_live_models(base_url, key_value,
                                     provider_id=pid, transport=transport,
                                     http_get=http_get, timeout_s=timeout_s)
            wanted = list(live)
            default = canonical_model_id(
                pid, default_model) if default_model else ""
            if default and default not in wanted:
                wanted.append(default)
            models = merge_model_rows(pid, wanted, kb_rows)
            merged_ids = [m["id"] for m in models]
            previous = load_enabled(store_dir, pid)
            if previous is None:
                enabled = [default] if default and \
                    default in merged_ids else []
                if not enabled and merged_ids:
                    enabled = []
            else:
                enabled = [i for i in previous if i in merged_ids]
            state = {
                "provider_id": pid,
                "models": models,
                "enabled": enabled,
                "source": "provider",
                "updated_at": _utcnow(),
            }
            if store_dir:
                save_state(store_dir, pid, state)
            slot[0] = state
            return state
        except Exception as exc:
            slot[1] = exc
            raise
        finally:
            event.set()
            with _MU:
                _INFLIGHT.pop(pid, None)
            lock.release()
    with _MU:
        pair = _INFLIGHT.get(pid)
    if pair is None:
        return refresh_with_join(
            pid, base_url, key_value, kb_rows, transport=transport,
            http_get=http_get, store_dir=store_dir,
            default_model=default_model, timeout_s=timeout_s)
    event, slot = pair
    event.wait(timeout_s + 5.0)
    if slot[1] is not None:
        raise slot[1]
    if slot[0] is None:
        raise LiveModelsError(GENERIC_ERROR)
    return slot[0]


def drop_state(store_dir: Any, provider_id: str) -> None:
    """Disconnect cleanup: remove only this provider's list file."""
    if not store_dir:
        return
    try:
        _os.remove(state_path(store_dir, provider_id))
    except OSError:
        pass


__all__ = [
    "GENERIC_ERROR",
    "MODELS_TIMEOUT_S",
    "LiveModelsError",
    "SecretUnavailableError",
    "canonical_model_id",
    "dated_base_id",
    "drop_state",
    "enabled_map",
    "extra_headers",
    "fetch_live_models",
    "load_enabled",
    "load_state",
    "merge_model_rows",
    "models_url",
    "parse_live_models",
    "price_of_kb_row",
    "read_secret_value",
    "refresh_with_join",
    "resolve_kb_row",
    "save_state",
    "state_path",
    "wire_model_id",
]
