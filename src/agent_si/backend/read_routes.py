"""K02R3 project/task READ routes (M-ROUTES).

register_read_routes(app) binds the read-only project/task endpoints onto
the passed-in FastAPI app (same pattern as kb_routes.register_kb_routes):
reads need no token. Project and task rows live in K13 repository ports
used as-is (ProjectRepository; load/append/compare_and_set/list_by with
ID_FIELD record_id); this module keeps no second store, no dict and no
in-route cache. Unknown ids give an honest 404. Shared repo access for
the console write module comes from repos_for(app).
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from agent_si.storage.repositories import ProjectRepository


def repos_for(app: Any) -> tuple:
    """Return the (projects, tasks) K13 ports for this app.

    Both ports are ProjectRepository used as-is: the project aggregate
    port holds project rows, and a second independent port instance
    holds task rows (every task row carries record_id + project_id, so
    the port mechanics and list_by({"project_id": ...}) apply unchanged).
    Ports live on app.state so reads and writes share one store per app.
    """
    projects = getattr(app.state, "k02r3_projects", None)
    if projects is None:
        projects = ProjectRepository()
        app.state.k02r3_projects = projects
    tasks = getattr(app.state, "k02r3_tasks", None)
    if tasks is None:
        tasks = ProjectRepository()
        app.state.k02r3_tasks = tasks
    return projects, tasks


def project_view(record: Any) -> dict:
    """UI-parsable project shape (matches ProjectRecord zod schema)."""
    return {
        "project_id": record["project_id"],
        "name": record["name"],
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
        projects, tasks = repos_for(app)
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

    return app
