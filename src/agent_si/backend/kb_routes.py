"""K09-A KB HTTP routes, STEP2.

register_kb_routes(app) wires the six KB endpoints onto a duck-typed web
application object. No web framework is imported here: GET routes bind via
app.get when present, POST routes via app.post, otherwise via app.route
with an explicit methods list. Each handler takes a single dict argument
and forwards it to the matching behaviour function in the KB
implementation homes (models for types, retriever for behaviour).
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from src.agent_si.kb import models as _models
from src.agent_si.kb import retriever as _behaviour


def _params_of(payload: Any) -> Dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return payload
    raise TypeError("KB route handlers take a single dict argument")


def kb_list(payload: Any = None) -> Any:
    params = _params_of(payload)
    return _behaviour.list_kbs(params["project_id"], params.get("role"))


def kb_attach(payload: Any = None) -> Any:
    params = _params_of(payload)
    source = params.get("source", params)
    if isinstance(source, dict):
        source = _models.KnowledgeSource(**source)
    return _behaviour.attach_kb(source)


def kb_detach(payload: Any = None) -> Any:
    params = _params_of(payload)
    return _behaviour.detach_kb(params["kb_id"])


def kb_manifest(payload: Any = None) -> Any:
    params = _params_of(payload)
    return _behaviour.manifest_lookup(params["kb_id"], params.get("query", ""))


def kb_section(payload: Any = None) -> Any:
    params = _params_of(payload)
    return _behaviour.read_section(params["kb_id"], params["section_id"])


def kb_retrieve(payload: Any = None) -> Any:
    params = _params_of(payload)
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
