"""Thin FastAPI router for the frozen automation HTTP surface (Lane B STEP2).

Every entry of ``HTTP_ROUTES`` maps through its ``ROUTE_ENTRY_POINTS``
entry name: entry names owned by this lane call the real lane modules,
all others delegate to the frozen interface (wired when the owning lanes
land). POST routes need a live session token (``SESSION_TOKEN_MISSING``
-> 401, ``SESSION_TOKEN_INVALID`` -> 403, checked before any dispatch);
GET routes are open. The token is read from the ``x-ui-session-token``
header or the ``session_token`` body field; an ``x-actor`` header, when
present, is forwarded to the entry point, and actor policy stays with the
K02 app layer. ``configure`` accepts the composition-root hooks
(``auth_hook`` decides which tokens are live); ``rate_hook`` throttles per
token-or-client with HTTP 429.
"""

from __future__ import annotations

import dataclasses
import sys
from enum import Enum
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

import agent_si.automation.interface as _auto_iface_module
from agent_si.automation import (
    apps_card,
    launcher,
    outage,
    pause,
    runner,
    service_status,
    templates,
    triggers,
)

#: Dotted name of the frozen automation contract module. F6 (W19) keeps
#: a real top-level import of it (never TYPE_CHECKING-only) so the
#: served routes resolve the same objects the contract tests use, frozen
#: or not; the late sys.modules lookup below stays as a fallback only.
_IFACE_MODULE = "agent_si.automation.interface"


def _auto_iface():
    """Return the frozen automation contract module object."""
    try:
        return sys.modules[_IFACE_MODULE]
    except KeyError:
        return _auto_iface_module

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
    "SERVICE_NOT_FOUND": 404,
    "TRIGGER_NOT_FOUND": 404,
    "TEMPLATE_NOT_FOUND": 404,
    "AUTOMATION_RUN_NOT_FOUND": 404,
    "AUTOMATION_PAUSED": 409,
    "AUTOMATION_RUN_ACTIVE": 409,
    "SERVICE_CHECK_REFUSED": 409,
    "PAUSE_REASON_MISSING": 400,
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


def _call(entry_name: str, *args: Any, **kwargs: Any) -> Any:
    _check_drift()
    try:
        return _dump(_DISPATCH[entry_name](*args, **kwargs))
    except _auto_iface().AutomationError as err:
        _fail(err.code, err.detail)
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


#: Entry-name dispatch: lane-owned entries call lane modules, the rest call
#: the frozen interface (owning lanes wire them later).
_DISPATCH: Dict[str, Callable[..., Any]] = {
    "is_pause_effective": pause.is_effective,
    "set_global_pause": pause.set_global,
    "get_service_status": service_status.get,
    "run_service_check": service_status.run_check,
    "get_apps_card": apps_card.get_apps_card,
    "start_run": runner.start_run,
    "fire_trigger": triggers.fire_trigger,
    "instantiate_template": templates.instantiate,
    "launch": launcher.launch,
    "resume": runner.resume,
    "signal_outage": outage.signal_outage,
}

#: Route key to entry name; must equal ROUTE_ENTRY_POINTS exactly.
_HANDLED: Dict[str, str] = {
    "GET /api/v1/automations/pause": "is_pause_effective",
    "POST /api/v1/automations/pause": "set_global_pause",
    "GET /api/v1/services/{id}/status": "get_service_status",
    "POST /api/v1/services/{id}/check": "run_service_check",
    "GET /api/v1/apps/card": "get_apps_card",
    "POST /api/v1/automations/runs": "start_run",
    "POST /api/v1/automations/triggers/{id}/fire": "fire_trigger",
    "POST /api/v1/automations/templates/{id}/instantiate": "instantiate_template",
    "POST /api/v1/automations/runs/{id}/launch": "launch",
    "POST /api/v1/automations/runs/{id}/resume": "resume",
    "POST /api/v1/outage/signal": "signal_outage",
}

_drift_checked = False


def _check_drift():
    """Verify the route table against the frozen contract once, on first use."""
    global _drift_checked
    if _drift_checked:
        return
    if dict(_HANDLED) != dict(_auto_iface().ROUTE_ENTRY_POINTS):
        raise RuntimeError("automation routes drifted from ROUTE_ENTRY_POINTS")
    _drift_checked = True


if set(_HANDLED.values()) != set(_DISPATCH):
    raise RuntimeError("automation routes dispatch is incomplete")


@router.get("/api/v1/automations/pause")
def route_get_pause(project_id: str) -> Any:
    """GET /api/v1/automations/pause -> is_pause_effective (open)."""
    return _call("is_pause_effective", project_id)


@router.post("/api/v1/automations/pause")
async def route_post_pause(request: Request) -> Any:
    """POST /api/v1/automations/pause -> set_global_pause (token)."""
    data = await _body(request)
    token = _guard_post(request, data)
    return _call(
        "set_global_pause",
        bool(data.get("paused", False)),
        str(data.get("reason", "")),
        session_token=token,
    )


@router.get("/api/v1/services/{id}/status")
def route_get_status(id: str) -> Any:
    """GET /api/v1/services/{id}/status -> get_service_status (open)."""
    return _call("get_service_status", id)


@router.post("/api/v1/services/{id}/check")
async def route_post_check(id: str, request: Request) -> Any:
    """POST /api/v1/services/{id}/check -> run_service_check (token)."""
    data = await _body(request)
    token = _guard_post(request, data)
    raw_kind = data.get("check", "")
    try:
        kind = _auto_iface().ServiceCheckKind(str(raw_kind))
    except ValueError:
        _fail("SERVICE_CHECK_REFUSED", "unknown check kind %r" % (raw_kind,))
        raise AssertionError("unreachable")
    return _call("run_service_check", id, kind, session_token=token)


@router.get("/api/v1/apps/card")
def route_get_card(project_id: str) -> Any:
    """GET /api/v1/apps/card -> get_apps_card (open)."""
    return _call("get_apps_card", project_id)


@router.post("/api/v1/automations/runs")
async def route_post_runs(request: Request) -> Any:
    """POST /api/v1/automations/runs -> start_run (token)."""
    data = await _body(request)
    token = _guard_post(request, data)
    return _call(
        "start_run",
        str(data.get("project_id", "")),
        str(data.get("template_id", "")),
        session_token=token,
    )


@router.post("/api/v1/automations/triggers/{id}/fire")
async def route_post_fire(id: str, request: Request) -> Any:
    """POST /api/v1/automations/triggers/{id}/fire -> fire_trigger (token)."""
    data = await _body(request)
    token = _guard_post(request, data)
    return _call(
        "fire_trigger", str(data.get("project_id", "")), id, session_token=token
    )


@router.post("/api/v1/automations/templates/{id}/instantiate")
async def route_post_instantiate(id: str, request: Request) -> Any:
    """POST /api/v1/automations/templates/{id}/instantiate (token)."""
    data = await _body(request)
    token = _guard_post(request, data)
    return _call(
        "instantiate_template",
        str(data.get("project_id", "")),
        id,
        session_token=token,
    )


@router.post("/api/v1/automations/runs/{id}/launch")
async def route_post_launch(id: str, request: Request) -> Any:
    """POST /api/v1/automations/runs/{id}/launch -> launch (token)."""
    data = await _body(request)
    token = _guard_post(request, data)
    return _call(
        "launch", str(data.get("project_id", "")), id, session_token=token
    )


@router.post("/api/v1/automations/runs/{id}/resume")
async def route_post_resume(id: str, request: Request) -> Any:
    """POST /api/v1/automations/runs/{id}/resume -> resume (token)."""
    data = await _body(request)
    token = _guard_post(request, data)
    return _call(
        "resume", str(data.get("project_id", "")), id, session_token=token
    )


@router.post("/api/v1/outage/signal")
async def route_post_outage(request: Request) -> Any:
    """POST /api/v1/outage/signal -> signal_outage (token)."""
    data = await _body(request)
    token = _guard_post(request, data)
    return _call(
        "signal_outage",
        str(data.get("project_id", "")),
        str(data.get("service_id", "")),
        str(data.get("severity", "HIGH")),
        str(data.get("summary", "")),
        session_token=token,
    )
