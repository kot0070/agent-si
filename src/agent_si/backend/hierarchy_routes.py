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
  HierarchyConfigStore.close_parent (Manager integrates). Every dispatched
  part runs through the real run_task_streamed entry (parallel threads
  capped at 2); each verdict comes from the terminal event only, never a
  hardcoded value. Refusals from the real modules surface as HTTP 400
  carrying the module reason; no bound provider answers HTTP 409
  NO_PROVIDER_BOUND.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import HTTPException, Request


def _pinned_identity(table: Any, project_id: str | None,
                     role: str) -> tuple:
    """Provider/model from the PINNED profile for one role (Nones absent).

    Only a PINNED profile names a single model for the run; any other
    mode, a missing profile, or a missing table yields (None, None).
    Never raises.
    """
    if table is None or not project_id:
        return (None, None)
    try:
        profile = table.get_profile(project_id, role)
    except Exception:
        return (None, None)
    if profile is None:
        return (None, None)
    try:
        if str(getattr(profile, "mode", "")) != "PINNED":
            return (None, None)
        return (str(profile.provider), str(profile.model))
    except Exception:
        return (None, None)


def _run_levels(request: Request, project_id: str | None,
                director_id: str, manager_id: str,
                tool_agent_ids: list) -> list[dict[str, Any]]:
    """Per-level role/agent/provider/model from pinned profiles.

    Reads the app's server-side role table (None-safe); levels are
    director, manager, then one worker entry per tool agent. Never
    raises: identity gaps surface as null provider/model, never a
    refused run.
    """
    try:
        ctx = getattr(getattr(request, "app", None), "state", None)
        table = getattr(getattr(ctx, "k04_ctx", None), "role_table", None)
    except Exception:
        table = None
    levels: list[dict[str, Any]] = []
    pairs = [("director", director_id), ("manager", manager_id)]
    pairs.extend(("worker", str(agent)) for agent in tool_agent_ids)
    for role, agent_id in pairs:
        provider, model = _pinned_identity(table, project_id, role)
        levels.append({"role": role, "agent_id": agent_id,
                       "provider": provider, "model": model})
    return levels


def _adapter_model(adapter: Any) -> str:
    """Model string carried by one bound adapter ("" when unevidenced)."""
    try:
        return str(
            getattr(getattr(adapter, "config", None), "model", "") or "")
    except Exception:
        return ""


def _verdict_for_terminal(terminal: Any) -> tuple[str, str, str]:
    """Map one terminal RunEvent to (status, terminal_event, reason).

    PASS only on a real success event; refusal, error, budget stop, or an
    approval hold give FAIL or BLOCKED plus a reason. Never raises.
    """
    try:
        name = str(getattr(terminal, "event", "") or "")
        data = getattr(terminal, "data", {})
        detail = str(getattr(terminal, "detail", "") or "")
    except Exception:
        return ("FAIL", "error", "unreadable terminal event")
    if not isinstance(data, Mapping):
        data = {}
    try:
        reason_field = str(data.get("reason") or "")
    except Exception:
        reason_field = ""
    if name == "done":
        try:
            held = bool(data.get("approval_requested")) or (
                data.get("executed") is False
            )
        except Exception:
            held = False
        if held:
            return (
                "BLOCKED", name,
                reason_field or detail or "run held for approval",
            )
        return ("PASS", name, "")
    if name == "dispatch_rejected":
        return ("FAIL", name, reason_field or detail or "dispatch rejected")
    if name == "budget_stop":
        return (
            "BLOCKED", name,
            detail or reason_field or "turn budget reached",
        )
    if name in ("error", "cancelled"):
        return ("FAIL", name, reason_field or detail or f"run {name}")
    return ("FAIL", "error", f"unexpected terminal event {name!r}")


def _consume_part(task: Any, graph: Any, adapter: Any, *,
                  project_id: str | None, task_id: str, message: str,
                  manager_id: str, run_id: str,
                  model: str) -> dict[str, Any]:
    """Run one dispatched part through the real manager entry to terminal.

    Consumes RunEvents to the terminal event; the verdict comes from that
    outcome only. Never raises: turn failures become FAIL with a reason.
    """
    from agent_si.runtime.manager import run_task_streamed

    subtask_id = str(getattr(task, "subtask_id", "") or "")
    try:
        terminal = None
        for event in run_task_streamed(
            None,
            agent_task=task,
            graph=graph,
            provider_adapter=adapter,
            project_id=project_id,
            task_id=task_id,
            message=message,
            manager_id=manager_id,
            run_id=run_id,
            # Hierarchy part sub-runs skip the run-end hook: the hook
            # belongs to user-facing turns, and each part must cost
            # exactly its own provider calls (adapter calls == parts).
            run_end_hook=False,
        ):
            terminal = event
    except Exception as err:
        return {
            "subtask_id": subtask_id,
            "run_id": run_id,
            "status": "FAIL",
            "terminal_event": "error",
            "model": model,
            "reason": f"{type(err).__name__}: {err}",
        }
    if terminal is None:
        return {
            "subtask_id": subtask_id,
            "run_id": run_id,
            "status": "FAIL",
            "terminal_event": "error",
            "model": model,
            "reason": "manager run yielded no events",
        }
    status, name, reason = _verdict_for_terminal(terminal)
    return {
        "subtask_id": subtask_id,
        "run_id": run_id,
        "status": status,
        "terminal_event": name,
        "model": model,
        "reason": reason,
    }


def _run_dispatched_parts(dispatched: list, graph: Any, adapter: Any, *,
                          project_id: str | None, package_id: str, goal: str,
                          manager_id: str,
                          model: str) -> list[dict[str, Any]]:
    """Run every dispatched part in parallel threads capped at 2, in order.

    Each part runs with goal=message plus the project_id/task_id/run_id of
    this run; live, journal, and budget rows come from the real run.
    """
    def _one(task: Any) -> dict[str, Any]:
        subtask_id = str(getattr(task, "subtask_id", "") or "")
        return _consume_part(
            task, graph, adapter,
            project_id=project_id,
            task_id=package_id,
            message=goal,
            manager_id=manager_id,
            run_id=f"{package_id}:{subtask_id}",
            model=model,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_one, task) for task in dispatched]
        return [future.result() for future in futures]


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
            project_id = str(body.get("project_id") or "").strip() or None
            worker_class = str(body.get("worker_class") or "tool-agent")
            execution_type = str(body.get("execution_type") or "tool-part")
            part_runs = None
            part_results: dict[str, str] = {}
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
            from agent_si.backend import chat_stream as _chat

            adapter = _chat.bind_routed_provider_adapter(
                request.app, project_id)
            if adapter is None:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": _chat.NO_PROVIDER_BOUND,
                        "message": (
                            f"no provider adapter bound for project {project_id!r}"
                        ),
                    },
                ) from None
            levels = _run_levels(request, project_id, director_id,
                                 manager_id, tool_agent_ids)
            worker_models = [
                entry.get("model") for entry in levels
                if entry.get("role") == "worker" and entry.get("model")
            ]
            model = _adapter_model(adapter) or (
                str(worker_models[0]) if worker_models else ""
            )
            part_runs = await asyncio.to_thread(
                _run_dispatched_parts,
                list(dispatched), subgraph, adapter,
                project_id=project_id,
                package_id=package_id,
                goal=goal,
                manager_id=manager_id,
                model=model,
            )
            part_results = {
                str(run["subtask_id"]): str(run["status"])
                for run in part_runs
            }
            integration = store.close_parent(
                part_results,
                {
                    "record_id": "integration-%s" % (package_id,),
                    "manager_id": manager_id,
                },
            )
        except _graph.ParentClosureBlocked as err:
            if part_runs is None:
                raise HTTPException(
                    status_code=400, detail=str(err)
                ) from None
            raise HTTPException(
                status_code=400,
                detail={
                    "reason": str(err),
                    "part_runs": part_runs,
                    "part_results": part_results,
                },
            ) from None
        except (
            ValueError,
            _graph.HierarchyRefused,
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
            "levels": levels,
            "parts": [
                {
                    "gate_verdict_ref": part.gate_verdict_ref,
                    "audit_verdict_ref": part.audit_verdict_ref,
                }
                for part in parts
            ],
            "routed": routed,
            "part_runs": part_runs,
            "part_results": part_results,
            "integration": integration,
        }

    return app
