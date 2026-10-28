"""K02R4 engine entry: chat SSE streaming over a Manager run (M-ENGINE).

Chain: route POST /api/v1/chat/stream -> Manager run events -> the
frozen OrchestrationInterface (run_turn, the SINGLE engine entry) -> the
SDK adapter (SDK calls live only in agent_si.sdk_adapter.sdk_adapter) ->
the routed provider adapter (tests inject the K04 mock adapter at that
boundary only). Route POST /api/v1/chat/cancel ends a live stream by id.

FROZEN seams (owned elsewhere, called here, never redefined):
- ``run_task_streamed``: owned by M-MANAGER. Resolved by lazy import at
  run time; when it is absent the bridge drives the same frozen chain
  directly (OrchestrationInterface -> SDK adapter -> routed provider).
  When neither the manager entry nor a provider adapter is available the
  run is refused honestly (ChatStreamAbsent -> HTTP 404), never faked.
- Agents live rows: owned by M-MANAGER (``live_rows``). Called when
  present; never redefined here. Absent -> the start event carries an
  empty row list, never invented rows.
- ``validate_dispatch`` (agent_si.backend.orchestration.graph): any
  AgentTask crossing this boundary must name a planned subtask; a
  subtask-less AgentTask is rejected BEFORE any provider call and never
  executes.

Validation only lives in ChatStreamRequest; no secrets travel here
(SecretRef refs only, never values; no token in URL).
"""

from __future__ import annotations

import importlib
import json
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

# Error codes (Manifest 21A pattern: module constant + Exception.code).
CHAT_BAD_REQUEST = "CHAT_BAD_REQUEST"
MANAGER_STREAM_ABSENT = "MANAGER_STREAM_ABSENT"
MANAGER_STREAM_FAILED = "MANAGER_STREAM_FAILED"

#: M-MANAGER-owned runtime entry (lazy import, never defined here).
MANAGER_MODULE = "agent_si.backend.runtime_manager"
MANAGER_FN = "run_task_streamed"

#: M-MANAGER-owned agents live rows entry (lazy import, never defined here).
AGENTS_LIVE_MODULE = "agent_si.backend.agents_live"
AGENTS_LIVE_FN = "live_rows"


class ChatBadRequest(ValueError):
    """Chat stream body failed validation (HTTP 400)."""

    code = CHAT_BAD_REQUEST


class ChatStreamAbsent(RuntimeError):
    """No live run engine is reachable (HTTP 404, never a fake stream)."""

    code = MANAGER_STREAM_ABSENT


class ChatStreamFailed(RuntimeError):
    """A bound Manager run failed (HTTP 500)."""

    code = MANAGER_STREAM_FAILED


@dataclass(frozen=True)
class ChatStreamRequest:
    """One chat stream ask: refs only, validation only, never executes."""

    project: str = ""
    task: str = ""
    message: str = ""
    actor: str = ""
    profile: str = ""
    pool: str = ""
    secret_refs: tuple = ()

    @classmethod
    def from_body(cls, body: Any, actor: str) -> ChatStreamRequest:
        """Build from a POST JSON body; raise ChatBadRequest (400) on bad."""
        if not isinstance(body, Mapping):
            raise ChatBadRequest("chat stream needs a JSON object body")
        message = body.get("message", "")
        if not (isinstance(message, str) and message.strip()):
            raise ChatBadRequest("chat stream needs a non-empty message")
        refs = body.get("secret_refs", ())
        if refs is None:
            refs = ()
        if not isinstance(refs, (tuple, list)):
            raise ChatBadRequest("secret_refs must be a list of refs")
        return cls(
            project=str(body.get("project", "") or ""),
            task=str(body.get("task", "") or ""),
            message=message.strip(),
            actor=str(actor or "").strip(),
            profile=str(body.get("profile", "") or ""),
            pool=str(body.get("pool", "") or ""),
            secret_refs=tuple(refs),
        )


def sse_bytes(payload: Mapping[str, Any]) -> bytes:
    """Encode one SSE data frame (deterministic key order, UTF-8)."""
    return (
        "data: " + json.dumps(payload, ensure_ascii=False, sort_keys=True)
        + "\n\n"
    ).encode("utf-8")


def _chat_error_event(stream_id: str, err: Exception) -> dict[str, Any]:
    """Render one terminal error SSE payload for a mid-stream failure."""
    code = getattr(err, "code", None) or type(err).__name__
    if isinstance(err, KeyError) and err.args \
            and isinstance(err.args[0], str):
        message = err.args[0]
    else:
        message = str(err) or type(err).__name__
    return {
        "type": "error",
        "stream_id": stream_id,
        "code": str(code),
        "message": str(message),
    }


def _load_manager_run_task_streamed() -> Any | None:
    """Lazy M-MANAGER entry; None when the manager module is absent."""
    try:
        module = importlib.import_module(MANAGER_MODULE)
    except ImportError:
        return None
    return getattr(module, MANAGER_FN, None)


def _load_manager_bound_provider() -> Any | None:
    """Lazy M-MANAGER bound provider; None when unbound or absent."""
    try:
        module = importlib.import_module(MANAGER_MODULE)
    except ImportError:
        return None
    loader = getattr(module, "bound_provider_adapter", None)
    if loader is None:
        return None
    try:
        return loader() if callable(loader) else loader
    except Exception:
        return None


def _load_agents_live_rows() -> Any | None:
    """Lazy M-MANAGER live-rows entry; None when that module is absent."""
    try:
        module = importlib.import_module(AGENTS_LIVE_MODULE)
    except ImportError:
        return None
    return getattr(module, AGENTS_LIVE_FN, None)


def _live_agent_rows(explicit: Any | None) -> list:
    """Call the M-MANAGER live-rows entry; absent -> [] (never invented)."""
    loader = explicit if explicit is not None else _load_agents_live_rows()
    if loader is None:
        return []
    try:
        rows = loader() if callable(loader) else loader
    except Exception:
        return []
    if isinstance(rows, Mapping):
        nested = rows.get("agents", [])
        return list(nested) if isinstance(nested, list) else []
    return list(rows) if isinstance(rows, (list, tuple)) else []


def guard_agent_task(agent_task: Any, graph: Any) -> Any:
    """Reject a subtask-less/unplanned AgentTask BEFORE any provider call.

    Delegates to the frozen graph.validate_dispatch; never executes.
    """
    from agent_si.backend.orchestration.graph import validate_dispatch

    return validate_dispatch(agent_task, graph)


class ManagerSdkBridge:
    """Engine bridge: Manager run events -> SSE bytes, cancellable by id."""

    def __init__(
        self,
        *,
        provider_adapter: Any | None = None,
        run_task_streamed: Any | None = None,
        agents_live_rows: Any | None = None,
    ) -> None:
        self._provider_adapter = provider_adapter
        self._run_task_streamed = run_task_streamed
        self._agents_live_rows = agents_live_rows
        self._live: dict[str, dict[str, Any]] = {}

    def run(
        self,
        request: ChatStreamRequest,
        *,
        agent_task: Any | None = None,
        graph: Any | None = None,
    ) -> tuple[str, Iterator[bytes]]:
        """Start a stream; return (stream_id, SSE bytes iterator).

        The dispatch guard runs first: a subtask-less AgentTask raises
        DispatchRejected before any provider call. Then the M-MANAGER
        run_task_streamed entry is preferred; without it the frozen
        orchestration chain drives the routed provider adapter; with
        neither, ChatStreamAbsent (honest 404, never a fake stream).
        """
        if agent_task is not None:
            guard_agent_task(agent_task, graph)
        run_task_streamed = self._run_task_streamed
        if run_task_streamed is None:
            run_task_streamed = _load_manager_run_task_streamed()
        if run_task_streamed is None and self._provider_adapter is None:
            raise ChatStreamAbsent(
                "no live chat engine: manager run entry and routed "
                "provider are both absent"
            )
        if (run_task_streamed is not None
                and self._provider_adapter is None
                and _load_manager_bound_provider() is None):
            raise ChatStreamAbsent(
                "no live chat engine: manager run entry has no "
                "routed provider adapter bound"
            )
        stream_id = uuid.uuid4().hex
        run_id = uuid.uuid4().hex
        state: dict[str, Any] = {"cancelled": False}
        self._live[stream_id] = state
        if run_task_streamed is not None:
            iterator = self._manager_events(
                stream_id, run_id, request, state, run_task_streamed)
        else:
            iterator = self._orchestration_events(
                stream_id, run_id, request, state)
        return stream_id, iterator

    def cancel(self, stream_id: str) -> bool:
        """End a live stream; False when the id names no live stream."""
        state = self._live.pop(stream_id, None)
        if state is None:
            return False
        state["cancelled"] = True
        return True

    # -- internals ------------------------------------------------------

    def _finish(self, stream_id: str) -> None:
        self._live.pop(stream_id, None)

    def _start_event(
        self, stream_id: str, run_id: str, request: ChatStreamRequest
    ) -> dict[str, Any]:
        rows = _live_agent_rows(self._agents_live_rows)
        try:
            json.dumps(rows)
        except (TypeError, ValueError):
            rows = []
        return {
            "type": "start",
            "stream_id": stream_id,
            "run_id": run_id,
            "actor": request.actor,
            "project": request.project,
            "task": request.task,
            "profile": request.profile,
            "pool": request.pool,
            "live_agents": len(rows),
            "agents": rows,
        }

    def _manager_events(
        self,
        stream_id: str,
        run_id: str,
        request: ChatStreamRequest,
        state: dict[str, Any],
        run_task_streamed: Any,
    ) -> Iterator[bytes]:
        """Stream RunEvents from the owned M-MANAGER entry as SSE."""
        yield sse_bytes(self._start_event(stream_id, run_id, request))
        if state["cancelled"]:
            yield sse_bytes({"type": "cancelled", "stream_id": stream_id})
            return
        routed = self._provider_adapter
        if routed is not None:
            run_kwargs: dict[str, Any] = {"provider_adapter": routed}
        else:
            run_kwargs = {}
        try:
            run_events = run_task_streamed(request, **run_kwargs)
        except Exception as err:
            self._finish(stream_id)
            yield sse_bytes(_chat_error_event(stream_id, err))
            return
        try:
            for event in run_events:
                if state["cancelled"]:
                    yield sse_bytes(
                        {"type": "cancelled", "stream_id": stream_id})
                    return
                yield sse_bytes(_manager_event_payload(
                    stream_id, run_id, event))
        except Exception as err:
            self._finish(stream_id)
            yield sse_bytes(_chat_error_event(stream_id, err))
            return
        finally:
            self._finish(stream_id)
        yield sse_bytes({**_manager_event_payload(stream_id, run_id, event),
                         "type": "done", "stream_id": stream_id, "run_id": run_id})

    def _orchestration_events(
        self,
        stream_id: str,
        run_id: str,
        request: ChatStreamRequest,
        state: dict[str, Any],
    ) -> Iterator[bytes]:
        """Drive one frozen turn (interface -> SDK -> provider) as SSE."""
        from agent_si.sdk_adapter.orchestration_interface import (
            OrchestrationInterface,
            TurnRequest,
        )
        from agent_si.sdk_adapter.sdk_adapter import (
            OpenAIAgentsSDKAdapter,
            RoutingDecisionBinding,
            RunConfig,
        )

        provider = self._provider_adapter
        yield sse_bytes(self._start_event(stream_id, run_id, request))
        if state["cancelled"] or provider is None:
            if not state["cancelled"]:
                self._finish(stream_id)
            yield sse_bytes({"type": "cancelled", "stream_id": stream_id})
            return
        captured: dict[str, Any] = {}

        def _runner(payload: dict[str, Any]) -> dict[str, Any]:
            response = provider.invoke(
                [{"role": "user", "content": request.message}])
            captured["text"] = response.output_text
            captured["mock"] = bool(response.mock)
            captured["finish_reason"] = response.finish_reason
            return {"ok": True}

        decision = RoutingDecisionBinding(
            decision_id=f"chat-{run_id}",
            project_id=request.project or "chat",
            task_id=request.task or "chat",
            run_id=run_id,
            selected_provider=str(provider.config.provider_id),
            selected_model=str(provider.config.model),
            route="chat",
            strategy="single-turn",
            reason="k02r4-chat-stream",
        )
        run_config = RunConfig.from_routing_decision(
            decision, executor_attempt_max=1)
        interface = OrchestrationInterface(
            adapter=OpenAIAgentsSDKAdapter(runner=_runner))
        turn = TurnRequest(
            project_id=request.project or "chat",
            task_id=request.task or "chat",
            run_id=run_id,
            contract_hash=request.profile or "",
            input_ref=f"artifact:run/{run_id}/input",
            secret_refs=tuple(request.secret_refs),
            run_config=run_config,
        )
        try:
            result = interface.run_turn(turn)
        except Exception as err:
            self._finish(stream_id)
            yield sse_bytes(_chat_error_event(stream_id, err))
            return
        if state["cancelled"]:
            self._finish(stream_id)
            yield sse_bytes({"type": "cancelled", "stream_id": stream_id})
            return
        if not result.executed:
            self._finish(stream_id)
            yield sse_bytes({
                "type": "approval",
                "stream_id": stream_id,
                "run_id": run_id,
                "reason": result.reason,
            })
            return
        yield sse_bytes({
            "type": "delta",
            "stream_id": stream_id,
            "run_id": run_id,
            "text": str(captured.get("text", "")),
        })
        if state["cancelled"]:
            self._finish(stream_id)
            yield sse_bytes({"type": "cancelled", "stream_id": stream_id})
            return
        self._finish(stream_id)
        yield sse_bytes({
            "type": "done",
            "stream_id": stream_id,
            "run_id": run_id,
            "output_ref": result.output_ref,
            "executed": True,
            "approval_requested": False,
            "mock": bool(captured.get("mock", False)),
            "finish_reason": str(captured.get("finish_reason", "")),
        })


def _manager_event_payload(
    stream_id: str, run_id: str, event: Any
) -> dict[str, Any]:
    """Render one frozen manager RunEvent as an SSE payload."""
    if isinstance(event, Mapping):
        payload = dict(event)
        payload.setdefault("stream_id", stream_id)
        payload.setdefault("run_id", run_id)
        payload.setdefault("type", "delta")
        return payload
    data = getattr(event, "data", None)
    if not isinstance(data, Mapping):
        data = {}
    kind = str(getattr(event, "event", None) or "delta")
    if kind == "turn":
        kind = "delta"
    payload = {
        "type": kind,
        "stream_id": stream_id,
        "run_id": run_id,
    }
    text = data.get("text", None)
    if text is not None:
        payload["text"] = str(text)
    for key in ("output_ref", "mock", "executed", "approval_requested",
                "reason", "finish_reason"):
        value = data.get(key, None)
        if value is not None:
            payload[key] = value
    return payload


def build_bridge(
    *,
    provider_adapter: Any | None = None,
    run_task_streamed: Any | None = None,
    agents_live_rows: Any | None = None,
) -> ManagerSdkBridge:
    """Build the chat engine bridge (routes call bridge_for_app)."""
    return ManagerSdkBridge(
        provider_adapter=provider_adapter,
        run_task_streamed=run_task_streamed,
        agents_live_rows=agents_live_rows,
    )


def bridge_for_app(app: Any) -> ManagerSdkBridge:
    """Return the app's shared bridge (one live registry per app).

    The provider adapter is read from app.state.chat_provider_adapter
    when the bridge is first built (tests inject the K04 mock there);
    a later-bound adapter still attaches while the bridge has none.
    """
    bridge = getattr(app.state, "chat_stream_bridge", None)
    if bridge is None:
        bridge = build_bridge(
            provider_adapter=getattr(
                app.state, "chat_provider_adapter", None))
        app.state.chat_stream_bridge = bridge
    elif getattr(bridge, "_provider_adapter", None) is None:
        provider = getattr(app.state, "chat_provider_adapter", None)
        if provider is not None:
            bridge._provider_adapter = provider
    return bridge


__all__ = [
    "AGENTS_LIVE_FN",
    "AGENTS_LIVE_MODULE",
    "CHAT_BAD_REQUEST",
    "MANAGER_FN",
    "MANAGER_MODULE",
    "MANAGER_STREAM_ABSENT",
    "MANAGER_STREAM_FAILED",
    "ChatBadRequest",
    "ChatStreamAbsent",
    "ChatStreamFailed",
    "ChatStreamRequest",
    "ManagerSdkBridge",
    "bridge_for_app",
    "build_bridge",
    "guard_agent_task",
    "sse_bytes",
]
