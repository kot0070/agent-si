"""Provider key save route (K04KEY1 lane owned).

POST /api/v1/providers/keys behind the session-token USER-write guard
(the host in backend/app.py applies the same x-actor plus
x-ui-session-token guard as all USER writes): body
``{"preset_id": ..., "key_value": ...}`` checks the pasted key first,
then stores the value in the bound credential store and answers 201
``{"key_ref": ...}`` only. The raw value is never echoed, never
logged, never audited. A store timeout answers code
``KEY_SAVE_TIMEOUT``. The connect route stays key-only
(raw keys still refused there).

Preflight (FXR2E wrong-key fix): the pasted key is held in memory
and checked with a live GET of the provider ``/models`` list through
the same egress (Bearer + per-provider headers) the model list uses.
The value reaches the store only when the provider answers 2xx. A
failed check answers the reason with no key_ref and stores nothing:
401/403 -> PROVIDER_KEY_REFUSED ("refused" text), network/timeout ->
503 EVIDENCE_PROBE_NETWORK ("unreachable" text), anything else ->
400 PROVIDER_CHECK_FAILED with the scrubbed plain text. A failed
replace keeps the old working key untouched (nothing is written
before success). Local runtimes (transport local) keep the legacy
store path: there is no network key to check.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor as _Pool
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

KEY_SAVE_TIMEOUT = "KEY_SAVE_TIMEOUT"

SAVE_TIMEOUT_S = 5.0

#: Preflight network budget (same order as the model-list fetch).
PREFLIGHT_TIMEOUT_S = 10.0

#: Refused-key plain text (the dialog shows this verbatim on 401/403).
KEY_REFUSED_MESSAGE = ("The provider refused this key. Paste the full "
                       "key again.")

#: Unreachable plain text (the dialog shows this verbatim on 503).
PROVIDER_UNREACHABLE_MESSAGE = "Could not reach the provider."

#: Surfaced reason codes for a failed preflight (the audit keeps the
#: PROVCK2 classes; these travel on the refused save response).
KEY_REFUSED_CODE = "PROVIDER_KEY_REFUSED"
PROVIDER_UNREACHABLE_CODE = "EVIDENCE_PROBE_NETWORK"
KEY_CHECK_FAILED_CODE = "PROVIDER_CHECK_FAILED"


def _store_value(store: Any, secret_id: str, value: str,
                 timeout_s: float) -> None:
    for attr in ("set_secret", "store_secret", "store", "put", "set",
                 "seed"):
        fn = getattr(store, attr, None)
        if callable(fn):
            def _do(_fn=fn) -> None:  # type: ignore[no-untyped-def]
                _fn(secret_id, value)

            with _Pool(max_workers=1) as pool:
                future = pool.submit(_do)
                try:
                    future.result(timeout=float(timeout_s))
                    return
                except Exception as exc:
                    try:
                        import concurrent.futures as _fut

                        if isinstance(exc, _fut.TimeoutError):
                            raise TimeoutError("save timed out") from None
                    except TimeoutError:
                        raise
                    raise
    raise ValueError("credential store has no write port")


def _timeout_for(ctx: Any) -> float:
    try:
        raw = getattr(ctx, "key_save_timeout_s", None)
    except Exception:
        raw = None
    if raw is not None:
        try:
            val = float(raw)
        except (TypeError, ValueError):
            pass
        else:
            if val > 0:
                return val
    return SAVE_TIMEOUT_S


def _preflight_live_models(ctx: Any, preset: Dict[str, Any],
                           key_value: str) -> Tuple[bool, str, Any]:
    """GET provider /models with the pasted key; (ok, kind, status).

    Same egress the model list uses (Bearer plus per-provider
    headers). kind is ok | auth | network | other; status is the int
    HTTP status when the provider answered one. Local transports skip
    the check (no network key exists) and report ok.
    """
    from agent_si.providers.registry import (
        provider_model_lists as _lists,
    )

    try:
        transport = str(preset.get("transport") or "")
    except Exception:
        transport = ""
    if transport == "local":
        return True, "ok", None
    try:
        url = _lists.models_url(preset.get("base_url"))
    except Exception:
        return False, "other", None
    headers = {"Accept": "application/json",
               "Authorization": "Bearer " + str(key_value)}
    try:
        headers.update(_lists.extra_headers(preset.get("provider_id"),
                                            transport))
    except Exception:
        pass
    timeout = PREFLIGHT_TIMEOUT_S
    getter = getattr(ctx, "http_get", None)
    try:
        if callable(getter):
            getter(url, dict(headers), timeout)
        else:
            import urllib.request as _urlrequest

            request = _urlrequest.Request(
                url, headers=dict(headers), method="GET")
            with _urlrequest.urlopen(request,
                                     timeout=timeout) as response:
                response.read()
    except Exception as exc:
        import urllib.error as _urlerror

        try:
            status = getattr(exc, "code", None)
        except Exception:
            status = None
        if isinstance(exc, _urlerror.HTTPError):
            try:
                status = int(getattr(exc, "code", 0) or 0)
            except (TypeError, ValueError):
                status = 0
            if status in (401, 403):
                return False, "auth", status
            return False, "other", status or None
        if isinstance(exc, (_urlerror.URLError, TimeoutError,
                            ConnectionError, OSError)):
            return False, "network", None
        return False, "other", None
    return True, "ok", None


def save_key(ctx: Any, query: Any, body: Any) -> Tuple[int, Dict[str, Any]]:
    """Save one provider key; answer 201 with the id-only key_ref."""
    store = getattr(ctx, "credential_store", None)
    audit = getattr(ctx, "audit_sink", None)
    if store is None:
        return 500, {"error": "credential store unbound"}
    if not isinstance(body, dict):
        return 400, {"error": "body must carry preset_id and key_value"}
    preset_id = body.get("preset_id")
    key_value = body.get("key_value")
    if not isinstance(preset_id, str) or not preset_id:
        return 400, {"error": "preset_id is required"}
    if not isinstance(key_value, str) or not key_value:
        return 400, {"error": "key_value is required"}
    try:
        from .presets import get_preset
    except Exception:
        return 500, {"error": "preset catalog unbound"}
    try:
        preset = get_preset(preset_id)
    except KeyError:
        return 400, {"error": "unknown preset %r" % (preset_id,)}
    secret_id = str(preset_id)
    provider_id = str(preset.get("provider_id", preset_id))
    timeout_s = _timeout_for(ctx)
    # FXR2E wrong-key turnaround: check the pasted key against the live
    # provider BEFORE anything is written. A failed check answers the
    # reason with no key_ref; a failed replace leaves the old working
    # key untouched (nothing is written before success).
    _pre_ok, _pre_kind, _pre_status = _preflight_live_models(
        ctx, preset, key_value)
    if not _pre_ok:
        if _pre_kind == "auth":
            return 401, {"code": KEY_REFUSED_CODE,
                         "message": KEY_REFUSED_MESSAGE}
        if _pre_kind == "network":
            return 503, {"code": PROVIDER_UNREACHABLE_CODE,
                         "message": PROVIDER_UNREACHABLE_MESSAGE}
        if isinstance(_pre_status, int) and _pre_status:
            return 400, {"code": KEY_CHECK_FAILED_CODE,
                         "message": "provider answered HTTP %d"
                                    % (_pre_status,)}
        return 400, {"code": KEY_CHECK_FAILED_CODE,
                     "message": "provider check failed"}
    try:
        _store_value(store, secret_id, key_value, timeout_s)
    except TimeoutError:
        return 504, {"error": "key save timed out",
                      "code": KEY_SAVE_TIMEOUT}
    except ValueError as exc:
        text = str(exc)
        if "timed out" in text:
            return 504, {"error": "key save timed out",
                          "code": KEY_SAVE_TIMEOUT}
        return 400, {"error": text}
    except Exception as exc:
        return 500, {"error": "%s" % (type(exc).__name__,)}
    if audit is not None:
        try:
            audit.append({
                "entry": secret_id,
                "provider_id": provider_id,
                "reason": "key-save",
                "at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass
    key_ref = {"secret_id": secret_id, "provider_id": provider_id}
    return 201, {"key_ref": key_ref}


ROUTES = (
    ("post", "/api/v1/providers/keys", "save_key", save_key),
)

__all__ = ["KEY_SAVE_TIMEOUT", "ROUTES", "save_key"]
