"""K09-A KB HTTP routes, STEP2.

register_kb_routes(app) wires the six KB endpoints onto a duck-typed web
application object or a FastAPI app (such as the frozen K02 seam app):
GET routes bind via app.get when present, POST routes via app.post,
otherwise via app.route with an explicit methods list. No separate app
object is created here; the passed-in app serves the routes.

DEMOF11: the versioned route POST /api/v1/kb/attach is served by the
same kb_attach handler; the legacy POST /kb/attach stays bound as an
alias and is never removed.

GET routes stay open (reads need no token). The three POST write routes
enforce the frozen USER_WRITE guard themselves: each write handler reads
the x-actor and x-ui-session-token headers from the incoming request and
checks them against app.state.ui_session_token / app.state.auth_hook
when present, raising 401 for a missing actor and 403 for a bad token
before KB behaviour runs (fail closed).
"""

import dataclasses
from typing import Any, Callable, Dict

from fastapi import HTTPException, Request

try:
    from agent_si.kb import models as _models
    from agent_si.kb import retriever as _behaviour
except ImportError:
    from src.agent_si.kb import models as _models
    from src.agent_si.kb import retriever as _behaviour

import sys as _mod_sys

_mod_sys.modules.setdefault(
    "src." + __name__ if not __name__.startswith("src.") else __name__[4:],
    _mod_sys.modules[__name__],
)
"""Dual-harness identity: root-based (src.*) and src-based (agent_si.*)
imports resolve to this same route module."""

USER_WRITE = "USER_WRITE"

# FXKBCHAT attach reason codes (every attach 4xx carries one).
KB_ATTACH_BAD_SOURCE = "KB_ATTACH_BAD_SOURCE"
KB_ATTACH_UNKNOWN_KIND = "KB_ATTACH_UNKNOWN_KIND"
KB_ATTACH_REJECTED = "KB_ATTACH_REJECTED"


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
    # FXKBCHAT attach block: a role-less body is accepted per
    # spec (role defaults to None, read_only to True). A
    # malformed source, an unknown kind or a bad KB dir answers
    # an honest 400 carrying a reason code, never a 500.
    _enforce_user_write(request)
    params = await _write_params(request)
    source = params.get("source", params)
    if not isinstance(source, dict):
        raise HTTPException(
            status_code=400,
            detail={"code": KB_ATTACH_BAD_SOURCE,
                    "message": "kb attach needs a source object"})
    data = dict(source)
    data.setdefault("role", None)
    data.setdefault("read_only", True)
    try:
        knowledge = _models.KnowledgeSource(**data)
    except TypeError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": KB_ATTACH_BAD_SOURCE,
                    "message": "kb attach source invalid: %s" % (exc,)},
        ) from None
    try:
        return _behaviour.attach_kb(knowledge)
    except ValueError as exc:
        text = str(exc) or "kb attach rejected"
        code = (KB_ATTACH_UNKNOWN_KIND
                if "unknown kind" in text else KB_ATTACH_REJECTED)
        raise HTTPException(
            status_code=400,
            detail={"code": code, "message": text},
        ) from None


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
    chunks, section_log = _behaviour.retrieve(
        params.get("query", ""),
        params["project_id"],
        params["role"],
        policy,
    )
    handoff = _behaviour.package_handoff(chunks)
    if handoff.get("mode") != "ref":
        return chunks, section_log
    ref = handoff.get("ref")
    if dataclasses.is_dataclass(ref):
        ref_dict = dataclasses.asdict(ref)
    elif isinstance(ref, dict):
        ref_dict = dict(ref)
    else:
        ref_dict = dict(vars(ref))
    _share_handoff_blob(handoff)
    return {
        "mode": "ref",
        "ref": ref_dict,
        "sha256": ref_dict.get("hash"),
        "size": ref_dict.get("size"),
        "citations": handoff.get("citations", []),
        "token_cost": handoff.get("token_cost", 0),
        "instruction_status": "DATA_ONLY",
    }


def _share_handoff_blob(handoff: dict) -> None:
    """Share one ref handoff payload with every loaded retriever alias.

    The dual-harness import (agent_si.* vs src.agent_si.*) can leave two
    retriever module objects sharing the registry but not the in-memory
    artifact blob store; a served consumer resolving through the other
    alias would miss. Copy the real payload bytes (resolved through this
    route's own behaviour module, never fabricated) into each loaded
    retriever blob store so resolve_handoff restores bytes either way.
    Fail-closed: any sharing failure leaves the primary store intact.
    """
    try:
        payload = _behaviour.resolve_handoff(handoff)
    except Exception:
        return
    for module in list(_mod_sys.modules.values()):
        store = getattr(module, "_ARTIFACT_BLOBS", None)
        if isinstance(store, dict):
            try:
                store.setdefault(_blob_key(handoff), payload)
            except Exception:
                continue


def _blob_key(handoff: dict) -> Any:
    """Artifact hash key for one packaged ref handoff."""
    ref = handoff.get("ref")
    if dataclasses.is_dataclass(ref):
        return ref.hash
    if isinstance(ref, dict):
        return ref.get("hash")
    return getattr(ref, "hash", None)


_ROUTES = (
    ("GET", "/api/v1/kb/list", kb_list),
    # DEMOF11: versioned attach served by the same handler; the legacy
    # POST /kb/attach below stays bound as an alias (never removed).
    ("POST", "/api/v1/kb/attach", kb_attach),
    ("POST", "/api/v1/kb/detach", kb_detach),
    ("GET", "/api/v1/kb/manifest", kb_manifest),
    ("GET", "/api/v1/kb/section", kb_section),
    ("POST", "/api/v1/kb/retrieve", kb_retrieve),
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
