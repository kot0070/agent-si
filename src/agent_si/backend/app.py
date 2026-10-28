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

    return app
