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

#: No routed provider adapter is bound (M-WIRE L0B-12; the terminal
#: SSE error over HTTP 200, never a 404 stack). A mid-stream manager
#: ProviderUnboundError maps to this code (see _chat_error_event).
NO_PROVIDER_BOUND = "NO_PROVIDER_BOUND"

#: An AgentTask crossing the chat boundary was rejected at dispatch.
CHAT_DISPATCH_REJECTED = "CHAT_DISPATCH_REJECTED"

#: Chat-route guard codes (M-WIRE L0B-11; every error body carries one).
CHAT_ACTOR_MISSING = "CHAT_ACTOR_MISSING"
CHAT_FORBIDDEN = "CHAT_FORBIDDEN"
CHAT_RATE_LIMITED = "CHAT_RATE_LIMITED"

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


def http_error_detail(code: str, message: str) -> dict[str, str]:
    """Build the {code, message} detail for a chat-route HTTP error.

    Every chat error body carries a stable machine code plus a human
    message; secret, key and token text never belong in either field.
    """
    return {"code": str(code), "message": str(message)}


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
    if code == "MANAGER_PROVIDER_UNBOUND":
        # M-WIRE L0B-12: an unbound provider mid-stream is the same
        # terminal condition as the no-provider open (never a 404).
        code = NO_PROVIDER_BOUND
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

    def no_provider_run(
        self, request: ChatStreamRequest, reason: Any | None = None
    ) -> tuple[str, Iterator[bytes]]:
        """Start a stream that ends in NO_PROVIDER_BOUND (M-WIRE L0B-12).

        No provider adapter is bound, so no engine runs: the stream
        carries exactly one `start` plus one terminal `error` event
        with code NO_PROVIDER_BOUND. Served over HTTP 200 SSE, never
        a 404.
        # K04BIND1: optional verbatim failure reason (never secret).
        """
        stream_id = uuid.uuid4().hex
        run_id = uuid.uuid4().hex
        state: dict[str, Any] = {"cancelled": False}
        self._live[stream_id] = state
        if isinstance(reason, str) and reason.strip():
            state["no_provider_reason"] = reason.strip()
        return stream_id, self._no_provider_events(
            stream_id, run_id, request, state)

    def _no_provider_events(
        self,
        stream_id: str,
        run_id: str,
        request: ChatStreamRequest,
        state: dict[str, Any],
    ) -> Iterator[bytes]:
        """Yield start plus the terminal NO_PROVIDER_BOUND error."""
        yield sse_bytes(self._start_event(stream_id, run_id, request))
        if state["cancelled"]:
            self._finish(stream_id)
            yield sse_bytes(
                {"type": "cancelled", "stream_id": stream_id})
            return
        self._finish(stream_id)
        # K04BIND1: append the verbatim last failure reason (never secret).
        base = ("no provider is connected; "
                "connect a provider to enable chat")
        reason = state.get("no_provider_reason")
        if isinstance(reason, str) and reason.strip():
            base = base + " (last error: " + reason.strip() + ")"
        yield sse_bytes({
            "type": "error",
            "stream_id": stream_id,
            "run_id": run_id,
            "code": NO_PROVIDER_BOUND,
            "message": base,
        })

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

    #: SSE event types that end a stream; exactly one is emitted last.
    _TERMINAL_TYPES = frozenset({
        "done", "dispatch_rejected", "budget_stop",
        "cancelled", "error", "approval",
    })

    def _manager_events(
        self,
        stream_id: str,
        run_id: str,
        request: ChatStreamRequest,
        state: dict[str, Any],
        run_task_streamed: Any,
    ) -> Iterator[bytes]:
        """Stream RunEvents from the owned M-MANAGER entry as SSE.

        Exactly one `start` opens the stream (the manager run's own
        start record is consumed, never forwarded) and exactly one
        terminal event closes it: the manager's terminal event when
        it emits one, a synthesized `done` only when it emits none,
        or a single `error` when the run fails first.
        """
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
        terminal_emitted = False
        try:
            for event in run_events:
                if state["cancelled"]:
                    yield sse_bytes(
                        {"type": "cancelled", "stream_id": stream_id})
                    return
                payload = _manager_event_payload(
                    stream_id, run_id, event)
                if payload.get("type") == "start":
                    continue
                yield sse_bytes(payload)
                if payload.get("type") in self._TERMINAL_TYPES:
                    terminal_emitted = True
        except Exception as err:
            self._finish(stream_id)
            if not terminal_emitted:
                yield sse_bytes(_chat_error_event(stream_id, err))
            return
        finally:
            self._finish(stream_id)
        if not terminal_emitted:
            yield sse_bytes({
                "type": "done",
                "stream_id": stream_id,
                "run_id": run_id,
            })

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
    A provider connected after app start binds on first use via
    bind_routed_provider_adapter (M-WIRE L0B-12).
    """
    bridge = getattr(app.state, "chat_stream_bridge", None)
    if bridge is None:
        bridge = build_bridge(
            provider_adapter=getattr(
                app.state, "chat_provider_adapter", None))
        app.state.chat_stream_bridge = bridge
    elif getattr(bridge, "_provider_adapter", None) is None:
        provider = getattr(app.state, "chat_provider_adapter", None)
        if provider is None:
            provider = bind_routed_provider_adapter(app)
        if provider is not None:
            bridge._provider_adapter = provider
    return bridge


def _read_secret_value(credential_store: Any, secret_id: str) -> str:
    """Resolve one secret value at call time (ids in, value out).

    Duck-typed over the credential-store port; raises AdapterConfigError
    (never logs, never stores the value) when the store cannot serve
    it. The value travels only to the provider transport Authorization
    header, never into a body, log, URL or fixture.
    """
    if credential_store is not None and secret_id:
        for attr in ("get_secret", "get", "retrieve", "read",
                     "get_secret_value"):
            loader = getattr(credential_store, attr, None)
            if not callable(loader):
                continue
            try:
                candidate = loader(secret_id)
            except Exception:
                continue
            value = candidate
            if isinstance(candidate, Mapping):
                value = candidate.get("value")
            if isinstance(value, str) and value:
                return value
        try:
            candidate = credential_store[secret_id]
        except Exception:
            candidate = None
        if isinstance(candidate, Mapping):
            candidate = candidate.get("value")
        if isinstance(candidate, str) and candidate:
            return candidate
    from agent_si.providers.adapters.base import AdapterConfigError

    raise AdapterConfigError(
        "secret value unavailable at call time for %r "
        "(bind the credential store value port)" % (secret_id,),
        "chat-bind:secret")


def _gateway_transport(base_url: str, credential_store: Any,
                       secret_ref: Mapping[str, Any]):
    """Build the chat-completions gateway transport (stdlib only).

    The transport performs network I/O only when the bound adapter is
    invoked, which needs an owner-connected provider; it never fires
    in tests (no provider is ever connected there). Secret values
    resolve at call time and travel only in the Authorization header.
    """
    from agent_si.providers.adapters.base import TransportHttpError
    from agent_si.providers.adapters.base import TransportTimeoutError

    secret_id = str((secret_ref or {}).get("secret_id", ""))
    endpoint = str(base_url or "").rstrip("/")

    def _transport(request: Mapping[str, Any]) -> dict[str, Any]:
        import json as _json
        import urllib.error as _urlerror
        import urllib.request as _urlrequest

        value = _read_secret_value(credential_store, secret_id)
        chat_path = str(request.get("chat_path") or "/chat/completions")
        url = endpoint + chat_path
        payload = _json.dumps({
            "model": request.get("model", ""),
            "messages": [dict(item) for item in request.get("messages", [])],
            "stream": False,
        }).encode("utf-8")
        http_request = _urlrequest.Request(
            url, data=payload,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + value},
            method="POST",
        )
        try:
            with _urlrequest.urlopen(http_request, timeout=60) as response:
                raw = response.read().decode("utf-8")
        except _urlerror.HTTPError as exc:
            raise TransportHttpError(
                getattr(exc, "code", 0) or 0, str(exc)) from None
        except _urlerror.URLError as exc:
            raise TransportTimeoutError(str(exc)) from None
        try:
            body = _json.loads(raw)
        except ValueError:
            raise TransportHttpError(502, "gateway answered non-JSON") from None
        choices = body.get("choices") if isinstance(body, dict) else None
        first = choices[0] if isinstance(choices, list) and choices else {}
        content = ""
        finish = "stop"
        if isinstance(first, Mapping):
            message = first.get("message", {})
            if isinstance(message, Mapping):
                content = str(message.get("content", "") or "")
            finish = str(first.get("finish_reason", "") or "stop")
        usage = body.get("usage", {}) if isinstance(body, dict) else {}
        return {
            "output_text": content,
            "finish": finish,
            "usage": dict(usage) if isinstance(usage, Mapping) else {},
        }

    return _transport


def _chat_models_for(ctx: Any, provider_id: str) -> list:
    """Provider-id -> model-id rows from the served ctx KB port."""
    kb = getattr(ctx, "kb", None)
    if kb is None:
        return []
    try:
        facts = kb.models()
    except Exception:
        return []
    models = []
    for fact in facts or []:
        if isinstance(fact, Mapping):
            provider = fact.get("provider")
            model = fact.get("model")
        else:
            provider = getattr(fact, "provider", None)
            model = getattr(fact, "model", None)
        if provider == provider_id and model:
            models.append(str(model))
    return models


def _chat_record_model(ctx: Any, project_id: str) -> str | None:
    """Saved chat model_id for one project, or None (public K04 read)."""
    if not project_id:
        return None
    try:
        from agent_si.backend import pools_routes as _pools
    except ImportError:
        return None
    try:
        record = _pools.get_chat_record(ctx, project_id)
    except Exception:
        return None
    if not isinstance(record, Mapping):
        return None
    model_id = record.get("model_id")
    return str(model_id) if model_id else None


def bind_routed_provider_adapter(app: Any,
                                 project_id: str | None = None) -> Any | None:
    """Bind the routed provider adapter at app start (M-WIRE L0B-12).

    Resolves the owner-connected provider through the K04 public API
    (the app's bound provider facade, the registry facade and the
    routing interface), picks the routed evidenced provider, and builds
    the real gateway adapter (refs only, no key material, no network).
    Sets app.state.chat_provider_adapter and returns the adapter; None
    when nothing routable is connected (the chat route then answers the
    terminal NO_PROVIDER_BOUND event). Never raises: every failure mode
    below returns None so app start and chat open stay total. An already
    bound adapter (e.g. the test seam) is never replaced.
    """
    state = getattr(app, "state", None)
    if state is None:
        return None
    current = getattr(state, "chat_provider_adapter", None)
    if current is not None:
        return current
    ctx = getattr(state, "k04_ctx", None)
    if ctx is None:
        return None
    facade = getattr(ctx, "provider_facade", None)
    if facade is None:
        return None
    try:
        views = facade.list_providers(True)
    except Exception:
        return None
    evidenced = [view for view in (views or [])
                 if getattr(view, "evidenced", False)]
    if not evidenced:
        return None
    routed_ids: set = set()
    for source in ("agent_si.routing.interface",
                   "agent_si.providers.registry.facades"):
        try:
            module = importlib.import_module(source)
        except ImportError:
            continue
        getter = getattr(module, "get_provider", None)
        if not callable(getter):
            continue
        for view in evidenced:
            provider_id = getattr(view, "provider_id", "")
            try:
                candidate = getter(provider_id)
            except Exception:
                continue
            if candidate is not None and getattr(
                    candidate, "evidenced", False):
                routed_ids.add(provider_id)
    wanted_model = _chat_record_model(
        ctx, project_id) if project_id else None
    chosen = None
    chosen_model = None
    if wanted_model:
        provider_part, _, model_part = wanted_model.partition("/")
        for view in evidenced:
            if model_part and getattr(view, "provider_id", "") == provider_part:
                chosen, chosen_model = view, model_part
                break
        if chosen is None and len(evidenced) == 1:
            chosen, chosen_model = evidenced[0], wanted_model
    if chosen is None:
        if len(evidenced) == 1:
            chosen = evidenced[0]
        else:
            ordered = sorted(
                evidenced, key=lambda v: getattr(v, "provider_id", ""))
            for view in ordered:
                if getattr(view, "provider_id", "") in routed_ids:
                    chosen = view
                    break
            if chosen is None:
                chosen = ordered[0]
    provider_id = getattr(chosen, "provider_id", "")
    instance_id = getattr(chosen, "instance_id", "") or "default"
    model = chosen_model
    if not model:
        kb_models = _chat_models_for(ctx, provider_id)
        model = kb_models[0] if kb_models else ""
    if not model or not provider_id:
        return None
    secret_ref = getattr(chosen, "secret_ref", None)
    secret_mapping: dict[str, Any] = {}
    if secret_ref is not None:
        describe = getattr(secret_ref, "describe", None)
        described = None
        if callable(describe):
            try:
                described = describe()
            except Exception:
                described = None
        elif isinstance(secret_ref, Mapping):
            described = secret_ref
        if isinstance(described, Mapping):
            secret_mapping = {key: value for key, value in described.items()
                            if key != "value"}
    base_url = getattr(chosen, "base_url", "") or ""
    credential_store = getattr(ctx, "credential_store", None)
    try:
        from agent_si.providers.adapters.legs import build_leg
    except ImportError:
        return None
    try:
        adapter = build_leg(
            provider_id, model, secret_mapping,
            transport=_gateway_transport(
                base_url, credential_store, secret_mapping),
            instance_id=instance_id,
            base_url=base_url or None,
        )
    except Exception:
        return None
    state.chat_provider_adapter = adapter
    return adapter


__all__ = [
    "AGENTS_LIVE_FN",
    "AGENTS_LIVE_MODULE",
    "CHAT_ACTOR_MISSING",
    "CHAT_BAD_REQUEST",
    "CHAT_DISPATCH_REJECTED",
    "CHAT_FORBIDDEN",
    "CHAT_RATE_LIMITED",
    "MANAGER_FN",
    "MANAGER_MODULE",
    "MANAGER_STREAM_ABSENT",
    "MANAGER_STREAM_FAILED",
    "ChatBadRequest",
    "ChatStreamAbsent",
    "ChatStreamFailed",
    "ChatStreamRequest",
    "ManagerSdkBridge",
    "NO_PROVIDER_BOUND",
    "bind_routed_provider_adapter",
    "bridge_for_app",
    "build_bridge",
    "guard_agent_task",
    "http_error_detail",
    "sse_bytes",
]
