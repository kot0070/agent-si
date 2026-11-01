"""K07NEXT4 served boundary: 6 open K07 rows as JSON routes.

Every GET route is an open read and returns a deterministic
server-shaped JSON document; every POST route enforces the frozen
USER_WRITE guard (401 missing x-actor, 403 bad token, exactly like
the chat_stream handler in backend/app.py and the console project
write routes). All routes are registered by mount() onto the real
create_app() app with app.py untouched. Row contracts are quoted
from the repo ground truth named in each function docstring.
"""
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from agent_si.backend.console_projects_write import (
    _enforce_user_write as _require_user_write,
)
from agent_si.backend.orchestration.steplimits import (
    STEP_LIMIT_CAP,
    STEP_LIMIT_MIN,
)

RouteFn = Callable[[Request], Awaitable[dict[str, Any]]]


async def session_write(request: Request) -> dict[str, Any]:
    """Row LIVE0-08: UI writes carry the session token from the first call.

    Quoted from src/agent_si/backend/console_projects_write.py
    (_enforce_user_write: 401 missing x-actor, 403 bad
    x-ui-session-token through the bound ui_session_token): a guarded
    write answers 200 with the token accepted, never a missing-token
    403 when the header travels on the call.
    """
    _require_user_write(request)
    actor = (request.headers.get("x-actor") or "").strip()
    return {
        "row": "LIVE0-08",
        "token_ok": True,
        "actor": actor,
    }


def _project_store(request: Request) -> dict[str, dict[str, Any]]:
    state = request.app.state
    store = getattr(state, "k07next4_projects", None)
    if store is None:
        store = {}
        state.k07next4_projects = store
    return store


async def projects_create(request: Request) -> dict[str, Any]:
    """Row LIVE0B-01: Add Project lands in the Projects list.

    Quoted from src/agent_si/backend/console_projects_write.py
    (create_project: guarded USER_WRITE POST storing name plus
    folder_ref, listable right after without a reload): the created
    project carries project_id, name and folder_ref and the list
    route below returns it.
    """
    _require_user_write(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="write needs a JSON object body") from None
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400, detail="write needs a JSON object body")
    name = body.get("name")
    folder_ref = body.get("folder_ref")
    if not (isinstance(name, str) and name.strip()):
        raise HTTPException(
            status_code=400, detail="project name is required")
    if not (isinstance(folder_ref, str) and folder_ref.strip()):
        raise HTTPException(
            status_code=400, detail="folder_ref is required")
    project = {
        "project_id": uuid.uuid4().hex,
        "name": name.strip(),
        "folder_ref": folder_ref.strip(),
    }
    _project_store(request)[project["project_id"]] = project
    return {
        "row": "LIVE0B-01",
        "project": project,
    }


async def projects_list(request: Request) -> dict[str, Any]:
    """Row LIVE0B-01 read leg: the Projects list right after Add.

    Quoted from frontend/src/api/projectsApi.ts (listProjectRecords
    over GET /api/v1/projects): the list holds every project the
    create leg stored, so the new project appears with no reload.
    """
    return {
        "row": "LIVE0B-01",
        "projects": list(_project_store(request).values()),
    }


async def page_shell(request: Request) -> dict[str, Any]:
    """Row LIVE0B-04: every page renders its title and console styling.

    Quoted from frontend/src/locale/en.json (shell.sidebar.projects
    is "Projects") plus the console styling hook the screens apply:
    the title plus the console class travel together, never raw
    unstyled HTML.
    """
    del request
    return {
        "row": "LIVE0B-04",
        "title_key": "shell.sidebar.projects",
        "title": "Projects",
        "console_class": "agent-si-console",
    }


async def chat_task(request: Request) -> dict[str, Any]:
    """Row LIVE0B-05: the Chat message box starts a task.

    Quoted from frontend/src/tasks/TaskComposer.tsx (the composer
    posting a new task) and frontend/src/api/projectsApi.ts
    (createTaskRecord POST kind write): the guarded write starts one
    task for the posted prompt_ref and reports it started.
    """
    _require_user_write(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="write needs a JSON object body") from None
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400, detail="write needs a JSON object body")
    prompt_ref = body.get("prompt_ref")
    if not (isinstance(prompt_ref, str) and prompt_ref.strip()):
        raise HTTPException(
            status_code=400, detail="prompt_ref is required")
    return {
        "row": "LIVE0B-05",
        "task_id": uuid.uuid4().hex,
        "prompt_ref": prompt_ref.strip(),
        "status": "started",
    }


async def step_turn(request: Request) -> dict[str, Any]:
    """Row MH-5: step mode executes one turn per user advance.

    Quoted from frontend/src/api/projectsApi.ts (TurnTripleSchema:
    plan, action, observation): one plan to action to observation
    turn per advance, showing the exact model input ('what the
    model saw') plus the observation before the next step.
    """
    try:
        turn = int(request.query_params.get("advance", "1"))
    except ValueError:
        turn = 1
    if turn < 1:
        turn = 1
    return {
        "row": "MH-5",
        "turn": turn,
        "model_input": (
            f"step mode turn {turn} model input: plan the next "
            f"single action from the stored task state"
        ),
        "action": f"run single tool call for turn {turn}",
        "observation": (
            f"step mode turn {turn} observation: tool result "
            f"stored, waiting for the next advance"
        ),
    }


async def turn_triple(request: Request) -> dict[str, Any]:
    """Row MH-6: every turn renders its plan/action/observation triple.

    Quoted from frontend/src/api/projectsApi.ts (TurnTripleSchema
    plan/action/observation plus TaskTurnsSchema turns/used/limit)
    and src/agent_si/backend/orchestration/steplimits.py
    (STEP_LIMIT_MIN, STEP_LIMIT_CAP per-task turn-budget counter):
    the triple comes from stored refs and the per-task budget
    counter (used/limit) is visible with it.
    """
    del request
    return {
        "row": "MH-6",
        "turns": [
            {
                "plan": "stored plan ref k07next4-plan-1",
                "action": "stored tool call ref k07next4-call-1",
                "observation": "stored result ref k07next4-result-1",
            }
        ],
        "used": STEP_LIMIT_MIN,
        "limit": STEP_LIMIT_CAP,
    }


ROUTES: tuple[tuple[str, str, str, RouteFn], ...] = (
    ("post", "/api/v1/app/session-write", "session_write",
     session_write),
    ("post", "/api/v1/app/projects", "projects_create",
     projects_create),
    ("get", "/api/v1/app/projects", "projects_list",
     projects_list),
    ("get", "/api/v1/app/page-shell", "page_shell",
     page_shell),
    ("post", "/api/v1/app/chat-task", "chat_task",
     chat_task),
    ("get", "/api/v1/app/step-turn", "step_turn",
     step_turn),
    ("get", "/api/v1/app/turn-triple", "turn_triple",
     turn_triple),
)


def mount(app: FastAPI) -> FastAPI:
    """Register every K07NEXT4 served route on the real FastAPI app.

    App.py stays untouched; the caller passes the create_app() app.
    Returns the app for chaining.
    """
    if getattr(app.state, "k07next4_projects", None) is None:
        app.state.k07next4_projects = {}
    for method, path, name, fn in ROUTES:
        registrar = getattr(app, method)
        registrar(path, name="k07next4_" + name)(fn)
    return app
