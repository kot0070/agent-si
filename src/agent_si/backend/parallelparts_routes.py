"""Project parallel-parts setting (FXPARALLEL user switch).

register_parallelparts_routes(app) mounts GET + PUT
/api/v1/projects/{project_id}/parallel-parts on the seam app. GET is an
open read served through the in-memory reader (unknown project -> honest
404). PUT keeps the frozen USER_WRITE guard (401 missing x-actor, 403 bad
token), requires max_parallel_parts as an integer 1..4, and delegates ALL
validation to the apply_parallel_change writer (applied=false -> HTTP 400
carrying outcome.reason). A successful PUT persists the value per project
to devrun_parallel.json under app.state.k02r3_store_dir with an atomic
temp-file + os.replace write (no-op when no store dir is bound), so a
restarted app reads the SAVED value back through effective_parallel_for
without touching the frozen R349A step-limits surface (its GET shape and
steplimits.json entries are pinned by test_steplimits_r349.py).
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request

#: File name (only) of the saved parallel-parts table under the store dir.
PARALLEL_PARTS_FILE = "devrun_parallel.json"

#: Hard bounds of the user-facing setting (1..4, default 1 = sequential).
PARALLEL_MIN = 1
PARALLEL_MAX = 4
PARALLEL_DEFAULT = 1

_OWNER_AUTHORITY = "project-owner"
_UPDATE_REASON = "update project parallel parts"


@dataclass
class ParallelOutcome:
    """One apply result: applied plus reason (mirrors steplimits.ApplyOutcome)."""

    applied: bool
    reason: str


_PROJECT_PARALLEL: dict[str, int] = {}


def _reset_state() -> None:
    """Clear module state (test helper; never a product path)."""
    _PROJECT_PARALLEL.clear()


def _store_dir(app: Any) -> str | None:
    """Store dir bound by the K02R3 wiring (None keeps in-memory)."""
    return getattr(getattr(app, "state", None), "k02r3_store_dir", None)


def _saved_file(store_dir: str | None) -> str | None:
    if not store_dir:
        return None
    return os.path.join(store_dir, PARALLEL_PARTS_FILE)


def load_saved_parallel(store_dir: str | None) -> dict:
    """Read the whole saved-parallel table; missing/bad file reads as empty."""
    path = _saved_file(store_dir)
    if path is None:
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (FileNotFoundError, ValueError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def saved_parallel_for(store_dir: str | None,
                       project_id: str) -> int | None:
    """SAVED value for one project, or None when unusable (never raises)."""
    entry = load_saved_parallel(store_dir).get(project_id)
    if isinstance(entry, bool) or not isinstance(entry, int):
        return None
    if entry < PARALLEL_MIN or entry > PARALLEL_MAX:
        return None
    return entry


def parallel_for(project_id: str) -> int:
    """In-memory value for one project; unknown project raises KeyError."""
    if project_id not in _PROJECT_PARALLEL:
        raise KeyError("no parallel-parts setting for project %r"
                       % (project_id,))
    return _PROJECT_PARALLEL[project_id]


def effective_parallel_for(store_dir: str | None,
                           project_id: str) -> int | None:
    """Usable value: in-memory first, else the SAVED file, else None."""
    try:
        value = parallel_for(project_id)
    except (KeyError, LookupError):
        value = None
    except Exception:
        value = None
    if value is not None:
        return value
    return saved_parallel_for(store_dir, project_id)


def apply_parallel_change(project_id: str, value: Any) -> ParallelOutcome:
    """Validate one parallel-parts change, then apply it. Never raises."""
    if not isinstance(project_id, str) or not project_id:
        return ParallelOutcome(
            applied=False,
            reason="POLICY_CONFLICT: project_id must be a non-empty string")
    if isinstance(value, bool) or not isinstance(value, int):
        return ParallelOutcome(
            applied=False,
            reason="POLICY_CONFLICT: max_parallel_parts must be an integer")
    if value < PARALLEL_MIN or value > PARALLEL_MAX:
        return ParallelOutcome(
            applied=False,
            reason=("POLICY_CONFLICT: max_parallel_parts %d outside "
                    "range %d..%d" % (value, PARALLEL_MIN, PARALLEL_MAX)))
    _PROJECT_PARALLEL[project_id] = value
    return ParallelOutcome(applied=True, reason="applied")


def _write_json_atomic(path: str, payload: dict) -> None:
    """Persist payload as JSON via temp file in the same folder + replace."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=parent or ".", prefix=".parallel-parts-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def persist_saved_parallel(app: Any, project_id: str, value: int) -> None:
    """Save one project's value; no-op without a store dir."""
    path = _saved_file(_store_dir(app))
    if path is None:
        return
    table = load_saved_parallel(_store_dir(app))
    table[project_id] = value
    _write_json_atomic(path, table)


def register_parallelparts_routes(app: Any) -> Any:
    """Mount the parallel-parts GET+PUT routes; returns the app."""

    @app.get("/api/v1/projects/{project_id}/parallel-parts")
    def get_parallel_parts(project_id: str) -> dict:
        try:
            value = effective_parallel_for(_store_dir(app), project_id)
        except Exception:
            value = None
        if value is None:
            raise HTTPException(
                status_code=404,
                detail="unknown project %r" % (project_id,),
            ) from None
        return {
            "project_id": project_id,
            "max_parallel_parts": value,
        }

    @app.put("/api/v1/projects/{project_id}/parallel-parts")
    async def put_parallel_parts(project_id: str, request: Request) -> dict:
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
        if "max_parallel_parts" not in body:
            raise HTTPException(
                status_code=400,
                detail="POLICY_CONFLICT: body must carry "
                "max_parallel_parts",
            ) from None
        outcome = apply_parallel_change(
            project_id, body["max_parallel_parts"])
        if not outcome.applied:
            raise HTTPException(status_code=400, detail=outcome.reason)
        persist_saved_parallel(app, project_id,
                               _PROJECT_PARALLEL[project_id])
        return {
            "project_id": project_id,
            "max_parallel_parts": _PROJECT_PARALLEL[project_id],
        }

    return app
