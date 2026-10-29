"""Watcher HTTP surface: real router over the frozen watcher contract.

Row R-323 plus row Q3, lane m_entry, author CODER-2 Sable. Every entry of
``ROUTE_ENTRY_POINTS`` maps to the owning lane module (automation_routes
pattern): reads serve the watcher lane, the stop-all entry serves
``agent_si.backend.stop_all``. POST routes need a live session token
(``SESSION_TOKEN_MISSING`` -> 401, ``SESSION_TOKEN_INVALID`` -> 403,
checked before any stop is recorded); GET routes are open. The token is
read from the ``x-ui-session-token`` header or the ``session_token`` body
field. ``configure`` accepts the composition-root hooks, mirroring the
automation router.
"""

from __future__ import annotations

import dataclasses
import sys
from enum import Enum
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from agent_si.backend import stop_all as _stop_home
from agent_si.watcher import integrity as _integrity_home
from agent_si.watcher import journal as _journal_home
from agent_si.watcher import rules as _rules_home
from agent_si.watcher import status as _status_home

#: Dotted name of the frozen watcher contract module. Product code keeps
#: no static import of it; the module object is resolved late at call
#: time, so raised errors and returned rows are the same objects the
#: contract tests use.
_IFACE_MODULE = "agent_si.watcher.interface"


def _watcher_iface():
    """Return the frozen watcher contract module object."""
    try:
        return sys.modules[_IFACE_MODULE]
    except KeyError:
        import importlib

        return importlib.import_module(_IFACE_MODULE)


__all__ = ("router", "configure", "token_live")

router = APIRouter()

_auth_hook: Optional[Callable[[str], bool]] = None
_rate_hook: Optional[Callable[[str], bool]] = None


def configure(
    auth_hook: Optional[Callable[[str], bool]] = None,
    rate_hook: Optional[Callable[[str], bool]] = None,
    model_factory: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """Install composition-root hooks (K02 owns auth/rate/model policy)."""
    global _auth_hook, _rate_hook
    _auth_hook = auth_hook
    _rate_hook = rate_hook
    return {
        "auth_hook": _auth_hook is not None,
        "rate_hook": _rate_hook is not None,
        "model_factory": model_factory is not None,
    }


def token_live(token: Optional[str]) -> bool:
    """True only when the configured auth hook accepts the token."""
    return (
        _auth_hook is not None
        and isinstance(token, str)
        and bool(token)
        and bool(_auth_hook(token))
    )


_STATUS_BY_CODE: Dict[str, int] = {
    "SESSION_TOKEN_MISSING": 401,
    "SESSION_TOKEN_INVALID": 403,
    "RULE_NOT_FOUND": 404,
    "PRESET_NOT_FOUND": 404,
    "JOURNAL_KIND_UNKNOWN": 404,
    "STOP_REASON_MISSING": 400,
    "GOVERNANCE_MISMATCH": 409,
}


def _fail(code: str, detail: str = "") -> None:
    raise HTTPException(
        status_code=_STATUS_BY_CODE.get(code, 400),
        detail={"code": code, "detail": detail},
    )


def _dump(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value):
        return {
            field.name: _dump(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, (tuple, list)):
        return [_dump(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _dump(item) for key, item in value.items()}
    return value


def _verify_integrity(project_id: str, session_token: str = ""):
    """Entry wrapper: integrity verify tolerates the route kwarg."""
    return _integrity_home.verify(project_id)


def _evaluate_rule(project_id: str, rule_id: str, session_token: str = ""):
    """Entry wrapper: rule evaluate tolerates the route kwarg."""
    return _rules_home.evaluate(project_id, rule_id)


def _stop_all(actor: str, project_id: str, grant_ref: str = "",
              session_token: str = ""):
    """Entry wrapper: stop-all tolerates the route kwarg."""
    return _stop_home.request_stop(actor, project_id, grant_ref)


def _call(entry_name: str, *args: Any, **kwargs: Any) -> Any:
    _check_drift()
    try:
        return _dump(_DISPATCH[entry_name](*args, **kwargs))
    except HTTPException:
        raise
    except Exception as err:
        # Lane errors travel as (code, detail) on either WatcherError
        # class (frozen contract or lane home); anything else is a bug.
        code = getattr(err, "code", "")
        if not code:
            raise
        _fail(code, getattr(err, "detail", "") or str(err))
    return None


async def _body(request: Request) -> Dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _token_of(request: Request, data: Dict[str, Any]) -> Optional[str]:
    header = request.headers.get("x-ui-session-token")
    if isinstance(header, str) and header:
        return header
    value = data.get("session_token")
    if isinstance(value, str) and value:
        return value
    return None


def _guard_post(request: Request, data: Dict[str, Any]) -> str:
    token = _token_of(request, data)
    if token is None:
        _fail("SESSION_TOKEN_MISSING", "POST needs a live session token")
        raise AssertionError("unreachable")
    if not token_live(token):
        _fail("SESSION_TOKEN_INVALID", "unknown session token")
        raise AssertionError("unreachable")
    if _rate_hook is not None:
        key = token
        try:
            allowed = bool(_rate_hook(key))
        except Exception:
            allowed = False
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={"code": "RATE_LIMITED", "detail": "rate hook refused"},
            )
    return token


#: Entry-name dispatch: every entry calls its 0C-named owning module.
_DISPATCH: Dict[str, Callable[..., Any]] = {
    "get_status": _status_home.get,
    "list_events": _journal_home.list_events,
    "verify_integrity": _verify_integrity,
    "evaluate_rule": _evaluate_rule,
    "stop_all_request_stop": _stop_all,
}

#: Route key to entry name; must equal ROUTE_ENTRY_POINTS exactly.
_HANDLED: Dict[str, str] = {
    "GET /api/v1/watcher/status": "get_status",
    "GET /api/v1/watcher/journal": "list_events",
    "POST /api/v1/watcher/integrity-check": "verify_integrity",
    "POST /api/v1/watcher/rules/{id}/evaluate": "evaluate_rule",
    "POST /api/v1/stop-all": "stop_all_request_stop",
}

_drift_checked = False


def _check_drift():
    """Verify the route table against the frozen contract once, on first use."""
    global _drift_checked
    if _drift_checked:
        return
    if dict(_HANDLED) != dict(_watcher_iface().ROUTE_ENTRY_POINTS):
        raise RuntimeError("watcher routes drifted from ROUTE_ENTRY_POINTS")
    _drift_checked = True


if set(_HANDLED.values()) != set(_DISPATCH):
    raise RuntimeError("watcher routes dispatch is incomplete")


@router.get("/api/v1/watcher/status")
def route_get_status(project_id: str) -> Any:
    """GET /api/v1/watcher/status -> get_status (open)."""
    return _call("get_status", project_id)


@router.get("/api/v1/watcher/journal")
def route_get_journal(project_id: str, kind: str = "") -> Any:
    """GET /api/v1/watcher/journal -> list_events (open)."""
    return _call("list_events", project_id, kind)


@router.post("/api/v1/watcher/integrity-check")
async def route_post_integrity(request: Request) -> Any:
    """POST /api/v1/watcher/integrity-check -> verify_integrity (token)."""
    data = await _body(request)
    token = _guard_post(request, data)
    return _call(
        "verify_integrity", str(data.get("project_id", "")),
        session_token=token,
    )


@router.post("/api/v1/watcher/rules/{id}/evaluate")
async def route_post_evaluate(id: str, request: Request) -> Any:
    """POST /api/v1/watcher/rules/{id}/evaluate -> evaluate_rule (token)."""
    data = await _body(request)
    token = _guard_post(request, data)
    return _call(
        "evaluate_rule", str(data.get("project_id", "")), id,
        session_token=token,
    )


@router.post("/api/v1/stop-all")
async def route_post_stop_all(request: Request) -> Any:
    """POST /api/v1/stop-all -> stop_all_request_stop (token)."""
    data = await _body(request)
    token = _guard_post(request, data)
    return _call(
        "stop_all_request_stop",
        str(data.get("actor", "")),
        str(data.get("project_id", "")),
        grant_ref=str(data.get("grant_ref", "")),
        session_token=token,
    )
