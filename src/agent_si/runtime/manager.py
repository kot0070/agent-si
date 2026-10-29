"""K02R4 runtime manager: streamed Manager runs over the frozen chain.

Canonical owner of ``run_task_streamed`` (M-MANAGER). One turn flows:
validate_dispatch (guarded dispatcher) -> route_task (manager_id plus
retry_policy_ref) -> assurance hook (fired before execution) -> frozen
OrchestrationInterface.run_turn (the SINGLE engine entry) ->
OpenAIAgentsSDKAdapter (SDK calls live only there) -> routed provider
adapter (tests inject the K04 mock at that boundary only).

Event names (exactly one terminal event is yielded last):
start (run opened), tool_call (one guarded tool call, hook already
fired), turn (one executed turn), done (run finished), dispatch_rejected
(an AgentTask without a planned subtask_id never executes),
budget_stop (the next turn would exceed the turn budget).

Turn budget: explicit max_agent_steps wins, else
steplimits.limits_for("task", project_id). The SDK layer uses
SdkClientConfig(max_retries=0); runner retries come only from the
RoutingDecision-bound RunConfig (max_runner_retries bound from
executor_attempt_max). Every yielded event is also recorded to the
live-row sink the agents_live module reads, so SSE consumers and
GET /api/v1/agents/live see the same run. No provider calls, no
network, no keys and no token in URL live in this module.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from agent_si.backend import task_turns as _task_turns
from agent_si.backend.agents_live import record_live_row
from agent_si.backend.orchestration import graph as _graph
from agent_si.backend.orchestration import steplimits as _steplimits
from agent_si.sdk_adapter.orchestration_interface import (
    OrchestrationInterface,
    TurnRequest,
)
from agent_si.sdk_adapter.sdk_adapter import (
    OpenAIAgentsSDKAdapter,
    RoutingDecisionBinding,
    RunConfig,
    SdkClientConfig,
    SecretRef,
)

TERMINAL_EVENTS = frozenset(
    {"done", "dispatch_rejected", "budget_stop"})
"""Events that end a stream; exactly one is yielded last."""

STATUS_BY_EVENT = {
    "start": "RUNNING",
    "tool_call": "RUNNING",
    "turn": "RUNNING",
    "done": "RETURNED",
    "dispatch_rejected": "REJECTED",
    "budget_stop": "BLOCKED",
}
"""Live-row status per event (parts-register status spellings)."""

WORKER_CLASS = "tool-agent"
EXECUTION_TYPE = "single-turn"


@dataclass(frozen=True)
class RunEvent:
    """One streamed Manager run event (frozen record, never mutated)."""

    event: str
    turn: int
    subtask_id: str
    detail: str
    data: Mapping[str, Any] = field(default_factory=dict)


class ProviderUnboundError(RuntimeError):
    """No provider adapter is bound for this run (honest refusal)."""

    code = "MANAGER_PROVIDER_UNBOUND"


class AssuranceRefusedError(RuntimeError):
    """The assurance hook refused a tool call (fail-closed, no execute)."""

    code = "MANAGER_ASSURANCE_REFUSED"


_BOUND_PROVIDER: Any = None


def bind_provider_adapter(adapter: Any) -> Any:
    """Bind the composition provider adapter; returns the previous one."""
    global _BOUND_PROVIDER
    previous = _BOUND_PROVIDER
    _BOUND_PROVIDER = adapter
    return previous


def bound_provider_adapter() -> Any | None:
    """Return the bound provider adapter, or None when unbound."""
    return _BOUND_PROVIDER


class _RecordingAssuranceHook:
    """Default hook: records each call and notes it, never auto-PASSes."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, call: Mapping[str, Any]) -> bool:
        self.calls.append(dict(call))
        return True


def _request_value(request: Any, name: str, default: Any = None) -> Any:
    if request is None:
        return default
    value = getattr(request, name, None)
    return default if value is None else value


def _resolve_run_shape(request: Any, explicit: dict[str, Any]) -> dict:
    shape: dict[str, Any] = {
        "project_id": _request_value(request, "project", ""),
        "task_id": _request_value(request, "task", ""),
        "message": _request_value(request, "message", ""),
        "actor": _request_value(request, "actor", ""),
        "profile": _request_value(request, "profile", ""),
        "pool": _request_value(request, "pool", ""),
        "secret_refs": tuple(_request_value(request, "secret_refs", ()) or ()),
    }
    for key, value in explicit.items():
        if value is not None:
            shape[key] = value
    return shape


def _planned_run_task(
    shape: dict[str, Any],
) -> tuple[Any, _graph.SubtaskGraph, str]:
    planner = _graph.TaskPlanner()
    task_id = str(shape["task_id"] or "task")
    subtask_id = f"{task_id}:sub-001"
    plan_ref, graph = planner.plan(
        f"pkg-{shape['project_id'] or 'run'}",
        f"manager run for {task_id}",
        [{"subtask_id": subtask_id, "goal": shape["message"] or task_id,
          "task_class": "general", "risk": "LOW"}],
    )
    agent_task = {
        "agent_task_id": f"dispatch-{subtask_id}",
        "subtask_id": subtask_id,
        "agent_id": str(shape["actor"] or "manager"),
        "contract_hash": str(shape["profile"] or ""),
    }
    return agent_task, graph, plan_ref


def _secret_refs_only(refs: Any) -> tuple:
    items = tuple(refs or ())
    if all(isinstance(item, SecretRef) for item in items):
        return items
    return ()


def run_task_streamed(
    request: Any = None,
    *,
    agent_task: Any = None,
    graph: Any = None,
    provider_adapter: Any = None,
    project_id: str | None = None,
    task_id: str | None = None,
    message: str | None = None,
    max_agent_steps: int | None = None,
    manager_id: str = "manager",
    retry_policy_ref: str = "retry:default",
    executor_attempt_max: int = 0,
    assurance_hook: Callable[[Mapping[str, Any]], Any] | None = None,
    secret_refs: Any = None,
    run_id: str | None = None,
) -> Iterator[RunEvent]:
    """Stream a Manager run as RunEvents; a terminal event is always last.

    First step is validate_dispatch: a rejected AgentTask yields one
    terminal dispatch_rejected event with ZERO provider/runner calls.
    Raises ProviderUnboundError before yielding when no provider
    adapter is bound; raises AssuranceRefusedError (fail-closed) when
    the assurance hook refuses a tool call.
    """
    shape = _resolve_run_shape(request, {
        "project_id": project_id,
        "task_id": task_id,
        "message": message,
        "secret_refs": secret_refs,
    })
    plan_ref: str | None = None
    if agent_task is None and graph is None:
        agent_task, graph, plan_ref = _planned_run_task(shape)
    if graph is None:
        graph = _graph.SubtaskGraph()
    try:
        validated = _graph.validate_dispatch(agent_task, graph)
    except _graph.DispatchRejected as err:
        rejected = RunEvent(
            event="dispatch_rejected", turn=0,
            subtask_id=str(shape["task_id"] or ""),
            detail=f"AgentTask rejected at dispatch: {err}",
            data={"reason": str(err)},
        )
        _record(shape, run_id or "run-refused", rejected,
                str(shape["task_id"] or ""), str(manager_id))
        yield rejected
        return
    planned = graph.nodes[validated.subtask_id]
    if plan_ref is None:
        plan_ref = planned.plan_ref
    budget = (max_agent_steps if max_agent_steps is not None
              else _steplimits.limits_for("task", shape["project_id"] or None))
    provider = (provider_adapter if provider_adapter is not None
                else bound_provider_adapter())
    if provider is None:
        raise ProviderUnboundError(
            f"no provider adapter bound for project {shape['project_id']!r}")
    active_run_id = run_id or uuid.uuid4().hex
    hook = assurance_hook if assurance_hook is not None \
        else _RecordingAssuranceHook()
    assurance_calls = 0

    def _emit(event: RunEvent) -> RunEvent:
        _record(shape, active_run_id, event, validated.subtask_id,
                validated.agent_id or str(manager_id))
        return event

    yield _emit(RunEvent(
        event="start", turn=0, subtask_id=validated.subtask_id,
        detail=f"manager run started for {validated.subtask_id}",
        data={"run_id": active_run_id,
              "project_id": shape["project_id"],
              "task_id": shape["task_id"],
              "manager_id": str(manager_id),
              "budget": budget,
              "provider": str(
                  getattr(getattr(provider, "config", None),
                          "provider_id", "")),
              },
    ))
    client_config = SdkClientConfig(max_retries=0)
    captured: dict[str, Any] = {}

    def _runner(payload: dict[str, Any]) -> dict[str, Any]:
        response = provider.invoke(
            [{"role": "user", "content": str(shape["message"])}])
        captured["text"] = str(getattr(response, "output_text", "") or "")
        captured["mock"] = bool(getattr(response, "mock", False))
        captured["finish_reason"] = str(
            getattr(response, "finish_reason", "") or "")
        return {"ok": True}

    sdk = OpenAIAgentsSDKAdapter(client_config=client_config, runner=_runner)
    interface = OrchestrationInterface(adapter=sdk)
    turn = 0
    while True:
        if turn + 1 > budget:
            yield _emit(RunEvent(
                event="budget_stop", turn=turn,
                subtask_id=validated.subtask_id,
                detail=f"turn budget {budget} reached after {turn} turns",
                data={"budget": budget, "turns": turn,
                      "run_id": active_run_id},
            ))
            return
        turn += 1
        decision = _graph.route_task(
            planned, WORKER_CLASS, EXECUTION_TYPE,
            manager_id=str(manager_id),
            retry_policy_ref=str(retry_policy_ref),
        )
        call = {
            "tool": "provider.invoke",
            "turn": turn,
            "run_id": active_run_id,
            "subtask_id": validated.subtask_id,
            "decision_id": decision.decision_id,
            "retry_policy_ref": decision.retry_policy_ref,
            "manager_id": str(manager_id),
        }
        allowed = hook(call)
        if isinstance(hook, _RecordingAssuranceHook):
            assurance_calls = len(hook.calls)
        else:
            assurance_calls += 1 if allowed else 0
        if not allowed:
            raise AssuranceRefusedError(
                f"assurance hook refused turn {turn} of run {active_run_id}")
        yield _emit(RunEvent(
            event="tool_call", turn=turn,
            subtask_id=validated.subtask_id,
            detail=f"guarded tool call for turn {turn}",
            data=dict(call),
        ))
        binding = RoutingDecisionBinding(
            decision_id=decision.decision_id,
            project_id=str(shape["project_id"] or "run"),
            task_id=str(shape["task_id"] or validated.subtask_id),
            run_id=active_run_id,
            selected_provider=str(
                getattr(getattr(provider, "config", None),
                        "provider_id", "")),
            selected_model=str(
                getattr(getattr(provider, "config", None), "model", "")),
            route="manager",
            strategy="single-turn",
            reason="k02r4-manager-run",
        )
        sdk_run_config = RunConfig.from_routing_decision(
            binding, executor_attempt_max=int(executor_attempt_max))
        turn_request = TurnRequest(
            project_id=str(shape["project_id"] or "run"),
            task_id=str(shape["task_id"] or validated.subtask_id),
            run_id=active_run_id,
            contract_hash=str(validated.contract_hash or ""),
            input_ref=f"artifact:run/{active_run_id}/input",
            secret_refs=_secret_refs_only(shape["secret_refs"]),
            run_config=sdk_run_config,
        )
        result = interface.run_turn(turn_request)
        if not result.executed:
            yield _emit(RunEvent(
                event="done", turn=turn,
                subtask_id=validated.subtask_id,
                detail=f"run held: {result.reason}",
                data={"turns": turn, "run_id": active_run_id,
                      "output_ref": result.output_ref,
                      "executed": False, "approval_requested": True,
                      "reason": result.reason,
                      "assurance_calls": assurance_calls},
            ))
            return
        _task_turns.record_turn(
            str(shape["task_id"] or validated.subtask_id),
            plan=str(plan_ref),
            action="tool-call %s %s" % (
                decision.decision_id, call["tool"]),
            observation="result %s %s %s" % (
                result.output_ref,
                captured.get("finish_reason", ""),
                captured.get("text", "")),
        )
        yield _emit(RunEvent(
            event="turn", turn=turn,
            subtask_id=validated.subtask_id,
            detail=f"turn {turn} executed",
            data={"turn": turn, "run_id": active_run_id,
                  "output_ref": result.output_ref,
                  "text": captured.get("text", ""),
                  "mock": bool(captured.get("mock", False)),
                  "finish_reason": str(
                      captured.get("finish_reason", "")),
                  "client_max_retries": sdk.client_config.max_retries,
                  "max_runner_retries":
                      sdk_run_config.max_runner_retries,
                  "decision_id": decision.decision_id},
        ))
        if str(captured.get("finish_reason", "")) == "stop":
            yield _emit(RunEvent(
                event="done", turn=turn,
                subtask_id=validated.subtask_id,
                detail=f"manager run finished after {turn} turns",
                data={"turns": turn, "run_id": active_run_id,
                      "output_ref": result.output_ref,
                      "executed": True, "approval_requested": False,
                      "mock": bool(captured.get("mock", False)),
                      "finish_reason": str(
                          captured.get("finish_reason", "")),
                      "assurance_calls": assurance_calls},
            ))
            return


def _record(shape: dict[str, Any], run_id: str, event: RunEvent,
            subtask_id: str, agent: str) -> None:
    """Record one yielded event to the live-row sink (never raises)."""
    record_live_row(
        f"{run_id}/{subtask_id or shape['task_id'] or 'run'}",
        {"agent": agent or "manager",
         "scope": f"{shape['task_id'] or 'task'}/{subtask_id or 'run'}",
         "deliverable": f"artifact://run/{run_id}/output",
         "status": STATUS_BY_EVENT.get(event.event, "RUNNING")},
    )


__all__ = [
    "EXECUTION_TYPE",
    "STATUS_BY_EVENT",
    "TERMINAL_EVENTS",
    "WORKER_CLASS",
    "AssuranceRefusedError",
    "ProviderUnboundError",
    "RunEvent",
    "bind_provider_adapter",
    "bound_provider_adapter",
    "run_task_streamed",
]
