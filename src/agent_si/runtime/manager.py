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
At run end the local-tests hook runs one test stage with the run's
data root (explicit, else the executor bind) plus the run's gateway;
a hook failure is recorded on the run, never dropped.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from agent_si.backend import task_turns as _task_turns
from agent_si.backend.agents_live import COST_UNAVAILABLE, record_live_row
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
from agent_si.telemetry import run_store as _telemetry_store

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


_BUDGET_GATE: Any = None


def set_budget_gate(gate: Any) -> Any:
    """Bind the live BudgetGate for post-call charging (test seam safe)."""
    global _BUDGET_GATE
    _BUDGET_GATE = gate
    return gate


def _usage_tokens(usage: Any) -> tuple:
    """Extract input plus output token counts; Nones when not evidenced."""
    if not isinstance(usage, Mapping):
        return (None, None)

    def _as_int(value: Any) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        return None

    inp = _as_int(usage.get("input_tokens"))
    if inp is None:
        inp = _as_int(usage.get("prompt_tokens"))
    outp = _as_int(usage.get("output_tokens"))
    if outp is None:
        outp = _as_int(usage.get("completion_tokens"))
    return (inp, outp)


def _kb_price_for_manager(provider_id: str, model: str) -> tuple:
    """KB input plus output price for one pair; Nones when unknown.

    Logs the exact provider/model pair plus the normalized bare id
    and the hit/miss outcome, so a live price lookup miss names the
    pair (K04SPEND2 L3 diagnosis; never raises, never invents a price).
    """
    try:
        import logging as _logging
        _log = _logging.getLogger(__name__)
    except Exception:
        _log = None  # type: ignore[assignment]
    prov = str(provider_id or "")
    bare = str(model or "")
    if "/" in bare:
        head, _, tail = bare.partition("/")
        if head == prov and tail:
            bare = tail
    try:
        if _log is not None:
            _log.debug("kb price lookup: exact pair %s/%s bare %s",
                       prov, str(model or ""), bare)
    except Exception:
        pass
    try:
        from agent_si.model_kb import kb_reader as _kbr
        reader = _kbr.CatalogKbReader()
        rows = reader.models(prov)
    except Exception:
        try:
            if _log is not None:
                _log.debug("kb price lookup miss (reader error): %s/%s",
                           prov, str(model or ""))
        except Exception:
            pass
        return (None, None)
    for fact in rows or []:
        try:
            fmodel = str(getattr(fact, "model", "") or "")
        except Exception:
            continue
        if "/" in fmodel:
            fmodel = fmodel.split("/")[-1]
        if fmodel != bare:
            continue
        try:
            inp = getattr(fact, "input_price", None)
            outp = getattr(fact, "output_price", None)
        except Exception:
            return (None, None)

        def _num(value: Any) -> float | None:
            if isinstance(value, bool):
                return None
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value.strip())
                except (TypeError, ValueError):
                    return None
            return None
        try:
            if _log is not None:
                _log.debug("kb price lookup hit: %s/%s bare %s in=%s out=%s",
                           prov, str(model or ""), bare, inp, outp)
        except Exception:
            pass
        return (_num(inp), _num(outp))
    try:
        if _log is not None:
            _log.debug("kb price lookup miss (no row): %s/%s bare %s",
                       prov, str(model or ""), bare)
    except Exception:
        pass
    return (None, None)


def _charge_budget_gate(project_id: str, provider_id: str, model: str,
                        usage: Any, run_id: str) -> str | None:
    """Charge the bound BudgetGate from usage times KB price (never raises).

    Kit BUILD_PLAN 657-658: Cost stays UNAVAILABLE without a price snapshot
    (never zero, never estimated); the price snapshot is authoritative and
    every calculated cost references it. Known price: reserve plus settle
    so spent grows by the real cost. Unknown price: leave spent alone and
    let telemetry keep cost UNAVAILABLE (never 0 as if free, never invented).
    A billed turn with a missing price fails loud (log warning, UNAVAILABLE
    marker); usage-absent turns stay UNAVAILABLE by the firewall, never 0.
    A billed turn whose reserve or settle the gate refuses (for example a
    live-scale computed cost above the project's hard limit) fails loud
    the same way: log warning naming the exact provider/model pair plus
    token counts plus cost, UNAVAILABLE marker; served spend is never
    silently reported as 0.
    """
    try:
        import logging as _logging
        _log = _logging.getLogger(__name__)
    except Exception:
        _log = None  # type: ignore[assignment]
    try:
        gate = _BUDGET_GATE
        if gate is None:
            return None
        pid = str(project_id or "run")
        prov = str(provider_id or "")
        mod = str(model or "")
        if not prov:
            return None
        inp_tok, out_tok = _usage_tokens(
            usage if isinstance(usage, Mapping) else {})
        if inp_tok is None and out_tok is None:
            return "UNAVAILABLE"
        inp_price, out_price = _kb_price_for_manager(prov, mod)
        if inp_tok is not None and inp_price is None:
            try:
                if _log is not None:
                    _log.warning("spend UNAVAILABLE: no input price for %s/%s "
                                 "(in=%s out=%s) [MEASURED-absent]", prov, mod,
                                 inp_tok, out_tok)
            except Exception:
                pass
            return "UNAVAILABLE"
        if out_tok is not None and out_price is None:
            try:
                if _log is not None:
                    _log.warning("spend UNAVAILABLE: no output price for %s/%s "
                                 "(in=%s out=%s) [MEASURED-absent]", prov, mod,
                                 inp_tok, out_tok)
            except Exception:
                pass
            return "UNAVAILABLE"
        from decimal import Decimal as _Dec
        # MODEL_KB prices are per 1M tokens (meta.md:96-97: 0.1/0.2 per 1M),
        # so tokens x price must be divided by 1_000_000 (D-K04SPEND3V-01).
        cost = ((_Dec(str(inp_price or "0")) * _Dec(int(inp_tok or 0))
                 + _Dec(str(out_price or "0")) * _Dec(int(out_tok or 0)))
                / _Dec(1_000_000))
        cost_str = str(cost.quantize(_Dec("0.000001")))
        try:
            gate.get_state(pid)
        except Exception:
            return "UNAVAILABLE"
        rid = "chat-%s-%s" % (str(run_id or "run"), prov)
        try:
            gate.compare_and_reserve({
                "project_id": pid, "task_id": "chat",
                "run_id": str(run_id or ""),
                "reservation_id": rid,
                "estimated_amount": cost_str,
                "reserved_at": "2026-10-26T00:00:00Z",
                "expires_at": "2026-10-27T00:00:00Z",
                "provider_id": prov,
            })
        except Exception as exc:
            try:
                if _log is not None:
                    _log.warning("spend UNRECORDED: reserve refused for "
                                 "%s/%s (in=%s out=%s cost=%s) %s: %s "
                                 "[MEASURED-spent]",
                                 prov, mod, inp_tok, out_tok, cost_str,
                                 type(exc).__name__, exc)
            except Exception:
                pass
            return "UNAVAILABLE"
        try:
            gate.settle({
                "reservation_id": rid,
                "actual_amount": cost_str,
                "provider_usage_evidence_ref": "usage-%s" % (str(run_id or ""),),
                "provider_request_ref": "req-%s" % (str(run_id or ""),),
                "source": "provider_usage_api",
                "settled_at": "2026-10-26T01:00:00Z",
            })
        except Exception as exc:
            try:
                if _log is not None:
                    _log.warning("spend UNRECORDED: settle failed for %s/%s "
                                 "(in=%s out=%s cost=%s) %s: %s "
                                 "[MEASURED-spent]",
                                 prov, mod, inp_tok, out_tok, cost_str,
                                 type(exc).__name__, exc)
            except Exception:
                pass
            return "UNAVAILABLE"
        return cost_str
    except Exception as _exc:
        try:
            if _log is not None:
                _log.warning("spend charge failed: %s: %s [MEASURED-absent]",
                             type(_exc).__name__, _exc)
        except Exception:
            pass
        return None


class _RecordingAssuranceHook:
    """Default hook: records each call and notes it, never auto-PASSes."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, call: Mapping[str, Any]) -> bool:
        self.calls.append(dict(call))
        return True


def admit_budget_call(gate: Any, project_id: str, provider_id: str,
                      task_id: str, run_id: str,
                      admission_id: str) -> None:
    """Block one billable call before it runs when the gate refuses.

    Fail-closed (FXLOC C5): a missing gate, an unconfigured project, a
    provider cap or hard limit of 0, or spent/reserved already at or
    over the cap/hard raises the gate's own BudgetBlockedError (existing
    refusal text, existing incident row) before the call. A held
    admission is released before returning, so racing calls serialize
    on the gate lock (reserve, then settle) instead of passing the
    limit. Any other gate failure propagates to the caller (never
    silently allowed); the post-call charge still reports UNAVAILABLE.
    An empty task label defaults to "run" exactly like the project id
    (the gate facade requires a non-empty label; enforcement never
    reads it).
    A release failure of our own admission hold never blocks the
    admitted call (cleanup only, after admission succeeded).
    """
    from agent_si.budget.gate import BudgetBlockedError as _Blocked

    pid = str(project_id or "run")
    tid = str(task_id or "run")
    if gate is None:
        raise _Blocked(
            "no budget gate bound: new billable cloud work is refused "
            "until a gate is configured: project %s task %s run %s "
            "[BUDGET_GATE_MISSING]"
            % (pid, tid,
               str(run_id or "")))
    prov = str(provider_id or "")
    if not prov:
        return None
    # FXLOC2: the gate facade requires a non-empty task label on the
    # admission reservation; task-less callers (watcher model calls)
    # pass "": default it exactly like the project id. Enforcement
    # (caps, hard limit, reserve) never depends on the label.

    try:
        state = gate.get_state(pid)
    except (KeyError, LookupError) as exc:
        raise _Blocked(
            "unknown budget project %s: new billable cloud work is "
            "refused until the project is configured: task %s run %s "
            "[BUDGET_PROJECT_UNKNOWN]"
            % (pid, tid, str(run_id or ""))) from exc
    from decimal import Decimal as _Dec

    hard = _Dec(str(getattr(state, "hard_limit", "0") or "0"))
    if hard <= 0:
        raise _Blocked(
            "hard budget limit blocks new billable cloud work: "
            "project %s task %s run %s requested 0 %s would exceed "
            "hard %s %s (spent %s, reserved %s) [BUDGET_HARD_BLOCKED]"
            % (pid, tid, str(run_id or ""),
               str(getattr(state, "currency", "") or ""),
               getattr(state, "hard_limit", "0"),
               str(getattr(state, "currency", "") or ""),
               getattr(state, "spent", "0"),
               getattr(state, "reserved", "0")))
    caps = getattr(state, "provider_spend_caps", None) or {}
    cap = caps.get(prov)
    if cap is not None and _Dec(str(cap)) <= 0:
        raise _Blocked(
            "provider budget spend cap blocks new billable cloud work"
            ": project %s provider %s requested 0 %s would exceed "
            "cap %s %s [PROVIDER_SPEND_CAP_BLOCKED]"
            % (pid, prov,
               str(getattr(state, "currency", "") or ""), cap,
               str(getattr(state, "currency", "") or "")))
    try:
        gate.compare_and_reserve({
            "project_id": pid, "task_id": tid,
            "run_id": str(run_id or ""),
            "reservation_id": str(admission_id),
            "estimated_amount": "0",
            "reserved_at": "2026-10-26T00:00:00Z",
            "expires_at": "2026-10-27T00:00:00Z",
            "provider_id": prov,
        })
    except _Blocked:
        raise
    try:
        gate.release(str(admission_id), "admission ok")
    except Exception:
        pass
    return None


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


def _telemetry_report_usage(
    provider: Any,
    shape: dict[str, Any],
    run_id: str,
    response: Any,
) -> None:
    """Append cloud_calls + usage + PROVIDER_USAGE_REPORTED (never raises)."""
    try:
        config = getattr(provider, "config", None)
        raw_pid = getattr(config, "provider_id", "") if config else ""
        provider_id = str(raw_pid or "")
        raw_model = getattr(config, "model", "") if config else ""
        model = str(raw_model or "")
        usage = getattr(response, "usage", None)
        if usage is None and isinstance(response, Mapping):
            usage = response.get("usage")
        _telemetry_store.record_provider_usage(
            project_id=str(shape.get("project_id") or "run"),
            task_id=str(shape.get("task_id") or ""),
            run_id=str(run_id or ""),
            provider=provider_id,
            model=model,
            usage=usage,
        )
        try:
            _charge_budget_gate(
                str(shape.get("project_id") or "run"),
                provider_id, model, usage, str(run_id or ""))
        except Exception:
            pass
    except Exception:
        pass


def _telemetry_report_terminated(
    shape: dict[str, Any],
    run_id: str,
    reason: str,
) -> None:
    """Append one RUN_TERMINATED event (never raises, never stores secrets)."""
    try:
        _telemetry_store.record_run_terminated(
            project_id=str(shape.get("project_id") or "run"),
            task_id=str(shape.get("task_id") or ""),
            run_id=str(run_id or ""),
            reason=str(reason or ""),
        )
    except Exception:
        pass


def _close_owner_gone(
    shape: dict[str, Any],
    run_id: str,
    subtask_id: str,
    agent: str,
    model: str = "",
) -> None:
    """Close an orphaned stream: terminal BLOCKED row + one log line.

    FXCLASS CB-10: the app stays alive but the stream owner is truly
    gone (tab switch, network drop). Never kill a run for navigation;
    when the owner of the stream is gone, the live row reaches a
    terminal state so the page shows it instead of RUNNING forever.
    """
    try:
        record_live_row(
            f"{run_id}/{subtask_id or shape.get('task_id') or 'run'}",
            {"agent": agent or "manager",
             "scope": f"{shape.get('task_id') or 'task'}/{subtask_id or 'run'}",
             "deliverable": f"artifact://run/{run_id}/output",
             "status": "BLOCKED",
             "role": "manager",
             "model": str(model or ""),
             "step": 0,
             "file": "",
             "cost": COST_UNAVAILABLE,
             "tokens": {"input": None, "output": None},
             "context": f"artifact:run/{run_id}/input",
             "errors": ["owner-gone"],
             "waits": []},
        )
    except Exception:
        pass
    try:
        from agent_si.watcher import journal as _journal

        _journal.append_event(
            str(shape.get("project_id") or "run"), "manager",
            "RUN_OWNER_GONE", "owner-gone: stream closed for run %s" % (run_id,),
            (run_id,))
    except Exception:
        pass


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
    data_root: str | None = None,
    run_end_hook: bool = True,
    app: Any = None,
) -> Iterator[RunEvent]:
    """Stream a Manager run as RunEvents; a terminal event is always last.

    First step is validate_dispatch: a rejected AgentTask yields one
    terminal dispatch_rejected event with ZERO provider/runner calls.
    Raises ProviderUnboundError before yielding when no provider
    adapter is bound; raises AssuranceRefusedError (fail-closed) when
    the assurance hook refuses a tool call. run_end_hook=False skips
    the local-tests stage for sub-runs (hierarchy parts): the hook
    belongs to user-facing turns, and a part run must cost exactly its
    own provider calls.
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
        _telemetry_report_terminated(
            shape, run_id or "run-refused", "dispatch_rejected")
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
    _term_state = {"done": False}

    def _finish(reason: str) -> None:
        if _term_state["done"]:
            return
        _term_state["done"] = True
        _telemetry_report_terminated(shape, active_run_id, reason)
        if reason != "cancelled" and run_end_hook:
            # FXTESTS2 run-end hook (F3): the local-tests switch decides.
            # Switch on runs one test stage with the run's data root plus
            # the run's gateway; switch off records a skip. A hook
            # failure is recorded on the run, never dropped; the run
            # still finishes with its terminal event below.
            try:
                from agent_si.test_runners import (
                    code_executor as _hook_executor,
                )
                from agent_si.test_runners import (
                    run_end as _run_end,
                )

                root = (
                    data_root
                    if data_root
                    else _hook_executor.executor_data_root()
                )
                _run_end.run_local_tests_at_run_end(
                    project_id=str(shape.get("project_id") or ""),
                    run_id=str(active_run_id or ""),
                    task_id=str(shape.get("task_id") or ""),
                    data_root=root,
                    gateway=provider,
                    timeout_s=60.0,
                )
            except Exception as exc:
                try:
                    from agent_si.test_runners import run_end as _run_end

                    _run_end.record_hook_error(
                        str(active_run_id or ""),
                        str(shape.get("project_id") or ""),
                        str(shape.get("task_id") or ""),
                        exc,
                    )
                except Exception:
                    pass

    def _emit(event: RunEvent) -> RunEvent:
        try:
            model = str(
                getattr(getattr(provider, "config", None), "model", "")
                or "")
        except Exception:
            model = ""
        try:
            input_tok, output_tok = _usage_tokens(captured.get("usage"))
        except Exception:
            input_tok, output_tok = (None, None)
        _record(shape, active_run_id, event, validated.subtask_id,
                validated.agent_id or str(manager_id),
                model=model,
                tokens={"input": input_tok, "output": output_tok})
        return event

    try:
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
    except GeneratorExit:
        _finish("cancelled")
        _close_owner_gone(shape, active_run_id, validated.subtask_id,
                           str(manager_id))
        raise
    client_config = SdkClientConfig(max_retries=0)
    captured: dict[str, Any] = {}

    def _runner(payload: dict[str, Any]) -> dict[str, Any]:
        # FXCTX: earlier turns of this project's chat ride along as
        # context (best effort: without an app or on a history read
        # failure the plain single-message call stays, the turn answers).
        try:
            from agent_si.backend import chat_history as _chat_history

            history_messages = _chat_history.chat_messages(
                app, str(shape["project_id"] or "run"),
                str(shape["message"]), exclude_run_id=active_run_id)
        except Exception:
            history_messages = None
        if not history_messages:
            history_messages = [
                {"role": "user", "content": str(shape["message"])}]
        response = provider.invoke(history_messages)
        captured["text"] = str(getattr(response, "output_text", "") or "")
        captured["mock"] = bool(getattr(response, "mock", False))
        captured["finish_reason"] = str(
            getattr(response, "finish_reason", "") or "")
        captured["usage"] = getattr(response, "usage", None)
        _telemetry_report_usage(provider, shape, active_run_id, response)
        return {"ok": True}

    sdk = OpenAIAgentsSDKAdapter(client_config=client_config, runner=_runner)
    interface = OrchestrationInterface(adapter=sdk)
    turn = 0
    while True:
        if turn + 1 > budget:
            _finish("budget_stop")
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
            _finish("error")
            raise AssuranceRefusedError(
                f"assurance hook refused turn {turn} of run {active_run_id}")
        try:
            yield _emit(RunEvent(
                event="tool_call", turn=turn,
                subtask_id=validated.subtask_id,
                detail=f"guarded tool call for turn {turn}",
                data=dict(call),
            ))
        except GeneratorExit:
            _finish("cancelled")
            _close_owner_gone(shape, active_run_id, validated.subtask_id,
                               str(manager_id))
            raise
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
        from agent_si.budget.gate import (
            BudgetBlockedError as _AdmitBlocked,
        )
        try:
            _admit_provider = str(
                getattr(getattr(provider, "config", None),
                        "provider_id", "") or "")
            if _admit_provider:
                admit_budget_call(
                    _BUDGET_GATE, str(shape["project_id"] or "run"),
                    _admit_provider,
                    str(shape["task_id"] or validated.subtask_id),
                    active_run_id,
                    "admit-%s-t%d" % (active_run_id, turn))
        except _AdmitBlocked as _admit_exc:
            _finish("budget_stop")
            try:
                from agent_si.watcher import journal as _admit_journal

                _admit_journal.append_event(
                    str(shape["project_id"] or "run"), "budget",
                    "GUARD_BLOCK", "budget stop: %s" % (_admit_exc,),
                    (active_run_id,))
            except Exception:
                pass
            yield _emit(RunEvent(
                event="budget_stop", turn=turn,
                subtask_id=validated.subtask_id,
                detail="budget stop: %s" % (_admit_exc,),
                data={"budget": budget, "turns": turn,
                      "run_id": active_run_id,
                      "reason": str(_admit_exc),
                      "error": str(_admit_exc)},
            ))
            return
        try:
            result = interface.run_turn(turn_request)
        except Exception:
            _finish("error")
            raise
        if not result.executed:
            _finish("done")
            # FXASK2: the held tool's id rides the done payload (the
            # guarded call's tool_name) so the window answers the ask
            # per tool; holds that name no tool carry no tool_id.
            held_data: dict[str, Any] = {
                "turns": turn, "run_id": active_run_id,
                "output_ref": result.output_ref,
                "executed": False, "approval_requested": True,
                "reason": result.reason,
                "assurance_calls": assurance_calls}
            if result.tool_id:
                held_data["tool_id"] = result.tool_id
            yield _emit(RunEvent(
                event="done", turn=turn,
                subtask_id=validated.subtask_id,
                detail=f"run held: {result.reason}",
                data=held_data,
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
        try:
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
        except GeneratorExit:
            _finish("cancelled")
            _close_owner_gone(shape, active_run_id, validated.subtask_id,
                               str(manager_id))
            raise
        if str(captured.get("finish_reason", "")) == "stop":
            _finish("done")
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
            subtask_id: str, agent: str, model: str = "",
            tokens: Mapping[str, Any] | None = None) -> None:
    """Record one yielded event to the live-row sink (never raises).

    FXPANEL append-only fields ride on the frozen four: role is always
    this manager run, model the bound provider model, step the event
    turn, file the produced output ref, cost the event cost or
    UNAVAILABLE (pricing stays owned by the BudgetGate charge path),
    tokens the latest evidenced usage, context the run input ref,
    errors the refusal reason, waits the pending approval or budget.
    """
    try:
        data = event.data if isinstance(event.data, Mapping) else {}
        errors: list[str] = []
        if event.event == "dispatch_rejected" and data.get("reason"):
            errors.append(str(data.get("reason")))
        if data.get("error"):
            errors.append(str(data.get("error")))
        waits: list[str] = []
        if data.get("approval_requested"):
            waits.append("approval")
        if event.event == "budget_stop":
            waits.append("budget")
        record_live_row(
            f"{run_id}/{subtask_id or shape['task_id'] or 'run'}",
            {"agent": agent or "manager",
             "scope": f"{shape['task_id'] or 'task'}/{subtask_id or 'run'}",
             "deliverable": f"artifact://run/{run_id}/output",
             "status": STATUS_BY_EVENT.get(event.event, "RUNNING"),
             "role": "manager",
             "model": str(model or ""),
             "step": event.turn,
             "file": str(data.get("output_ref") or ""),
             "cost": str(data.get("cost") or COST_UNAVAILABLE),
             "tokens": dict(tokens) if isinstance(tokens, Mapping)
             else {"input": None, "output": None},
             "context": f"artifact:run/{run_id}/input",
             "errors": errors,
             "waits": waits},
        )
    except Exception:
        pass


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
