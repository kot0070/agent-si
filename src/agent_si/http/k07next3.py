"""K07NEXT3 split-A served boundary: 7 open K07 rows as GET JSON routes.

Every route is an open read (no token), returns a deterministic
server-shaped JSON document, and is registered by mount() onto the
real create_app() app with app.py untouched. Row contracts are quoted
from the repo ground truth named in each function docstring.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI


def policy_lifecycle() -> dict[str, Any]:
    """Row B0B-BP09-30: the frozen policy lifecycle event set.

    Quoted from src/agent_si/policies/policies.py (Manifest section
    25A PolicyLifecycleEvent: ACTIVATED, SUPERSEDED, RETIRED).
    """
    return {
        "row": "B0B-BP09-30",
        "section": "Manifest section 25A PolicyLifecycleEvent",
        "events": ["ACTIVATED", "SUPERSEDED", "RETIRED"],
    }


def gate_verdicts() -> dict[str, Any]:
    """Row B0B-UNCOVERED_ARCH-563: the part gate verdict sets.

    Quoted from src/agent_si/backend/orchestration/parts.py
    (GATE_PASS, GATE_VERDICTS, AUDIT_RESULTS, MODEL_ID).
    """
    return {
        "row": "B0B-UNCOVERED_ARCH-563",
        "gate_pass": "PASS",
        "gate_verdicts": ["BLOCKED", "FAIL", "PASS"],
        "audit_results": ["BLOCKED", "ESCALATE", "FAIL", "PASS", "REWORK"],
        "model": "meta/muse-spark-1.3-contributor",
    }


def ledger_register() -> dict[str, Any]:
    """Row B0B-UNCOVERED_ARCH-683: the ledger register states.

    Quoted from src/agent_si/backend/orchestration/ledger.py
    (REGISTER_PRESERVED/CHANGED/MISSING/CONTRADICTED plus the
    LedgerRow shape package_id/agents/peak_concurrency/wall_time_s).
    """
    return {
        "row": "B0B-UNCOVERED_ARCH-683",
        "states": ["PRESERVED", "CHANGED", "MISSING", "CONTRADICTED"],
        "ledger_row": ["package_id", "agents", "peak_concurrency",
                       "wall_time_s"],
    }


def step_limits() -> dict[str, Any]:
    """Row B0B-UNCOVERED_ARCH-686: the step-limit kinds and bounds.

    Quoted from src/agent_si/backend/orchestration/steplimits.py
    (TASK_KIND, CHAT_KIND, STEPLIMIT_SCOPE_PREFIX, STEP_LIMIT_MIN,
    STEP_LIMIT_CAP).
    """
    return {
        "row": "B0B-UNCOVERED_ARCH-686",
        "task_kind": "task",
        "chat_kind": "chat",
        "scope_prefix": "steplimits:",
        "min": 1,
        "cap": 10000,
    }


def project_defaults() -> dict[str, Any]:
    """Row B0B-UNCOVERED_ARCH-716: the new-project starting values.

    Quoted from src/agent_si/backend/project_defaults.py (CURRENCY,
    BUDGET_LIMIT, SOFT_LIMIT, HARD_LIMIT, TASK_MAX_STEPS,
    CHAT_MAX_STEPS).
    """
    return {
        "row": "B0B-UNCOVERED_ARCH-716",
        "currency": "USD",
        "budget_limit": "5.00",
        "soft_limit": "4.00",
        "hard_limit": "5.00",
        "task_max_steps": 40,
        "chat_max_steps": 15,
    }


def control_plane() -> dict[str, Any]:
    """Row B0B-UNCOVERED_ARCH-718: the control-plane map and risk levels.

    Quoted from src/agent_si/backend/orchestration/graph.py
    (RISK_LEVELS, PLANNED, CONTROL_PLANE_MAP).
    """
    return {
        "row": "B0B-UNCOVERED_ARCH-718",
        "risk_levels": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
        "planned": "PLANNED",
        "map": {
            "director.split": "split.split_package",
            "director.route": "graph.route_task",
            "director.policy": "graph.CONTROL_PLANE_MAP",
            "director.integrate": "graph.HierarchyConfigStore.close_parent",
            "director.decide": "teamcard.DecisionLog.append",
        },
    }


def team_card() -> dict[str, Any]:
    """Row B0B-UNCOVERED_ARCH-720: the team-card shape and model id.

    Quoted from src/agent_si/backend/orchestration/teamcard.py
    (TeamCard provider/model/model_kb_facts/budget_left/limits,
    MODEL_ID).
    """
    return {
        "row": "B0B-UNCOVERED_ARCH-720",
        "shape": ["provider", "model", "model_kb_facts", "budget_left",
                  "limits"],
        "model": "meta/muse-spark-1.3-contributor",
    }


ROUTES: tuple[tuple[str, str, str, Callable[[], dict[str, Any]]], ...] = (
    ("get", "/api/v1/app/policy-lifecycle", "policy_lifecycle",
     policy_lifecycle),
    ("get", "/api/v1/app/gate-verdicts", "gate_verdicts",
     gate_verdicts),
    ("get", "/api/v1/app/ledger-register", "ledger_register",
     ledger_register),
    ("get", "/api/v1/app/step-limits", "step_limits",
     step_limits),
    ("get", "/api/v1/app/project-defaults", "project_defaults",
     project_defaults),
    ("get", "/api/v1/app/control-plane", "control_plane",
     control_plane),
    ("get", "/api/v1/app/team-card", "team_card",
     team_card),
)


def mount(app: FastAPI) -> FastAPI:
    """Register every K07NEXT3 split-A route on the real FastAPI app.

    App.py stays untouched; the caller passes the create_app() app.
    Returns the app for chaining.
    """
    for method, path, name, fn in ROUTES:
        registrar = getattr(app, method)
        registrar(path, name="k07next3_" + name)(fn)
    return app
