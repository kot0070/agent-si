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
answers honestly: the seam chat entry keeps no live-stream registry,
so every stream_id is an honest 404 (see the module note below).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request

from agent_si.backend.read_routes import (
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
        return {"ok": True}

    async def _create_task(request: Request, project_id: str) -> dict:
        _enforce_user_write(request)
        projects, tasks = repos_for(request.app)
        if _stored_project(projects, project_id) is None:
            raise _unknown_project(project_id)
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
        task_id = _new_id()
        record = {
            "record_id": task_id,
            "project_id": project_id,
            "task_id": task_id,
            "title": title.strip(),
            "scope": list(scope),
            "status": "CREATED",
            "created_at": _utcnow(),
        }
        stored = tasks.append(record)
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
        # Guarded as a USER write. The seam chat entry (chat_stream in
        # backend/app.py) is stateless: it accepts a prompt, returns no
        # stream ids and keeps no live-stream registry on the app, so no
        # stream_id can name a live run. Answer an honest 404 rather than
        # a faked {ok: true} until a real live-run engine entry reachable
        # from the app exists (NOT-DONE waits-for-HD row).
        _enforce_user_write(request)
        body = await _json_body(request)
        stream_id = body.get("stream_id")
        if not (isinstance(stream_id, str) and stream_id.strip()):
            raise HTTPException(
                status_code=400,
                detail="chat cancel needs a non-empty stream_id")
        raise HTTPException(
            status_code=404,
            detail=f"no live chat stream {stream_id.strip()!r}",
        )

    return app
