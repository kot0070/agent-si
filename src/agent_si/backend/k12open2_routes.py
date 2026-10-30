"""K12OPEN2 served routes (rows R-350 + HC-3).

register_k12open2_routes(app) mounts exactly two routes on the seam
app: POST /api/v1/k12open2/public-text/check (USER_WRITE guard,
EMPTY_IDEA_TEXT on a blank or omitted idea_text, else {ok, violations}
from public_text.check_idea) and POST /api/v1/k12open2/submission/scan
(USER_WRITE guard, EMPTY_SUBMISSION when no files and blank notes, else
{ok, findings} from secretscan.scan_files). Writes keep the frozen
USER_WRITE guard (401 missing x-actor, 403 bad token); every refusal
body carries {code, message}.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from agent_si.backend import public_text as _public_text
from agent_si.backend import secretscan as _secretscan
from agent_si.backend.app import USER_WRITE

#: Refusal when the x-actor header is blank.
ACTOR_MISSING = "ACTOR_MISSING"

#: Refusal when the session token does not verify.
FORBIDDEN = "FORBIDDEN"

#: Refusal when idea_text is blank or omitted.
EMPTY_IDEA_TEXT = "EMPTY_IDEA_TEXT"

#: Refusal when the submission carries no files and blank notes.
EMPTY_SUBMISSION = "EMPTY_SUBMISSION"

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
    """Mount the two K12OPEN2 routes plus the contributions ledger; returns the app."""
    if getattr(getattr(app, "state", None), "k12_contributions", None) is None:
        app.state.k12_contributions = {}

    @app.post("/api/v1/k12open2/public-text/check")
    async def post_k12open2_public_text_check(request: Request) -> Any:
        refused = _guard(request)
        if refused is not None:
            return refused
        body = await _json_body(request)
        idea_text = body.get("idea_text")
        if not (isinstance(idea_text, str) and idea_text.strip()):
            return _refuse(
                400, EMPTY_IDEA_TEXT, "check needs a non-empty idea_text"
            )
        violations = _public_text.check_idea(
            idea_text,
            presentation=body.get("presentation"),
            video_demo=body.get("video_demo"),
        )
        return {"ok": not violations, "violations": violations}

    @app.post("/api/v1/k12open2/submission/scan")
    async def post_k12open2_submission_scan(request: Request) -> Any:
        refused = _guard(request)
        if refused is not None:
            return refused
        body = await _json_body(request)
        raw_files = body.get("files")
        files = raw_files if isinstance(raw_files, list) else []
        notes = body.get("notes")
        has_files = len(files) > 0
        has_notes = isinstance(notes, str) and bool(notes.strip())
        if not has_files and not has_notes:
            return _refuse(
                400, EMPTY_SUBMISSION, "scan needs files or notes"
            )
        findings = _secretscan.scan_files(files, notes)
        return {"ok": not findings, "findings": findings}

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
