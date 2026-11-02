"""Project team mode setting (FXTEAM M2 user switch).

register_teammode_routes(app) mounts GET + PUT
/api/v1/projects/{project_id}/team on the seam app. GET is an open
read served through the in-memory reader (unknown project -> honest
404). PUT keeps the frozen USER_WRITE guard (401 missing x-actor, 403
bad token), requires team as "on"/"off" (plain words), and persists
per project to devrun_team.json under app.state.k02r3_store_dir with
an atomic temp-file + os.replace write. Default is on: unknown or
unusable reads as on (team runs), only an explicit off disables the
Director/Manager/Auditor chain.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request

#: File name (only) of the saved team table under the store dir.
TEAM_MODE_FILE = "devrun_team.json"

#: Allowed values (plain words).
TEAM_ON = "on"
TEAM_OFF = "off"


@dataclass
class TeamOutcome:
    """One apply result: applied plus reason."""

    applied: bool
    reason: str


_TEAM_MODE: dict[str, str] = {}


def _reset_state() -> None:
    """Clear module state (test helper; never a product path)."""
    _TEAM_MODE.clear()


def _store_dir(app: Any) -> str | None:
    """Store dir bound by the K02R3 wiring (None keeps in-memory)."""
    return getattr(getattr(app, "state", None), "k02r3_store_dir", None)


def _saved_file(store_dir: str | None) -> str | None:
    if not store_dir:
        return None
    return os.path.join(store_dir, TEAM_MODE_FILE)


def load_saved_team(store_dir: str | None) -> dict:
    """Read the whole saved team table; missing/bad reads as empty."""
    path = _saved_file(store_dir)
    if path is None:
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (FileNotFoundError, ValueError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def saved_team_for(store_dir: str | None, project_id: str) -> str | None:
    """SAVED value for one project, or None when unusable (never raises)."""
    entry = load_saved_team(store_dir).get(project_id)
    if entry not in (TEAM_ON, TEAM_OFF):
        return None
    return entry


def team_for(project_id: str) -> str:
    """In-memory value for one project; unknown raises KeyError."""
    if project_id not in _TEAM_MODE:
        raise KeyError("no team setting for project %r" % (project_id,))
    return _TEAM_MODE[project_id]


def effective_team_for(store_dir: str | None, project_id: str) -> str | None:
    """Usable value: in-memory first, else SAVED, else None."""
    try:
        value = team_for(project_id)
    except (KeyError, LookupError):
        value = None
    except Exception:
        value = None
    if value is not None:
        return value
    return saved_team_for(store_dir, project_id)


def team_enabled_for(store_dir: str | None, project_id: str) -> bool:
    """True when the team runs (default on); only explicit off disables."""
    try:
        value = effective_team_for(store_dir, project_id)
    except Exception:
        return True
    return value != TEAM_OFF


def apply_team_change(project_id: str, value: Any) -> TeamOutcome:
    """Validate one team change, then apply it. Never raises."""
    if not isinstance(project_id, str) or not project_id:
        return TeamOutcome(
            applied=False,
            reason="POLICY_CONFLICT: project_id must be a non-empty string")
    if not isinstance(value, str) or value not in (TEAM_ON, TEAM_OFF):
        return TeamOutcome(
            applied=False,
            reason="POLICY_CONFLICT: team must be 'on' or 'off'")
    _TEAM_MODE[project_id] = value
    return TeamOutcome(applied=True, reason="applied")


def _write_json_atomic(path: str, payload: dict) -> None:
    """Persist payload as JSON via temp file in same folder + replace."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=parent or ".", prefix=".team-mode-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def persist_saved_team(app: Any, project_id: str, value: str) -> None:
    """Save one project's value; no-op without a store dir."""
    path = _saved_file(_store_dir(app))
    if path is None:
        return
    table = load_saved_team(_store_dir(app))
    table[project_id] = value
    _write_json_atomic(path, table)


def register_teammode_routes(app: Any) -> Any:
    """Mount the team GET+PUT routes; returns the app."""

    @app.get("/api/v1/projects/{project_id}/team")
    def get_team(project_id: str) -> dict:
        try:
            value = effective_team_for(_store_dir(app), project_id)
        except Exception:
            value = None
        if value is None:
            raise HTTPException(
                status_code=404,
                detail="unknown project %r" % (project_id,),
            ) from None
        return {"project_id": project_id, "team": value}

    @app.put("/api/v1/projects/{project_id}/team")
    async def put_team(project_id: str, request: Request) -> dict:
        from agent_si.backend import (
            console_projects_write as _console_write,
        )

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
        if "team" not in body:
            raise HTTPException(
                status_code=400,
                detail="POLICY_CONFLICT: body must carry team",
            ) from None
        outcome = apply_team_change(project_id, body["team"])
        if not outcome.applied:
            raise HTTPException(status_code=400, detail=outcome.reason)
        persist_saved_team(app, project_id, _TEAM_MODE[project_id])
        return {"project_id": project_id, "team": _TEAM_MODE[project_id]}

    return app
