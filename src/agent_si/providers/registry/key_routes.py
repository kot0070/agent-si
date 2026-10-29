"""Provider key save route (K04KEY1 lane owned).

POST /api/v1/providers/keys behind the session-token USER-write guard
(the host in backend/app.py applies the same x-actor plus
x-ui-session-token guard as all USER writes): body
``{"preset_id": ..., "key_value": ...}`` stores the value in the bound
credential store and answers 201 ``{"key_ref": ...}`` only. The raw
value is never echoed, never logged, never audited. A store timeout
answers code ``KEY_SAVE_TIMEOUT``. The connect route stays key-only
(raw keys still refused there).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor as _Pool
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

KEY_SAVE_TIMEOUT = "KEY_SAVE_TIMEOUT"

SAVE_TIMEOUT_S = 5.0


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
