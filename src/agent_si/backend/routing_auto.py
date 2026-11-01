"""DEMOF3 auto-hierarchy served surface: GET /api/v1/routing/auto.

register_routing_auto_routes(app) mounts onto the seam app
(additions-only): choice runs through the frozen MOD seams
(model_kb.loader.candidates_for_auto for the AUTO shortlist from
connected providers only, routing.roles.resolve_manager to bind the
Manager profile model), and every STORE read runs through
model_kb.loader.find_row (exact provider/model match; model ids pass
through verbatim, never invented here).

Query params follow the k04n4 convention (budget/routes.py
k04n4_kb_auto): `task_type` (default "coding"; known {"coding",
"general"} from loader.auto_fit_price_quality default plus the
orchestration default task_class) and comma-separated `connected`
providers. Unknown task_type -> 422; no resolvable candidate (nobody
connected, or no connected KB row) -> fail-closed 422 carrying the
seam's BLOCKED reason.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

KNOWN_TASK_TYPES = ("coding", "general")


class UnknownTask(ValueError):
    """A task_type outside the known seam convention."""


class AutoBlocked(ValueError):
    """AUTO shortlist resolved no candidate (fail-closed)."""


def _parse_connected(raw_values: Any) -> list:
    """Comma-separated `connected` params as a clean provider list."""
    if raw_values is None:
        items = []
    elif isinstance(raw_values, (list, tuple)):
        items = list(raw_values)
    else:
        items = [raw_values]
    connected = []
    for item in items:
        for part in str(item).split(","):
            name = part.strip()
            if name and name not in connected:
                connected.append(name)
    return connected


def pick_auto(catalog: dict, connected: list,
              task_type: str) -> dict:
    """Resolve the AUTO manager choice through the frozen seams.

    Unknown task_type raises UnknownTask; an empty shortlist (or no
    store-verified row) raises AutoBlocked. The pick is the first
    connected candidate in catalog order whose row the store confirms
    via find_row, bound through resolve_manager with no target (the
    router keeps the profile model, never re-selects per run).
    """
    from agent_si.model_kb import loader as _loader
    from agent_si.routing import roles as _roles

    task = str(task_type or "").strip() or "coding"
    if task not in KNOWN_TASK_TYPES:
        raise UnknownTask(
            "unknown task_type %r (known: %s)"
            % (task_type, ", ".join(KNOWN_TASK_TYPES)))
    auto = _loader.candidates_for_auto(catalog, list(connected or []))
    for cand in auto.get("candidates", []):
        provider = cand.get("provider_id")
        model = cand.get("model_id")
        if not provider or not model:
            continue
        if _loader.find_row(catalog, provider, model) is None:
            continue
        profile = _roles.make_default_manager_profile(provider, model)
        _, bound = _roles.resolve_manager(profile)
        return {"manager": str(bound.provider),
                "model": str(bound.model)}
    raise AutoBlocked(
        "AUTO BLOCKED: %s" % (auto.get("reason") or "no candidate"))


def register_routing_auto_routes(app: Any) -> Any:
    """Mount GET /api/v1/routing/auto onto the seam app."""

    @app.get("/api/v1/routing/auto")
    def get_routing_auto(request: Request) -> dict:
        from agent_si.model_kb import kb as _kb

        params = request.query_params
        task_type = params.get("task_type") or "coding"
        connected = _parse_connected(params.getlist("connected"))
        try:
            return pick_auto(_kb.bound_catalog(), connected, task_type)
        except (UnknownTask, AutoBlocked) as err:
            raise HTTPException(
                status_code=422, detail=str(err)) from None

    return app
