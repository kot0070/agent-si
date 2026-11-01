"""Hierarchy claims R5-R8: role authority, scopes, routing, demand caps.

Pure orchestration logic behind the served /hierarchy rows R5-R8
(claims BP06-78, ARCH-456, ARCH-461, ARCH-755). No I/O, no secrets,
no network: each function validates its inputs and either returns a
plain-dict payload or raises one of the module errors, which the served
route maps to its HTTP status (403 / 409 / 422 / 409).

Reuse (imported, never copied): cap values are validated with
steplimits._check_budget_value and the demand partition honours
hierarchy._decompose (parallel largest-first up to the cap, the rest
queued with positions).
"""

from __future__ import annotations

from typing import Any

from agent_si.backend.orchestration import hierarchy as _hierarchy
from agent_si.backend.orchestration import steplimits as _steplimits

__all__ = [
    "REJECTED_SCOPE_OVERLAP",
    "ROLE_NOT_CONFIGURED",
    "ROUTING_BYPASS",
    "CAPS_EXCEEDED",
    "RoleAuthorityError",
    "ScopeOverlapError",
    "RoutingError",
    "CapsExceededError",
    "role_authority",
    "check_scopes_distinct",
    "route_plan",
    "queue_demand",
]

REJECTED_SCOPE_OVERLAP = "REJECTED_SCOPE_OVERLAP"
ROLE_NOT_CONFIGURED = "ROLE_NOT_CONFIGURED"
ROUTING_BYPASS = "ROUTING_BYPASS"
CAPS_EXCEEDED = "CAPS_EXCEEDED"


class RoleAuthorityError(Exception):
    """Unconfigured role; the served route maps this to a 403."""

    code = ROLE_NOT_CONFIGURED
    status_code = 403

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ScopeOverlapError(Exception):
    """Overlapping agent scopes; the served route maps this to a 409."""

    code = REJECTED_SCOPE_OVERLAP
    status_code = 409

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = REJECTED_SCOPE_OVERLAP


class RoutingError(Exception):
    """Plan bypasses the Manager hierarchy; served as a 422."""

    code = ROUTING_BYPASS
    status_code = 422

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class CapsExceededError(Exception):
    """Demand exceeds the Manager caps; the served route maps this to a 409."""

    code = CAPS_EXCEEDED
    status_code = 409

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def role_authority(role: str, *, role_models: dict) -> dict:
    """Resolve one role's authority only through configured role models.

    Returns {"role", "model"}. Raises RoleAuthorityError when the role
    is blank, when role_models is not a usable mapping, when the role
    has no configured entry, or when the entry names no model.
    """
    if not isinstance(role, str) or not role.strip():
        raise RoleAuthorityError(
            f"{ROLE_NOT_CONFIGURED}: role must be a non-empty string"
        )
    if not isinstance(role_models, dict) or not role_models:
        raise RoleAuthorityError(
            f"{ROLE_NOT_CONFIGURED}: no role models are configured"
        )
    key = role.strip()
    if key not in role_models:
        raise RoleAuthorityError(
            f"{ROLE_NOT_CONFIGURED}: role {key!r} has no configured model"
        )
    configured = role_models[key]
    if isinstance(configured, dict):
        model: Any = None
        for name in ("model", "model_id", "name"):
            candidate = configured.get(name)
            if isinstance(candidate, str) and candidate.strip():
                model = candidate.strip()
                break
    elif isinstance(configured, str) and configured.strip():
        model = configured.strip()
    else:
        model = None
    if model is None:
        raise RoleAuthorityError(
            f"{ROLE_NOT_CONFIGURED}: role {key!r} names no usable model"
        )
    return {"role": key, "model": model}


def _scope_text(entry: Any) -> str:
    if isinstance(entry, str):
        return entry.strip()
    if isinstance(entry, dict):
        for key in ("scope", "id", "name"):
            value = entry.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _scopes_overlap(first: str, second: str) -> bool:
    if first == second:
        return True
    return first.startswith(second + "/") or second.startswith(first + "/")


def check_scopes_distinct(scopes: list) -> None:
    """Require every agent scope to be distinct and non-overlapping.

    Returns None when the scopes are pairwise distinct. Raises
    ScopeOverlapError (code REJECTED_SCOPE_OVERLAP) on an exact
    duplicate or on a nested scope (one scope extending another at a
    "/" boundary). Raises ValueError on a malformed scopes list.
    """
    if not isinstance(scopes, list):
        raise ValueError("scopes must be a list")
    cleaned: list[str] = []
    for entry in scopes:
        text = _scope_text(entry)
        if not text:
            raise ValueError("each scope must be a non-empty string")
        cleaned.append(text)
    for index in range(len(cleaned)):
        for other in range(index + 1, len(cleaned)):
            if _scopes_overlap(cleaned[index], cleaned[other]):
                raise ScopeOverlapError(
                    f"{REJECTED_SCOPE_OVERLAP}: scopes "
                    f"{cleaned[index]!r} and {cleaned[other]!r} overlap"
                )
    return None


def _id_list(value: Any, keys: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    if isinstance(value, str):
        if value.strip():
            found.append(value.strip())
    elif isinstance(value, list):
        for entry in value:
            if isinstance(entry, str):
                if entry.strip():
                    found.append(entry.strip())
            elif isinstance(entry, dict):
                for key in keys:
                    candidate = entry.get(key)
                    if isinstance(candidate, str) and candidate.strip():
                        found.append(candidate.strip())
                        break
    elif isinstance(value, dict):
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                found.append(candidate.strip())
                break
    return found


def _normalize_hierarchy(hierarchy: Any) -> tuple[list[str], set[str]]:
    """Collect (managers, known nodes) from a manager hierarchy mapping."""
    if not isinstance(hierarchy, dict):
        raise ValueError("manager_hierarchy must be a mapping")
    nested = hierarchy.get("hierarchy")
    if isinstance(nested, dict):
        outer_managers, outer_nodes = _normalize_hierarchy(nested)
    else:
        outer_managers, outer_nodes = [], set()
    managers: list[str] = list(outer_managers)
    nodes: set[str] = set(outer_nodes) | {"director"}

    def _add_manager(mid: str) -> None:
        if mid not in managers:
            managers.append(mid)
        nodes.add(mid)

    for mid in _id_list(
        hierarchy.get("managers"), ("id", "name", "manager", "manager_id")
    ):
        _add_manager(mid)
    for entry in (
        hierarchy.get("managers") if isinstance(hierarchy.get("managers"), list)
        else []
    ):
        if isinstance(entry, dict):
            owner = _id_list(entry, ("id", "name", "manager", "manager_id"))
            if owner:
                for agent in _id_list(
                    entry.get("agents"), ("id", "name", "agent", "agent_id")
                ):
                    nodes.add(agent)
    single = hierarchy.get("manager")
    if isinstance(single, str) and single.strip():
        _add_manager(single.strip())
    for agent in _id_list(
        hierarchy.get("agents"), ("id", "name", "agent", "agent_id")
    ):
        nodes.add(agent)
    chain = hierarchy.get("chain")
    if isinstance(chain, list):
        for link in chain:
            if not isinstance(link, str) or not link.strip():
                continue
            text = link.strip()
            if text.startswith("manager:") and text[len("manager:"):].strip():
                _add_manager(text[len("manager:"):].strip())
            elif text.startswith("agent:") and text[len("agent:"):].strip():
                nodes.add(text[len("agent:"):].strip())
            elif text in managers or text == "director":
                nodes.add(text)
    if not managers:
        raise ValueError("manager_hierarchy must name at least one manager")
    return managers, nodes


def _plan_nodes(plan: dict) -> list[str]:
    nodes: list[str] = []

    def _take(text: str) -> None:
        cleaned = text.strip()
        if cleaned and cleaned not in nodes:
            nodes.append(cleaned)

    for key in ("route", "path", "steps"):
        seq = plan.get(key)
        if not isinstance(seq, list):
            continue
        for entry in seq:
            if isinstance(entry, str):
                _take(entry)
            elif isinstance(entry, dict):
                for name in (
                    "to", "via", "by", "node", "agent", "manager", "id", "name"
                ):
                    candidate = entry.get(name)
                    if isinstance(candidate, str):
                        _take(candidate)
    return nodes


def route_plan(plan: dict, *, manager_hierarchy: dict) -> dict:
    """Route one plan through the Manager hierarchy.

    Returns {"manager", "route", "subordinate": True} when every node
    the plan names is known to the hierarchy and a configured Manager
    stays in charge. Raises RoutingError when the plan declares a
    bypass (direct/bypass flags), names an unknown Manager, routes to
    an unknown node, or names no Manager at all. Raises ValueError on
    a malformed plan or hierarchy.
    """
    if not isinstance(plan, dict):
        raise ValueError("plan must be a mapping")
    for flag in ("bypass", "bypass_manager", "direct"):
        if plan.get(flag) is True:
            raise RoutingError(
                f"{ROUTING_BYPASS}: plan sets {flag!r} and bypasses "
                "the Manager hierarchy"
            )
    managers, nodes = _normalize_hierarchy(manager_hierarchy)
    routed = _plan_nodes(plan)
    manager: Any = None
    for key in ("manager", "via", "by"):
        candidate = plan.get(key)
        if isinstance(candidate, str) and candidate.strip():
            manager = candidate.strip()
            break
    if manager is None and routed and routed[0] in managers:
        manager = routed[0]
    if (
        manager is None
        and len(managers) == 1
        and routed
        and all(node in nodes for node in routed)
    ):
        manager = managers[0]
    if manager is None:
        raise RoutingError(
            f"{ROUTING_BYPASS}: plan names no Manager from the hierarchy"
        )
    if manager not in managers:
        raise RoutingError(
            f"{ROUTING_BYPASS}: manager {manager!r} is outside "
            "the Manager hierarchy"
        )
    for node in routed:
        if node not in nodes:
            raise RoutingError(
                f"{ROUTING_BYPASS}: node {node!r} is outside "
                "the Manager hierarchy"
            )
    return {"manager": manager, "route": routed, "subordinate": True}


def _demand_tasks(demand: Any) -> list[tuple[str, float]]:
    if not isinstance(demand, dict):
        raise ValueError("demand must be a mapping")
    items: Any = None
    for key in ("items", "tasks", "demand", "queue"):
        candidate = demand.get(key)
        if isinstance(candidate, list):
            items = candidate
            break
    if items is None:
        raise ValueError("demand must carry an items list")
    tasks: list[tuple[str, float]] = []
    for entry in items:
        if isinstance(entry, str):
            if not entry.strip():
                raise ValueError("each demand item needs a non-empty id")
            tasks.append((entry.strip(), 1.0))
            continue
        if not isinstance(entry, dict):
            raise ValueError("each demand item must be an {id} mapping")
        item_id: Any = None
        for key in ("id", "task_id", "name"):
            candidate = entry.get(key)
            if isinstance(candidate, str) and candidate.strip():
                item_id = candidate.strip()
                break
        if item_id is None:
            raise ValueError("each demand item needs a non-empty id")
        size: Any = 1.0
        for key in ("size", "weight", "cost"):
            if key in entry:
                size = entry.get(key)
                break
        if not _steplimits._is_number(size):
            raise ValueError(f"demand item {item_id!r} needs a numeric size")
        tasks.append((item_id, float(size)))
    return tasks


def _demand_cap(caps: Any) -> int:
    if not isinstance(caps, dict):
        raise ValueError("caps must be a mapping")
    for key in ("cap", "capacity", "max_total", "max_items"):
        if caps.get(key) is not None:
            return _steplimits._check_budget_value("cap", caps.get(key))
    raise ValueError("caps must carry a cap integer")


def queue_demand(demand: dict, *, caps: dict) -> dict:
    """Queue one demand batch within the Manager capacity caps.

    The cap bounds how many items the Manager holds: items past the
    parallel slots queue with positions, and demand larger than the cap
    raises CapsExceededError so the caller retains it (nothing is ever
    dropped). Returns {"parallel", "queued", "cap"}. Raises ValueError
    on a malformed demand or caps mapping.
    """
    tasks = _demand_tasks(demand)
    cap = _demand_cap(caps)
    if len(tasks) > cap:
        raise CapsExceededError(
            f"{CAPS_EXCEEDED}: demand of {len(tasks)} items "
            f"exceeds cap {cap}"
        )
    parallel_slots = cap
    for key in ("max_parallel", "max_parallel_managers", "parallel"):
        if caps.get(key) is not None:
            parallel_slots = _steplimits._check_budget_value(key, caps.get(key))
            break
    parallel_slots = min(parallel_slots, cap)
    payload = [{"id": item_id, "size": size} for item_id, size in tasks]
    parallel, queued = _hierarchy._decompose(payload, parallel_slots)
    return {
        "parallel": parallel,
        "queued": [
            {"id": item_id, "position": position}
            for position, item_id in enumerate(queued, 1)
        ],
        "cap": cap,
    }
