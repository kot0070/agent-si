"""K07NEXT2 split-A served boundary: 8 open K07 rows as GET JSON routes.

Every route is an open read (no token), returns a deterministic
server-shaped JSON document, and is registered by mount() onto the
real create_app() app with app.py untouched. Row contracts are quoted
from the repo ground truth named in each function docstring.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI


def context_card() -> dict[str, Any]:
    """Row M-P4-159: context 70/85 card with source and recorded action.

    Thresholds plus the served-budget source follow
    frontend/src/projects/projectsApi.ts (contextUsage, CONTEXT_SOURCE)
    with the source endpoint frontend/src/api/endpoints.ts
    ("/api/v1/budget").
    """
    return {
        "row": "M-P4-159",
        "card": "chat-context-card",
        "warn_pct": 70,
        "severe_pct": 85,
        "source": "/api/v1/budget",
        "recorded_action": "one entry per threshold crossing,"
                           " idempotent on re-render",
    }


def channel_lane() -> dict[str, Any]:
    """Row M-D-D5: channel evaluation persisted before socket use.

    Fail-closed lane with a pinned address, following
    src/agent_si/services/channel_eval.py (evaluation record durable
    before any socket use; temp file plus os.replace; store
    agent_si_channel_eval.jsonl) and
    src/agent_si/services/channel_socket.py (only a persisted allow
    verdict reaches the socket; socket waits at most timeout seconds;
    _MAX_TIMEOUT 60.0).
    """
    return {
        "row": "M-D-D5",
        "evaluation": "persisted before socket use",
        "fail_closed": True,
        "pinned_address": True,
        "store": "agent_si_channel_eval.jsonl",
        "socket_timeout_s": 60.0,
    }


def app_id() -> dict[str, Any]:
    """Row HD-APP-ID: the application identity.

    Quoted from frontend/src/app/About.tsx (APP_ID, AGENT_SI_NAME).
    """
    return {
        "row": "HD-APP-ID",
        "app_id": "com.agentsi.app",
        "name": "Agent SI",
    }


def brand() -> dict[str, Any]:
    """Row M-R-BRAND: the user-visible product brand.

    Quoted from frontend/src/app/About.tsx (AGENT_SI_NAME,
    LICENCE_LINE, MIT_LICENSE_REF).
    """
    return {
        "row": "M-R-BRAND",
        "name": "Agent SI",
        "licence_line": "Copyright (c) 2026 Ivan Soprun",
        "mit_ref": "about.licence.mitText",
    }


def retry_policy() -> dict[str, Any]:
    """Row B0B-BP09-27: the manifest retry policy defaults.

    Quoted from src/agent_si/policies/policies.py (Manifest section
    16 RetryPolicy: executor/provider/format/verification attempt
    maxima, correction maxima, backoff policy).
    """
    return {
        "row": "B0B-BP09-27",
        "section": "Manifest section 16 RetryPolicy",
        "executor_attempt_max": 3,
        "provider_retry_max": 2,
        "format_retry_max": 1,
        "verification_retry_max": 1,
        "verification_correction_max": 2,
        "audit_correction_max": 2,
        "runtime_correction_max": 3,
        "backoff_policy": "",
    }


def local_config_gate() -> dict[str, Any]:
    """Row B0B-UNCOVERED_BP06-67: the local-only config gate.

    Quoted from src/agent_si/local/config.py (used-level identity
    keys _LOCAL_LEVEL_ID_KEYS, per-level resource-cap mapping key
    _LOCAL_LEVEL_RESOURCE_CAP_KEY, require_local_ai_allowed_at_used_
    levels, check_local_only_activation; fail-closed default deny).
    """
    return {
        "row": "B0B-UNCOVERED_BP06-67",
        "level_id_keys": ["level", "role", "id", "name"],
        "resource_cap_key": "resource_cap",
        "require_gate": "require_local_ai_allowed_at_used_levels",
        "activation_gate": "check_local_only_activation",
        "fail_closed": True,
    }


def planner_router() -> dict[str, Any]:
    """Row B0B-UNCOVERED_ARCH-541: the planner/router split.

    Quoted from src/agent_si/backend/orchestration/graph.py (the
    planner builds the subtask graph and never selects a provider or
    model; the router picks worker class, execution type and needs,
    never a concrete model).
    """
    return {
        "row": "B0B-UNCOVERED_ARCH-541",
        "planner": "builds subtask graph,"
                   " never selects provider or model",
        "router": "picks worker class, execution type and needs,"
                  " never a concrete model",
    }


def shell_menus() -> dict[str, Any]:
    """Row B0B-UNCOVERED_ARCH-679: named menus wired to named views.

    Quoted from frontend/src/__tests__/untest3_ui.test.tsx (every
    named menu is wired on the real shell; ROUTES.agentsLive,
    ROUTES.projects, ROUTES.projectReports).
    """
    return {
        "row": "B0B-UNCOVERED_ARCH-679",
        "menus": [
            "menu-chat",
            "menu-agents-live",
            "menu-new-task",
            "menu-projects",
            "menu-tasks",
            "menu-results",
            "menu-settings",
        ],
        "routes": {
            "agentsLive": "/agents/live",
            "projects": "/projects",
            "projectReports": "/projects/:projectId/reports",
        },
    }


ROUTES: tuple[tuple[str, str, str, Callable[[], dict[str, Any]]], ...] = (
    ("get", "/api/v1/app/context-card", "context_card",
     context_card),
    ("get", "/api/v1/app/channel-lane", "channel_lane",
     channel_lane),
    ("get", "/api/v1/app/app-id", "app_id", app_id),
    ("get", "/api/v1/app/brand", "brand", brand),
    ("get", "/api/v1/app/retry-policy", "retry_policy",
     retry_policy),
    ("get", "/api/v1/app/local-config-gate", "local_config_gate",
     local_config_gate),
    ("get", "/api/v1/app/planner-router", "planner_router",
     planner_router),
    ("get", "/api/v1/app/shell-menus", "shell_menus",
     shell_menus),
)


def mount(app: FastAPI) -> FastAPI:
    """Register every K07NEXT2 split-A route on the real FastAPI app.

    App.py stays untouched; the caller passes the create_app() app.
    Returns the app for chaining.
    """
    for method, path, name, fn in ROUTES:
        registrar = getattr(app, method)
        registrar(path, name="k07next2_" + name)(fn)
    return app
