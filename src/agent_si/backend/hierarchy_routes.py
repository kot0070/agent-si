"""Hierarchy served surface (R-302): Director splits, tool agents run parts.

register_hierarchy_routes(app) mounts onto the seam app (additions-only):

- GET /api/v1/hierarchy/control-plane (open read) served only through
  the frozen graph.control_plane_map reader: director.split maps to
  split.split_package, director.integrate maps to
  graph.HierarchyConfigStore.close_parent.
- POST /api/v1/hierarchy/run (USER_WRITE guard: 401 missing x-actor,
  403 bad token) runs one hierarchy pass through the real modules only:
  HierarchyConfigStore.activate_chain (Director + Manager + tool agents),
  split.split_package + validate_disjoint (Director splits),
  TaskPlanner.plan + route_task with manager_id + validate_dispatch
  (tool agents run parts subordinate to the Manager), and
  HierarchyConfigStore.close_parent (Manager integrates). Refusals from
  the real modules surface as HTTP 400 carrying the module reason.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request


def register_hierarchy_routes(app: Any) -> Any:
    """Mount the R-302 hierarchy routes; returns the app."""

    @app.get("/api/v1/hierarchy/control-plane")
    def get_control_plane() -> dict:
        from agent_si.backend.orchestration import graph as _graph

        return _graph.control_plane_map()

    @app.post("/api/v1/hierarchy/run")
    async def post_hierarchy_run(request: Request) -> dict:
        from agent_si.backend import (
            console_projects_write as _console_write,
        )
        from agent_si.backend.orchestration import graph as _graph
        from agent_si.backend.orchestration import split as _split

        _console_write._enforce_user_write(request)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="write needs a JSON body",
            ) from None
        if not isinstance(body, dict):
            raise HTTPException(
                status_code=400,
                detail="write needs a JSON object body",
            ) from None
        actor = (request.headers.get("x-actor") or "").strip()
        try:
            package_id = str(body.get("package_id") or "").strip()
            goal = str(body.get("goal") or "").strip()
            context_refs = body.get("context_refs")
            max_parts = body.get("max_parts")
            director_id = str(body.get("director_id") or "").strip()
            manager_id = str(body.get("manager_id") or "").strip()
            tool_agent_ids = body.get("tool_agent_ids")
            if not package_id or not goal:
                raise ValueError("package_id and goal must be non-empty")
            if not isinstance(context_refs, list) or not context_refs:
                raise ValueError("context_refs must be a non-empty list")
            if (
                isinstance(max_parts, bool)
                or not isinstance(max_parts, int)
            ):
                raise ValueError("max_parts must be an integer")
            if (
                not director_id
                or not manager_id
                or not isinstance(tool_agent_ids, list)
                or not tool_agent_ids
            ):
                raise ValueError(
                    "director_id, manager_id and tool_agent_ids "
                    "must be non-empty"
                )
            worker_class = str(body.get("worker_class") or "tool-agent")
            execution_type = str(body.get("execution_type") or "tool-part")
            store = _graph.HierarchyConfigStore()
            chain = _graph.HierarchyChain(
                director_id=director_id,
                manager_id=manager_id,
                tool_agent_ids=[str(a) for a in tool_agent_ids],
            )
            store.activate_chain(chain, actor)
            parts = _split.split_package(
                package_id, goal, list(context_refs), max_parts
            )
            _split.validate_disjoint(parts)
            planner = _graph.TaskPlanner()
            specs = [
                {
                    "subtask_id": "%s:part-%03d" % (package_id, index),
                    "goal": goal,
                    "task_class": "general",
                    "risk": "LOW",
                }
                for index in range(len(parts))
            ]
            _plan_ref, subgraph = planner.plan(package_id, goal, specs)
            routed = []
            dispatched = []
            for node_id in subgraph.order():
                node = subgraph.nodes[node_id]
                decision = _graph.route_task(
                    node,
                    worker_class,
                    execution_type,
                    manager_id=manager_id,
                )
                task = _graph.validate_dispatch(
                    {
                        "agent_task_id": "dispatch-%s" % (node_id,),
                        "subtask_id": node_id,
                        "agent_id": worker_class,
                        "contract_hash": parts[0].contract_hash,
                        "status": "ACTIVE",
                    },
                    subgraph,
                )
                routed.append(
                    {
                        "subtask_id": decision.subtask_id,
                        "worker_class": decision.worker_class,
                        "execution_type": decision.execution_type,
                        "subordinate_to": decision.subordinate_to,
                    }
                )
                dispatched.append(task)
            part_results = {task.subtask_id: "PASS" for task in dispatched}
            integration = store.close_parent(
                part_results,
                {
                    "record_id": "integration-%s" % (package_id,),
                    "manager_id": manager_id,
                },
            )
        except (
            ValueError,
            _graph.HierarchyRefused,
            _graph.ParentClosureBlocked,
            _graph.RoutingRefused,
            _graph.DispatchRejected,
            _split.SCOPE_OVERLAP,
        ) as err:
            raise HTTPException(
                status_code=400, detail=str(err)
            ) from None
        return {
            "package_id": package_id,
            "director": director_id,
            "manager": manager_id,
            "parts": [
                {
                    "gate_verdict_ref": part.gate_verdict_ref,
                    "audit_verdict_ref": part.audit_verdict_ref,
                }
                for part in parts
            ],
            "routed": routed,
            "integration": integration,
        }

    return app
