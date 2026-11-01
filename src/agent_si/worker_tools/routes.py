"""K06 OC served worker path (MH-1/MH-3 + rows 189/253/254).

Binds per-app in-memory K06 state on app.state and registers the
/api/v1/k06/ handlers. All handlers run the real K06 product modules
(worker_tools dispatcher/escalation/install_records, services
acceptance, script_import text); reads are open, writes keep the K02
guard (401 missing x-actor, 403 bad token via app.state.auth_hook).
"""

from __future__ import annotations

from typing import Any

from fastapi import Request


def bind_k06oc_state(app: Any) -> None:
    """Create fresh per-app K06 OC stores (each create_app starts clean)."""
    from agent_si.services.acceptance import build_acceptance_registry

    app.state.k06oc_runs = {}
    app.state.k06oc_guard_records = []
    app.state.k06oc_acceptance_runs = []
    app.state.k06oc_installs = []
    app.state.k06oc_registry = build_acceptance_registry()


def _write_auth(app: Any, request: Request) -> None:
    """Enforce the write guard: 401 no actor, 403 bad token (fail closed)."""
    from fastapi import HTTPException

    actor = (request.headers.get("x-actor") or "").strip()
    if not actor:
        raise HTTPException(status_code=401, detail="missing x-actor header")
    token = request.headers.get("x-ui-session-token")
    check_auth = app.state.auth_hook
    try:
        ok = bool(check_auth(token, actor, "user_write"))
    except Exception:
        ok = False
    if not ok:
        raise HTTPException(status_code=403, detail="forbidden")


def register_k06oc_routes(app: Any) -> None:
    """Register every K06 OC served route (additions only, no other edit)."""
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse

    from agent_si.script_import import text as _contract_text
    from agent_si.services.acceptance import (
        file_acceptance_run,
        list_acceptance_runs,
    )
    from agent_si.worker_tools import command_runner as _commands
    from agent_si.worker_tools import escalation as _escalation
    from agent_si.worker_tools import install_records as _installs
    from agent_si.worker_tools.dispatcher import (
        dispatch_command,
        guarded_dispatch,
    )
    from agent_si.worker_tools.guard_records import (
        TOOL_NOT_AUTHORIZED,
        list_guard_records,
    )
    from agent_si.worker_tools.registry import (
        ToolNotAuthorizedError,
        ToolNotFoundError,
    )

    @app.post("/api/v1/k06/tools/dispatch")
    async def k06oc_dispatch(request: Request) -> Any:
        """POST dispatch -> real guarded_dispatch over the served registry."""
        _write_auth(app, request)
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        tool = body.get("tool", "")
        argv = body.get("argv", [])
        action_class = body.get("action_class", "R0")
        auth = body.get("auth", {})
        task_authorized = body.get("task_authorized")
        if not isinstance(auth, dict):
            auth = {}
        try:
            result = guarded_dispatch(
                list(argv) if isinstance(argv, list) else argv,
                action_class,
                dict(auth),
                tool=tool,
                registry=app.state.k06oc_registry,
                task_authorized=task_authorized,
                guard_store=app.state.k06oc_guard_records,
            )
        except ToolNotAuthorizedError as exc:
            records = list_guard_records(app.state.k06oc_guard_records)
            if not records:
                return JSONResponse(
                    status_code=404,
                    content={"code": "TOOL_NOT_FOUND", "message": str(exc)},
                )
            return JSONResponse(
                status_code=403,
                content={
                    "code": TOOL_NOT_AUTHORIZED,
                    "message": str(exc),
                    "guard_record": records[-1],
                },
            )
        except ToolNotFoundError as exc:
            return JSONResponse(
                status_code=404,
                content={"code": "TOOL_NOT_FOUND", "message": str(exc)},
            )
        except (TypeError, PermissionError) as exc:
            return JSONResponse(
                status_code=403,
                content={"code": "TOOLGUARD_DENIED", "message": str(exc)},
            )
        return dict(result)

    @app.post("/api/v1/k06/tools/command/start")
    async def k06oc_command_start(request: Request) -> Any:
        """POST command/start -> real spawn via dispatcher, attached."""
        _write_auth(app, request)
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            result = dispatch_command(
                body.get("project_id", ""),
                body.get("run_id", ""),
                body.get("argv", []),
            )
        except (TypeError, ValueError) as exc:
            return JSONResponse(
                status_code=400,
                content={"code": "COMMAND_REJECTED", "message": str(exc)},
            )
        except PermissionError as exc:
            return JSONResponse(
                status_code=403,
                content={"code": "TOOLGUARD_DENIED", "message": str(exc)},
            )
        return dict(result)

    @app.get("/api/v1/k06/tools/command/status")
    def k06oc_command_status(request: Request,
                             run_id: str = "") -> Any:
        """GET command/status -> pid plus liveness for one tracked run."""
        _write_auth(app, request)
        try:
            return dict(_commands.command_status(run_id))
        except (TypeError, ValueError) as exc:
            return JSONResponse(
                status_code=400,
                content={"code": "COMMAND_REJECTED", "message": str(exc)},
            )
        except LookupError as exc:
            return JSONResponse(
                status_code=404,
                content={"code": "COMMAND_UNKNOWN", "message": str(exc)},
            )

    @app.get("/api/v1/k06/guard-records")
    def k06oc_guard_records() -> dict[str, Any]:
        """GET guard-records -> every filed guard decision, oldest first."""
        return {
            "records": list_guard_records(app.state.k06oc_guard_records)
        }

    @app.post("/api/v1/k06/runs/attempt")
    async def k06oc_run_attempt(request: Request) -> Any:
        """POST attempt -> record vs budget; exhaustion parks ESCALATED."""
        _write_auth(app, request)
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            budget = int(body.get("budget", 0))
        except (TypeError, ValueError):
            budget = 0
        state = _escalation.record_attempt(
            app.state.k06oc_runs,
            str(body.get("run_id", "")),
            ok=bool(body.get("ok", False)),
            evidence_ref=str(body.get("evidence_ref", "attempt")),
            budget=budget,
        )
        return dict(state)

    @app.post("/api/v1/k06/runs/{run_id}/resume")
    async def k06oc_run_resume(run_id: str, request: Request) -> Any:
        """POST resume -> parked run back to RUNNING, card cleared."""
        _write_auth(app, request)
        return dict(_escalation.resume_run(app.state.k06oc_runs, run_id))

    @app.post("/api/v1/k06/runs/{run_id}/discard")
    async def k06oc_run_discard(run_id: str, request: Request) -> Any:
        """POST discard -> parked run terminally DISCARDED."""
        _write_auth(app, request)
        return dict(_escalation.discard_run(app.state.k06oc_runs, run_id))

    @app.get("/api/v1/k06/runs/{run_id}")
    def k06oc_run_view(run_id: str) -> dict[str, Any]:
        """GET run view -> run state plus the escalation card when parked."""
        return dict(_escalation.get_run_state(app.state.k06oc_runs, run_id))

    @app.get("/api/v1/k06/chat/cards")
    def k06oc_chat_cards(run_id: str = "") -> dict[str, Any]:
        """GET chat cards -> the escalation card for a parked run."""
        state = _escalation.get_run_state(app.state.k06oc_runs, run_id)
        cards = [state["card"]] if state.get("card") else []
        return {"run_id": run_id, "cards": cards}

    @app.get("/api/v1/k06/script-contract")
    def k06oc_script_contract() -> dict[str, Any]:
        """GET script-contract -> row 189 texts (contract/template/rules)."""
        return {
            "contract_text": _contract_text.contract_text(),
            "template_text": _contract_text.template_text(),
            "instruction_text": _contract_text.instruction_text(),
        }

    @app.post("/api/v1/k06/services/acceptance")
    async def k06oc_acceptance(request: Request) -> Any:
        """POST acceptance -> declared service via the real belt, run filed."""
        _write_auth(app, request)
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        auth = body.get("auth", {})
        if not isinstance(auth, dict):
            auth = {}
        run = file_acceptance_run(
            app.state.k06oc_acceptance_runs,
            service=str(body.get("service", "")),
            argv=list(body.get("argv", [])),
            action_class=str(body.get("action_class", "R0")),
            auth=dict(auth),
            registry=app.state.k06oc_registry,
            task_authorized=body.get("task_authorized"),
            guard_store=app.state.k06oc_guard_records,
        )
        if isinstance(run, dict) and "error" in run and "run_id" not in run:
            raise HTTPException(status_code=400, detail=run)
        return dict(run)

    @app.get("/api/v1/k06/services/acceptance")
    def k06oc_acceptance_list() -> dict[str, Any]:
        """GET acceptance -> every filed declared-services run."""
        return {
            "runs": list_acceptance_runs(app.state.k06oc_acceptance_runs)
        }

    @app.post("/api/v1/k06/installs")
    async def k06oc_install_record(request: Request) -> Any:
        """POST installs -> file one install record (ASK decision)."""
        _write_auth(app, request)
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        return dict(
            _installs.record_install(
                app.state.k06oc_installs,
                tool=str(body.get("tool", "")),
                version=str(body.get("version", "")),
                status=str(body.get("status", "")),
                source=str(body.get("source", "install-ask")),
                verified=bool(body.get("verified", False)),
            )
        )

    @app.get("/api/v1/k06/installs")
    def k06oc_install_view(tool: str | None = None) -> dict[str, Any]:
        """GET installs -> row 254 install-record view (names unknown)."""
        return dict(
            _installs.view_install_records(
                app.state.k06oc_installs, tool=tool
            )
        )
