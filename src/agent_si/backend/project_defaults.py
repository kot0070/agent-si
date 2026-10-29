"""Project starting values for newly created or loaded projects (BEDEF1).

Product starting values (HD decision, spec silent): a later settings screen
edits these; no other fixture constants live in product code.

Budget: currency USD, budget_limit 5.00, soft_limit 4.00, hard_limit 5.00
(the owner's first live run limit is 5 USD).
Step limits: task_max_steps 40, chat_max_steps 15.
"""

from __future__ import annotations

from typing import Any

CURRENCY = "USD"
BUDGET_LIMIT = "5.00"
SOFT_LIMIT = "4.00"
HARD_LIMIT = "5.00"

TASK_MAX_STEPS = 40
CHAT_MAX_STEPS = 15

_DEFAULT_AUTHORITY = "project-defaults"
_DEFAULT_REASON = "configure default step limits for new project"


def _budget_gate_for(app: Any) -> Any | None:
    ctx = getattr(getattr(app, "state", None), "k04_ctx", None)
    gate = getattr(ctx, "budget_state", None)
    if gate is None:
        return None
    if not (hasattr(gate, "get_state") and hasattr(gate, "configure_project")):
        return None
    return gate


def ensure_project_defaults(app: Any, project_id: str) -> None:
    """Configure default budget state + step limits for one project.

    Idempotent: an existing budget state is never overwritten and existing
    step limits are never re-applied. Budget state is persisted by the K04
    public BudgetGate API on the same gate object the app serves; step limits
    go through the public steplimits writer.
    """
    gate = _budget_gate_for(app)
    if gate is not None:
        try:
            gate.get_state(project_id)
        except (KeyError, LookupError):
            gate.configure_project(
                project_id,
                CURRENCY,
                BUDGET_LIMIT,
                SOFT_LIMIT,
                HARD_LIMIT,
            )
    from agent_si.backend.orchestration import steplimits as _steplimits

    try:
        _steplimits.limits_for("task", project_id)
        _steplimits.limits_for("chat", project_id)
        return
    except (KeyError, LookupError):
        pass
    # R349A: restore SAVED values first (lazy import: steplimit_routes
    # owns steplimits.json and must stay import-cycle free).
    from agent_si.backend import steplimit_routes as _step_routes

    _saved_store = getattr(getattr(app, "state", None),
                           "k02r3_store_dir", None)
    _saved = _step_routes.saved_limits_for(_saved_store, project_id)
    if _saved is not None:
        _saved_outcome = _steplimits.apply_steplimit_config_change(
            {
                "project_id": project_id,
                "task_max_steps": _saved[0],
                "chat_max_steps": _saved[1],
                "authority": _DEFAULT_AUTHORITY,
                "reason": _DEFAULT_REASON,
                "statement": "step limits for project %s" % (project_id,),
            }
        )
        if _saved_outcome.applied:
            return
    outcome = _steplimits.apply_steplimit_config_change(
        {
            "project_id": project_id,
            "task_max_steps": TASK_MAX_STEPS,
            "chat_max_steps": CHAT_MAX_STEPS,
            "authority": _DEFAULT_AUTHORITY,
            "reason": _DEFAULT_REASON,
            "statement": "step limits for project %s" % (project_id,),
        }
    )
    if not outcome.applied:
        raise RuntimeError(
            "default step limits refused for project %r: %s"
            % (project_id, outcome.reason)
        )
