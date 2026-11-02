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
import os
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

import dataclasses
from fastapi import HTTPException
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

#: FXKBCHAT KB-context reason code (unknown kb_id on chat open).
CHAT_KB_UNKNOWN = "CHAT_KB_UNKNOWN"

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
    kb_id: str = ""
    role: str = ""
    secret_refs: tuple = ()
    # FXDEVRUN entry: the project folder for the autonomous dev
    # engine. Empty keeps today's path; set drives run_dev_task.
    folder: str = ""

    @classmethod
    def from_body(cls, body: Any, actor: str) -> ChatStreamRequest:
        """Build from a POST JSON body; raise ChatBadRequest (400) on bad."""
        if not isinstance(body, Mapping):
            raise ChatBadRequest("chat stream needs a JSON object body")
        message = body.get("message", "")
        if not (isinstance(message, str) and message.strip()):
            alias = body.get("prompt_ref", "")
            if isinstance(alias, str) and alias.strip():
                message = alias
        if not (isinstance(message, str) and message.strip()):
            raise ChatBadRequest("chat stream needs a non-empty message")
        refs = body.get("secret_refs", ())
        if refs is None:
            refs = ()
        if not isinstance(refs, (tuple, list)):
            raise ChatBadRequest("secret_refs must be a list of refs")
        folder = body.get("folder", "")
        if folder is None:
            folder = ""
        if not isinstance(folder, str):
            raise ChatBadRequest("folder must be a project folder string")
        return cls(
            project=str(body.get("project", "") or ""),
            task=str(body.get("task", "") or ""),
            message=message.strip(),
            actor=str(actor or "").strip(),
            profile=str(body.get("profile", "") or ""),
            pool=str(body.get("pool", "") or ""),
            kb_id=str(body.get("kb_id", "") or ""),
            role=str(body.get("role", "") or ""),
            secret_refs=tuple(refs),
            folder=folder,
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


#: Terminal SSE type -> task repo status (FXR4B D1: every run's task,
#: including the first-chat auto task, closes with the run).
_TASK_STATUS_BY_TERMINAL = {
    "done": "done",
    "approval": "held",
    "cancelled": "stopped",
    "error": "failed",
    "budget_stop": "failed",
    "dispatch_rejected": "failed",
}

#: Terminal SSE type -> chat-history turn status (FXR4B D2: the server
#: records the final text + status at the end of every engine turn).
_TURN_STATUS_BY_TERMINAL = {
    "done": "ok",
    "approval": "ok",
    "cancelled": "stopped",
    "error": "failed",
    "budget_stop": "failed",
    "dispatch_rejected": "failed",
}


def _record_server_turn(app: Any, project: str, user_text: str,
                        assistant_text: str, status: str,
                        run_id: str = "", error_code: str = "") -> None:
    """Store one server-side chat turn; never raises, never breaks flow.

    The stream start stores the user message (no run id: every stream
    opens its own row); the terminal write carries the run id. Client
    writes keep their own run ids, so their running/terminal pair
    still upserts to one row.
    """
    try:
        if app is None:
            return
        name = (project or "").strip()
        if not name:
            return
        from agent_si.backend import chat_history as _chathist

        _chathist.record_turn(
            app, name, user_text or "", assistant_text or "",
            status=status, run_id=run_id or "",
            error_code=error_code or "")
    except Exception:
        pass


def _mirror_run_tasks(app: Any, project: str, task: str,
                      message: str, status: str) -> None:
    """Mirror one stream's state onto its task rows; never raises."""
    try:
        if app is None:
            return
        from agent_si.backend import (
            console_projects_write as _task_write,
        )

        _task_write.mirror_run_task_status(
            app, project or "", task or "", message or "", status)
    except Exception:
        pass


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


# -- FXKBCHAT KB-context block (the only KB code in this file) --
# Chat for a project with an attached KB (or an explicit kb_id)
# retrieves top sections through the frozen retriever.retrieve
# (never reimplemented here), passes them as provider context,
# and cites them in the streamed answer.


def _kb_retriever() -> Any:
    """Lazy KB retriever (real behaviour; never redefined here)."""
    try:
        from agent_si.kb import retriever as module
    except ImportError:
        from src.agent_si.kb import retriever as module
    return module


def _kb_registry() -> Any:
    """Lazy KB registry (read-only views; never redefined here)."""
    try:
        from agent_si.kb import registry as module
    except ImportError:
        from src.agent_si.kb import registry as module
    return module


def _kb_scope_for(request: ChatStreamRequest) -> tuple:
    """Resolve (project_id, role, only_kb_id) for one chat open.

    An explicit kb_id wins: an unattached kb_id raises an honest
    404 (CHAT_KB_UNKNOWN) so the route answers it directly; an
    attached kb_id scopes the retrieve to that KB's own
    (project_id, role). Otherwise the request (project, role)
    scopes the retrieve. app.py is lane-frozen, so the 404 is
    raised here as an HTTPException the route lets through.
    """
    only_kb_id = request.kb_id
    if only_kb_id:
        registry = _kb_registry()
        if not registry.is_attached(only_kb_id):
            raise HTTPException(
                status_code=404,
                detail=http_error_detail(
                    CHAT_KB_UNKNOWN,
                    "unknown kb_id: %r" % (only_kb_id,)),
            )
        source = registry.attached_source(only_kb_id)
        if source is None:
            raise HTTPException(
                status_code=404,
                detail=http_error_detail(
                    CHAT_KB_UNKNOWN,
                    "unknown kb_id: %r" % (only_kb_id,)),
            )
        return (source.project_id, source.role or "", only_kb_id)
    return (request.project, request.role or "", "")


def _kb_chunk_field(chunk: Any, name: str) -> str:
    """Read one text field from a retrieved KB chunk."""
    value = getattr(chunk, name, "")
    return value if isinstance(value, str) else ""


def _kb_chunk_citation(chunk: Any) -> str:
    """Citation for one chunk (falls back to kb_id#section_id)."""
    citation = _kb_chunk_field(chunk, "citation")
    if citation:
        return citation
    return "%s#%s" % (_kb_chunk_field(chunk, "kb_id"),
                      _kb_chunk_field(chunk, "section_id"))


def _kb_chunks_for(request: ChatStreamRequest) -> list:
    """Retrieve KB chunks for one chat open (never fails chat).

    Calls the frozen retriever.retrieve; an unknown explicit
    kb_id raises 404 via _kb_scope_for. Any other retrieval
    failure degrades to no chunks: KB enrichment never fails
    the chat itself.
    """
    project_id, role, only_kb_id = _kb_scope_for(request)
    if not only_kb_id and not project_id:
        return []
    try:
        chunks, _section_log = _kb_retriever().retrieve(
            request.message, project_id, role, None)
    except Exception:
        return []
    if only_kb_id:
        chunks = [chunk for chunk in chunks
                if _kb_chunk_field(chunk, "kb_id") == only_kb_id]
    return list(chunks)


def _kb_context_prefix(chunks: list) -> str:
    """Provider input prefix carrying the retrieved sections."""
    if not chunks:
        return ""
    lines = ["[%s]\n%s" % (_kb_chunk_citation(chunk),
                             _kb_chunk_field(chunk, "text"))
             for chunk in chunks]
    return ("KB context:\n" + "\n\n".join(lines)
            + "\n\nUser message:\n")


def _kb_citations_note(chunks: list) -> str:
    """Answer suffix citing every retrieved section."""
    if not chunks:
        return ""
    lines = ["- %s\n%s" % (_kb_chunk_citation(chunk),
                             _kb_chunk_field(chunk, "text"))
             for chunk in chunks]
    return "\n\nKB sources:\n" + "\n".join(lines)


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
        kb_chunks = _kb_chunks_for(request)
        kb_note = _kb_citations_note(kb_chunks)
        if kb_chunks:
            request = dataclasses.replace(
                request,
                message=_kb_context_prefix(kb_chunks) + request.message)
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
        state: dict[str, Any] = {"cancelled": False,
                                 "project_id": request.project}
        self._live[stream_id] = state
        # FXDEVRUN entry: project+folder+bound provider drives the
        # autonomous dev engine through the same manager-events path
        # (same RunEvent objects, same SSE rendering); anything else
        # keeps today's path.
        devrun_entry = self._devrun_entry(request, state)
        if devrun_entry is not None:
            return stream_id, self._manager_events(
                stream_id, run_id, request, state, devrun_entry,
                kb_note=kb_note)
        if run_task_streamed is not None:
            iterator = self._manager_events(
                stream_id, run_id, request, state, run_task_streamed,
                kb_note=kb_note)
        else:
            iterator = self._orchestration_events(
                stream_id, run_id, request, state, kb_note=kb_note)
        return stream_id, iterator

    def no_provider_run(
        self, request: ChatStreamRequest, reason: Any | None = None
    ) -> tuple[str, Iterator[bytes]]:
        # FXKBCHAT: unknown kb_id stays an honest 404 even with
        # no provider bound (input check runs before the stream).
        _kb_scope_for(request)
        """Start a stream that ends in NO_PROVIDER_BOUND (M-WIRE L0B-12).

        No provider adapter is bound, so no engine runs: the stream
        carries exactly one `start` plus one terminal `error` event
        with code NO_PROVIDER_BOUND. Served over HTTP 200 SSE, never
        a 404.
        # K04BIND1: optional verbatim failure reason (never secret).
        """
        stream_id = uuid.uuid4().hex
        run_id = uuid.uuid4().hex
        state: dict[str, Any] = {"cancelled": False,
                                 "project_id": request.project}
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

    def _devrun_folder(
        self, app: Any, project: str, folder: str
    ) -> tuple:
        """Resolve the devrun working folder: (folder, honest).

        An explicit body folder wins: an existing dir is used, an
        absolute missing path ends the stream with one honest line.
        A non-absolute ref (the first-message box stores its text as
        the project folder_ref) uses the managed folder
        <data-dir>/workspaces/<project_id>, created on demand through
        the app data dir. honest is None when the engine may run.
        """
        candidate = str(folder or "")
        if not candidate:
            try:
                from agent_si.backend import (
                    console_projects_write as _write,
                )
                from agent_si.backend import read_routes as _reads

                projects, _tasks = _reads.repos_for(app)
                stored = _write._stored_project(projects, project)
                if stored is not None:
                    candidate = str(stored.get("folder_ref") or "")
            except Exception:
                candidate = ""
        if not candidate:
            return "", None
        if os.path.isabs(candidate):
            if os.path.isdir(candidate):
                return candidate, None
            return "", ("project folder not found: %s; "
                        "choose in Projects" % (candidate,))
        data_dir = getattr(getattr(app, "state", None), "data_dir", None)
        if not data_dir:
            return "", ("project folder not found: %s; "
                        "choose in Projects" % (candidate,))
        managed = os.path.join(
            str(data_dir), "workspaces", str(project))
        try:
            os.makedirs(managed, exist_ok=True)
        except Exception:
            return "", ("project folder not found: %s; "
                        "choose in Projects" % (candidate,))
        if not os.path.isdir(managed):
            return "", ("project folder not found: %s; "
                        "choose in Projects" % (candidate,))
        return managed, None

    def _devrun_entry(
        self, request: ChatStreamRequest, state: dict[str, Any]
    ) -> Any | None:
        """FXDEVRUN entry: run_dev_task when project+folder bound.

        Returns the run-task-streamed-shaped entry the manager path
        consumes, or None to keep today's path. Never raises. The
        folder resolves from the stored project row when the body
        carries none; the first stream delta names the working
        folder, and a missing absolute path ends the stream with
        one honest line (the engine never runs for it).
        """
        try:
            folder = str(getattr(request, "folder", "") or "")
            project = str(getattr(request, "project", "") or "")
        except Exception:
            return None
        if not project:
            return None
        bound = self._provider_adapter
        if bound is None:
            try:
                bound = _load_manager_bound_provider()
            except Exception:
                bound = None
        if bound is None:
            return None
        app = getattr(self, "_app", None)
        if app is None:
            return None
        resolved, honest = self._devrun_folder(app, project, folder)
        try:
            from agent_si.runtime import devrun as _devrun
        except ImportError:
            return None
        if honest is not None:
            text = str(honest)
            if not text.endswith("\n"):
                text = text + "\n"

            def _honest_entry(
                dev_request: ChatStreamRequest, **kwargs: Any
            ) -> Any:
                yield {"type": "delta", "text": text}
                yield {"type": "done", "text": text}

            return _honest_entry
        if not resolved:
            return None
        effective = request
        if resolved != folder:
            try:
                effective = dataclasses.replace(
                    request, folder=resolved)
            except Exception:
                return None
        try:
            if not _devrun.wants_devrun(effective, bound, app):
                return None
        except Exception:
            return None
        working = "Working folder: %s\n" % (resolved,)

        def _entry(dev_request: ChatStreamRequest, **kwargs: Any) -> Any:
            yield {"type": "delta", "text": working}
            # FXCTX: _manager_events threads app through run kwargs; the
            # engine already takes it explicitly, so drop the duplicate.
            kwargs.pop("app", None)
            yield from _devrun.run_dev_task(
                effective, stream_state=state, app=app, **kwargs)

        return _entry

    def cancel(self, stream_id: str) -> bool:
        """End a live stream; False when the id names no live stream."""
        state = self._live.pop(stream_id, None)
        if state is None:
            return False
        state["cancelled"] = True
        return True

    def cancel_project(self, project_id: str) -> bool:
        """End every live stream of one project (same effect as cancel)."""
        target = str(project_id or "")
        if not target:
            return False
        hit = False
        for stream_id, state in list(self._live.items()):
            try:
                same = str(state.get("project_id") or "") == target
            except Exception:
                continue
            if not same:
                continue
            state = self._live.pop(stream_id, None)
            if isinstance(state, dict):
                state["cancelled"] = True
            hit = True
        return hit

    def cancel_all(self) -> bool:
        """End every live stream (same effect as cancel)."""
        hit = False
        for stream_id, state in list(self._live.items()):
            state = self._live.pop(stream_id, None)
            if isinstance(state, dict):
                state["cancelled"] = True
            hit = True
        return hit

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
        kb_note: str = "",
    ) -> Iterator[bytes]:
        """Stream RunEvents from the owned M-MANAGER entry as SSE.

        Exactly one `start` opens the stream (the manager run's own
        start record is consumed, never forwarded) and exactly one
        terminal event closes it: the manager's terminal event when
        it emits one, a synthesized `done` only when it emits none,
        or a single `error` when the run fails first.

        FXR4B: the server records its own history turn (user message
        at start, final text + status at the end, on the devrun path
        too) and mirrors the run state onto its task rows, so a
        closed window loses no turn and every task closes.
        """
        app = getattr(self, "_app", None)
        project = str(getattr(request, "project", "") or "")
        task = str(getattr(request, "task", "") or "")
        message = str(getattr(request, "message", "") or "")
        texts: list[str] = []
        closed = False

        def _close(kind: str, error_code: str = "") -> None:
            """Store the terminal turn + mirror tasks once (idempotent)."""
            nonlocal closed
            if closed:
                return
            closed = True
            history_status = _TURN_STATUS_BY_TERMINAL.get(kind, "failed")
            task_status = _TASK_STATUS_BY_TERMINAL.get(kind, "failed")
            final = "\n".join(text for text in texts if text)
            _record_server_turn(
                app, project, message, final, history_status,
                run_id=run_id, error_code=error_code)
            _mirror_run_tasks(app, project, task, message, task_status)

        yield sse_bytes(self._start_event(stream_id, run_id, request))
        _record_server_turn(app, project, message, "", "running")
        _mirror_run_tasks(app, project, task, message, "running")
        if state["cancelled"]:
            yield sse_bytes({"type": "cancelled", "stream_id": stream_id})
            _close("cancelled", error_code="STOPPED")
            return
        routed = self._provider_adapter
        if routed is not None:
            run_kwargs: dict[str, Any] = {"provider_adapter": routed}
        else:
            run_kwargs = {}
        # FXCTX: hand the manager the app so its provider call carries
        # the earlier turns; entries with no app seam keep old kwargs.
        if app is not None:
            run_kwargs["app"] = app
        try:
            run_events = run_task_streamed(request, **run_kwargs)
        except Exception as err:
            self._finish(stream_id)
            yield sse_bytes(_chat_error_event(stream_id, err))
            _close("error", error_code=str(
                getattr(err, "code", None) or type(err).__name__))
            return
        terminal_emitted = False
        try:
            for event in run_events:
                if state["cancelled"]:
                    yield sse_bytes(
                        {"type": "cancelled", "stream_id": stream_id})
                    _close("cancelled", error_code="STOPPED")
                    return
                payload = _manager_event_payload(
                    stream_id, run_id, event)
                if payload.get("type") == "start":
                    continue
                if (kb_note and payload.get("type") == "delta"
                        and isinstance(payload.get("text"), str)
                        and not state.get("kb_cited")):
                    payload["text"] = payload["text"] + kb_note
                    state["kb_cited"] = True
                text = payload.get("text")
                if isinstance(text, str) and text:
                    texts.append(text)
                yield sse_bytes(payload)
                if payload.get("type") in self._TERMINAL_TYPES:
                    terminal_emitted = True
                    kind = str(payload.get("type"))
                    if kind == "done" and payload.get(
                            "approval_requested") is True:
                        task_kind = "approval"
                    else:
                        task_kind = kind
                    history_status = _TURN_STATUS_BY_TERMINAL.get(
                        kind, "failed")
                    task_status = _TASK_STATUS_BY_TERMINAL.get(
                        task_kind, "failed")
                    final = "\n".join(
                        text for text in texts if text)
                    if not closed:
                        closed = True
                        _record_server_turn(
                            app, project, message, final,
                            history_status, run_id=str(
                                payload.get("run_id") or run_id),
                            error_code=str(payload.get("code") or ""))
                        _mirror_run_tasks(
                            app, project, task, message, task_status)
            if not terminal_emitted:
                yield sse_bytes({
                    "type": "done",
                    "stream_id": stream_id,
                    "run_id": run_id,
                })
                _close("done")
        except Exception as err:
            self._finish(stream_id)
            if not terminal_emitted:
                yield sse_bytes(_chat_error_event(stream_id, err))
            _close("error", error_code=str(
                getattr(err, "code", None) or type(err).__name__))
            return
        finally:
            self._finish(stream_id)
            if not closed:
                _close("cancelled", error_code="STOPPED")

    def _orchestration_events(
        self,
        stream_id: str,
        run_id: str,
        request: ChatStreamRequest,
        state: dict[str, Any],
        kb_note: str = "",
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
        app = getattr(self, "_app", None)
        project = str(getattr(request, "project", "") or "")
        task = str(getattr(request, "task", "") or "")
        message = str(getattr(request, "message", "") or "")
        yield sse_bytes(self._start_event(stream_id, run_id, request))
        _record_server_turn(app, project, message, "", "running")
        _mirror_run_tasks(app, project, task, message, "running")
        if state["cancelled"] or provider is None:
            if not state["cancelled"]:
                self._finish(stream_id)
            yield sse_bytes({"type": "cancelled", "stream_id": stream_id})
            _record_server_turn(
                app, project, message, "", "stopped", run_id=run_id,
                error_code="STOPPED")
            _mirror_run_tasks(app, project, task, message, "stopped")
            return
        captured: dict[str, Any] = {}
        meter_role = str(request.role or "chat")
        meter_shape = {
            "project_id": request.project or "chat",
            "task_id": request.task or "chat",
            "run_id": run_id,
            "role": meter_role,
            "provider_id": str(provider.config.provider_id),
            "model": str(provider.config.model),
        }

        def _runner(payload: dict[str, Any]) -> dict[str, Any]:
            from agent_si.runtime.devrun import roles as _roles

            gate = None
            try:
                app = getattr(self, "_app", None)
                ctx = getattr(getattr(app, "state", None), "k04_ctx", None)
                gate = getattr(ctx, "budget_state", None)
            except Exception:
                gate = None
            if gate is None:
                try:
                    from agent_si.runtime import manager as _manager

                    gate = _manager._BUDGET_GATE
                except Exception:
                    gate = None
            _roles.admit_role_call(
                gate, project_id=meter_shape["project_id"],
                task_id=meter_shape["task_id"], run_id=run_id,
                role=meter_role,
                provider_id=meter_shape["provider_id"])
            # FXCTX: earlier turns of this project's chat ride along as
            # context (best effort: a history read failure keeps the
            # plain single-message call, the turn still answers).
            try:
                from agent_si.backend import chat_history as _chat_history

                history_messages = _chat_history.chat_messages(
                    app, project, message, exclude_run_id=run_id)
            except Exception:
                history_messages = None
            if not history_messages:
                history_messages = [
                    {"role": "user", "content": request.message}]
            response = provider.invoke(history_messages)
            captured["text"] = response.output_text
            captured["mock"] = bool(response.mock)
            captured["finish_reason"] = response.finish_reason
            try:
                _roles.settle_role_call(
                    project_id=meter_shape["project_id"],
                    task_id=meter_shape["task_id"], run_id=run_id,
                    role=meter_role,
                    provider_id=meter_shape["provider_id"],
                    model=meter_shape["model"],
                    usage=getattr(response, "usage", None))
            except Exception:
                pass
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
            _record_server_turn(
                app, project, message, "", "failed", run_id=run_id,
                error_code=str(
                    getattr(err, "code", None) or type(err).__name__))
            _mirror_run_tasks(app, project, task, message, "failed")
            return
        if state["cancelled"]:
            self._finish(stream_id)
            yield sse_bytes({"type": "cancelled", "stream_id": stream_id})
            _record_server_turn(
                app, project, message,
                str(captured.get("text", "")), "stopped", run_id=run_id,
                error_code="STOPPED")
            _mirror_run_tasks(app, project, task, message, "stopped")
            return
        if not result.executed:
            self._finish(stream_id)
            # FXASK2: the approval event carries the held tool's id from
            # the turn result (the guarded call's tool_name at
            # sdk_adapter/tool_guard.py:152); the frontend answers it
            # through POST /api/v1/permissions/check, once per tool.
            # Holds that name no tool (B-001) carry no tool_id field.
            approval_event: dict[str, Any] = {
                "type": "approval",
                "stream_id": stream_id,
                "run_id": run_id,
                "reason": result.reason,
            }
            if result.tool_id:
                approval_event["tool_id"] = result.tool_id
            yield sse_bytes(approval_event)
            _record_server_turn(
                app, project, message, str(result.reason or ""), "ok",
                run_id=run_id)
            _mirror_run_tasks(app, project, task, message, "held")
            return
        yield sse_bytes({
            "type": "delta",
            "stream_id": stream_id,
            "run_id": run_id,
            "text": str(captured.get("text", "")) + kb_note,
        })
        if state["cancelled"]:
            self._finish(stream_id)
            yield sse_bytes({"type": "cancelled", "stream_id": stream_id})
            _record_server_turn(
                app, project, message,
                str(captured.get("text", "")), "stopped", run_id=run_id,
                error_code="STOPPED")
            _mirror_run_tasks(app, project, task, message, "stopped")
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
        _record_server_turn(
            app, project, message, str(captured.get("text", "")), "ok",
            run_id=run_id)
        _mirror_run_tasks(app, project, task, message, "done")


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
    # FXASK2: the held tool's id rides the same payload so the window
    # answers the ask per tool; forwarded only when the run names one.
    for key in ("output_ref", "mock", "executed", "approval_requested",
                "reason", "finish_reason", "tool_id"):
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
    # FXDEVRUN entry: the dev engine resolves roles against the app.
    try:
        bridge._app = app
    except Exception:
        pass
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


def _normalize_gateway_usage(usage: Any) -> dict:
    """Map OpenAI-compatible usage keys to METRIC_KEYS names.

    prompt_tokens -> input_tokens, completion_tokens -> output_tokens,
    prompt_tokens_details.cached_tokens -> cached_tokens,
    completion_tokens_details.reasoning_tokens -> reasoning_tokens.
    METRIC_KEYS names win when both are present; nothing is invented:
    a key is set only when an int value is actually present.
    """
    if not isinstance(usage, Mapping):
        return {}
    out: dict = {}

    def _as_int(value: Any) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        return None

    direct = _as_int(usage.get("input_tokens"))
    if direct is None:
        direct = _as_int(usage.get("prompt_tokens"))
    if direct is not None:
        out["input_tokens"] = direct
    direct = _as_int(usage.get("output_tokens"))
    if direct is None:
        direct = _as_int(usage.get("completion_tokens"))
    if direct is not None:
        out["output_tokens"] = direct
    cached = _as_int(usage.get("cached_tokens"))
    if cached is None:
        details = usage.get("prompt_tokens_details")
        if isinstance(details, Mapping):
            cached = _as_int(details.get("cached_tokens"))
    if cached is None:
        details = usage.get("completion_tokens_details")
        if isinstance(details, Mapping):
            cached = _as_int(details.get("cached_tokens"))
    if cached is not None:
        out["cached_tokens"] = cached
    reasoning = _as_int(usage.get("reasoning_tokens"))
    if reasoning is None:
        details = usage.get("completion_tokens_details")
        if isinstance(details, Mapping):
            reasoning = _as_int(details.get("reasoning_tokens"))
    if reasoning is not None:
        out["reasoning_tokens"] = reasoning
    return out


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
        import http.client as _httpclient
        import json as _json
        import urllib.error as _urlerror
        import urllib.request as _urlrequest

        value = _read_secret_value(credential_store, secret_id)
        chat_path = str(request.get("chat_path") or "/chat/completions")
        url = endpoint + chat_path
        raw_model = str(request.get("model", "") or "")
        provider_prefix = ""
        try:
            provider_prefix = str((secret_ref or {}).get("provider_id") or "")
        except Exception:
            provider_prefix = ""
        wire_model = raw_model
        if provider_prefix and wire_model.startswith(provider_prefix + "/"):
            wire_model = wire_model[len(provider_prefix) + 1:]
        elif wire_model.startswith("meta/"):
            wire_model = wire_model[len("meta/"):]
        body_out: dict[str, Any] = {
            "model": wire_model,
            "messages": [dict(item) for item in request.get("messages", [])],
            "stream": False,
        }
        try:
            max_tokens = request.get("max_tokens")
        except Exception:
            max_tokens = None
        if isinstance(max_tokens, int) and not isinstance(max_tokens, bool):
            if max_tokens > 0:
                body_out["max_tokens"] = max_tokens
        payload = _json.dumps(body_out).encode("utf-8")
        http_request = _urlrequest.Request(
            url, data=payload,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + value},
            method="POST",
        )
        try:
            # Aligned with the devrun per-call model bound (300 s):
            # a shorter provider read timeout fired first with an
            # "internal"-looking timeout error while the model call was
            # still inside its bound. Slow-but-healthy calls now run to
            # the same bound; dead connections still fail fast.
            with _urlrequest.urlopen(http_request, timeout=300) as response:
                try:
                    raw = response.read().decode("utf-8")
                except (ValueError, _httpclient.HTTPException):
                    # Truncated/garbled body: transport-level failure, never
                    # raw bytes or text (KEYECHO1); fixed message only.
                    raise TransportTimeoutError(
                        "gateway response unreadable") from None
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
            "usage": _normalize_gateway_usage(usage),
        }

    return _transport


def _preset_models_for(provider_id: str) -> list:
    """Preset catalogue models for one provider (bare ids, never invented)."""
    try:
        from agent_si.providers.registry import presets as _presets
    except ImportError:
        return []
    try:
        preset = _presets.get_preset(provider_id)
    except Exception:
        preset = None
    out: list = []
    try:
        entries = (preset or {}).get("catalogue", ()) or ()
    except Exception:
        entries = ()
    for entry in entries or []:
        text = str(entry or "")
        if not text:
            continue
        if "/" in text:
            text = text.split("/")[-1]
        if text and text not in out:
            out.append(text)
    if provider_id == "meta":
        try:
            extra = tuple(_presets.META_CATALOGUE or ())
        except Exception:
            extra = ()
        for entry in extra:
            text = str(entry or "")
            if "/" in text:
                text = text.split("/")[-1]
            if text and text not in out:
                out.append(text)
    return out


def _connect_models_for(ctx: Any, provider_id: str) -> list:
    """Connect-time model ids for one provider (bare ids, refs only)."""
    facade = getattr(ctx, "provider_facade", None)
    if facade is None:
        return []
    try:
        providers = getattr(facade, "_providers", None)
    except Exception:
        providers = None
    if not isinstance(providers, dict):
        return []
    record = providers.get(provider_id)
    if not isinstance(record, dict):
        return []
    models_map = record.get("models", {})
    if not isinstance(models_map, dict):
        return []
    out: list = []
    for value in models_map.values():
        text = str(value or "")
        if not text:
            continue
        if "/" in text:
            # keep full when it names another provider, else bare
            head, _, tail = text.partition("/")
            if head == provider_id and tail:
                text = tail
        if text and text not in out:
            out.append(text)
    return out


def _chat_models_for(ctx: Any, provider_id: str) -> list:
    """Provider-id -> model-id rows: connected models plus preset catalogue.

    Kit BUILD_PLAN 644-649: every model the connected accounts offer, with
    per-model fields; a field without a source is UNKNOWN, never guessed.
    Chat models are the connected plus evidenced providers models (their
    connect model plus preset catalogue); KB facts only enrich them.
    """
    kb_models: list = []
    kb = getattr(ctx, "kb", None)
    if kb is not None:
        try:
            facts = kb.models()
        except Exception:
            facts = []
        for fact in facts or []:
            if isinstance(fact, Mapping):
                provider = fact.get("provider")
                model = fact.get("model")
            else:
                provider = getattr(fact, "provider", None)
                model = getattr(fact, "model", None)
            if provider == provider_id and model:
                text = str(model)
                if "/" in text:
                    head, _, tail = text.partition("/")
                    if head == provider_id and tail:
                        text = tail
                if text not in kb_models:
                    kb_models.append(text)
    merged: list = []
    for text in _connect_models_for(ctx, provider_id):
        if text not in merged:
            merged.append(text)
    for text in _preset_models_for(provider_id):
        if text not in merged:
            merged.append(text)
    for text in kb_models:
        if text not in merged:
            merged.append(text)
    return merged


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


def _kb_price_for(ctx: Any, provider_id: str) -> tuple:
    """Cheapest known input plus output price for one provider, or Nones."""
    try:
        from agent_si.model_kb import kb_reader as _kbr
    except ImportError:
        return (None, None)
    try:
        reader = _kbr.CatalogKbReader()
        rows = reader.models(provider_id)
    except Exception:
        return (None, None)
    best = None
    for fact in rows or []:
        try:
            inp = getattr(fact, "input_price", None)
            outp = getattr(fact, "output_price", None)
        except Exception:
            continue
        try:
            total = None
            if isinstance(inp, (int, float)) and isinstance(outp, (int, float)):
                total = float(inp) + float(outp)
            elif isinstance(inp, (int, float)):
                total = float(inp)
            elif isinstance(outp, (int, float)):
                total = float(outp)
            else:
                continue
        except Exception:
            continue
        if best is None or total < best[0]:
            best = (total, inp, outp)
    if best is None:
        return (None, None)
    return (best[1], best[2])


def _connect_order(ctx: Any) -> dict:
    """Provider-id -> connection index (insertion order, never alpha)."""
    facade = getattr(ctx, "provider_facade", None)
    try:
        providers = getattr(facade, "_providers", None)
    except Exception:
        providers = None
    if not isinstance(providers, dict):
        return {}
    return {pid: idx for idx, pid in enumerate(providers.keys())}


def _cheapest_fit(evidenced: list, ctx: Any) -> Any | None:
    """Deterministic routed choice: cheapest fitting, unknown price loses.

    Kit BUILD_PLAN 678: served probes with a fake provider (routing prefers
    task fit over alphabet; unknown price loses; modality gate holds).
    Kit BUILD_PLAN 684-686: AUTO probes (a cheapest fitting model that is
    the same for every part is accepted as correct). Never alphabetical:
    ties break by connection order, never by provider-id sort.
    """
    order = _connect_order(ctx)
    scored: list = []
    for view in evidenced or []:
        pid = str(getattr(view, "provider_id", "") or "")
        inp, outp = _kb_price_for(ctx, pid)
        known = isinstance(inp, (int, float)) or isinstance(outp, (int, float))
        try:
            total = 0.0
            if isinstance(inp, (int, float)):
                total += float(inp)
            if isinstance(outp, (int, float)):
                total += float(outp)
        except Exception:
            total = 0.0
        rank = order.get(pid, 10**9)
        scored.append((0 if known else 1, total, rank, pid, view))
    if not scored:
        return None
    scored.sort(key=lambda row: (row[0], row[1], row[2]))
    return scored[0][4]


def _record_chat_decision(state: Any, provider_id: str, model: str,
                          reason: str) -> None:
    """Record why this chat provider was chosen (routing decision reason)."""
    try:
        state.chat_routing_decision = {
            "provider_id": str(provider_id or ""),
            "model": str(model or ""),
            "reason": str(reason or ""),
        }
    except Exception:
        pass
    try:
        ctx = getattr(state, "k04_ctx", None)
        store = getattr(ctx, "store", None)
        if store is not None and hasattr(store, "save_decision"):
            pass
    except Exception:
        pass


def _adapter_matches(adapter: Any, provider_id: str, model: str) -> bool:
    """True when a bound real adapter already serves provider plus model."""
    try:
        config = getattr(adapter, "config", None)
        if config is None:
            return False
        apid = str(getattr(config, "provider_id", "") or "")
        amodel = str(getattr(config, "model", "") or "")
    except Exception:
        return False
    if apid != str(provider_id or ""):
        return False
    if not model:
        return True
    wanted = str(model or "")
    if "/" in wanted:
        wanted = wanted.split("/")[-1]
    have = amodel
    if "/" in have:
        have = have.split("/")[-1]
    return have == wanted


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
    below returns None so app start and chat open stay total. A mock test
    seam is never replaced; a real adapter rebinds when the saved chat
    model names another evidenced provider.
    """
    state = getattr(app, "state", None)
    if state is None:
        return None
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
    current = getattr(state, "chat_provider_adapter", None)
    if current is not None:
        try:
            is_mock = bool(getattr(current, "mock", False))
        except Exception:
            is_mock = False
        try:
            kind = str(getattr(current, "adapter_kind", "") or "")
        except Exception:
            kind = ""
        if is_mock or kind == "mock":
            return current
        if project_id is None:
            return current
        try:
            cur_pid = str(getattr(getattr(current, "config", None),
                                  "provider_id", "") or "")
            cur_model = str(getattr(getattr(current, "config", None),
                                    "model", "") or "")
        except Exception:
            cur_pid, cur_model = "", ""
        if wanted_model:
            want_pid, _, want_part = wanted_model.partition("/")
            want_bare = want_part or wanted_model
            cur_bare = cur_model.split("/")[-1] if "/" in cur_model else cur_model
            if cur_pid == want_pid and cur_bare == want_bare:
                return current
        else:
            # no saved model: keep current when it still names an
            # evidenced provider (start bind stays stable)
            for view in evidenced:
                if str(getattr(view, "provider_id", "") or "") == cur_pid:
                    return current
    chosen = None
    chosen_model = None
    reason = ""
    if wanted_model:
        provider_part, _, model_part = wanted_model.partition("/")
        bare_wanted = model_part or wanted_model
        for view in evidenced:
            if model_part and getattr(view, "provider_id", "") == provider_part:
                chosen, chosen_model = view, model_part
                reason = ("saved chat model %s for project %s" % (
                    wanted_model, project_id))
                break
        if chosen is None and len(evidenced) == 1:
            chosen, chosen_model = evidenced[0], wanted_model
            reason = ("saved chat model %s for project %s "
                      "(single evidenced provider)" % (wanted_model,
                                                       project_id))
        if chosen is None:
            # saved model names an unevidenced provider: fall through to
            # deterministic routed choice, never NO_PROVIDER_BOUND here
            reason = ""
    if chosen is None:
        if len(evidenced) == 1:
            chosen = evidenced[0]
            reason = "single evidenced provider %s" % (
                getattr(chosen, "provider_id", ""),)
        else:
            pool = [v for v in evidenced
                    if str(getattr(v, "provider_id", "") or "") in routed_ids]
            if pool:
                picked = _cheapest_fit(pool, ctx)
                if picked is None:
                    picked = pool[0]
                chosen = picked
                reason = ("routed evidenced provider %s "
                          "(routing prefers task fit over alphabet; "
                          "unknown price loses)" % (
                              getattr(chosen, "provider_id", ""),))
            else:
                chosen = _cheapest_fit(evidenced, ctx)
                if chosen is None:
                    return None
                reason = ("cheapest fitting evidenced provider %s "
                          "(routing prefers task fit over alphabet; "
                          "unknown price loses; saved chat model %s)" % (
                              getattr(chosen, "provider_id", ""),
                              wanted_model or "unset"))
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
    try:
        _record_chat_decision(state, provider_id, model, reason)
    except Exception:
        pass
    return adapter


__all__ = [
    "AGENTS_LIVE_FN",
    "AGENTS_LIVE_MODULE",
    "CHAT_ACTOR_MISSING",
    "CHAT_BAD_REQUEST",
    "CHAT_DISPATCH_REJECTED",
    "CHAT_FORBIDDEN",
    "CHAT_KB_UNKNOWN",
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
