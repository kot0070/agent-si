"""K02R3 console project/task WRITE routes + chat cancel (M-ROUTES).

register_console_projects_write_routes(app) binds the USER-write
endpoints onto the passed-in FastAPI app (same pattern as
kb_routes.register_kb_routes). Every write enforces the frozen
USER_WRITE guard itself (401 missing x-actor, 403 bad token via
app.state.auth_hook against app.state.ui_session_token, exactly like
the chat_stream handler in backend/app.py); refused writes never reach
storage. Rows live in the K13 repository ports shared with read_routes
(repos_for(app)); this module keeps no second store, no dict and no
in-route cache. Unknown ids give an honest 404.

Chat cancel (POST /api/v1/chat/cancel) is guarded the same way and
ends a live stream by stream_id through the shared chat bridge
(agent_si.backend.chat_stream); unknown ids stay an honest 404.
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request

from agent_si.backend.read_routes import (
    persist_k02r3_store,
    project_view,
    repos_for,
    task_view,
)
from agent_si.storage.repositories import (
    RecordNotFoundError,
    VersionConflictError,
)

USER_WRITE = "USER_WRITE"


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


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
            status_code=400, detail="write needs a JSON body") from None
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400, detail="write needs a JSON object body")
    return body


def _stored_project(projects: Any, project_id: str) -> Any | None:
    stored = projects.load(project_id)
    if stored is None or stored.get("archived"):
        return None
    return stored


def _new_id() -> str:
    return uuid.uuid4().hex


def _unknown_project(project_id: str) -> HTTPException:
    return HTTPException(
        status_code=404, detail=f"unknown project {project_id!r}")


def _new_task_record(project_id: str, title: str, scope: list) -> dict:
    """Build one task row in the shared task shape (not yet stored)."""
    task_id = _new_id()
    return {
        "record_id": task_id,
        "project_id": project_id,
        "task_id": task_id,
        "title": title.strip(),
        "scope": list(scope),
        "status": "CREATED",
        "created_at": _utcnow(),
    }


def append_task_record(app: Any, project_id: str, title: str,
                       scope: list) -> dict:
    """Append one task row through the shared K13 ports, then persist.

    The single write path behind both HTTP task creates and the
    first-chat hook: unknown/archived projects refuse with the honest
    404; the stored row is returned.
    """
    projects, tasks = repos_for(app)
    if _stored_project(projects, project_id) is None:
        raise _unknown_project(project_id)
    stored = tasks.append(_new_task_record(project_id, title, scope))
    persist_k02r3_store(app)
    return stored


def ensure_first_chat_task(app: Any, project_id: str, message: str,
                           chat_task: str = "") -> dict | None:
    """Store one task row per accepted chat message (FXBATCH5-B2).

    Every accepted chat message stores ONE row through the shared
    append_task_record path: the stripped message text is the title
    (the task path caps nothing beyond non-empty, so no further
    truncation applies) with an empty scope. Nothing is stored when
    the project already holds a task with the same stripped title,
    or when the named chat task already exists. Skip (None) only:
    an empty project id, an unknown or archived project, or an
    empty stripped message.

    Never raises: every skip and every write failure yields None so
    the chat stream continues whole; write failures are logged. No
    key or secret is ever read or stored here: secrets travel as
    SecretRef refs only, and the task path has no redaction step to
    reuse, so none applies.
    """
    logger = logging.getLogger(__name__)
    project = (project_id or "").strip()
    if not project:
        return None
    text = (message or "").strip()
    if not text:
        logger.debug("fxchattask: skip empty message, stream continues")
        return None
    try:
        projects, tasks = repos_for(app)
        if _stored_project(projects, project) is None:
            logger.debug(
                "fxchattask: skip unknown/archived project %r", project)
            return None
        name = (chat_task or "").strip()
        if name and tasks.load(name) is not None:
            return None
        for row in tasks.list_by({"project_id": project}):
            if str(row.get("title", "")).strip() == text:
                return None
        stored = append_task_record(app, project, text, [])
    except Exception:
        logger.exception(
            "fxchattask: first-chat task write failed for project %r; "
            "stream continues", project)
        return None
    return stored


def mirror_run_task_status(app: Any, project_id: str, task_id: str,
                           message: str, status: str) -> int:
    """Mirror one run's state onto its task rows, best effort.

    Sets the named run task plus every same-project row titled exactly
    with the run's message (the first-chat auto task, whose id never
    matches the run's task) to status through compare_and_set, then
    persists once. Returns the mirrored row count. Unknown project or
    task, empty inputs, or any write failure: no-op (0), never raises,
    so the stream never breaks.
    """
    try:
        project = (project_id or "").strip()
        wanted = (status or "").strip()
        if not project or not wanted:
            return 0
        text = (message or "").strip()
        name = (task_id or "").strip()
        if not text and not name:
            return 0
        _projects, tasks = repos_for(app)
        targets: dict[str, dict] = {}
        if name:
            try:
                stored = tasks.load(name)
            except Exception:
                stored = None
            if isinstance(stored, dict) and str(
                    stored.get("project_id") or "") == project:
                targets[name] = stored
        if text:
            try:
                rows = list(tasks.list_by({"project_id": project}))
            except Exception:
                rows = []
            for row in rows:
                try:
                    if not isinstance(row, dict):
                        continue
                    if str(row.get("title", "")).strip() != text:
                        continue
                    key = row.get("record_id") or row.get("task_id")
                    if key and key not in targets:
                        targets[str(key)] = row
                except Exception:
                    continue
        mirrored = 0
        for key, stored in targets.items():
            try:
                updated = dict(stored)
                updated["status"] = wanted
                tasks.compare_and_set(key, stored.get("version"), updated)
                mirrored += 1
            except Exception:
                continue
        if mirrored:
            with contextlib.suppress(Exception):
                persist_k02r3_store(app)
        return mirrored
    except Exception:
        return 0


def register_console_projects_write_routes(app: Any) -> Any:
    """Mount the K02R3 write routes on a FastAPI app; returns the app."""

    @app.post("/api/v1/projects")
    async def create_project(request: Request) -> dict:
        _enforce_user_write(request)
        body = await _json_body(request)
        name = body.get("name")
        folder_ref = body.get("folder_ref")
        if not (isinstance(name, str) and name.strip()):
            raise HTTPException(
                status_code=400,
                detail="project needs a non-empty name")
        if not (isinstance(folder_ref, str) and folder_ref.strip()):
            raise HTTPException(
                status_code=400,
                detail="project needs a non-empty folder_ref")
        projects, _tasks = repos_for(request.app)
        project_id = _new_id()
        record = {
            "record_id": project_id,
            "project_id": project_id,
            "name": name.strip(),
            "folder_ref": folder_ref.strip(),
            "created_at": _utcnow(),
            "archived": False,
        }
        stored = projects.append(record)
        persist_k02r3_store(request.app)
        from agent_si.backend import project_defaults as _project_defaults

        _project_defaults.ensure_project_defaults(request.app, project_id)
        return {"project": project_view(stored)}

    @app.put("/api/v1/projects/{project_id}")
    async def update_project(project_id: str, request: Request) -> dict:
        _enforce_user_write(request)
        projects, _tasks = repos_for(request.app)
        stored = _stored_project(projects, project_id)
        if stored is None:
            raise _unknown_project(project_id)
        body = await _json_body(request)
        name = body.get("name", None)
        updated = dict(stored)
        if name is not None:
            if not (isinstance(name, str) and name.strip()):
                raise HTTPException(
                    status_code=400,
                    detail="project name must be a non-empty string "
                    "or null",
                )
            updated["name"] = name.strip()
        updated["updated_at"] = _utcnow()
        try:
            saved = projects.compare_and_set(
                project_id, stored.get("version"), updated)
        except RecordNotFoundError:
            raise _unknown_project(project_id) from None
        except VersionConflictError:
            raise HTTPException(
                status_code=409, detail="project changed; re-read"
            ) from None
        persist_k02r3_store(request.app)
        return {"project": project_view(saved)}

    @app.delete("/api/v1/projects/{project_id}")
    async def delete_project(project_id: str, request: Request) -> dict:
        _enforce_user_write(request)
        projects, _tasks = repos_for(request.app)
        stored = _stored_project(projects, project_id)
        if stored is None:
            raise _unknown_project(project_id)
        updated = dict(stored)
        updated["archived"] = True
        updated["updated_at"] = _utcnow()
        try:
            projects.compare_and_set(
                project_id, stored.get("version"), updated)
        except RecordNotFoundError:
            raise _unknown_project(project_id) from None
        except VersionConflictError:
            raise HTTPException(
                status_code=409, detail="project changed; re-read"
            ) from None
        persist_k02r3_store(request.app)
        return {"ok": True}

    async def _create_task(request: Request, project_id: str) -> dict:
        _enforce_user_write(request)
        body = await _json_body(request)
        title = body.get("title")
        scope = body.get("scope")
        if not (isinstance(title, str) and title.strip()):
            raise HTTPException(
                status_code=400,
                detail="task needs a non-empty title")
        if not (
            isinstance(scope, list)
            and all(isinstance(item, str) for item in scope)
        ):
            raise HTTPException(
                status_code=400,
                detail="task needs a scope list of strings")
        stored = append_task_record(
            request.app, project_id, title.strip(), list(scope))
        return {"task": task_view(stored)}

    @app.post("/api/v1/projects/{project_id}/tasks")
    async def create_project_task(
        project_id: str, request: Request
    ) -> dict:
        return await _create_task(request, project_id)

    @app.post("/api/v1/tasks")
    async def create_task(request: Request) -> dict:
        project_id = request.query_params.get("project_id")
        if not project_id:
            raise HTTPException(
                status_code=400,
                detail="task create needs ?project_id=",
            )
        return await _create_task(request, project_id)

    @app.post("/api/v1/chat/cancel")
    async def cancel_chat(request: Request) -> dict:
        # K02R4 engine entry: guarded as a USER write; ends a live
        # stream by stream_id through the shared chat bridge. Unknown
        # ids stay an honest 404, never a faked {ok: true}.
        _enforce_user_write(request)
        body = await _json_body(request)
        stream_id = body.get("stream_id")
        if not (isinstance(stream_id, str) and stream_id.strip()):
            raise HTTPException(
                status_code=400,
                detail="chat cancel needs a non-empty stream_id")
        from agent_si.backend import chat_stream as _k02r4_chat

        bridge = _k02r4_chat.bridge_for_app(request.app)
        name = stream_id.strip()
        if not bridge.cancel(name):
            raise HTTPException(
                status_code=404,
                detail=f"no live chat stream {name!r}",
            )
        return {"ok": True, "stream_id": name}

    return app
