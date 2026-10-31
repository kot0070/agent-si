"""K02 APP-SEAM: FastAPI wiring over the orchestration seam (round 1).

Serves live part rows and per-package ledger telemetry over HTTP, guarded
per the frozen route guard (reads need no token, USER writes need a
non-empty actor header plus the UI session token). All numbers come from
the real orchestration modules (parts.py + ledger.py); nothing here is
AI-generated. Product code uses only parts.py + ledger.py.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Mapping
from typing import Any

from fastapi import FastAPI, HTTPException, Request
# K02R4 openapi-annotation: module scope so FastAPI resolves the
# K04 endpoint return annotation when it builds the OpenAPI schema.
from fastapi.responses import JSONResponse as _K04JSONResponse

from agent_si.backend.orchestration import parts as _parts_store
from agent_si.backend.orchestration.ledger import PackageLedger, package_report
from agent_si.backend.orchestration.parts import PartRow, list_parts

USER_WRITE = "USER_WRITE"

#: Stable machine code for a missing report row (M-WIRE L0B-11).
REPORT_ROW_NOT_FOUND = "REPORT_ROW_NOT_FOUND"

AuthHook = Callable[[str | None, str, str], bool]
RateHook = Callable[[str], bool]


def _read_token(settings: Any) -> str | None:
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
               auth_hook: AuthHook | None = None,
               rate_hook: RateHook | None = None,
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

    def default_auth_hook(token: str | None, actor: str, action: str) -> bool:
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
        from agent_si.backend.agents_live import live_rows as _live_rows

        return _live_rows()

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
                          project_id: str | None) -> PackageLedger | None:
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
                           project_id: str | None = None) -> dict[str, Any]:
        ledger = _find_ledger_with(package_id, project_id)
        if ledger is None:
            from agent_si.backend import chat_stream as _wire_chat

            raise HTTPException(
                status_code=404,
                detail=_wire_chat.http_error_detail(
                    REPORT_ROW_NOT_FOUND,
                    f"no ledger row for package {package_id}"))
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
    async def chat_stream(request: Request) -> Any:
        # K02R4 engine entry: guard shape unchanged (401 missing
        # x-actor, 403 bad token, 429 rate limited); the accepted+json
        # placeholder is replaced by SSE streaming of a Manager run.
        # Every error body carries {code, message} (M-WIRE L0B-11).
        from fastapi.responses import StreamingResponse

        from agent_si.backend import chat_stream as _k02r4_chat
        from agent_si.backend.orchestration import graph as _k02r4_graph

        actor = (request.headers.get("x-actor") or "").strip()
        if not actor:
            raise HTTPException(
                status_code=401,
                detail=_k02r4_chat.http_error_detail(
                    _k02r4_chat.CHAT_ACTOR_MISSING,
                    "missing x-actor header"))
        token = request.headers.get("x-ui-session-token")
        check_auth: AuthHook = app.state.auth_hook
        if not check_auth(token, actor, USER_WRITE):
            raise HTTPException(
                status_code=403,
                detail=_k02r4_chat.http_error_detail(
                    _k02r4_chat.CHAT_FORBIDDEN, "forbidden"))
        check_rate: RateHook = app.state.rate_hook
        if not check_rate(actor):
            raise HTTPException(
                status_code=429,
                detail=_k02r4_chat.http_error_detail(
                    _k02r4_chat.CHAT_RATE_LIMITED, "rate limited"))

        try:
            raw = await request.body()
        except Exception:
            raw = b""
        if not raw:
            return {
                "status": "accepted",
                "actor": actor,
                "live_parts": len(list_parts(None)),
            }
        try:
            body = await request.json()
        except Exception:
            body = None
        try:
            chat_request = _k02r4_chat.ChatStreamRequest.from_body(
                body, actor)
        except _k02r4_chat.ChatBadRequest as err:
            raise HTTPException(
                status_code=400,
                detail=_k02r4_chat.http_error_detail(
                    _k02r4_chat.CHAT_BAD_REQUEST, str(err))) from None
        # M-WIRE L0B-12: resolve the routed provider adapter at open
        # (start bind, then the per-project chat record) so the bridge
        # sees a connected provider with no test help.
        _k02r4_chat.bind_routed_provider_adapter(
            app, project_id=chat_request.project or None)
        bridge = _k02r4_chat.bridge_for_app(app)
        try:
            from agent_si.runtime import manager as _k04bud1_mgr
            from agent_si.backend import project_defaults as _k04bud1_defs

            _k04bud1_ctx = getattr(app.state, "k04_ctx", None)
            _k04bud1_gate = (getattr(_k04bud1_ctx, "budget_state", None)
                             if _k04bud1_ctx is not None else None)
            if _k04bud1_gate is not None and hasattr(
                    _k04bud1_mgr, "set_budget_gate"):
                _k04bud1_mgr.set_budget_gate(_k04bud1_gate)
            try:
                if chat_request.project and _k04bud1_gate is not None:
                    _k04bud1_pid = str(chat_request.project)
                    try:
                        _k04bud1_gate.get_state(_k04bud1_pid)
                    except (KeyError, LookupError):
                        _k04bud1_gate.configure_project(
                            _k04bud1_pid, _k04bud1_defs.CURRENCY,
                            _k04bud1_defs.BUDGET_LIMIT,
                            _k04bud1_defs.SOFT_LIMIT,
                            _k04bud1_defs.HARD_LIMIT)
            except Exception:
                pass
        except Exception:
            pass
        try:
            stream_id, events = bridge.run(chat_request)
        except _k02r4_graph.DispatchRejected as err:
            raise HTTPException(
                status_code=400,
                detail=_k02r4_chat.http_error_detail(
                    getattr(err, "code", None)
                    or _k02r4_chat.CHAT_DISPATCH_REJECTED,
                    str(err))) from None
        except _k02r4_chat.ChatStreamAbsent as err:
            if getattr(app.state, "k04_ctx", None) is not None:
                # Configured app with nothing bound: the terminal
                # NO_PROVIDER_BOUND error over HTTP 200 SSE, never a 404.
                # K04BIND1: surface the verbatim last failure reason.
                _reason: Any = None
                try:
                    _fac = getattr(getattr(app.state, "k04_ctx", None),
                                   "provider_facade", None)
                    _getter = getattr(_fac, "last_provider_error", None)
                    if callable(_getter):
                        _reason = _getter()
                except Exception:
                    _reason = None
                stream_id, events = bridge.no_provider_run(
                    chat_request, _reason)
            else:
                raise HTTPException(
                    status_code=404,
                    detail=_k02r4_chat.http_error_detail(
                        getattr(err, "code", None)
                        or _k02r4_chat.MANAGER_STREAM_ABSENT,
                        str(err))) from None
        except _k02r4_chat.ChatStreamFailed as err:
            raise HTTPException(
                status_code=500,
                detail=_k02r4_chat.http_error_detail(
                    getattr(err, "code", None)
                    or _k02r4_chat.MANAGER_STREAM_FAILED,
                    str(err))) from None
        return StreamingResponse(
            events,
            media_type="text/event-stream",
            headers={
                "x-stream-id": stream_id,
                "Cache-Control": "no-cache",
            },
        )

    # K08 HTTP surface (additions-only): configure + include the frozen
    # automation router, then register the five declared watcher routes.
    # Session tokens travel in the x-ui-session-token header (never the
    # URL); POST bodies carrying a session_token field keep working.
    import agent_si.backend.automation_routes as _k08_automation_routes

    _K08_WATCHER_IFACE_MODULE = "agent_si.watcher.interface"

    def _k08_watcher_iface():
        """Return the frozen watcher contract module object (late)."""
        import sys

        try:
            return sys.modules[_K08_WATCHER_IFACE_MODULE]
        except KeyError:
            import importlib

            return importlib.import_module(_K08_WATCHER_IFACE_MODULE)

    def _k08_setting(name):
        """Read one composition setting from a dict or an object."""
        if isinstance(settings, Mapping):
            return settings.get(name)
        return getattr(settings, name, None)

    _k08_auth = _k08_setting("auth_hook")
    _k08_rate = _k08_setting("rate_hook")
    _k08_factory = _k08_setting("model_factory")
    if _k08_factory is None:
        _k08_factory = model_factory

    def _k08_token_live(token):
        """True when the composed hooks (or the app token) accept it."""
        if _k08_auth is not None:
            try:
                return bool(_k08_auth(token))
            except TypeError:
                return bool(_k08_auth(token, "", USER_WRITE))
        return isinstance(token, str) and bool(token) and token == app_token

    if _k08_auth is not None:
        _k08_automation_routes.configure(_k08_auth, _k08_rate, _k08_factory)
    else:
        _k08_automation_routes.configure(
            lambda token: token == app_token, _k08_rate, _k08_factory
        )

    def _k08_drop_token(fn):
        """Drop the seam-validated session_token kwarg lanes ignore."""
        def _call(*args, **kwargs):
            kwargs.pop("session_token", None)
            return fn(*args, **kwargs)
        return _call

    for _k08_name in list(_k08_automation_routes._DISPATCH):
        _k08_automation_routes._DISPATCH[_k08_name] = _k08_drop_token(
            _k08_automation_routes._DISPATCH[_k08_name]
        )
    app.include_router(_k08_automation_routes.router)

    # K08R7 entry lane (row R-323 plus Q3; lane m_entry; author Sable):
    # sibling-router mount only; no other line in this file changes.
    import agent_si.backend.watcher_routes as _k08_watcher_routes

    if _k08_auth is not None:
        _k08_watcher_routes.configure(_k08_auth, _k08_rate, _k08_factory)
    else:
        _k08_watcher_routes.configure(
            lambda token: token == app_token, _k08_rate, _k08_factory
        )
    app.include_router(_k08_watcher_routes.router)

    _K08_WATCHER_STATUS_BY_CODE = {
        "SESSION_TOKEN_MISSING": 401,
        "SESSION_TOKEN_INVALID": 403,
        "RULE_NOT_FOUND": 404,
        "TRIGGER_NOT_FOUND": 404,
        "TEMPLATE_NOT_FOUND": 404,
        "SERVICE_NOT_FOUND": 404,
        "AUTOMATION_RUN_NOT_FOUND": 404,
        "PRESET_NOT_FOUND": 404,
        "JOURNAL_KIND_UNKNOWN": 404,
        "PAUSE_REASON_MISSING": 400,
        "STOP_REASON_MISSING": 400,
        "GOVERNANCE_MISMATCH": 409,
        "AUTOMATION_PAUSED": 409,
        "AUTOMATION_RUN_ACTIVE": 409,
        "SERVICE_CHECK_REFUSED": 409,
    }

    def _k08_watcher_dump(value):
        """Render dataclass/Enum payloads as plain JSON values."""
        import dataclasses as _k08_dataclasses
        import enum as _k08_enum

        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, _k08_enum.Enum):
            return value.value
        if _k08_dataclasses.is_dataclass(value):
            return {
                field.name: _k08_watcher_dump(getattr(value, field.name))
                for field in _k08_dataclasses.fields(value)
            }
        if isinstance(value, (tuple, list)):
            return [_k08_watcher_dump(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): _k08_watcher_dump(item)
                for key, item in value.items()
            }
        return value

    async def _k08_watcher_body(request):
        """Read a JSON object body, tolerating missing/bad payloads."""
        try:
            data = await request.json()
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _k08_watcher_token(request, data):
        """Session token: x-ui-session-token header first, body fallback."""
        header = request.headers.get("x-ui-session-token")
        if isinstance(header, str) and header:
            return header
        value = data.get("session_token")
        if isinstance(value, str) and value:
            return value
        return None

    def _k08_watcher_guard(request, data):
        """Refuse POSTs without a live token before any write happens."""
        token = _k08_watcher_token(request, data)
        if token is None:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "SESSION_TOKEN_MISSING",
                    "detail": "POST needs a live session token",
                },
            )
        if not _k08_token_live(token):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "SESSION_TOKEN_INVALID",
                    "detail": "unknown session token",
                },
            )
        if _k08_rate is not None:
            try:
                allowed = bool(_k08_rate(token))
            except Exception:
                allowed = False
            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "code": "RATE_LIMITED",
                        "detail": "rate hook refused",
                    },
                )
        return token

    def _k08_watcher_fail(code, detail=""):
        """Map a lane error code to its HTTP refusal."""
        raise HTTPException(
            status_code=_K08_WATCHER_STATUS_BY_CODE.get(code, 400),
            detail={"code": code, "detail": detail},
        )

    def _k08_watcher_call(route_key, *args, **kwargs):
        """Run one declared watcher entry point; the entry resolves late."""
        entry = _k08_watcher_iface().ROUTE_ENTRY_POINTS[route_key]
        try:
            return _k08_watcher_dump(
                getattr(_k08_watcher_iface(), entry)(*args, **kwargs)
            )
        except HTTPException:
            raise
        except Exception as err:
            code = getattr(err, "code", "")
            if not code:
                raise
            _k08_watcher_fail(code, getattr(err, "detail", "") or str(err))

    def register_watcher_routes(app):
        """Bind the five declared watcher routes to the seam app."""

        @app.get("/api/v1/watcher/status")
        def _k08_watcher_get_status(project_id: str):
            """GET /api/v1/watcher/status -> get_status (open)."""
            return _k08_watcher_call("GET /api/v1/watcher/status", project_id)

        @app.get("/api/v1/watcher/journal")
        def _k08_watcher_get_journal(project_id: str, kind: str = ""):
            """GET /api/v1/watcher/journal -> list_events (open)."""
            return _k08_watcher_call(
                "GET /api/v1/watcher/journal", project_id, kind
            )

        @app.post("/api/v1/watcher/integrity-check")
        async def _k08_watcher_post_integrity(request: Request):
            """POST /api/v1/watcher/integrity-check -> verify_integrity."""
            data = await _k08_watcher_body(request)
            token = _k08_watcher_guard(request, data)
            return _k08_watcher_call(
                "POST /api/v1/watcher/integrity-check",
                str(data.get("project_id", "")),
                session_token=token,
            )

        @app.post("/api/v1/watcher/rules/{id}/evaluate")
        async def _k08_watcher_post_evaluate(id: str, request: Request):
            """POST /api/v1/watcher/rules/{id}/evaluate -> evaluate_rule."""
            data = await _k08_watcher_body(request)
            token = _k08_watcher_guard(request, data)
            return _k08_watcher_call(
                "POST /api/v1/watcher/rules/{id}/evaluate",
                str(data.get("project_id", "")),
                id,
                session_token=token,
            )

        @app.post("/api/v1/stop-all")
        async def _k08_watcher_post_stop_all(request: Request):
            """POST /api/v1/stop-all -> stop_all_request_stop (token)."""
            data = await _k08_watcher_body(request)
            token = _k08_watcher_guard(request, data)
            return _k08_watcher_call(
                "POST /api/v1/stop-all",
                str(data.get("actor", "")),
                str(data.get("project_id", "")),
                grant_ref=str(data.get("grant_ref", "")),
                session_token=token,
            )

    register_watcher_routes(app)

    # M-WIRE R1: K03 + K09 + K05 routes through their real entry points
    # (function-local imports keep the composition root cycle-free; the
    # bound UI session token and hooks travel on app.state, never hardcoded).
    from agent_si.backend import kb_routes as _kb_routes
    from agent_si.backend import local_connect as _local_connect
    from agent_si.backend import localbench_routes as _localbench_routes
    from agent_si.test_runners import stage_runner as _stage_runner

    _kb_routes.register_kb_routes(app)
    from agent_si.backend.k09rows import k09b_router
    app.include_router(k09b_router)
    _local_connect.register_local_connect_routes(app)
    _localbench_routes.register_localbench_routes(app)
    _stage_runner.register_stage_routes(app)

    from agent_si.backend import assurance_mount as _k03mnt1_assurance_mount

    _k03mnt1_assurance_mount.register_assurance_routes(app)

    # K02R3: project/task read + console write routes (M-ROUTES). Reads
    # need no token; writes enforce the frozen USER_WRITE guard
    # themselves. Never touch the K04 block below.
    from agent_si.backend import console_projects_write as _k02r3_write
    from agent_si.backend import read_routes as _k02r3_read

    def _k02r3_store_dir(_settings: Any) -> str | None:
        # Same settings keys as the K04 lookup below (read-only
        # reference): when configured, project/task rows persist to
        # JSONL under this dir and hydrate on first bind; with no key
        # the ports stay purely in-memory.
        for _key in ("store_dir", "data_dir", "data_directory"):
            if isinstance(_settings, Mapping):
                if _key in _settings:
                    if not _settings[_key]:
                        raise ValueError(
                            f"K02R3 store setting {_key!r} is empty: pass "
                            "a real dir, never a silent tmp fallback")
                    return str(_settings[_key])
            elif _settings is not None and hasattr(_settings, _key):
                _val = getattr(_settings, _key)
                if not _val:
                    raise ValueError(
                        f"K02R3 store setting {_key!r} is empty: pass a "
                        "real dir, never a silent tmp fallback")
                return str(_val)
        return None

    app.state.k02r3_store_dir = _k02r3_store_dir(settings)
    from agent_si.telemetry import run_store as _l0c06_telemetry_store

    app.state.telemetry_store_dir = app.state.k02r3_store_dir
    _l0c06_telemetry_store.bind_store_dir(app.state.k02r3_store_dir)
    _k02r3_read.register_read_routes(app)
    _k02r3_write.register_console_projects_write_routes(app)

    # R349A project step limits (additions-only): GET+PUT surface plus
    # steplimits.json persistence owned by steplimit_routes; the K02 seam
    # above and the K04 block below are unchanged.
    from agent_si.backend import steplimit_routes as _r349_steplimits

    _r349_steplimits.register_steplimit_routes(app)

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

    from agent_si.backend import pools_routes as _k04_pr
    from agent_si.budget.gate import BudgetGate as _K04BudgetGate
    from agent_si.model_kb import kb_reader as _k04_kb_reader
    from agent_si.providers.registry import facades as _k04_facades
    import copy as _k04_copy
    from agent_si.routing.roles import RoleTable as _K04RoleTable
    from agent_si.routing.store import RoutingStore as _K04RoutingStore
    from agent_si.routing.telemetry_port import (
        TelemetryEmitter as _K04TelemetryEmitter)

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

    def _k04_secret_kind(_settings: Any) -> str:
        _raw: Any = None
        if isinstance(_settings, Mapping):
            if "secret_store" in _settings:
                _raw = _settings["secret_store"]
        elif _settings is not None and hasattr(_settings, "secret_store"):
            _raw = getattr(_settings, "secret_store")
        if isinstance(_raw, str) and _raw.strip():
            _low = _raw.strip().lower()
            if _low == "memory":
                return "memory"
            if _low == "os":
                return "os"
        if isinstance(_settings, Mapping):
            if _settings.get("testing") is True:
                return "memory"
        elif _settings is not None and getattr(
                _settings, "testing", None) is True:
            return "memory"
        return "os"

    def _k04_label_suffix(_settings: Any) -> str:
        _raw2: Any = None
        if isinstance(_settings, Mapping):
            if "secret_label_suffix" in _settings:
                _raw2 = _settings["secret_label_suffix"]
        elif _settings is not None and hasattr(
                _settings, "secret_label_suffix"):
            _raw2 = getattr(_settings, "secret_label_suffix")
        if isinstance(_raw2, str) and _raw2.strip():
            return _raw2.strip()
        return ""

    def _k04_save_timeout(_settings: Any) -> float:
        _raw3: Any = None
        if isinstance(_settings, Mapping):
            if "key_save_timeout_s" in _settings:
                _raw3 = _settings["key_save_timeout_s"]
        elif _settings is not None and hasattr(
                _settings, "key_save_timeout_s"):
            _raw3 = getattr(_settings, "key_save_timeout_s")
        try:
            _val = float(_raw3)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 5.0
        if _val > 0:
            return _val
        return 5.0

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
        _k04_kind = _k04_secret_kind(settings)
        _k04_suffix = _k04_label_suffix(settings)
        if _k04_kind == "memory":
            _k04_api, _k04_credstore, _k04_auditsink = \
                _k04_facades.memory_stack()
        else:
            try:
                _k04_api, _k04_credstore, _k04_auditsink = \
                    _k04_facades.os_stack(
                        label_suffix=_k04_suffix,
                        audit_path=_k04_os.path.join(
                            _k04_dir, "provider_audit.jsonl"))
            except Exception as _k04_os_exc:
                _k04_config_error = (
                    "K04 OS credential store unavailable: %s: %s"
                    % (type(_k04_os_exc).__name__, _k04_os_exc))
        if _k04_config_error is None:
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
            try:
                from agent_si.runtime import manager as _k04_mgr
                if hasattr(_k04_mgr, "set_budget_gate"):
                    _k04_mgr.set_budget_gate(_k04_ctx.budget_state)
            except Exception:
                pass
            try:

                class _ChatKbEnriched:
                    """KB reader plus connected models and preset catalogue.

                    Kit BUILD_PLAN 644-649: every model the connected
                    accounts offer; a field without a source is UNKNOWN.
                    Chat models are the connected plus evidenced providers
                    models (their connect model plus preset catalogue);
                    KB facts only enrich them.
                    """

                    def __init__(self, base: Any, facade: Any) -> None:
                        self._base = base
                        self._facade = facade

                    def facts(self, provider: str, model: str) -> Any:
                        try:
                            return self._base.facts(provider, model)
                        except Exception:
                            return None

                    def models(self, provider: Any = None) -> list:
                        try:
                            base_rows = list(self._base.models(provider) or [])
                        except Exception:
                            base_rows = []
                        try:
                            seen = set()
                            for row in base_rows:
                                try:
                                    p = str(getattr(row, "provider", "") or "")
                                    m = str(getattr(row, "model", "") or "")
                                except Exception:
                                    continue
                                if "/" in m:
                                    m = m.split("/")[-1]
                                seen.add((p, m))
                        except Exception:
                            seen = set()
                        extra: list = []
                        try:
                            from agent_si.model_kb import kb as _kbmod
                            from agent_si.model_kb import kb_reader as _kbr
                            from agent_si.providers.registry import (
                                presets as _presets)
                        except Exception:
                            return base_rows
                        try:
                            views = self._facade.list_providers(True)
                        except Exception:
                            views = []
                        wanted: list = []
                        for view in views or []:
                            try:
                                pid = str(getattr(view, "evidenced", False)
                                          and getattr(view, "provider_id", "")
                                          or "")
                            except Exception:
                                continue
                            if not pid:
                                continue
                            if provider is not None and pid != str(provider):
                                continue
                            wanted.append(pid)
                        if provider is not None and str(provider) not in wanted:
                            # listing for one provider still offers its
                            # catalogue even before evidence
                            wanted.append(str(provider))
                        for pid in wanted:
                            bare_models: list = []
                            try:
                                provs = getattr(self._facade, "_providers", {})
                                rec = provs.get(pid, {}) if isinstance(
                                    provs, dict) else {}
                                mmap = rec.get("models", {}) if isinstance(
                                    rec, dict) else {}
                                for val in (mmap.values() if isinstance(
                                        mmap, dict) else []):
                                    text = str(val or "")
                                    if "/" in text:
                                        head, _, tail = text.partition("/")
                                        if head == pid and tail:
                                            text = tail
                                    if text and text not in bare_models:
                                        bare_models.append(text)
                            except Exception:
                                pass
                            try:
                                preset = _presets.get_preset(pid)
                                cat = (preset or {}).get("catalogue", ()) or ()
                            except Exception:
                                cat = ()
                            for entry in cat or []:
                                text = str(entry or "")
                                if "/" in text:
                                    text = text.split("/")[-1]
                                if text and text not in bare_models:
                                    bare_models.append(text)
                            if pid == "meta":
                                try:
                                    mcat = tuple(
                                        _presets.META_CATALOGUE or ())
                                except Exception:
                                    mcat = ()
                                for entry in mcat:
                                    text = str(entry or "")
                                    if "/" in text:
                                        text = text.split("/")[-1]
                                    if text and text not in bare_models:
                                        bare_models.append(text)
                            for bare in bare_models:
                                if (pid, bare) in seen:
                                    continue
                                try:
                                    row = _kbmod.make_model_row(pid, bare)
                                    fact = _kbr.row_to_facts(row)
                                except Exception:
                                    continue
                                seen.add((pid, bare))
                                extra.append(fact)
                        return base_rows + extra

                _k04_ctx.kb = _ChatKbEnriched(
                    _k04_ctx.kb, _k04_ctx.provider_facade)
            except Exception:
                pass
            try:
                _k04_ctx.key_save_timeout_s = _k04_save_timeout(settings)
            except Exception:
                pass
            # PROVCK2/KEYECHO1: only allowlisted failure codes are ever
            # surfaced or restored (never exception text, never secret
            # bytes). Stale free-text reasons persisted on disk are
            # dropped, never re-surfaced.
            _PROVCK2_STORE_REASON = "credential store unavailable"
            _PROVCK2_SURFACED_STATIC = frozenset([
                "provider check failed",
                _PROVCK2_STORE_REASON,
                "evidence probe timed out after 10s",
                "usage probe returned UNKNOWN",
                "usage probe returned UNSUPPORTED",
            ])

            def _provck2_surfaced_ok(text: object) -> bool:
                try:
                    value = str(text or "")  # type: ignore[arg-type]
                except Exception:
                    return False
                if value in _PROVCK2_SURFACED_STATIC:
                    return True
                if value.startswith("provider answered HTTP "):
                    return value[len(
                        "provider answered HTTP "):].isdigit()
                return False

            # K04BIND1: re-bind persisted providers before the start bind.

            try:
                from agent_si.providers.registry import (
                    provider_store as _k04bind_store)
                for _rec in _k04bind_store.load_connections(_k04_dir):
                    try:
                        _pid = str((_rec or {}).get("provider_id") or "")
                        _model = str((_rec or {}).get("model") or "")
                        _kr = (_rec or {}).get("key_ref") or {}
                        _eref = (_rec or {}).get("evidence_ref")
                        _type = str((_rec or {}).get("type") or _pid)
                        _burl = str((_rec or {}).get("base_url") or "")
                        _inst = str((_rec or {}).get("instance_id")
                                    or "default")
                        if not _pid or not _model or not _burl:
                            continue
                        if not isinstance(_kr, dict) or not _kr.get(
                                "secret_id"):
                            continue
                        try:
                            _k04_api.register_provider(
                                {"provider_id": _pid, "type": _type,
                                 "base_url": _burl, "model": _model,
                                 "instance_id": _inst},
                                _kr,
                                instance_id=_inst,
                                evidence_ref=(str(_eref) if _eref else None),
                                mock=bool((_rec or {}).get("mock", False)))
                        except ValueError:
                            pass
                        _err = (_rec or {}).get("error")
                        # KEYECHO1: only codes/refs are restored; a stale
                        # free-text reason (possibly pre-fix leak bytes)
                        # is dropped, never re-surfaced.
                        if (isinstance(_err, str) and _err
                                and _provck2_surfaced_ok(_err)):
                            try:
                                _k04_api.set_provider_error(
                                    _pid, _inst, _err)
                            except Exception:
                                pass
                        elif _eref:
                            try:
                                _k04_api.clear_provider_error(_pid, _inst)
                            except Exception:
                                pass
                            try:
                                _k04_api.record_health(_pid, _inst, "ONLINE")
                            except Exception:
                                pass
                    except Exception:
                        continue
            except Exception:
                pass
    app.state.k04_ctx = _k04_ctx
    app.state.k04_config_error = _k04_config_error
    # M-WIRE L0B-12: bind the routed provider adapter at app start via
    # the K04 public API, so bridge_for_app sees
    # app.state.chat_provider_adapter with no test help. No connected
    # provider (or no K04) leaves it unset: the chat route then answers
    # the terminal NO_PROVIDER_BOUND event over HTTP 200 SSE. Never
    # raises: start stays total even when binding cannot complete.
    app.state.chat_provider_adapter = None
    if _k04_ctx is not None:
        try:
            from agent_si.backend import chat_stream as _wire_chat_bind

            _wire_chat_bind.bind_routed_provider_adapter(app)
        except Exception:
            pass

    # BEDEF1 ensure-at-start: projects loaded from the store that have no
    # budget state or step limits get the product starting values
    # (idempotent; an existing state is never overwritten).
    try:
        from agent_si.backend import project_defaults as _bedef1_defaults
        from agent_si.backend import read_routes as _bedef1_read

        _bedef1_projects, _bedef1_tasks = _bedef1_read.repos_for(app)
        for _bedef1_row in _bedef1_projects.list_by({}):
            _bedef1_pid = _bedef1_row.get("project_id")
            if _bedef1_pid and not _bedef1_row.get("archived"):
                _bedef1_defaults.ensure_project_defaults(app, _bedef1_pid)
    except Exception:
        pass

    # K04BIND1: evidence + persistence + rebind helpers (additions-only).
    # (KEYECHO1 reason codes/allowlist live above with the restore gate.)
    def _k04bind_scrub(text: str) -> str:
        try:
            out = str(text or "")
        except Exception:
            return "provider check failed"
        try:
            store = getattr(_k04_ctx, "credential_store", None)
            if store is not None:
                for attr in ("get_secret", "get", "retrieve", "read",
                             "get_secret_value"):
                    fn = getattr(store, attr, None)
                    if not callable(fn):
                        continue
                    try:
                        for sid in ("openai", "meta", "anthropic"):
                            try:
                                val = fn(sid)
                            except Exception:
                                continue
                            if isinstance(val, dict):
                                val = val.get("value", "")
                            if isinstance(val, str) and val and val in out:
                                out = out.replace(val, "[redacted]")
                    except Exception:
                        pass
        except Exception:
            pass
        return out

    def _k04bind_snapshot() -> list:
        try:
            api = getattr(_k04_ctx, "provider_facade", None)
            if api is None:
                return []
            rows = []
            providers = getattr(api, "_providers", {}) or {}
            for pid in sorted(providers):
                try:
                    view = api.get_provider(pid)
                    if view is None:
                        continue
                    try:
                        secret_desc = view.secret_ref.describe()
                    except Exception:
                        secret_desc = {"secret_id": "",
                                       "provider_id": pid}
                    try:
                        eref = api.get_evidence_ref(
                            pid, getattr(view, "instance_id", "default"))
                    except Exception:
                        eref = None
                    try:
                        err = api.get_provider_error(pid)
                    except Exception:
                        err = None
                    rows.append({
                        "provider_id": pid,
                        "model": str(
                            (providers[pid].get("models", {}) or {}).get(
                                getattr(view, "instance_id", "default"),
                                "") or ""),
                        "instance_id": str(getattr(
                            view, "instance_id", "default") or "default"),
                        "type": str(getattr(view, "type", "") or ""),
                        "base_url": str(getattr(view, "base_url", "") or ""),
                        "key_ref": dict(secret_desc) if isinstance(
                            secret_desc, dict) else {},
                        "evidence_ref": eref,
                        "health": str(getattr(view, "health", "") or ""),
                        "error": err,
                        "mock": bool(getattr(view, "mock", False)),
                    })
                except Exception:
                    continue
            return rows
        except Exception:
            return []

    def _k04bind_save() -> None:
        try:
            if _k04_dir is None:
                return
            from agent_si.providers.registry import (
                provider_store as _k04bind_pstore)
            _k04bind_pstore.save_connections(_k04_dir, _k04bind_snapshot())
        except Exception:
            pass

    # PROVCK2: connect-time preflight + allowlisted failure classes.
    # Surfaced reasons are fixed codes only (KEYECHO1: never exception
    # text, never secret bytes). The machine-readable class/code pair is
    # recorded on the audit sink (ids + codes + counts only, no values,
    # no text) so the next live run separates store-read vs network vs
    # HTTP without leaking anything. _PROVCK2_STORE_REASON and
    # _provck2_surfaced_ok are defined above (restore gate needs them).
    _PROVCK2_CODES = {
        "ok": "EVIDENCE_OK",
        "store-read": "CREDENTIAL_STORE_UNAVAILABLE",
        "network": "EVIDENCE_PROBE_NETWORK",
        "http": "PROVIDER_ANSWERED_HTTP",
        "probe-timeout": "EVIDENCE_PROBE_TIMEOUT",
        "unknown": "PROVIDER_CHECK_FAILED",
    }
    try:
        from agent_si.providers.adapters.base import (
            AdapterConfigError as _PROVCK2_STORE_EXC)
        from agent_si.providers.adapters.base import (
            TransportHttpError as _PROVCK2_HTTP_EXC)
        from agent_si.providers.adapters.base import (
            TransportTimeoutError as _PROVCK2_NET_EXC)
    except Exception:
        _PROVCK2_STORE_EXC = None
        _PROVCK2_HTTP_EXC = None
        _PROVCK2_NET_EXC = None

    def _provck2_audit(record: dict) -> None:
        try:
            _sink = getattr(_k04_ctx, "audit_sink", None)
            if _sink is None:
                return
            _sink.append(dict(record))
        except Exception:
            pass

    def _k04bind_evidence(pid: str, inst: str, model: str,
                          base_url: str, secret_map: dict) -> tuple:
        # K04BIND1: real check via the EXISTING usage_probe over the real
        # gateway transport (key from the store by ref, never echoed).
        _provck2_inst = str(inst or "default")
        _store_attempts = 0
        try:
            from agent_si.backend import chat_stream as _cs
            from agent_si.providers.adapters import legs as _legs
            from agent_si.providers.adapters import (
                usage_probe as _uprobe)
            try:
                _chat_path = _legs.leg_descriptor(pid)["chat_path"]
            except Exception:
                _chat_path = "/chat/completions"
            _store = getattr(_k04_ctx, "credential_store", None)
            # PROVCK2 preflight: prove the store entry reads BEFORE any
            # network I/O. One retry on a transient store-read failure
            # (each attempt is fully audited); then fail closed with the
            # allowlisted store-read code. The value is dropped at once.
            _sid = ""
            try:
                _sid = str((secret_map or {}).get("secret_id", "") or "")
            except Exception:
                _sid = ""
            _store_ok = False
            for _attempt in (1, 2):
                _store_attempts = _attempt
                try:
                    _preflight_value = _cs._read_secret_value(_store, _sid)
                except Exception:
                    _provck2_audit({
                        "event": "provck2-store-retry",
                        "provider_id": pid,
                        "instance_id": _provck2_inst,
                        "attempt": _attempt,
                        "outcome": ("retrying" if _attempt == 1
                                    else "exhausted"),
                    })
                    continue
                _store_ok = True
                try:
                    del _preflight_value
                except Exception:
                    pass
                if _attempt > 1:
                    _provck2_audit({
                        "event": "provck2-store-retry",
                        "provider_id": pid,
                        "instance_id": _provck2_inst,
                        "attempt": _attempt,
                        "outcome": "recovered",
                    })
                break
            if not _store_ok:
                _provck2_audit({
                    "event": "provck2-evidence",
                    "provider_id": pid,
                    "instance_id": _provck2_inst,
                    "class": "store-read",
                    "code": _PROVCK2_CODES["store-read"],
                    "store_attempts": _store_attempts,
                })
                return (False, _PROVCK2_STORE_REASON)
            _real = _cs._gateway_transport(base_url, _store, secret_map)
            _seen: dict = {}

            def _usage_trans(req: dict) -> dict:
                try:
                    reply = _real({
                        "model": model,
                        "messages": [{"role": "user",
                                      "content": "ping"}],
                        "max_tokens": 1,
                        "stream": False,
                        "chat_path": _chat_path,
                    })
                except Exception as _exc:
                    _seen["exc"] = _exc
                    raise
                usage = {}
                if isinstance(reply, dict):
                    usage = reply.get("usage", {})
                    if not isinstance(usage, dict):
                        usage = {}
                return {"usage": dict(usage)}

            def _run() -> dict:
                return _uprobe.probe_usage(pid, inst or "default",
                                            _usage_trans)
            import concurrent.futures as _fut
            with _fut.ThreadPoolExecutor(max_workers=1) as _pool:
                _future = _pool.submit(_run)
                try:
                    _cap = _future.result(timeout=10.0)
                except _fut.TimeoutError:
                    _provck2_audit({
                        "event": "provck2-evidence",
                        "provider_id": pid,
                        "instance_id": _provck2_inst,
                        "class": "probe-timeout",
                        "code": _PROVCK2_CODES["probe-timeout"],
                        "store_attempts": _store_attempts,
                    })
                    return (False, "evidence probe timed out after 10s")
            _state = ""
            try:
                _state = str((_cap or {}).get("state", "") or "")
            except Exception:
                _state = ""
            if _state in ("VERIFIED", "PARTIAL"):
                _provck2_audit({
                    "event": "provck2-evidence",
                    "provider_id": pid,
                    "instance_id": _provck2_inst,
                    "class": "ok",
                    "code": _PROVCK2_CODES["ok"],
                    "store_attempts": _store_attempts,
                })
                return (True, "")
            # PROVCK2 classification: fixed codes only, never exception
            # text (KEYECHO1). HTTP carries the int status; the store-read
            # class carries its own surfaced reason; network and unknown
            # stay on the generic code so no transport text can escape.
            _exc = _seen.get("exc")
            _cls = "unknown"
            _code = _PROVCK2_CODES["unknown"]
            _http_status = None
            _reason = "provider check failed"
            if (_exc is not None and _PROVCK2_HTTP_EXC is not None
                    and isinstance(_exc, _PROVCK2_HTTP_EXC)):
                try:
                    _maybe_status = getattr(_exc, "status", None)
                except Exception:
                    _maybe_status = None
                if (isinstance(_maybe_status, int)
                        and not isinstance(_maybe_status, bool)
                        and _maybe_status):
                    _http_status = _maybe_status
                    _cls = "http"
                    _code = _PROVCK2_CODES["http"]
                    _reason = "provider answered HTTP %d" % (_http_status,)
            elif (_exc is not None and _PROVCK2_STORE_EXC is not None
                    and isinstance(_exc, _PROVCK2_STORE_EXC)):
                _cls = "store-read"
                _code = _PROVCK2_CODES["store-read"]
                _reason = _PROVCK2_STORE_REASON
            elif isinstance(_exc, ((() if _PROVCK2_NET_EXC is None else _PROVCK2_NET_EXC),
                                   TimeoutError, ConnectionError, OSError)):
                _cls = "network"
                _code = _PROVCK2_CODES["network"]
                _reason = "provider check failed"
            elif _exc is None:
                _reason = "usage probe returned %s" % (_state or "UNKNOWN")
            _provck2_audit({
                "event": "provck2-evidence",
                "provider_id": pid,
                "instance_id": _provck2_inst,
                "class": _cls,
                "code": _code,
                **({"status": _http_status}
                   if _http_status is not None else {}),
                "store_attempts": _store_attempts,
            })
            return (False, _k04bind_scrub(_reason))
        except Exception:
            try:
                _provck2_audit({
                    "event": "provck2-evidence",
                    "provider_id": pid,
                    "instance_id": _provck2_inst,
                    "class": "unknown",
                    "code": _PROVCK2_CODES["unknown"],
                    "store_attempts": _store_attempts,
                })
            except Exception:
                pass
            return (False, "provider check failed")

    def _k04bind_rebind(force_clear: bool = False,
                        only_provider: str | None = None) -> None:
        try:
            from agent_si.backend import chat_stream as _cs2
            if force_clear:
                try:
                    cur = getattr(app.state, "chat_provider_adapter", None)
                    cur_pid = getattr(
                        getattr(cur, "config", None), "provider_id", "")
                    if only_provider is None or cur_pid == only_provider:
                        app.state.chat_provider_adapter = None
                        try:
                            _bridge = getattr(
                                app.state, "chat_stream_bridge", None)
                            if _bridge is not None:
                                _bridge._provider_adapter = None
                        except Exception:
                            pass
                    elif only_provider is not None:
                        return
                except Exception:
                    pass
            else:
                try:
                    app.state.chat_provider_adapter = None
                except Exception:
                    pass
            try:
                _new = _cs2.bind_routed_provider_adapter(app)
            except Exception:
                _new = None
            try:
                _bridge2 = getattr(app.state, "chat_stream_bridge", None)
                if _bridge2 is not None and _new is not None:
                    if getattr(_bridge2, "_provider_adapter", None) is None:
                        _bridge2._provider_adapter = _new
                    else:
                        _bridge2._provider_adapter = _new
            except Exception:
                pass
        except Exception:
            pass

    def _k04_make_endpoint(_fn: Callable, _is_write: bool,
                           _name: str = "") -> Callable:
        async def _k04_endpoint(request: Request) -> _K04JSONResponse:
            if _k04_config_error is not None:
                return _K04JSONResponse(
                    status_code=503,
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
            # HD ADDENDUM (K04P2-CHATSAVE): the chat-model save takes its
            # token ONLY from the x-ui-session-token header through the
            # K02 binding (a per-request ctx.session_token). The URL query
            # and the JSON body are never token channels here, so a
            # query-only token is refused with 401. Old routes keep the
            # shared write path below unchanged.
            _call_ctx: Any = _k04_ctx
            if _name == "put_chat_model":
                _header_token = request.headers.get("x-ui-session-token")
                if not (isinstance(_header_token, str)
                        and _header_token.strip()) \
                        or _header_token != app.state.ui_session_token:
                    return _K04JSONResponse(
                        status_code=401,
                        content={
                            "error": "chat save refused: a valid "
                                     "x-ui-session-token header is required "
                                     "(never in the URL query or the JSON "
                                     "body)",
                            "code": _k04_pr._USER_WRITE_DENIED_CODE,
                        })
                _call_ctx = _k04_copy.copy(_k04_ctx)
                _call_ctx.session_token = _header_token
                if getattr(_call_ctx, "emitter", None) is None:
                    _call_ctx.emitter = _K04TelemetryEmitter()
            elif _is_write:
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
                _call_ctx = _k04_copy.copy(_k04_ctx)
                _call_ctx.session_token = _token
            try:
                _status, _payload = _fn(_call_ctx, _query, _body)
            except Exception as _exc:
                return _K04JSONResponse(
                    status_code=500,
                    content={"error": "%s: %s" % (type(_exc).__name__,
                                                 _exc)})
            # K04BIND1: connect runs the real evidence check, persists and
            # re-binds; disconnect clears the bound adapter and persists.
            try:
                if _name == "connect_provider" and _status == 200:
                    _api = getattr(_k04_ctx, "provider_facade", None)
                    _prov = {}
                    try:
                        _prov = (_payload or {}).get("provider", {}) or {}
                    except Exception:
                        _prov = {}
                    _pid = str(_prov.get("provider_id", "") or "")
                    _inst = str(_prov.get("instance_id", "") or "default")
                    _model = ""
                    try:
                        _body_m = (_body or {}).get("model", "")
                        if isinstance(_body_m, str) and _body_m:
                            _model = _body_m
                    except Exception:
                        pass
                    if _api is not None and _pid and _model:
                        try:
                            _view0 = _api.get_provider(_pid)
                        except Exception:
                            _view0 = None
                        _burl = ""
                        _smap: dict = {}
                        try:
                            _burl = str(getattr(_view0, "base_url", "") or "")
                            _sref = getattr(_view0, "secret_ref", None)
                            _desc = _sref.describe() if hasattr(
                                _sref, "describe") else {}
                            if isinstance(_desc, dict):
                                _smap = {k: v for k, v in _desc.items()
                                         if k != "value"}
                        except Exception:
                            pass
                        if _burl and _smap:
                            _ok, _reason = _k04bind_evidence(
                                _pid, _inst, _model, _burl, _smap)
                            try:
                                if _ok:
                                    import datetime as _dt
                                    _eref = "connect-probe:%s/%s:%s" % (
                                        _pid, _inst,
                                        _dt.datetime.now(
                                            _dt.timezone.utc).isoformat())
                                    try:
                                        _api._registry.record_credential_evidence(
                                            _pid, _inst, _eref)
                                    except Exception:
                                        pass
                                    try:
                                        _api.clear_provider_error(_pid, _inst)
                                    except Exception:
                                        pass
                                    try:
                                        _api.record_health(_pid, _inst,
                                                           "ONLINE")
                                    except Exception:
                                        pass
                                else:
                                    try:
                                        _api.set_provider_error(
                                            _pid, _inst, _reason)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                            try:
                                _fresh = _api.get_provider(_pid)
                                if _fresh is not None:
                                    _payload = {"provider": _fresh.describe()}
                                    try:
                                        _err2 = _api.get_provider_error(_pid)
                                        if _err2:
                                            _payload["error"] = _err2
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                            try:
                                _k04bind_save()
                            except Exception:
                                pass
                            try:
                                if _fresh is not None and getattr(
                                        _fresh, "evidenced", False):
                                    _k04bind_rebind()
                            except Exception:
                                pass
                        else:
                            try:
                                _k04bind_save()
                            except Exception:
                                pass
                elif _name == "disconnect_provider" and _status == 200:
                    try:
                        _dpid = ""
                        try:
                            _dpid = str((_payload or {}).get(
                                "provider_id", "") or "")
                        except Exception:
                            pass
                        if not _dpid:
                            try:
                                _dpid = str((_query or {}).get("id", "") or "")
                            except Exception:
                                pass
                        _k04bind_save()
                    except Exception:
                        pass
                    try:
                        _k04bind_rebind(force_clear=True,
                                        only_provider=_dpid or None)
                    except Exception:
                        pass
                elif _name == "put_chat_model" and _status == 200:
                    try:
                        _k04bind_rebind(force_clear=True)
                    except Exception:
                        pass
            except Exception:
                pass
            return _K04JSONResponse(status_code=_status,
                                    content=_k04_jsonable(_payload))
        return _k04_endpoint

    for _method, _path, _name, _fn in _k04_pr.ROUTES:
        app.add_api_route(
            _path,
            _k04_make_endpoint(
                _fn, _method.lower() in _k04_pr._USER_WRITE_METHODS, _name),
            methods=[_method.upper()],
            name="k04_" + _name)

    try:
        from agent_si.providers.registry import key_routes as _k04_keys

        app.add_api_route(
            "/api/v1/providers/keys",
            _k04_make_endpoint(_k04_keys.save_key, True, "save_key"),
            methods=["POST"],
            name="k04_save_key")
    except Exception:
        pass

    # K13F1 routes: amend / finalize-read / stop over the real K13 entries.
    # Additions-only block: binds per-app in-memory K13 state on app.state
    # and registers the /api/v1/k13/ handlers. Writes keep the K02 guard
    # (401 missing x-actor, 403 bad token via app.state.auth_hook).
    from agent_si.backend import k13f1_routes as _k13f1_routes

    _k13f1_routes.bind_k13f1_state(app)
    _k13f1_routes.register_k13f1_routes(app)

    # --- K06 ask-UI routes (HD-authorised additions-only block). ---
    # HD_VERDICT_K06INT1: GET /sessions and POST /asks serve the K06 ask UI
    # (agent_si.backend.ui_session, lane A); no K02 brief or route owns them,
    # so route ownership is K06. This block only ADDS routes; no existing
    # line above changes. Tokens travel in the x-ui-session-token header
    # only, never in a URL.
    from agent_si.backend import ui_session as _k06_ui_session

    def _k06_session_payload(summary: Any) -> dict[str, Any]:
        return {
            "session_id": summary.session_id,
            "title": summary.title,
        }

    @app.get("/sessions")
    def k06_list_sessions() -> dict[str, Any]:
        """GET /sessions -> list_sessions over the real UI session store."""
        sessions = _k06_ui_session.list_sessions(
            store_path=_k06_ui_session._default_store_dir())
        return {"sessions": [_k06_session_payload(s) for s in sessions]}

    @app.post("/asks")
    async def k06_create_ask(request: Request) -> dict[str, Any]:
        """POST /asks -> create_ask_card; writes need a live header token."""
        actor = (request.headers.get("x-actor") or "").strip()
        if not actor:
            raise HTTPException(status_code=401,
                                detail="missing x-actor header")
        token = request.headers.get("x-ui-session-token")
        if not token:
            raise HTTPException(status_code=401,
                                detail="missing x-ui-session-token header")
        check_auth: AuthHook = app.state.auth_hook
        try:
            ok = bool(check_auth(token, actor, USER_WRITE))
        except Exception:
            ok = False
        if not ok:
            raise HTTPException(status_code=403, detail="forbidden")
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        raw_options = body.get("options", [])
        options = []
        if isinstance(raw_options, list):
            for raw in raw_options:
                if (isinstance(raw, dict) and raw.get("option_id")
                        and raw.get("label")):
                    options.append(
                        _k06_ui_session.AskOption(
                            option_id=str(raw["option_id"]),
                            label=str(raw["label"])))
        try:
            card = _k06_ui_session.create_ask_card(
                kind=body.get("kind", "approval"),
                summary=body.get("summary", ""),
                options=options,
                secret_ref=body.get("secret_ref"))
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {
            "ask_id": card.ask_id,
            "kind": card.kind,
            "summary": card.summary,
            "options": [{"option_id": o.option_id, "label": o.label}
                        for o in card.options],
            "resume_token": card.resume_token,
        }
    # --- K09-REFRESH stale KB copy refresh (LIVE0-06 additions-only). ---
    # Per-app recorded versions + changelog over local KB dirs (no
    # network; the KB dir is never mutated). GET proposal is an open read
    # that records the on-disk copy on the first call and reports
    # staleness with a section diff + version bump preview. POST apply
    # keeps the frozen USER_WRITE guard (401 missing x-actor, 403 bad
    # token via app.state.auth_hook, fail closed; the session token
    # travels in the x-ui-session-token header only, never in the URL).
    import datetime as _k09r_datetime
    import json as _k09r_json
    from pathlib import Path as _K09RPath

    from src.agent_si.kb import registry as _k09r_registry

    _K09R_UNKNOWN = "UNKNOWN"

    app.state.kb_refresh_recorded = {}
    app.state.kb_refresh_changelog = []

    def _k09r_source_version(kb_id: str) -> str:
        """On-disk manifest "version" string, else UNKNOWN (never guessed)."""
        try:
            _manifest = _k09r_json.loads(
                (_K09RPath(kb_id) / "manifest.json").read_text(
                    encoding="utf-8"))
        except (OSError, ValueError):
            return _K09R_UNKNOWN
        if not isinstance(_manifest, dict):
            return _K09R_UNKNOWN
        _version = _manifest.get("version")
        if not isinstance(_version, str) or not _version.strip():
            return _K09R_UNKNOWN
        return _version

    def _k09r_current_sections(kb_id: str) -> dict[str, Any]:
        """Current on-disk section texts keyed by section id."""
        _snapshot: dict[str, Any] = {}
        for _section_id in _k09r_registry.section_ids(kb_id):
            try:
                _snapshot[_section_id] = _k09r_registry.section_text(
                    kb_id, _section_id)
            except KeyError:
                continue
        return _snapshot

    def _k09r_diff(_recorded_sections: dict[str, Any],
                   _current_sections: dict[str, Any],
                   _recorded_version: str,
                   _source_version: str) -> dict[str, Any]:
        _current_ids = set(_current_sections)
        _recorded_ids = set(_recorded_sections)
        return {
            "added": sorted(_current_ids - _recorded_ids),
            "removed": sorted(_recorded_ids - _current_ids),
            "changed": sorted(
                _sid for _sid in _current_ids & _recorded_ids
                if _recorded_sections[_sid] != _current_sections[_sid]),
            "version_from": _recorded_version,
            "version_to": _source_version,
        }

    def _k09r_status(kb_id: str) -> dict[str, Any]:
        """Proposal payload; the first call records the on-disk copy."""
        _source_version = _k09r_source_version(kb_id)
        _current_sections = _k09r_current_sections(kb_id)
        _recorded = app.state.kb_refresh_recorded.get(kb_id)
        if _recorded is None:
            _recorded = {"recorded_version": _source_version,
                         "sections": _current_sections}
            app.state.kb_refresh_recorded[kb_id] = _recorded
        _recorded_version = _recorded["recorded_version"]
        _diff = _k09r_diff(_recorded["sections"], _current_sections,
                           _recorded_version, _source_version)
        _stale = (
            _source_version == _K09R_UNKNOWN
            or _recorded_version != _source_version
            or bool(_diff["added"] or _diff["removed"] or _diff["changed"]))
        return {"kb_id": kb_id,
                "stale": _stale,
                "recorded_version": _recorded_version,
                "source_version": _source_version,
                "diff": _diff}

    @app.get("/api/v1/kb/refresh/proposal")
    def _k09r_get_proposal(kb_id: str | None = None) -> dict[str, Any]:
        if not kb_id:
            _items: list[dict[str, Any]] = []
            for _known in sorted(app.state.kb_refresh_recorded):
                if _K09RPath(_known).is_dir():
                    _items.append(_k09r_status(_known))
            return {"kb_id": None,
                    "stale": any(_it["stale"] for _it in _items),
                    "proposals": _items}
        if not _K09RPath(kb_id).is_dir():
            raise HTTPException(status_code=404, detail="unknown kb_id")
        return _k09r_status(kb_id)

    @app.post("/api/v1/kb/refresh/apply")
    async def _k09r_post_apply(request: Request) -> dict[str, Any]:
        _actor = (request.headers.get("x-actor") or "").strip()
        if not _actor:
            raise HTTPException(status_code=401,
                                detail="missing x-actor header")
        _token = request.headers.get("x-ui-session-token")
        _check = getattr(app.state, "auth_hook", None)
        _allowed = False
        if callable(_check):
            try:
                _allowed = bool(_check(_token, _actor, USER_WRITE))
            except Exception:
                _allowed = False
        else:
            _expected = getattr(app.state, "ui_session_token", None)
            _allowed = (_expected is not None and _token == _expected)
        if not _allowed:
            raise HTTPException(status_code=403, detail="forbidden")
        try:
            _body = await request.json()
        except Exception:
            _body = None
        _kb_id = None
        if isinstance(_body, dict):
            _kb_id = _body.get("kb_id")
        if not _kb_id:
            _kb_id = request.query_params.get("kb_id")
        if not isinstance(_kb_id, str) or not _kb_id:
            raise HTTPException(status_code=400, detail="kb_id required")
        if not _K09RPath(_kb_id).is_dir():
            raise HTTPException(status_code=404, detail="unknown kb_id")
        _status = _k09r_status(_kb_id)
        if _status["source_version"] == _K09R_UNKNOWN:
            raise HTTPException(
                status_code=409,
                detail="unsourced version is never current evidence")
        if not _status["stale"]:
            return {"applied": False,
                    "kb_id": _kb_id,
                    "recorded_version": _status["recorded_version"],
                    "source_version": _status["source_version"]}
        _row = {"kb_id": _kb_id,
                "from": _status["recorded_version"],
                "to": _status["source_version"],
                "at": _k09r_datetime.datetime.now(
                    _k09r_datetime.timezone.utc).isoformat(),
                "actor": _actor}
        app.state.kb_refresh_recorded[_kb_id] = {
            "recorded_version": _status["source_version"],
            "sections": _k09r_current_sections(_kb_id)}
        app.state.kb_refresh_changelog.append(_row)
        return {"applied": True,
                "recorded_version": _status["source_version"],
                "source_version": _status["source_version"],
                **_row}

    return app
