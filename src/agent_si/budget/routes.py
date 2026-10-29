"""Budget HTTP surface (Lane B2): GET /api/v1/budget over ctx.budget_state."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, Tuple

#: Stable machine codes for the budget error bodies (M-WIRE L0B-08/11).
BUDGET_PROJECT_ID_REQUIRED = "BUDGET_PROJECT_ID_REQUIRED"
BUDGET_NOT_CONFIGURED = "BUDGET_NOT_CONFIGURED"


def _query_value(query, name, default=None):
    value = (query or {}).get(name, default)
    if isinstance(value, list):
        return value[0] if value else default
    return value


def _state_payload(state):
    if hasattr(state, "to_dict"):
        payload = dict(state.to_dict())
    elif isinstance(state, Mapping):
        payload = dict(state)
    else:
        payload = {key: value for key, value in vars(state).items()
                   if not key.startswith("_")}
    remaining = getattr(state, "remaining_derived", None)
    if remaining is not None and "remaining_derived" not in payload:
        payload["remaining_derived"] = remaining
    return payload


def get_budget(ctx, query, body) -> Tuple[int, Dict[str, Any]]:
    """Return (status, payload) for GET /api/v1/budget.

    Reads ctx.budget_state, which may be a BudgetGate (has get_state), a
    BudgetState-like object, or a mapping. Missing state is a 404.
    """
    query = query or {}
    params = body if isinstance(body, Mapping) else {}
    project_id = _query_value(query, "project_id", None)
    if project_id is None:
        project_id = params.get("project_id", "p1")
    if not isinstance(project_id, str) or not project_id:
        return 400, {"code": BUDGET_PROJECT_ID_REQUIRED,
                         "message": "project_id required"}
    budget_state = getattr(ctx, "budget_state", None)
    if budget_state is None:
        return 404, {"code": BUDGET_NOT_CONFIGURED, "message": "no budget state on file for %r" % (project_id,)}
    get_state = getattr(budget_state, "get_state", None)
    if callable(get_state):
        try:
            state = get_state(project_id)
        except (KeyError, LookupError):
            return 404, {"code": BUDGET_NOT_CONFIGURED, "message": "no budget state on file for %r"
                         % (project_id,)}
        return 200, {"project_id": project_id,
                     "budget": _state_payload(state)}
    if isinstance(budget_state, Mapping):
        node = dict(budget_state)
        if project_id in node and isinstance(node[project_id], Mapping):
            return 200, {"project_id": project_id,
                         "budget": dict(node[project_id])}
        if "project_id" in node:
            if node.get("project_id") != project_id:
                return 404, {"code": BUDGET_NOT_CONFIGURED, "message": "no budget state on file for %r"
                             % (project_id,)}
            return 200, {"project_id": project_id, "budget": node}
        return 404, {"code": BUDGET_NOT_CONFIGURED, "message": "no budget state on file for %r" % (project_id,)}
    state_project = getattr(budget_state, "project_id", None)
    if state_project is not None and state_project != project_id:
        return 404, {"code": BUDGET_NOT_CONFIGURED, "message": "no budget state on file for %r" % (project_id,)}
    return 200, {"project_id": project_id,
                 "budget": _state_payload(budget_state)}


BUDGET_ROUTES = (
    ("get", "/api/v1/budget", "get_budget", get_budget),
)
