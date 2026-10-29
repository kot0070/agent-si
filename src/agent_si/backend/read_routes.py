"""K02R3 project/task READ routes (M-ROUTES).

register_read_routes(app) binds the read-only project/task endpoints onto
the passed-in FastAPI app (same pattern as kb_routes.register_kb_routes):
reads need no token. Project and task rows live in K13 repository ports
used as-is (ProjectRepository; load/append/compare_and_set/list_by with
ID_FIELD record_id); this module keeps no second store, no dict and no
in-route cache. Unknown ids give an honest 404. Shared repo access for
the console write module comes from repos_for(app).

Durability lives in K02 wiring only: when app.state.k02r3_store_dir
names a real dir (bound by the K02R3 section of backend/app.py), the
ports hydrate on first bind by replaying a JSONL file under that dir
via append, and every successful project/task write persists both ports
back to JSONL with an atomic temp-file + os.replace write. With no
store dir the ports stay purely in-memory. Only K13 public port methods
are used here; port internals are never touched.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from typing import Any

from fastapi import HTTPException, Request

from agent_si.backend import task_turns as _task_turns
from agent_si.backend.orchestration import steplimits as _steplimits
from agent_si.backend.project_defaults import TASK_MAX_STEPS
from agent_si.storage.repositories import ProjectRepository

#: JSONL snapshot names under the bound store dir (file names only;
#: the dir itself comes from settings via backend/app.py).
_PROJECTS_FILE = "k02r3_projects.jsonl"
_TASKS_FILE = "k02r3_tasks.jsonl"


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
                    f"k02r3 store row in {path!r} is not an object")
            rows.append(loaded)
    return rows


def _write_jsonl_atomic(path: str, rows: list) -> None:
    """Persist rows as JSONL via temp file in the same folder + replace."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=parent or ".", prefix=".k02r3-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
        os.replace(tmp_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def persist_k02r3_store(app: Any) -> None:
    """Snapshot both K02R3 ports to the bound store dir.

    No-op when no store dir is bound (in-memory behaviour unchanged).
    Called after every successful project/task write.
    """
    store_dir = _store_dir(app)
    if not store_dir:
        return
    projects = getattr(app.state, "k02r3_projects", None)
    tasks = getattr(app.state, "k02r3_tasks", None)
    project_rows = projects.list_by({}) if projects is not None else []
    task_rows = tasks.list_by({}) if tasks is not None else []
    _write_jsonl_atomic(os.path.join(store_dir, _PROJECTS_FILE),
                        project_rows)
    _write_jsonl_atomic(os.path.join(store_dir, _TASKS_FILE), task_rows)


def _hydrate_once(app: Any, projects: Any, tasks: Any) -> None:
    """Replay the store snapshots into fresh ports, once per app."""
    if getattr(app.state, "k02r3_hydrated", False):
        return
    app.state.k02r3_hydrated = True
    store_dir = _store_dir(app)
    if not store_dir:
        return
    for filename, port in ((_PROJECTS_FILE, projects),
                           (_TASKS_FILE, tasks)):
        for row in _read_jsonl(os.path.join(store_dir, filename)):
            port.append(dict(row))


def repos_for(app: Any) -> tuple:
    """Return the (projects, tasks) K13 ports for this app.

    Both ports are ProjectRepository used as-is: the project aggregate
    port holds project rows, and a second independent port instance
    holds task rows (every task row carries record_id + project_id, so
    the port mechanics and list_by({"project_id": ...}) apply unchanged).
    Ports live on app.state so reads and writes share one store per app.
    On first bind with a store dir configured, both ports hydrate from
    the JSONL snapshots via append.
    """
    projects = getattr(app.state, "k02r3_projects", None)
    if projects is None:
        projects = ProjectRepository()
        app.state.k02r3_projects = projects
    tasks = getattr(app.state, "k02r3_tasks", None)
    if tasks is None:
        tasks = ProjectRepository()
        app.state.k02r3_tasks = tasks
    _hydrate_once(app, projects, tasks)
    return projects, tasks


def project_view(record: Any) -> dict:
    """UI-parsable project shape (matches ProjectRecord zod schema)."""
    return {
        "project_id": record["project_id"],
        "name": record["name"],
        "folder_ref": record["folder_ref"],
        "created_at": record["created_at"],
    }


def task_view(record: Any) -> dict:
    """UI-parsable task shape (matches TaskRecord zod schema)."""
    return {
        "task_id": record["task_id"],
        "project_id": record["project_id"],
        "title": record["title"],
        "status": record["status"],
        "created_at": record["created_at"],
    }


def _visible_project(projects: Any, project_id: str) -> Any | None:
    stored = projects.load(project_id)
    if stored is None or stored.get("archived"):
        return None
    return stored


def register_read_routes(app: Any) -> Any:
    """Mount the K02R3 read routes on a FastAPI app; returns the app."""

    @app.get("/api/v1/projects")
    def list_projects() -> dict:
        projects, _tasks = repos_for(app)
        rows = [
            project_view(record)
            for record in projects.list_by({})
            if not record.get("archived")
        ]
        return {"projects": rows}

    @app.get("/api/v1/projects/{project_id}")
    def read_project(project_id: str) -> dict:
        projects, _tasks = repos_for(app)
        stored = _visible_project(projects, project_id)
        if stored is None:
            raise HTTPException(
                status_code=404,
                detail=f"unknown project {project_id!r}",
            )
        return {"project": project_view(stored)}

    @app.get("/api/v1/tasks")
    def list_tasks(request: Request) -> dict:
        project_id = request.query_params.get("project_id")
        if not project_id:
            raise HTTPException(
                status_code=400,
                detail="tasks list needs ?project_id=",
            )
        projects, tasks = repos_for(request.app)
        if _visible_project(projects, project_id) is None:
            raise HTTPException(
                status_code=404,
                detail=f"unknown project {project_id!r}",
            )
        rows = [
            task_view(record)
            for record in tasks.list_by({"project_id": project_id})
        ]
        return {"tasks": rows}

    @app.get("/api/v1/tasks/{task_id}")
    def read_task(task_id: str) -> dict:
        _projects, tasks = repos_for(app)
        stored = tasks.load(task_id)
        if stored is None:
            raise HTTPException(
                status_code=404,
                detail=f"unknown task {task_id!r}",
            )
        return {"task": task_view(stored)}

    @app.get("/api/v1/tasks/{task_id}/turns")
    def read_task_turns(task_id: str) -> dict:
        _projects, tasks = repos_for(app)
        stored = tasks.load(task_id)
        if stored is None:
            raise HTTPException(
                status_code=404,
                detail=f"unknown task {task_id!r}",
            )
        try:
            limit = _steplimits.limits_for(
                "task", stored.get("project_id"))
        except KeyError:
            limit = TASK_MAX_STEPS
        turns = _task_turns.list_turns(task_id)
        return {"turns": turns, "used": len(turns), "limit": limit}

    return app
