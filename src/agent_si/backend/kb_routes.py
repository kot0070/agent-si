"""K09-A KB HTTP routes, STEP2.

register_kb_routes(app) wires the six KB endpoints onto a duck-typed web
application object or a FastAPI app (such as the frozen K02 seam app):
GET routes bind via app.get when present, POST routes via app.post,
otherwise via app.route with an explicit methods list. No separate app
object is created here; the passed-in app serves the routes.

GET routes stay open (reads need no token). The three POST write routes
enforce the frozen USER_WRITE guard themselves: each write handler reads
the x-actor and x-ui-session-token headers from the incoming request and
checks them against app.state.ui_session_token / app.state.auth_hook
when present, raising 401 for a missing actor and 403 for a bad token
before KB behaviour runs (fail closed).
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from fastapi import HTTPException, Request

from src.agent_si.kb import models as _models
from src.agent_si.kb import retriever as _behaviour

USER_WRITE = "USER_WRITE"


def _params_of(payload: Any) -> Dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return payload
    raise TypeError("KB route handlers take a single dict argument")


def _params_of_request(request_or_payload: Any) -> Dict[str, Any]:
    query_params = getattr(request_or_payload, "query_params", None)
    headers = getattr(request_or_payload, "headers", None)
    if query_params is not None or headers is not None:
        return dict(query_params) if query_params is not None else {}
    return _params_of(request_or_payload)


async def _write_params(request_or_payload: Any) -> Dict[str, Any]:
    params = _params_of_request(request_or_payload)
    headers = getattr(request_or_payload, "headers", None)
    if headers is not None:
        content_type = headers.get("content-type", "") or ""
        if "application/json" in content_type:
            try:
                body = await request_or_payload.json()
            except Exception:
                body = None
            if isinstance(body, dict):
                merged = dict(params)
                merged.update(body)
                return merged
    return params


def _enforce_user_write(request_or_payload: Any) -> None:
    """Frozen USER_WRITE guard for the three POST KB routes.

    Reads x-actor + x-ui-session-token from the request and checks them
    against request.app.state.auth_hook / request.app.state.ui_session_token
    when present. Raises 401 (missing actor) / 403 (bad token) before KB
    behaviour runs; fails closed when no verifiable credential is present.
    """
    headers = getattr(request_or_payload, "headers", None)
    try:
        actor = (headers.get("x-actor") or "").strip()
    except Exception:
        actor = ""
    if not actor:
        raise HTTPException(status_code=401,
                            detail="missing x-actor header")
    try:
        token = headers.get("x-ui-session-token")
    except Exception:
        token = None
    state = getattr(getattr(request_or_payload, "app", None), "state", None)
    auth_hook = getattr(state, "auth_hook", None) if state is not None else None
    if callable(auth_hook):
        try:
            allowed = auth_hook(token, actor, USER_WRITE)
        except Exception:
            allowed = False
        if not allowed:
            raise HTTPException(status_code=403, detail="forbidden")
        return
    expected = getattr(state, "ui_session_token", None)
    if state is None or expected is None or token != expected:
        raise HTTPException(status_code=403, detail="forbidden")


async def kb_list(request: Request) -> Any:
    params = _params_of_request(request)
    return _behaviour.list_kbs(params["project_id"], params.get("role"))


async def kb_attach(request: Request) -> Any:
    _enforce_user_write(request)
    params = await _write_params(request)
    source = params.get("source", params)
    if isinstance(source, dict):
        source = _models.KnowledgeSource(**source)
    return _behaviour.attach_kb(source)


async def kb_detach(request: Request) -> Any:
    _enforce_user_write(request)
    params = await _write_params(request)
    return _behaviour.detach_kb(params["kb_id"])


async def kb_manifest(request: Request) -> Any:
    params = _params_of_request(request)
    return _behaviour.manifest_lookup(params["kb_id"], params.get("query", ""))


async def kb_section(request: Request) -> Any:
    params = _params_of_request(request)
    return _behaviour.read_section(params["kb_id"], params["section_id"])


async def kb_retrieve(request: Request) -> Any:
    _enforce_user_write(request)
    params = await _write_params(request)
    policy = params.get("policy")
    if isinstance(policy, dict):
        policy = _models.RetrievalPolicy(**policy)
    return _behaviour.retrieve(
        params.get("query", ""),
        params["project_id"],
        params["role"],
        policy,
    )


_ROUTES = (
    ("GET", "/kb/list", kb_list),
    ("POST", "/kb/attach", kb_attach),
    ("POST", "/kb/detach", kb_detach),
    ("GET", "/kb/manifest", kb_manifest),
    ("GET", "/kb/section", kb_section),
    ("POST", "/kb/retrieve", kb_retrieve),
)


def _bind(app: Any, http_method: str, path: str) -> Callable:
    binder = None
    try:
        binder = app.get if http_method == "GET" else app.post
    except AttributeError:
        binder = None
    if binder is None:
        return app.route(path, methods=[http_method])
    return binder(path)


def register_kb_routes(app: Any) -> Any:
    for http_method, path, handler in _ROUTES:
        _bind(app, http_method, path)(handler)
    return app
