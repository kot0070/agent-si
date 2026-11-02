"""FXCHATHIST + FXHARD1 chat history turns (served per-project store).

register_chat_history_routes(app) binds the per-project chat history
endpoints onto the passed-in FastAPI app (same pattern as
kb_routes.register_kb_routes and the K02R3 read/write modules):

  POST /api/v1/chat/history  token-guarded USER write storing one turn
  GET  /api/v1/chat/history  open read retrieving turns oldest-first

A turn is {project_id, user_text, assistant_text, time, id, status,
run_id, error_code}: extra body fields are never stored. Secret-shaped
text is scrubbed through the store-path redaction below (labelled
forms plus bare pasted key shapes); the scrub never raises and never
returns raw text on an internal failure.

Concurrency: appends take a per-project lock and the snapshot rewrite
is atomic (temp file + os.replace), so two fast appends never lose a
turn. A run start stores a running turn (user text + run id); the
terminal write upserts the same run id, so each run leaves one turn.
GET serves the newest 200 turns by default plus a `before` cursor for
earlier pages.

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
import re
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request

USER_WRITE = "USER_WRITE"

#: JSONL snapshot name under the bound store dir (file name only; the
#: dir itself comes from settings via backend/app.py, same as K02R3).
_HISTORY_FILE = "chat_history.jsonl"

#: Only these fields ever persist; anything else in the body is dropped.
_TURN_FIELDS = ("project_id", "user_text", "assistant_text", "time",
                "id", "status", "run_id", "error_code")

#: Stored turn states: a run starts as running, ends ok / failed /
#: stopped. Every terminal write lands, so restarts can show the last
#: state instead of dropping it.
_TURN_STATUSES = ("ok", "running", "failed", "stopped")

#: GET page size: the newest N turns plus a cursor for earlier pages.
_DEFAULT_LIMIT = 200
_MAX_LIMIT = 1000

#: Failure marker stored when the scrub itself breaks: never raw text.
_SCRUB_FAILED = "[redacted]"


#: One append lock per project: two fast appends to the same project
#: serialize, so neither turn is lost. The snapshot rewrite takes the
#: global snapshot lock on top (always project-then-snapshot order), so
#: the file replace never interleaves halfway.
_locks_guard = threading.Lock()
_project_locks: dict[str, threading.Lock] = {}
_snapshot_lock = threading.Lock()


def _lock_for(project: str) -> threading.Lock:
    """Per-project append lock, created once under the guard."""
    with _locks_guard:
        lock = _project_locks.get(project)
        if lock is None:
            lock = threading.Lock()
            _project_locks[project] = lock
        return lock


#: Labelled secret forms: label + (: or = or =>) + value. The value is
#: replaced, the label stays.
_LABEL_RE = re.compile(
    r"(api[_ -]?keys?|tokens?|secrets?|passwds?|passwords?|"
    r"credentials?|private[_ -]?keys?)"
    r"(\s*(=>|[:=])\s*)\S+",
    re.IGNORECASE,
)

#: One PEM private-key block (headers + base64 body + footer).
_PEM_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?"
    r"-----END [A-Z0-9 ]*PRIVATE KEY-----")

#: Bare pasted provider-style tokens (no label needed). Plain `sk-`
#: needs 20+ trailing chars so ordinary words never match; the named
#: prefixes are distinctive enough for a shorter tail.
_TOKEN_RES = (
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"gho_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[bpas]-[A-Za-z0-9-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"sk-live-[A-Za-z0-9-_]{8,}"),
    re.compile(r"sk-test-[A-Za-z0-9-_]{8,}"),
    re.compile(r"sk-ant-[A-Za-z0-9-_]{8,}"),
    re.compile(r"sk-proj-[A-Za-z0-9-_]{8,}"),
    re.compile(r"sk-[A-Za-z0-9-_]{20,}"),
)


def _scrub_bare(text: str) -> str:
    """Replace labelled values, PEM blocks and bare tokens."""
    out = _LABEL_RE.sub(
        lambda match: match.group(1) + match.group(2) + "[redacted]",
        text,
    )
    out = _PEM_RE.sub("[redacted]", out)
    for token_re in _TOKEN_RES:
        out = token_re.sub("[redacted]", out)
    return out


def _scrub(text: Any) -> str:
    """Scrub secret-shaped text; never raises, never returns raw text.

    Runs the shared redaction helper first (best effort), then the
    store-path bare-token set. Any internal failure stores the
    failure marker instead of the raw text.
    """
    try:
        raw = text if isinstance(text, str) else ""
        try:
            from agent_si.runtime.devrun.actions import (
                redact_text as _redact,
            )
        except Exception:
            _redact = None  # type: ignore[assignment]
        if _redact is not None:
            with contextlib.suppress(Exception):
                raw = str(_redact(raw))
        return _scrub_bare(raw)
    except Exception:
        return _SCRUB_FAILED


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
            legacy_seq = 0
            for row in _read_jsonl(
                    os.path.join(store_dir, _HISTORY_FILE)):
                project = row.get("project_id")
                if not (isinstance(project, str) and project.strip()):
                    continue
                turn = {key: row.get(key, "") for key in _TURN_FIELDS}
                turn["project_id"] = project.strip()
                if not isinstance(turn["time"], str) or not turn["time"]:
                    turn["time"] = _utcnow()
                if not isinstance(turn.get("id"), str) or not turn["id"]:
                    # Legacy rows predate server ids: a deterministic
                    # fallback keeps merge-by-id stable across restarts.
                    turn["id"] = "legacy-%s-%d" % (
                        turn["project_id"], legacy_seq)
                legacy_seq += 1
                if turn.get("status") not in _TURN_STATUSES:
                    turn["status"] = "ok"
                for key in ("run_id", "error_code"):
                    if not isinstance(turn.get(key), str):
                        turn[key] = ""
                turns.setdefault(turn["project_id"], []).append(turn)
    return turns


def _persist(app: Any) -> None:
    """Snapshot every turn to the bound store dir (no-op in-memory).

    Takes the snapshot lock; callers hold their project lock first, so
    an append plus its snapshot rewrite are one atomic step and two
    fast appends never lose a turn. The file replace itself is atomic.
    """
    with _snapshot_lock:
        store_dir = _store_dir(app)
        if not store_dir:
            return
        rows: list = []
        for project_turns in _memory(app).values():
            rows.extend(project_turns)
        _write_jsonl_atomic(os.path.join(store_dir, _HISTORY_FILE), rows)


def _new_turn_id() -> str:
    """One server id per turn (upserted runs keep the first one)."""
    return uuid.uuid4().hex


def record_turn(app: Any, project_id: str, user_text: str,
                assistant_text: str, *, status: str = "ok",
                run_id: str = "", error_code: str = "",
                turn_id: str = "") -> dict:
    """Store one scrubbed turn for a project; returns the stored turn.

    Atomic under the project's lock: the append plus its snapshot
    rewrite serialize with other appends to the same project. A
    non-empty run_id upserts the project's running turn with that id,
    so a run start (running) plus its terminal write leave one turn.
    """
    project = (project_id or "").strip()
    if not project:
        raise ValueError("chat history needs a non-empty project_id")
    if status not in _TURN_STATUSES:
        raise ValueError("chat history needs a known status")
    code = error_code if isinstance(error_code, str) else ""
    rid = run_id.strip() if isinstance(run_id, str) else ""
    lock = _lock_for(project)
    with lock:
        project_turns = _memory(app).setdefault(project, [])
        stored: dict | None = None
        if rid:
            for turn in project_turns:
                if turn.get("run_id") == rid and (
                        turn.get("status") == "running"):
                    turn["user_text"] = _scrub(user_text)
                    turn["assistant_text"] = _scrub(assistant_text)
                    turn["time"] = _utcnow()
                    turn["status"] = status
                    turn["error_code"] = code
                    stored = dict(turn)
                    break
        if stored is None:
            turn = {
                "project_id": project,
                "user_text": _scrub(user_text),
                "assistant_text": _scrub(assistant_text),
                "time": _utcnow(),
                "id": (turn_id.strip() if isinstance(turn_id, str)
                       and turn_id.strip() else _new_turn_id()),
                "status": status,
                "run_id": rid,
                "error_code": code,
            }
            project_turns.append(dict(turn))
            stored = dict(turn)
        _persist(app)
        return stored


def _copy_turns(app: Any, project: str) -> list:
    """Snapshot copies of one project's turns, oldest first."""
    with _snapshot_lock:
        return [dict(turn) for turn in _memory(app).get(project, [])]


def list_turns(app: Any, project_id: str, *, limit: int = _DEFAULT_LIMIT,
               before: str = "") -> list:
    """Return the stored turns for a project, oldest first.

    `before` is a turn id: only turns stored earlier than it return.
    The window holds the newest `limit` turns of that prefix.
    """
    page = history_page(app, project_id, limit=limit, before=before)
    return page["turns"]


def history_page(app: Any, project_id: str, *, limit: int = _DEFAULT_LIMIT,
                 before: str = "") -> dict:
    """One newest-first-window page: turns + cursor + total.

    `turns` are oldest-first within the window; `next_before` is the
    id to pass as `before` for the earlier page (None when the window
    already reaches the oldest turn); `total` counts the prefix.
    """
    project = (project_id or "").strip()
    if not project:
        raise ValueError("chat history needs a non-empty project_id")
    try:
        count = int(limit)
    except (TypeError, ValueError):
        count = _DEFAULT_LIMIT
    count = max(1, min(count, _MAX_LIMIT))
    turns = _copy_turns(app, project)
    if isinstance(before, str) and before.strip():
        cursor = before.strip()
        index = next(
            (pos for pos, turn in enumerate(turns)
             if turn.get("id") == cursor),
            None,
        )
        turns = turns[:index] if index is not None else []
    total = len(turns)
    window = turns[-count:] if total > count else list(turns)
    older = total - len(window)
    return {
        "turns": window,
        "next_before": window[0]["id"] if older > 0 else None,
        "total": total,
    }


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
                status=(body.get("status", "ok")
                        if isinstance(body.get("status"), str)
                        else "ok"),
                run_id=(body.get("run_id", "")
                        if isinstance(body.get("run_id"), str)
                        else ""),
                error_code=(body.get("error_code", "")
                            if isinstance(body.get("error_code"), str)
                            else ""),
            )
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from None

    @app.get("/api/v1/chat/history")
    async def read_chat_history(
        request: Request, project_id: str = "", limit: int = 200,
        before: str = "",
    ) -> dict:
        if not (isinstance(project_id, str) and project_id.strip()):
            raise HTTPException(
                status_code=400,
                detail="chat history needs ?project_id=",
            )
        try:
            return history_page(
                request.app, project_id.strip(), limit=limit,
                before=before if isinstance(before, str) else "")
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from None

    return app


__all__ = [
    "history_page",
    "list_turns",
    "record_turn",
    "register_chat_history_routes",
]
