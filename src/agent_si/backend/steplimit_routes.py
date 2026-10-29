"""Project step-limits HTTP surface (R349A).

register_steplimit_routes(app) mounts GET + PUT
/api/v1/projects/{project_id}/step-limits on the seam app. GET is an open
read served only through the frozen steplimits.limits_for reader (unknown
project -> honest 404). PUT keeps the frozen USER_WRITE guard (401 missing
x-actor, 403 bad token), requires BOTH task_max_steps and chat_max_steps,
fills the server-owned audit trio, and delegates ALL validation to the
frozen apply_steplimit_config_change writer (applied=false -> HTTP 400
carrying outcome.reason). A successful PUT persists {task, chat} per
project to steplimits.json under app.state.k02r3_store_dir with an atomic
temp-file + os.replace write (no-op when no store dir is bound), so the
start hook can restore SAVED values after a restart.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from typing import Any

from fastapi import HTTPException, Request

#: File name (only) of the saved step limits under the bound store dir.
STEP_LIMITS_FILE = "steplimits.json"

_OWNER_AUTHORITY = "project-owner"
_UPDATE_REASON = "update project step limits"


def _store_dir(app: Any) -> str | None:
    """Store dir bound by the K02R3 wiring (None keeps in-memory)."""
    return getattr(getattr(app, "state", None), "k02r3_store_dir", None)


def _saved_file(store_dir: str | None) -> str | None:
    if not store_dir:
        return None
    return os.path.join(store_dir, STEP_LIMITS_FILE)


def load_saved_limits(store_dir: str | None) -> dict:
    """Read the whole saved-limits table; missing/bad file reads as empty."""
    path = _saved_file(store_dir)
    if path is None:
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (FileNotFoundError, ValueError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def saved_limits_for(store_dir: str | None,
                     project_id: str) -> tuple[int, int] | None:
    """SAVED (task, chat) pair for one project, or None when unusable."""
    entry = load_saved_limits(store_dir).get(project_id)
    if not isinstance(entry, dict):
        return None
    task = entry.get("task")
    chat = entry.get("chat")
    for value in (task, chat):
        if isinstance(value, bool) or not isinstance(value, int):
            return None
    return (task, chat)


def _write_json_atomic(path: str, payload: dict) -> None:
    """Persist payload as JSON via temp file in the same folder + replace."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=parent or ".", prefix=".steplimits-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def persist_saved_limits(app: Any, project_id: str,
                         task_max_steps: int, chat_max_steps: int) -> None:
    """Save one project's {task, chat} pair; no-op without a store dir."""
    path = _saved_file(_store_dir(app))
    if path is None:
        return
    table = load_saved_limits(_store_dir(app))
    table[project_id] = {"task": task_max_steps, "chat": chat_max_steps}
    _write_json_atomic(path, table)


def register_steplimit_routes(app: Any) -> Any:
    """Mount the R349A step-limits GET+PUT routes; returns the app."""

    @app.get("/api/v1/projects/{project_id}/step-limits")
    def get_step_limits(project_id: str) -> dict:
        from agent_si.backend.orchestration import steplimits as _steplimits

        try:
            task = _steplimits.limits_for("task", project_id)
            chat = _steplimits.limits_for("chat", project_id)
        except (KeyError, LookupError):
            raise HTTPException(
                status_code=404,
                detail="unknown project %r" % (project_id,),
            ) from None
        return {
            "project_id": project_id,
            "task_max_steps": task,
            "chat_max_steps": chat,
        }

    @app.put("/api/v1/projects/{project_id}/step-limits")
    async def put_step_limits(project_id: str, request: Request) -> dict:
        from agent_si.backend import (
            console_projects_write as _console_write,
        )
        from agent_si.backend.orchestration import steplimits as _steplimits

        _console_write._enforce_user_write(request)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="write needs a JSON body",
            ) from None
        if not isinstance(body, dict):
            raise HTTPException(
                status_code=400,
                detail="write needs a JSON object body",
            ) from None
        if "task_max_steps" not in body or "chat_max_steps" not in body:
            raise HTTPException(
                status_code=400,
                detail="POLICY_CONFLICT: body must carry both "
                "task_max_steps and chat_max_steps",
            ) from None
        outcome = _steplimits.apply_steplimit_config_change(
            {
                "project_id": project_id,
                "task_max_steps": body["task_max_steps"],
                "chat_max_steps": body["chat_max_steps"],
                "authority": _OWNER_AUTHORITY,
                "reason": _UPDATE_REASON,
                "statement": "step limits for project %s" % (project_id,),
            }
        )
        if not outcome.applied:
            raise HTTPException(status_code=400, detail=outcome.reason)
        task_value = _steplimits.limits_for("task", project_id)
        chat_value = _steplimits.limits_for("chat", project_id)
        persist_saved_limits(request.app, project_id, task_value, chat_value)
        return {
            "project_id": project_id,
            "task_max_steps": task_value,
            "chat_max_steps": chat_value,
            "decision_ref": outcome.decision_ref,
        }

    return app
