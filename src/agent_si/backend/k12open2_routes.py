"""K12OPEN2 served contributions ledger.

register_k12open2_routes(app) mounts exactly two routes on the seam
app: POST /api/v1/contributions (USER_WRITE guard, EMPTY_PACKAGE_ID on
a blank or omitted package_id, DUPLICATE_PACKAGE_ID on a repeat, else
the recorded {contribution}) and GET /api/v1/contributions (open read
of the recorded contributions). Writes keep the frozen USER_WRITE
guard (401 missing x-actor, 403 bad token); every refusal body carries
{code, message}.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from agent_si.backend.app import USER_WRITE

#: Refusal when the x-actor header is blank.
ACTOR_MISSING = "ACTOR_MISSING"

#: Refusal when the session token does not verify.
FORBIDDEN = "FORBIDDEN"

#: Refusal when the contribution package_id is already recorded.
DUPLICATE_PACKAGE_ID = "DUPLICATE_PACKAGE_ID"

#: Refusal when the contribution package_id is blank or omitted.
EMPTY_PACKAGE_ID = "EMPTY_PACKAGE_ID"


def _refuse(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"code": code, "message": message}
    )


def _guard(request: Request) -> JSONResponse | None:
    """Frozen USER_WRITE guard; None when the write may proceed."""
    actor = (request.headers.get("x-actor") or "").strip()
    if not actor:
        return _refuse(401, ACTOR_MISSING, "missing x-actor header")
    token = request.headers.get("x-ui-session-token")
    state = getattr(request.app, "state", None)
    auth_hook = getattr(state, "auth_hook", None)
    allowed = False
    if callable(auth_hook):
        try:
            allowed = bool(auth_hook(token, actor, USER_WRITE))
        except Exception:
            allowed = False
    else:
        expected = getattr(state, "ui_session_token", None)
        allowed = (
            state is not None and expected is not None and token == expected
        )
    if not allowed:
        return _refuse(403, FORBIDDEN, "forbidden")
    return None


async def _json_body(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def register_k12open2_routes(app: Any) -> Any:
    """Mount the K12OPEN2 contributions POST+GET routes; returns the app."""
    if getattr(getattr(app, "state", None), "k12_contributions", None) is None:
        app.state.k12_contributions = {}

    @app.post("/api/v1/contributions")
    async def post_contributions(request: Request) -> Any:
        refused = _guard(request)
        if refused is not None:
            return refused
        body = await _json_body(request)
        package_id = body.get("package_id")
        if not (isinstance(package_id, str) and package_id.strip()):
            return _refuse(
                400, EMPTY_PACKAGE_ID, "contribution needs a non-empty package_id"
            )
        store = app.state.k12_contributions
        if package_id in store:
            return _refuse(
                409, DUPLICATE_PACKAGE_ID, "package_id already recorded"
            )
        recorded_at = body.get("recorded_at")
        if not (isinstance(recorded_at, str) and recorded_at.strip()):
            recorded_at = _dt.date.today().isoformat()
        entry = {
            "package_id": package_id,
            "evidence_ref": body.get("evidence_ref"),
            "recorded_at": recorded_at,
        }
        store[package_id] = entry
        return {"contribution": entry}

    @app.get("/api/v1/contributions")
    async def get_contributions() -> Any:
        return {"contributions": list(app.state.k12_contributions.values())}

    return app
