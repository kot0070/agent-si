"""Subtask graph, planner, router, control-plane map, hierarchy (lane A, coder A).

SPEC 21E/22/23/25A/28 + ROW22 + R-302/303 + B0B-BP01-10/73 + B0B-BP03-4
+ B0B-UNCOVERED_ARCH-7/461/704/766 + B0B-UNCOVERED_BP06-30/68/78
+ B0B-UNCOVERED_UI_DELTA-57/59/60/62 + M-P1-42 + M-P2-80 + M-R-GOV.
The planner builds the subtask graph and never selects a provider or
model; the router picks worker class, execution type and needs, never a
concrete model. V2 ONE-HOME: the shared kernel (ApplyOutcome,
DecisionLog, DecisionRow, utc_now, ensure_compact_english,
is_compact_english) lives in common.py and is re-exported here.
"""

from __future__ import annotations  # noqa: I001  # frozen-cite K02

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Mapping, Sequence  # noqa: UP035  # frozen-cite K02

from .common import (
    ApplyOutcome,
    DecisionLog,
    DecisionRow,
    ensure_compact_english,
    is_compact_english,
    utc_now,
)


RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

PLANNED = "PLANNED"

MODEL_ID = "meta/muse-spark-1.3-contributor"

DIRECTOR_RUNTIME: None = None

CONTROL_PLANE_MAP: dict[str, str] = {
    "director.split": "split.split_package",
    "director.route": "graph.route_task",
    "director.policy": "graph.CONTROL_PLANE_MAP",
    "director.integrate": "graph.HierarchyConfigStore.close_parent",
    "director.decide": "teamcard.DecisionLog.append",
}


class CycleError(ValueError):
    """Raised when subtask dependencies contain a cycle."""


class DependencyError(ValueError):
    """Raised when a subtask depends on an unknown subtask."""


class RoutingRefused(Exception):
    """Raised when a routing decision cannot be served."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class DispatchRejected(Exception):
    """Raised when an AgentTask cannot be dispatched."""


class HierarchyRefused(Exception):
    """Raised when a hierarchy change is refused without mutating config."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ParentClosureBlocked(Exception):
    """Raised when a parent cannot close (parts or integration missing)."""


class DirectorControlOnly(Exception):
    """Raised when a live Director runtime is requested (control-plane only)."""


@dataclass
class PlannedSubtask:
    subtask_id: str
    plan_ref: str
    goal: str
    task_class: str
    risk: str
    required_capabilities: list[str] = field(default_factory=list)
    knowledge_needs: list[str] = field(default_factory=list)
    tool_needs: list[str] = field(default_factory=list)
    acceptance_criteria_refs: list[str] = field(default_factory=list)
    dependency_ids: list[str] = field(default_factory=list)
    status: str = PLANNED

    def __post_init__(self) -> None:
        if not self.subtask_id.strip():
            raise ValueError("subtask_id must be non-empty")
        if not self.goal.strip():
            raise ValueError("subtask goal must be non-empty")
        if not self.task_class.strip():
            raise ValueError("task_class must be non-empty")
        if self.risk not in RISK_LEVELS:
            raise ValueError(f"risk must be one of {list(RISK_LEVELS)}")


@dataclass
class RunConfig:
    client_max_retries: int = 0
    retry_policy_ref: str = "retry:default"

    def __post_init__(self) -> None:
        if self.client_max_retries != 0:
            raise ValueError("client_max_retries stays 0; retries run via policy")


@dataclass
class RoutingDecision:
    decision_id: str
    subtask_id: str
    worker_class: str
    execution_type: str
    required_capabilities: list[str] = field(default_factory=list)
    tool_needs: list[str] = field(default_factory=list)
    knowledge_needs: list[str] = field(default_factory=list)
    constraints: str = ""
    retry_policy_ref: str = "retry:default"
    run_config: RunConfig = field(default_factory=RunConfig)
    subordinate_to: str = ""


@dataclass
class AgentTask:
    agent_task_id: str
    subtask_id: str
    agent_id: str
    contract_hash: str
    status: str = "ACTIVE"


@dataclass
class HierarchyChain:
    director_id: str
    manager_id: str
    tool_agent_ids: list[str] = field(default_factory=list)


@dataclass
class TeamSizing:
    block_id: str
    members: int
    roles: list[str] = field(default_factory=list)
    why: str = ""


class SubtaskGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, PlannedSubtask] = {}

    def add(self, node: PlannedSubtask) -> None:
        if not isinstance(node, PlannedSubtask):
            raise ValueError("only planned subtasks execute")
        if node.subtask_id in self.nodes:
            raise ValueError(f"duplicate subtask_id: {node.subtask_id}")
        self.nodes[node.subtask_id] = node

    def validate(self) -> None:
        missing: set[str] = set()
        for node in self.nodes.values():
            for dep in node.dependency_ids:
                if dep not in self.nodes:
                    missing.add(dep)
        if missing:
            raise DependencyError(f"unknown subtask dependencies: {sorted(missing)}")

    def order(self) -> list[str]:
        self.validate()
        permanent: set[str] = set()
        temporary: set[str] = set()
        result: list[str] = []

        def visit(subtask_id: str) -> None:
            if subtask_id in permanent:
                return
            if subtask_id in temporary:
                raise CycleError(f"dependency cycle at {subtask_id}")
            temporary.add(subtask_id)
            for dep in self.nodes[subtask_id].dependency_ids:
                visit(dep)
            temporary.discard(subtask_id)
            permanent.add(subtask_id)
            result.append(subtask_id)

        for subtask_id in self.nodes:
            visit(subtask_id)
        return result


class TaskPlanner:
    def __init__(self) -> None:
        self._plans: dict[tuple[str, str], tuple[str, SubtaskGraph]] = {}

    def plan(
        self,
        package_id: str,
        goal: str,
        specs: Sequence[Mapping[str, Any]],
    ) -> tuple[str, SubtaskGraph]:
        if not package_id.strip():
            raise ValueError("package_id must be non-empty")
        if not goal.strip():
            raise ValueError("goal must be non-empty")
        goal_hash = sha256(goal.encode("utf-8")).hexdigest()
        key = (package_id, goal_hash)
        if key in self._plans:
            return self._plans[key]
        plan_ref = f"plan-{package_id}-{goal_hash[:8]}"
        graph = SubtaskGraph()
        for index, spec in enumerate(specs):
            if not isinstance(spec, Mapping):
                raise ValueError("subtask specs must be mappings")
            subtask_id = str(spec.get("subtask_id") or f"{package_id}:sub-{index:03d}")
            node = PlannedSubtask(
                subtask_id=subtask_id,
                plan_ref=plan_ref,
                goal=str(spec.get("goal", "")),
                task_class=str(spec.get("task_class", "general")),
                risk=str(spec.get("risk", "LOW")),
                required_capabilities=[str(c) for c in spec.get("required_capabilities", ())],  # noqa: E501  # frozen-cite K02
                knowledge_needs=[str(c) for c in spec.get("knowledge_needs", ())],
                tool_needs=[str(c) for c in spec.get("tool_needs", ())],
                acceptance_criteria_refs=[
                    str(c) for c in spec.get("acceptance_criteria_refs", ())
                ],
                dependency_ids=[str(c) for c in spec.get("dependency_ids", ())],
            )
            graph.add(node)
        graph.order()
        self._plans[key] = (plan_ref, graph)
        return plan_ref, graph

    def clear(self) -> None:
        self._plans.clear()


def route_task(
    subtask: PlannedSubtask,
    worker_class: str,
    execution_type: str,
    required_capabilities: Sequence[str] = (),
    tool_needs: Sequence[str] = (),
    knowledge_needs: Sequence[str] = (),
    constraints: str = "",
    retry_policy_ref: str = "retry:default",
    manager_id: str = "",
) -> RoutingDecision:
    if not isinstance(subtask, PlannedSubtask):
        raise RoutingRefused("route only planned subtasks")
    if not worker_class.strip():
        raise RoutingRefused("worker_class must be non-empty")
    if not execution_type.strip():
        raise RoutingRefused("execution_type must be non-empty")
    if not manager_id.strip():
        raise RoutingRefused(
            "routing is subordinate to the Manager hierarchy: manager_id required"
        )
    if not retry_policy_ref.strip():
        raise RoutingRefused("retry_policy_ref must be non-empty")
    return RoutingDecision(
        decision_id=f"route-{subtask.subtask_id}",
        subtask_id=subtask.subtask_id,
        worker_class=worker_class.strip(),
        execution_type=execution_type.strip(),
        required_capabilities=[str(c) for c in required_capabilities],
        tool_needs=[str(c) for c in tool_needs],
        knowledge_needs=[str(c) for c in knowledge_needs],
        constraints=constraints,
        retry_policy_ref=retry_policy_ref,
        run_config=RunConfig(
            client_max_retries=0, retry_policy_ref=retry_policy_ref
        ),
        subordinate_to=manager_id.strip(),
    )


def validate_dispatch(
    agent_task: Mapping[str, Any] | AgentTask, graph: SubtaskGraph
) -> AgentTask:
    if isinstance(agent_task, AgentTask):
        data: dict[str, Any] = {
            "agent_task_id": agent_task.agent_task_id,
            "subtask_id": agent_task.subtask_id,
            "agent_id": agent_task.agent_id,
            "contract_hash": agent_task.contract_hash,
            "status": agent_task.status,
        }
    elif isinstance(agent_task, Mapping):
        data = dict(agent_task)
    else:
        raise DispatchRejected("AgentTask must be a mapping")
    subtask_id = str(data.get("subtask_id") or "").strip()
    if not subtask_id:
        raise DispatchRejected("AgentTask without subtask_id rejected at dispatch")
    if subtask_id not in graph.nodes:
        raise DispatchRejected(
            f"only planned AgentTasks execute: {subtask_id} not in the graph"
        )
    return AgentTask(
        agent_task_id=str(data.get("agent_task_id") or f"dispatch-{subtask_id}"),
        subtask_id=subtask_id,
        agent_id=str(data.get("agent_id") or ""),
        contract_hash=str(data.get("contract_hash") or ""),
        status=str(data.get("status") or "ACTIVE"),
    )


def build_graph(
    parts: list[str], deps: list[tuple[str, str]]
) -> dict[str, list[str]]:
    """Build an adjacency map of part -> its dependencies.

    Keys follow the input ``parts`` order. Each ``deps`` entry is a
    ``(part, dependency)`` pair: ``part`` depends on ``dependency``.
    Raises :class:`DependencyError` for unknown dep nodes and
    :class:`CycleError` when dependencies contain a cycle.
    """
    graph: dict[str, list[str]] = {}
    for part in parts:
        if not isinstance(part, str) or not part.strip():
            raise ValueError("parts must be non-empty strings")
        if part in graph:
            raise ValueError(f"duplicate part: {part}")
        graph[part] = []
    for pair in deps:
        part, dependency = pair
        if part not in graph or dependency not in graph:
            raise DependencyError(
                "unknown dep nodes: "
                f"{sorted({part, dependency} - set(graph))}"
            )
        if dependency not in graph[part]:
            graph[part].append(dependency)
    _check_graph_cycles(graph)
    return graph


def _check_graph_cycles(graph: dict[str, list[str]]) -> None:
    permanent: set[str] = set()
    temporary: set[str] = set()

    def visit(node: str) -> None:
        if node in permanent:
            return
        if node in temporary:
            raise CycleError(f"dependency cycle at {node}")
        temporary.add(node)
        for dep in graph[node]:
            visit(dep)
        temporary.discard(node)
        permanent.add(node)

    for node in graph:
        visit(node)


def ready_parts(graph: dict[str, list[str]], completed: set[str]) -> list[str]:
    """Return not-yet-completed parts whose deps are all completed.

    Order follows the graph key order (stable).
    """
    return [
        part
        for part, dependencies in graph.items()
        if part not in completed and all(dep in completed for dep in dependencies)
    ]


def mark_completed(
    graph: dict[str, list[str]], completed: set[str], part: str
) -> set[str]:
    """Return a NEW set with ``part`` added; the input set is unchanged.

    Raises :class:`DependencyError` for a part unknown to the graph.
    """
    if part not in graph:
        raise DependencyError(f"unknown part: {part}")
    updated = set(completed)
    updated.add(part)
    return updated


def control_plane_map() -> dict[str, str]:
    return dict(CONTROL_PLANE_MAP)


def require_explicit_director(ref: str | None) -> str:
    if ref is None or not ref.strip() or ref.strip() == "provisional":
        raise DirectorControlOnly(
            "no live provisional Director default; control-plane-only rule"
        )
    return ref


def stage_rows_to_hierarchy(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    staged: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("staged rows must be mappings")
        row_id = str(row.get("row_id") or "").strip()
        if not row_id:
            raise ValueError("staged row needs a row_id")
        staged.append(
            {"row_id": row_id, "hierarchy_ref": f"ARTIFACT_REF:{row_id}/hierarchy"}
        )
    return staged


class HierarchyConfigStore:
    def __init__(
        self, config: Mapping[str, Any] | None = None, log: DecisionLog | None = None
    ) -> None:
        self.config: dict[str, Any] = {
            "director": "",
            "manager": "",
            "tool_agents": [],
            "integration_policy": "manager-integrates",
            "role_models": {},
            "user_corrections": [],
        }
        if config:
            self.config.update(config)
        self.log: DecisionLog = log if log is not None else DecisionLog()

    def activate_chain(self, chain: HierarchyChain, actor: str) -> ApplyOutcome:
        if not chain.director_id.strip():
            raise HierarchyRefused("chain needs a Director to split")
        if not chain.manager_id.strip():
            raise HierarchyRefused("chain needs a Manager to integrate")
        if not chain.tool_agent_ids:
            raise HierarchyRefused("chain needs tool agents to run parts")
        tools = [str(agent) for agent in chain.tool_agent_ids]
        if len(set(tools)) != len(tools):
            raise HierarchyRefused("tool agent scopes must be distinct")
        if chain.manager_id in tools:
            raise HierarchyRefused("manager must not run as a tool agent")
        self.config["director"] = chain.director_id
        self.config["manager"] = chain.manager_id
        self.config["tool_agents"] = list(tools)
        statement = ensure_compact_english(
            f"activate hierarchy chain with director {chain.director_id} "
            f"manager {chain.manager_id} and {len(tools)} tool agents"
        )
        reason = ensure_compact_english(
            f"director splits work manager {chain.manager_id} integrates "
            f"tool agents run parts"
        )
        row = self.log.append("hierarchy", statement, reason, actor, utc_now())
        return ApplyOutcome(
            accepted=True, reason="chain activated", row=row, surfaced="change applied"
        )

    def append_user_correction(self, actor: str, text: str) -> ApplyOutcome:
        if actor != "user":
            raise HierarchyRefused(
                "only the USER appends to the user corrections channel"
            )
        entry = {"actor": actor, "text": text, "created_at": utc_now()}
        corrections = list(self.config.get("user_corrections", ()))
        corrections.append(entry)
        self.config["user_corrections"] = corrections
        statement = ensure_compact_english("record user correction")
        row = self.log.append("user-correction", statement, text.strip(), actor, utc_now())  # noqa: E501  # frozen-cite K02
        return ApplyOutcome(
            accepted=True, reason="correction recorded", row=row,
            surfaced="change applied",
        )

    def grant_role_authority(
        self, role: str, binding: Mapping[str, Any], actor: str
    ) -> ApplyOutcome:
        role_models = dict(self.config.get("role_models", {}))
        if role not in role_models:
            raise HierarchyRefused(f"unconfigured role: no authority for {role}")
        candidate = dict(binding)
        if candidate.get("model") == MODEL_ID and candidate.get("purpose") == "production":  # noqa: E501  # frozen-cite K02
            raise HierarchyRefused(
                "contributor binding is development-only: production refused"
            )
        role_models[role] = candidate
        self.config["role_models"] = role_models
        statement = ensure_compact_english(f"grant authority for role {role}")
        row = self.log.append("role-authority", statement, statement, actor, utc_now())
        return ApplyOutcome(
            accepted=True, reason="authority granted", row=row,
            surfaced="change applied",
        )

    def close_parent(
        self,
        part_results: Mapping[str, str],
        integration_record: Mapping[str, Any] | None,
    ) -> dict[str, str]:
        record_id = ""
        if isinstance(integration_record, Mapping):
            record_id = str(integration_record.get("record_id") or "").strip()
        if not record_id:
            raise ParentClosureBlocked(
                "parent closure blocked: integration task missing after parts PASS"
            )
        if not part_results:
            raise ParentClosureBlocked("parent closure blocked: no part results")
        failing = sorted(
            part_id for part_id, verdict in part_results.items() if verdict != "PASS"
        )
        if failing:
            raise ParentClosureBlocked(f"parent closure blocked: parts not PASS: {failing}")  # noqa: E501  # frozen-cite K02
        return {
            "parent": "closed",
            "parts": ",".join(sorted(part_results)),
            "integration_ref": record_id,
        }

    def size_team(
        self,
        block_id: str,
        subtask_count: int,
        risk: str,
        actor: str,
    ) -> TeamSizing:
        if not block_id.strip():
            raise ValueError("block_id must be non-empty")
        if risk not in RISK_LEVELS:
            raise ValueError(f"risk must be one of {list(RISK_LEVELS)}")
        if subtask_count < 0:
            raise ValueError("subtask_count must be >= 0")
        members = max(1, subtask_count)
        roles = ["manager"] + ["tool-agent"] * members
        why = ensure_compact_english(
            f"block {block_id.strip()} needs {members} tool agents for "
            f"{subtask_count} subtasks at risk {risk} with manager integration"
        )
        self.log.append(
            "team-sizing", f"size team for {block_id.strip()}", why, actor, utc_now()
        )
        return TeamSizing(
            block_id=block_id.strip(), members=members, roles=roles, why=why
        )

    def get_config(self) -> dict:
        return dict(self.config)

    def validate(self, patch: dict) -> tuple[bool, str]:
        from .delta import validate_config_change

        return validate_config_change(patch, self.config)

    def apply(
        self, scope: str, statement: str, reason: str, authority: str, patch: dict
    ) -> dict:
        from .delta import apply_config_change

        return apply_config_change(
            self.config, self.log.rows, scope, statement, reason, authority, patch
        )


# V2 ONE-HOME: the shared kernel names below are re-exported here (the frozen
# contract test asserts graph.DecisionRow/graph.is_compact_english identity
# with common), so they are listed explicitly to mark the re-export.
__all__ = [
    "ApplyOutcome",
    "DecisionLog",
    "DecisionRow",
    "ensure_compact_english",
    "is_compact_english",
    "utc_now",
]
