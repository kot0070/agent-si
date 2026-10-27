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

from agent_si.backend.orchestration import parts as _parts_store
from agent_si.backend.orchestration.ledger import PackageLedger, package_report
from agent_si.backend.orchestration.parts import PartRow, list_parts

USER_WRITE = "USER_WRITE"

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

    return app
