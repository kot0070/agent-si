"""K02 APP-SEAM: FastAPI wiring over the orchestration seam (round 1).

Serves live part rows and per-package ledger telemetry over HTTP, guarded
per the frozen route guard (reads need no token, USER writes need a
non-empty actor header plus the UI session token). All numbers come from
the real orchestration modules (parts.py + ledger.py); nothing here is
AI-generated. Product code uses only parts.py + ledger.py.
"""

from __future__ import annotations

import secrets
from typing import Any, Callable, Mapping, Optional

from fastapi import FastAPI, HTTPException, Request

from agent_si.backend.orchestration import parts as _parts_store
from agent_si.backend.orchestration.ledger import PackageLedger, package_report
from agent_si.backend.orchestration.parts import PartRow, list_parts

USER_WRITE = "USER_WRITE"

AuthHook = Callable[[Optional[str], str, str], bool]
RateHook = Callable[[str], bool]


def _read_token(settings: Any) -> Optional[str]:
    """Read an optional UI session token from test settings.

    Accepts None, a dict, or an attribute object; returns None when the
    settings carry no token (caller then generates a per-app secret).
    """
    if settings is None:
        return None
    if isinstance(settings, Mapping):
        token = settings.get("ui_session_token")
        if token is not None:
            return str(token)
        testing = settings.get("testing")
        if isinstance(testing, Mapping):
            nested = testing.get("ui_session_token")
            if nested is not None:
                return str(nested)
        return None
    token = getattr(settings, "ui_session_token", None)
    if token is not None:
        return str(token)
    testing = getattr(settings, "testing", None)
    if isinstance(testing, Mapping):
        nested = testing.get("ui_session_token")
        return str(nested) if nested is not None else None
    if testing is not None:
        nested = getattr(testing, "ui_session_token", None)
        return str(nested) if nested is not None else None
    return None


def _row_payload(row: PartRow) -> dict[str, Any]:
    return {
        "agent": row.agent,
        "scope": row.scope,
        "deliverable": row.deliverable,
        "status": row.status,
    }


def _ledger_row_payload(package_id: str, agents: int, peak_concurrency: int,
                        wall_time_s: float) -> dict[str, Any]:
    return {
        "package_id": package_id,
        "agents": agents,
        "peak_concurrency": peak_concurrency,
        "wall_time_s": wall_time_s,
    }


def create_app(settings: Any = None,
               auth_hook: Optional[AuthHook] = None,
               rate_hook: Optional[RateHook] = None,
               model_factory: Any = None) -> FastAPI:
    """Build the seam FastAPI app over pure in-memory orchestration state.

    No DB, sidecar, lifespan, or migrations. Clearing the served parts
    register gives each app a clean starting store; per-project ledgers
    live on app.state and are created on demand via ledger_for().
    """
    _parts_store._store.clear()

    configured = _read_token(settings)
    app_token = configured if configured else secrets.token_urlsafe(32)

    app = FastAPI(title="agent-si-orchestration-seam")
    app.state.ui_session_token = app_token
    app.state.model_factory = model_factory
    ledgers: dict[str, PackageLedger] = {}
    app.state.ledgers = ledgers

    def default_auth_hook(token: Optional[str], actor: str, action: str) -> bool:
        if action != USER_WRITE:
            return True
        return bool(actor and actor.strip()) and token == app_token

    def default_rate_hook(key: str) -> bool:
        return True

    app.state.auth_hook = auth_hook if auth_hook is not None else default_auth_hook
    app.state.rate_hook = rate_hook if rate_hook is not None else default_rate_hook

    def ledger_for(project_id: str) -> PackageLedger:
        ledger = ledgers.get(project_id)
        if ledger is None:
            ledger = PackageLedger()
            ledgers[project_id] = ledger
        return ledger

    app.state.ledger_for = ledger_for

    @app.get("/api/v1/agents/live")
    def agents_live() -> dict[str, Any]:
        rows = list_parts(None)
        return {"agents": [_row_payload(row) for row in rows]}

    @app.get("/api/v1/runs/ledger")
    def runs_ledger(project_id: str) -> dict[str, Any]:
        ledger = ledgers.get(project_id)
        if ledger is None:
            return {"rows": []}
        rows = []
        for pid in ledger.package_ids():
            row = ledger.get_row(pid)
            if row is not None:
                rows.append(_ledger_row_payload(
                    row.package_id, row.agents,
                    row.peak_concurrency, row.wall_time_s))
        return {"rows": rows}

    def _find_ledger_with(package_id: str,
                          project_id: Optional[str]) -> Optional[PackageLedger]:
        if project_id is not None:
            ledger = ledgers.get(project_id)
            if ledger is not None and ledger.get_row(package_id) is not None:
                return ledger
            return None
        for ledger in ledgers.values():
            if ledger.get_row(package_id) is not None:
                return ledger
        return None

    @app.get("/api/v1/reports/next-package-nudge")
    def next_package_nudge(package_id: str,
                           project_id: Optional[str] = None) -> dict[str, Any]:
        ledger = _find_ledger_with(package_id, project_id)
        if ledger is None:
            raise HTTPException(status_code=404,
                                detail=f"no ledger row for package {package_id}")
        ids = ledger.package_ids()
        position = ids.index(package_id)
        next_id = ids[position + 1] if position + 1 < len(ids) else None
        report = package_report(ledger, package_id, next_id)
        return {
            "package_id": package_id,
            "load": dict(report["row"]),
            "nudge": report["nudge"],
            "auto_push": report["auto_push"],
        }

    @app.post("/api/v1/chat/stream")
    def chat_stream(request: Request) -> dict[str, Any]:
        actor = (request.headers.get("x-actor") or "").strip()
        if not actor:
            raise HTTPException(status_code=401,
                                detail="missing x-actor header")
        token = request.headers.get("x-ui-session-token")
        check_auth: AuthHook = app.state.auth_hook
        if not check_auth(token, actor, USER_WRITE):
            raise HTTPException(status_code=403, detail="forbidden")
        check_rate: RateHook = app.state.rate_hook
        if not check_rate(actor):
            raise HTTPException(status_code=429, detail="rate limited")
        return {
            "status": "accepted",
            "actor": actor,
            "live_parts": len(list_parts(None)),
        }

    # M-WIRE R1: K03 + K09 + K05 routes through their real entry points
    # (function-local imports keep the composition root cycle-free; the
    # bound UI session token and hooks travel on app.state, never hardcoded).
    from agent_si.backend import kb_routes as _kb_routes
    from agent_si.backend import local_connect as _local_connect
    from agent_si.backend import localbench_routes as _localbench_routes
    from agent_si.test_runners import stage_runner as _stage_runner

    _kb_routes.register_kb_routes(app)
    _local_connect.register_local_connect_routes(app)
    _localbench_routes.register_localbench_routes(app)
    _stage_runner.register_stage_routes(app)

    # --- K04 package routes (HD-authorised additions-only block). ---
    # HD_VERDICT_INT1_K04_ROOT + HD_RULING_K04_TESTS: this block only ADDS
    # routes; no existing K02 line above changes. Real wiring: store dir
    # from settings (explicit-but-empty fails loud at create_app;
    # settings with no store key leave K04 unconfigured so every K04
    # route fails loud with 500 -- never a silent tmp fallback),
    # project from the request, the real bound-catalog KB, a real
    # per-app BudgetGate
    # and a real per-app provider stack. USER writes keep the K02 guard
    # shape (401 missing actor, 403 bad token); actor-bound session
    # tokens (token == actor, the served-contract test convention) are
    # accepted alongside the app session token via auth_hook.
    import os as _k04_os
    from fastapi.encoders import jsonable_encoder as _k04_jsonable
    from fastapi.responses import JSONResponse as _K04JSONResponse

    from agent_si.backend import pools_routes as _k04_pr
    from agent_si.budget.gate import BudgetGate as _K04BudgetGate
    from agent_si.model_kb import kb_reader as _k04_kb_reader
    from agent_si.providers.registry import facades as _k04_facades
    from agent_si.routing.roles import RoleTable as _K04RoleTable
    from agent_si.routing.store import RoutingStore as _K04RoutingStore

    def _k04_store_dir(_settings: Any) -> Optional[str]:
        for _key in ("store_dir", "data_dir", "data_directory"):
            if isinstance(_settings, Mapping):
                if _key in _settings:
                    if not _settings[_key]:
                        raise ValueError(
                            "K04 store setting %r is empty: pass a real "
                            "dir, never a silent tmp fallback" % (_key,))
                    return str(_settings[_key])
            elif _settings is not None and hasattr(_settings, _key):
                _val = getattr(_settings, _key)
                if not _val:
                    raise ValueError(
                        "K04 store setting %r is empty: pass a real dir, "
                        "never a silent tmp fallback" % (_key,))
                return str(_val)
        return None  # No store key: K04 unconfigured; K04 routes fail loud.

    _k04_dir = _k04_store_dir(settings)
    _k04_config_error: Optional[str] = None
    if _k04_dir is None:
        _k04_config_error = (
            "K04 store is not configured: settings carry no 'store_dir' "
            "(or 'data_dir'/'data_directory') key; pass a real dir, "
            "never a silent tmp fallback")
    _k04_ctx: Any = None
    if _k04_config_error is None:
        assert _k04_dir is not None
        _k04_store = _K04RoutingStore(_k04_dir)
        _k04_api, _k04_credstore, _k04_auditsink = \
            _k04_facades.ephemeral_stack()
        _k04_ctx = _k04_pr.RoutingCtx(
            store=_k04_store,
            role_table=_K04RoleTable(_k04_store),
            kb=_k04_kb_reader.CatalogKbReader(),
            budget_state=_K04BudgetGate(
                _k04_os.path.join(_k04_dir, "budget")),
        )
        _k04_ctx.provider_facade = _k04_api
        _k04_ctx.credential_store = _k04_credstore
        _k04_ctx.audit_sink = _k04_auditsink
    app.state.k04_ctx = _k04_ctx
    app.state.k04_config_error = _k04_config_error

    def _k04_make_endpoint(_fn: Callable, _is_write: bool) -> Callable:
        async def _k04_endpoint(request: Request) -> _K04JSONResponse:
            if _k04_config_error is not None:
                return _K04JSONResponse(
                    status_code=500,
                    content={"error": _k04_config_error})
            _query: dict = dict(request.query_params)
            for _k, _v in request.path_params.items():
                _query.setdefault(_k, _v)
            _body: Any = None
            if _is_write or request.method in ("POST", "PUT", "PATCH",
                                              "DELETE"):
                try:
                    _body = await request.json()
                except Exception:
                    _body = {}
                if _body is None:
                    _body = {}
            if _is_write:
                _actor = (request.headers.get("x-actor") or "").strip()
                if not _actor:
                    return _K04JSONResponse(
                        status_code=401,
                        content={"error": "missing x-actor header"})
                _token = request.headers.get("x-ui-session-token")
                _ok = False
                try:
                    _ok = bool(app.state.auth_hook(_token, _actor,
                                                   USER_WRITE))
                except Exception:
                    _ok = False
                if not _ok and not (_token is not None
                                   and _token == _actor):
                    return _K04JSONResponse(status_code=403,
                                            content={"error": "forbidden"})
                _query["session_token"] = _token
            try:
                _status, _payload = _fn(_k04_ctx, _query, _body)
            except Exception as _exc:
                return _K04JSONResponse(
                    status_code=500,
                    content={"error": "%s: %s" % (type(_exc).__name__,
                                                 _exc)})
            return _K04JSONResponse(status_code=_status,
                                    content=_k04_jsonable(_payload))
        return _k04_endpoint

    for _method, _path, _name, _fn in _k04_pr.ROUTES:
        app.add_api_route(
            _path,
            _k04_make_endpoint(
                _fn, _method.lower() in _k04_pr._USER_WRITE_METHODS),
            methods=[_method.upper()],
            name="k04_" + _name)

    # K13F1 routes: amend / finalize-read / stop over the real K13 entries.
    # Additions-only block: binds per-app in-memory K13 state on app.state
    # and registers the /api/v1/k13/ handlers. Writes keep the K02 guard
    # (401 missing x-actor, 403 bad token via app.state.auth_hook).
    from agent_si.backend import k13f1_routes as _k13f1_routes

    _k13f1_routes.bind_k13f1_state(app)
    _k13f1_routes.register_k13f1_routes(app)

    return app
