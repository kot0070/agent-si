"""FXCHATHIST chat history turns (Part 1, NOT wired into chat yet).

register_chat_history_routes(app) binds the per-project chat history
endpoints onto the passed-in FastAPI app (same pattern as
kb_routes.register_kb_routes and the K02R3 read/write modules):

  POST /api/v1/chat/history  token-guarded USER write storing one turn
  GET  /api/v1/chat/history  open read retrieving turns oldest-first

A turn is {project_id, user_text, assistant_text, time} only: no key
or secret is ever stored (extra body fields are ignored, never
persisted). Secret-shaped text is scrubbed through the redaction
helper on the path (agent_si.runtime.devrun.actions.redact_text).

Durability mirrors read_routes: when app.state.k02r3_store_dir names a
real dir (bound by the K02R3 section of backend/app.py), turns hydrate
on first bind by replaying chat_history.jsonl under that dir, and every
successful write persists back with an atomic temp-file + os.replace
write. With no store dir the history stays purely in-memory.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request

USER_WRITE = "USER_WRITE"

#: JSONL snapshot name under the bound store dir (file name only; the
#: dir itself comes from settings via backend/app.py, same as K02R3).
_HISTORY_FILE = "chat_history.jsonl"

#: Only these fields ever persist; anything else in the body is dropped.
_TURN_FIELDS = ("project_id", "user_text", "assistant_text", "time")


def _scrub(text: Any) -> str:
    """Scrub secret-shaped text via the redaction helper on the path."""
    try:
        from agent_si.runtime.devrun.actions import (
            redact_text as _redact,
        )
    except Exception:
        _redact = None  # type: ignore[assignment]
    raw = text if isinstance(text, str) else ""
    if _redact is not None:
        try:
            return str(_redact(raw))
        except Exception:
            return raw
    return raw


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _store_dir(app: Any) -> str | None:
    """Store dir bound by the K02R3 wiring (None keeps in-memory)."""
    return getattr(getattr(app, "state", None), "k02r3_store_dir", None)


def _read_jsonl(path: str) -> list:
    """Read a JSONL snapshot; a missing file replays as empty."""
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except FileNotFoundError:
        return []
    rows = []
    for line in text.splitlines():
        if line.strip():
            loaded = json.loads(line)
            if not isinstance(loaded, dict):
                raise ValueError(
                    f"chat history row in {path!r} is not an object")
            rows.append(loaded)
    return rows


def _write_jsonl_atomic(path: str, rows: list) -> None:
    """Persist rows as JSONL via temp file in the same folder + replace."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=parent or ".", prefix=".chathist-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
        os.replace(tmp_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def _memory(app: Any) -> dict:
    """Per-app in-memory turns {project_id: [turn, ...]} (hydrated once)."""
    state = getattr(app, "state", None)
    turns = getattr(state, "chat_history_turns", None)
    if turns is None:
        turns = {}
        if state is not None:
            state.chat_history_turns = turns
            state.chat_history_hydrated = False
    if state is not None and not getattr(
            state, "chat_history_hydrated", False):
        state.chat_history_hydrated = True
        store_dir = _store_dir(app)
        if store_dir:
            for row in _read_jsonl(
                    os.path.join(store_dir, _HISTORY_FILE)):
                project = row.get("project_id")
                if not (isinstance(project, str) and project.strip()):
                    continue
                turn = {key: row.get(key, "") for key in _TURN_FIELDS}
                turn["project_id"] = project.strip()
                turns.setdefault(turn["project_id"], []).append(turn)
    return turns


def _persist(app: Any) -> None:
    """Snapshot every turn to the bound store dir (no-op in-memory)."""
    store_dir = _store_dir(app)
    if not store_dir:
        return
    rows: list = []
    for project_turns in _memory(app).values():
        rows.extend(project_turns)
    _write_jsonl_atomic(os.path.join(store_dir, _HISTORY_FILE), rows)


def record_turn(app: Any, project_id: str, user_text: str,
                assistant_text: str) -> dict:
    """Store one scrubbed turn for a project; returns the stored turn."""
    project = (project_id or "").strip()
    if not project:
        raise ValueError("chat history needs a non-empty project_id")
    turn = {
        "project_id": project,
        "user_text": _scrub(user_text),
        "assistant_text": _scrub(assistant_text),
        "time": _utcnow(),
    }
    _memory(app).setdefault(project, []).append(dict(turn))
    _persist(app)
    return dict(turn)


def list_turns(app: Any, project_id: str) -> list:
    """Return the stored turns for a project, oldest first."""
    project = (project_id or "").strip()
    if not project:
        raise ValueError("chat history needs a non-empty project_id")
    return [dict(turn) for turn in _memory(app).get(project, [])]


def _enforce_user_write(request: Request) -> None:
    """Frozen USER_WRITE guard (mirrors chat_stream in backend/app.py).

    401 for a missing x-actor header, 403 for a bad x-ui-session-token
    checked through request.app.state.auth_hook (falling back to the
    bound ui_session_token); fails closed when nothing verifiable exists.
    """
    actor = (request.headers.get("x-actor") or "").strip()
    if not actor:
        raise HTTPException(
            status_code=401, detail="missing x-actor header")
    token = request.headers.get("x-ui-session-token")
    state = getattr(request.app, "state", None)
    auth_hook = getattr(state, "auth_hook", None)
    if callable(auth_hook):
        try:
            allowed = bool(auth_hook(token, actor, USER_WRITE))
        except Exception:
            allowed = False
        if not allowed:
            raise HTTPException(status_code=403, detail="forbidden")
        return
    expected = getattr(state, "ui_session_token", None)
    if state is None or expected is None or token != expected:
        raise HTTPException(status_code=403, detail="forbidden")


async def _json_body(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=400, detail="chat history needs a JSON body"
        ) from None
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400, detail="chat history needs a JSON object body")
    return body


def register_chat_history_routes(app: Any) -> Any:
    """Mount the chat history routes on a FastAPI app; returns the app."""

    @app.post("/api/v1/chat/history")
    async def create_chat_turn(request: Request) -> dict:
        _enforce_user_write(request)
        body = await _json_body(request)
        try:
            return record_turn(
                request.app,
                body.get("project_id", ""),
                body.get("user_text", ""),
                body.get("assistant_text", ""),
            )
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from None

    @app.get("/api/v1/chat/history")
    async def read_chat_history(
        request: Request, project_id: str = ""
    ) -> dict:
        if not (isinstance(project_id, str) and project_id.strip()):
            raise HTTPException(
                status_code=400,
                detail="chat history needs ?project_id=",
            )
        return {"turns": list_turns(request.app, project_id.strip())}

    return app


__all__ = [
    "list_turns",
    "record_turn",
    "register_chat_history_routes",
]
