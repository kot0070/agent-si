"""DEMOF3 auto-hierarchy served surface: GET /api/v1/routing/auto.

register_routing_auto_routes(app) mounts onto the seam app
(additions-only): choice runs through the frozen MOD seams
(model_kb.loader.candidates_for_auto for the AUTO shortlist from
connected providers only, routing.roles.resolve_manager to bind the
Manager profile model), and every STORE read runs through
model_kb.loader.find_row (exact provider/model match; model ids pass
through verbatim, never invented here).

Connected set (FXKB F03): the provider-registry ONLINE providers read
off the app (app.state.k04_ctx.provider_facade, ids only, never key
material); the `connected` query param may only narrow that set, never
widen it. With no registry visible the query param is the connected
set, which keeps the frozen DEMOF3 contract. With no param the
registry default resolves and the 200 carries the why-record; an
explicit param keeps the frozen exact {"manager", "model"} shape.

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


def registry_online_connected(request: Request) -> list | None:
    """ONLINE provider ids off the app registry, or None when unseen.

    Reads app.state.k04_ctx.provider_facade.list_providers (ids only,
    never key material) and keeps health == "ONLINE" in facade order.
    Any failure reads as unseen (None): callers fall back to the
    frozen query-param contract instead of failing open or closed.
    """
    try:
        app = getattr(request, "app", None)
        state = getattr(app, "state", None)
        ctx = getattr(state, "k04_ctx", None)
        facade = getattr(ctx, "provider_facade", None)
        if facade is None:
            return None
        views = facade.list_providers()
    except Exception:
        return None
    try:
        items = list(views or [])
    except TypeError:
        return None
    online = []
    for view in items:
        try:
            if getattr(view, "health", None) != "ONLINE":
                continue
            pid = str(getattr(view, "provider_id", "") or "")
        except Exception:
            continue
        if pid and pid not in online:
            online.append(pid)
    return online



def _row_price(row) -> float | None:
    """Known input + output token price of a KB row; None when either is UNKNOWN."""
    try:
        fields = (row or {}).get("fields") or {}
        total = 0.0
        for name in ("input_token_price", "output_token_price"):
            value = (fields.get(name) or {}).get("value")
            total += float(value)
        return total
    except (TypeError, ValueError, AttributeError):
        return None


def _cheapest_first(candidates: list) -> list:
    """Known-price candidates cheapest first, unknown prices after them, catalog
    order kept inside ties (PART1DRIVE4 F03 01.11: gpt-4o was picked over the
    cheaper KB-priced gpt-4o-mini because the first catalog row always won)."""
    indexed = list(enumerate(candidates))

    def key(item):
        idx, cand = item
        price = _row_price(cand.get("row"))
        return (price is None, price if price is not None else 0.0, idx)
    return [cand for _idx, cand in sorted(indexed, key=key)]


def _enabled_hit(enabled: dict, provider: str, model: str) -> bool:
    """True when a candidate survives the server tick list (one reader).

    Canonical compare (``meta/x`` and ``x`` are one model), plus the
    dated/tag base so a capability gate never drops a model only
    because its id is dated.
    """
    from agent_si.providers.registry import provider_model_lists as _lists

    try:
        ticks = enabled.get(provider)
    except AttributeError:
        return True
    if ticks is None:
        return True
    candidate = _lists.canonical_model_id(provider, model)
    wanted = {_lists.canonical_model_id(provider, i) for i in ticks or []}
    if candidate in wanted:
        return True
    bases = {_lists.dated_base_id(w) for w in wanted}
    return candidate in bases


def pick_auto(catalog: dict, connected: list,
              task_type: str, enabled: dict | None = None) -> dict:
    """Resolve the AUTO manager choice through the frozen seams.

    Unknown task_type raises UnknownTask; an empty shortlist (or no
    store-verified row) raises AutoBlocked. The pick is the first
    connected candidate in catalog order whose row the store confirms
    via find_row, bound through resolve_manager with no target (the
    router keeps the profile model, never re-selects per run). The
    why-record carries the effective connected set, the task type and
    the seam's shortlist reason.
    """
    from agent_si.model_kb import loader as _loader
    from agent_si.routing import roles as _roles

    task = str(task_type or "").strip() or "coding"
    if task not in KNOWN_TASK_TYPES:
        raise UnknownTask(
            "unknown task_type %r (known: %s)"
            % (task_type, ", ".join(KNOWN_TASK_TYPES)))
    auto = _loader.candidates_for_auto(catalog, list(connected or []))
    if enabled is not None:
        auto = dict(auto)
        auto["candidates"] = [c for c in auto.get("candidates", [])
                              if _enabled_hit(enabled, c.get("provider_id"),
                                             c.get("model_id"))]
    ranked = _cheapest_first(auto.get("candidates", []))
    compared = [{"provider": c.get("provider_id"), "model": c.get("model_id"),
                 "price_in_plus_out": _row_price(c.get("row"))} for c in ranked]
    for cand in ranked:
        provider = cand.get("provider_id")
        model = cand.get("model_id")
        if not provider or not model:
            continue
        if _loader.row_proves_non_text(cand.get("row") or {}):
            continue
        if _loader.match_row(catalog, provider, model) is None:
            continue
        profile = _roles.make_default_manager_profile(provider, model)
        _, bound = _roles.resolve_manager(profile)
        if enabled is not None and not _enabled_hit(
                enabled, str(bound.provider), str(bound.model)):
            continue
        return {"manager": str(bound.provider),
                "model": str(bound.model),
                "why": {"connected": list(connected or []),
                        "task_type": task,
                        "reason": auto.get("reason"),
                        "rule": "cheapest known price first, UNKNOWN prices last",
                        "compared": compared}}
    raise AutoBlocked(
        "AUTO BLOCKED: %s" % (auto.get("reason") or "no candidate"))


def _route_enabled(request: Request, connected: list) -> dict | None:
    """Stored tick lists for the route (one reader); None keeps legacy."""
    try:
        ctx = getattr(getattr(request, "app", None), "state", None)
        ctx = getattr(ctx, "k04_ctx", None)
        state_dir = getattr(ctx, "model_state_dir", None)
    except Exception:
        return None
    if not state_dir:
        return None
    try:
        from agent_si.providers.registry import (
            provider_model_lists as _lists)
        return _lists.enabled_map(state_dir, connected)
    except Exception:
        return None


def register_routing_auto_routes(app: Any) -> Any:
    """Mount GET /api/v1/routing/auto onto the seam app."""

    @app.get("/api/v1/routing/auto")
    def get_routing_auto(request: Request) -> dict:
        from agent_si.model_kb import kb as _kb

        params = request.query_params
        task_type = params.get("task_type") or "coding"
        requested = _parse_connected(params.getlist("connected"))
        online = registry_online_connected(request)
        if online is None:
            connected = requested
            explicit = True
        elif requested:
            connected = [p for p in requested if p in online]
            explicit = True
        else:
            connected = list(online)
            explicit = False
        try:
            pick = pick_auto(_kb.bound_catalog(), connected, task_type,
                             _route_enabled(request, connected))
        except (UnknownTask, AutoBlocked) as err:
            raise HTTPException(
                status_code=422, detail=str(err)) from None
        if explicit:
            return {"manager": pick["manager"], "model": pick["model"]}
        return pick

    return app
