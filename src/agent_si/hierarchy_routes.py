"""K02REST2 hierarchy-routes seam (rows 116/117/87/22 + 33/35/R-301/R-303).

register_k02rest2_routes(app) mounts onto the seam app (additions-only):

- GET /v1/k02rest2/control-plane (open read) served only through the
  frozen graph.control_plane_map reader (row 22).
- POST /v1/k02rest2/delta-intake (USER_WRITE guard: 401 missing
  x-actor, 403 bad token) opens one bounded delta package through the
  real delta.intake_bounded_delta (row 116); an over-bound scope
  refuses with HTTP 400 carrying DELTA_OVER_BOUND.
- POST /v1/k02rest2/delta-close (USER_WRITE guard) closes one delta
  with a link-check through the real delta.close_with_linkcheck
  (row 117); PASS plus PASS plus evidence refs closes PASS, a missing
  evidence joint stays BLOCKED.
- POST /v1/k02rest2/phase-gate (USER_WRITE guard) evaluates the served
  phase gate through the real gates.evaluate_phase_gate (row 87); no
  next phase until CLOSE (HTTP 409 while any verdict is not PASS).
- POST plus GET /v1/k02rest2/part-register (write guarded, read open)
  delegate every row decision to parts.serve_register_part plus
  parts.serve_part_register (row 33, CODER-B owns orchestration).
- POST /v1/k02rest2/ledger-nudge (USER_WRITE guard) delegates to
  ledger.serve_package_nudge (row 35, CODER-B owns orchestration).
- POST /v1/k02rest2/decomposition-record (USER_WRITE guard) delegates
  to teamcard.serve_decomposition_facts (row R-301, CODER-B owns
  orchestration).
- POST /v1/k02rest2/team-sizing (USER_WRITE guard) delegates to
  graph.serve_team_sizing (row R-303, CODER-B owns orchestration).

B-row handlers shape HTTP only and delegate every row decision to the
named orchestration entry point: ValueError/TypeError refuse with
HTTP 400, KeyError/LookupError with HTTP 404, and a still-missing
entry point surfaces HTTP 503 ROW_UNSERVED until CODER-B lands.

K02NEXT2 CODER-A rows (additions only, same USER_WRITE guard shape):

- POST /v1/k02rest2/team-config-change (USER_WRITE guard) validates one
  team config patch through the real teamcard.validate_team_config_change
  and applies it only when valid through the real
  teamcard.apply_team_config_change (row R-358: every configuration
  change validated and recorded before it applies; a refused change
  answers accepted False with its reason and records no row).
- POST /v1/k02rest2/multi-manager-settings (USER_WRITE guard) validates
  one multi-manager settings dict through the real
  overlap.validate_multi_manager_settings (row R-359: an invalid config
  is blocked with its POLICY_CONFLICT reason and applies nothing).
- POST /v1/k02rest2/closed-part-ref (USER_WRITE guard) serves the frozen
  parts.ClosedPartRef shape {package_id, contract_hash, gate_verdict_ref,
  audit_verdict_ref} (row M-P1-15); blank fields refuse with HTTP 400.
- POST /v1/k02rest2/ledger-roundtrip (USER_WRITE guard) records the given
  rows on a fresh ledger, persists them with the real
  ledger.persist_ledger to a portable temp file, loads them back with the
  real ledger.load_ledger, and answers the sorted
  PackageLedger.package_ids (row M-P1-17).

K02NEXT3 Quarry rows (register_k02next3_routes; additions only, same
USER_WRITE guard shape; every route delegates its row decision to the
named real entry point, never a double):

- GET /v1/k02next3/sdk-transport?provider= (open read) answers the SDK
  transport for one provider through the single generic entry
  sdk_adapter.transport_for_provider (rows UI_DELTA-36 + ARCH-57):
  non-OpenAI providers answer "chat_completions", OpenAI answers
  "sdk_default"; the served contract never names a Responses API.
- GET /v1/k02next3/sdk-surface (open read) answers the verified SDK
  surface through sdk_adapter.verified_sdk_surface (row SDK-132):
  exactly the module __all__ names that resolve, plus the real guarded
  SDK availability flag.
- POST /v1/k02next3/run-config (USER_WRITE guard) binds one
  RoutingDecision to a RunConfig through the real adapter entry
  (row BP03-4); the client stays max_retries=0 (any other value
  refuses SDK_CLIENT_MAX_RETRIES_NONZERO) and runner retries come
  only from the bound RunConfig.
- POST /v1/k02next3/target-flow (USER_WRITE guard) loads one
  project-to-role target flow through the real roles.load_target_flow
  and resolves every role (row BP06-81); a missing role refuses with
  NO_TARGET_FLOW_DEFAULT, never a default.
- POST /v1/k02next3/plan (USER_WRITE guard) decomposes through the
  real graph.TaskPlanner held on the app (row BP01-10): the same
  package ref plus goal hash answers the existing plan ref.
- POST /v1/k02next3/dispatch (USER_WRITE guard) plans the given specs
  then validates the AgentTask through the real
  graph.validate_dispatch (row ARCH-7); a missing subtask_id or an
  unplanned one refuses DISPATCH_REJECTED.
- POST /v1/k02next3/issue (USER_WRITE guard) issues one TaskPackage
  through the real split.split_package with the checked corrections
  hash (row ARCH-705); a mismatch refuses CORRECTIONS_MISMATCH.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, Request

from agent_si.backend.orchestration import delta as _delta
from agent_si.backend.orchestration import gates as _gates
from agent_si.backend.orchestration import graph as _graph
from agent_si.backend.orchestration import ledger as _ledger
from agent_si.backend.orchestration import overlap as _overlap
from agent_si.backend.orchestration import parts as _parts
from agent_si.backend.orchestration import teamcard as _teamcard

#: Served code while a B-row orchestration entry point is still absent.
ROW_UNSERVED = "ROW_UNSERVED"


def _write_guard(request: Request) -> str:
    """Refuse served K02REST2 writes without actor plus live token."""
    actor = (request.headers.get("x-actor") or "").strip()
    if not actor:
        raise HTTPException(
            status_code=401, detail="missing x-actor header")
    token = request.headers.get("x-ui-session-token")
    check = request.app.state.auth_hook
    try:
        allowed = bool(check(token, actor, "USER_WRITE"))
    except Exception:
        allowed = False
    if not allowed:
        raise HTTPException(status_code=403, detail="forbidden")
    return actor


async def _json_body(request: Request) -> dict[str, Any]:
    """Read one JSON object body; refuse missing or bad payloads."""
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail={"code": "ROW_REFUSED",
                    "message": "write needs a JSON body"}) from None
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=400,
            detail={"code": "ROW_REFUSED",
                    "message": "write needs a JSON object body"}) from None
    return data


def _unserved(entry: str) -> HTTPException:
    """HTTP 503 until the CODER-B orchestration entry point lands."""
    return HTTPException(
        status_code=503,
        detail={"code": ROW_UNSERVED,
                "message": f"row unserved until {entry} lands"})


def register_k02rest2_routes(app: Any) -> Any:
    """Mount the K02REST2 hierarchy routes; returns the app."""

    @app.get("/v1/k02rest2/control-plane")
    def get_control_plane() -> dict[str, str]:
        return _graph.control_plane_map()

    @app.post("/v1/k02rest2/delta-intake")
    async def post_delta_intake(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        scope = data.get("scope")
        blocking = data.get("blocking", False)
        if not isinstance(scope, list) or not isinstance(blocking, bool):
            raise HTTPException(
                status_code=400,
                detail={"code": "DELTA_REFUSED",
                        "message": "scope must be a list, blocking a bool"})
        try:
            return _delta.intake_bounded_delta(
                [str(item) for item in scope], blocking)
        except _delta.DELTA_OVER_BOUND as err:
            raise HTTPException(
                status_code=400,
                detail={"code": "DELTA_OVER_BOUND",
                        "message": str(err)}) from None
        except (ValueError, TypeError) as err:
            raise HTTPException(
                status_code=400,
                detail={"code": "DELTA_REFUSED",
                        "message": str(err)}) from None

    @app.post("/v1/k02rest2/delta-close")
    async def post_delta_close(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        delta_pkg = data.get("delta")
        verdict = data.get("verdict")
        if not isinstance(delta_pkg, dict) or not isinstance(verdict, dict):
            raise HTTPException(
                status_code=400,
                detail={"code": "DELTA_REFUSED",
                        "message": "delta plus verdict must be objects"})
        return _delta.close_with_linkcheck(delta_pkg, verdict)

    @app.post("/v1/k02rest2/phase-gate")
    async def post_phase_gate(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        package_ids = data.get("package_ids")
        if (not isinstance(package_ids, list) or not package_ids
                or any(not isinstance(item, str) or not item.strip()
                       for item in package_ids)):
            raise HTTPException(
                status_code=400,
                detail={"code": "GATE_REFUSED",
                        "message": "package_ids must be a non-empty list"})
        try:
            return _gates.evaluate_phase_gate(package_ids)
        except _gates.MISSING_INTEGRATION_TASK as err:
            raise HTTPException(
                status_code=409,
                detail={"code": "MISSING_INTEGRATION_TASK",
                        "message": str(err)}) from None
        except _gates.GATE_NOT_PASSED as err:
            raise HTTPException(
                status_code=409,
                detail={"code": "GATE_NOT_PASSED",
                        "message": str(err)}) from None

    @app.post("/v1/k02rest2/part-register")
    async def post_part_register(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        serve = getattr(_parts, "serve_register_part", None)
        if serve is None:
            raise _unserved("parts.serve_register_part")
        try:
            return dict(serve(data))
        except (ValueError, TypeError) as err:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": str(err)}) from None

    @app.get("/v1/k02rest2/part-register")
    def get_part_register() -> dict[str, Any]:
        serve = getattr(_parts, "serve_part_register", None)
        if serve is None:
            raise _unserved("parts.serve_part_register")
        return dict(serve())

    @app.post("/v1/k02rest2/ledger-nudge")
    async def post_ledger_nudge(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        serve = getattr(_ledger, "serve_package_nudge", None)
        if serve is None:
            raise _unserved("ledger.serve_package_nudge")
        try:
            return dict(serve(data.get("packages"), data.get("package_id")))
        except (ValueError, TypeError) as err:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": str(err)}) from None
        except (KeyError, LookupError) as err:
            raise HTTPException(
                status_code=404,
                detail={"code": "ROW_NOT_FOUND",
                        "message": str(err)}) from None

    @app.post("/v1/k02rest2/decomposition-record")
    async def post_decomposition_record(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        serve = getattr(_teamcard, "serve_decomposition_facts", None)
        if serve is None:
            raise _unserved("teamcard.serve_decomposition_facts")
        try:
            return dict(serve(data))
        except (ValueError, TypeError) as err:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": str(err)}) from None

    @app.post("/v1/k02rest2/team-sizing")
    async def post_team_sizing(request: Request) -> dict[str, Any]:
        actor = _write_guard(request)
        data = await _json_body(request)
        serve = getattr(_graph, "serve_team_sizing", None)
        if serve is None:
            raise _unserved("graph.serve_team_sizing")
        try:
            return dict(serve(data, actor))
        except (ValueError, TypeError) as err:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": str(err)}) from None

    @app.post("/v1/k02rest2/team-config-change")
    async def post_team_config_change(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        statement = data.get("statement")
        reason = data.get("reason")
        authority = data.get("authority")
        patch = data.get("patch")
        for name, value in (("statement", statement), ("reason", reason),
                            ("authority", authority)):
            if not isinstance(value, str) or not value.strip():
                raise HTTPException(
                    status_code=400,
                    detail={"code": "ROW_REFUSED",
                            "message": f"{name} must be a non-empty string"})
        if not isinstance(patch, dict):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "patch must be an object"})
        store = _teamcard.TeamConfigStore()
        ok, check_reason = _teamcard.validate_team_config_change(
            dict(patch), store.config)
        if not ok:
            return {"accepted": False, "reason": check_reason,
                    "decision_ref": None}
        outcome = _teamcard.apply_team_config_change(
            store, str(statement).strip(), str(reason).strip(),
            str(authority).strip(), dict(patch))
        row = outcome.row
        return {"accepted": bool(outcome.accepted),
                "reason": outcome.reason,
                "decision_ref": row.decision_id if row is not None else None}

    @app.post("/v1/k02rest2/multi-manager-settings")
    async def post_multi_manager_settings(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        settings = data.get("settings")
        if not isinstance(settings, dict):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "settings must be an object"})
        ok, reason = _overlap.validate_multi_manager_settings(settings)
        return {"ok": bool(ok), "reason": str(reason)}

    @app.post("/v1/k02rest2/closed-part-ref")
    async def post_closed_part_ref(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        fields: dict[str, str] = {}
        for name in ("package_id", "contract_hash", "gate_verdict_ref",
                     "audit_verdict_ref"):
            value = data.get(name)
            if not isinstance(value, str) or not value.strip():
                raise HTTPException(
                    status_code=400,
                    detail={"code": "ROW_REFUSED",
                            "message": f"{name} must be a non-empty string"})
            fields[name] = value.strip()
        ref = _parts.ClosedPartRef(**fields)
        return {"package_id": ref.package_id,
                "contract_hash": ref.contract_hash,
                "gate_verdict_ref": ref.gate_verdict_ref,
                "audit_verdict_ref": ref.audit_verdict_ref}

    @app.post("/v1/k02rest2/ledger-roundtrip")
    async def post_ledger_roundtrip(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        rows = data.get("rows")
        if not isinstance(rows, list) or not rows:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "rows must be a non-empty list"})
        ledger = _ledger.PackageLedger()
        for item in rows:
            if not isinstance(item, Mapping):
                raise HTTPException(
                    status_code=400,
                    detail={"code": "ROW_REFUSED",
                            "message": "each row must be an object"})
            try:
                package_id = item["package_id"]
                agents = item["agents"]
                peak = item["peak_concurrency"]
                wall = item["wall_time_s"]
            except KeyError as err:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "ROW_REFUSED",
                            "message": f"ledger row misses {err}"}) from None
            if not isinstance(package_id, str) or not package_id.strip():
                raise HTTPException(
                    status_code=400,
                    detail={"code": "ROW_REFUSED",
                            "message": "package_id must be a non-empty string"})
            try:
                ledger.record_row(package_id.strip(), agents, peak, wall)
            except (ValueError, TypeError) as err:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "ROW_REFUSED",
                            "message": str(err)}) from None
        handle, path = tempfile.mkstemp(prefix="k02next2-ledger-",
                                        suffix=".json")
        os.close(handle)
        try:
            _ledger.persist_ledger(path, ledger)
            reloaded = _ledger.load_ledger(path)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(path)
        return {"package_ids": reloaded.package_ids(),
                "rows": len(reloaded.package_ids())}

    return app


def register_k02next3_routes(app: Any) -> Any:
    """Mount the K02NEXT3 Quarry routes; returns the app."""
    from agent_si.backend.orchestration import graph as _q_graph
    from agent_si.backend.orchestration import split as _q_split
    from agent_si.routing import roles as _q_roles
    from agent_si.routing import types as _q_types
    from agent_si.sdk_adapter import sdk_adapter as _q_sdk

    planner = _q_graph.TaskPlanner()

    @app.get("/v1/k02next3/sdk-transport")
    def get_sdk_transport(provider: str = "") -> dict[str, Any]:
        name = (provider or "").strip()
        if not name:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "provider must be a non-empty string"})
        return {"provider": name,
                "transport": _q_sdk.transport_for_provider(name),
                "entry": "transport_for_provider"}

    @app.get("/v1/k02next3/sdk-surface")
    def get_sdk_surface() -> dict[str, Any]:
        return dict(_q_sdk.verified_sdk_surface(),
                    entry="verified_sdk_surface")

    @app.post("/v1/k02next3/run-config")
    async def post_run_config(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        decision = data.get("decision")
        if not isinstance(decision, dict):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "decision must be an object"})
        fields: dict[str, str] = {}
        for name in ("decision_id", "project_id", "task_id", "run_id",
                     "selected_provider", "selected_model"):
            value = decision.get(name)
            if not isinstance(value, str) or not value.strip():
                raise HTTPException(
                    status_code=400,
                    detail={"code": "ROW_REFUSED",
                            "message": f"{name} must be a non-empty string"})
            fields[name] = value.strip()
        budget = data.get("executor_attempt_max")
        if (isinstance(budget, bool) or not isinstance(budget, int)
                or budget < 0):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "executor_attempt_max must be an int >= 0"})
        client_retries = data.get("client_max_retries", 0)
        if isinstance(client_retries, bool) or \
                not isinstance(client_retries, int):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "client_max_retries must be an int"})
        try:
            binding = _q_sdk.RoutingDecisionBinding(
                decision_id=fields["decision_id"],
                project_id=fields["project_id"],
                task_id=fields["task_id"],
                run_id=fields["run_id"],
                routing_snapshot_id=str(
                    decision.get("routing_snapshot_id") or ""),
                selected_provider=fields["selected_provider"],
                selected_model=fields["selected_model"],
                route=str(decision.get("route") or ""),
                strategy=str(decision.get("strategy") or ""),
                reason=str(decision.get("reason") or ""))
            adapter = _q_sdk.OpenAIAgentsSDKAdapter(
                client_config=_q_sdk.SdkClientConfig(
                    max_retries=client_retries))
        except _q_sdk.SdkClientConfigError as err:
            raise HTTPException(
                status_code=400,
                detail={"code": getattr(
                    err, "code",
                    _q_sdk.SDK_CLIENT_MAX_RETRIES_NONZERO),
                    "message": str(err)}) from None
        run_config = adapter.build_run_config(
            binding, executor_attempt_max=budget)
        return {"decision_id": binding.decision_id,
                "client_max_retries": adapter.client_config.max_retries,
                "max_runner_retries": run_config.max_runner_retries,
                "transport": _q_sdk.transport_for_provider(
                    binding.selected_provider),
                "route": binding.route,
                "strategy": binding.strategy}

    @app.post("/v1/k02next3/target-flow")
    async def post_target_flow(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        project_id = data.get("project_id")
        if not isinstance(project_id, str) or not project_id.strip():
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "project_id must be a non-empty string"})
        config = data.get("target_flow")
        if not isinstance(config, dict):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "target_flow must be an object"})
        clean_project = project_id.strip()
        table = _q_roles.RoleTable()
        try:
            loaded = _q_roles.load_target_flow(
                table, config, project_id=clean_project)
        except _q_roles.TargetFlowMissingError as err:
            raise HTTPException(
                status_code=400,
                detail={"code": getattr(
                    err, "code", _q_roles.NO_TARGET_FLOW_DEFAULT),
                    "message": str(err)}) from None
        roles: dict[str, dict[str, Any]] = {}
        for role in _q_types.ROLES:
            resolved = table.resolve(clean_project, role)
            roles[role] = {"provider": resolved.provider,
                           "model": resolved.model,
                           "status": resolved.status,
                           "reason": resolved.reason}
        return {"project_id": clean_project, "roles": roles,
                "loaded": loaded}

    @app.post("/v1/k02next3/plan")
    async def post_plan(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        package_id = data.get("package_id")
        goal = data.get("goal")
        specs = data.get("specs")
        if not isinstance(package_id, str) or not package_id.strip():
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "package_id must be a non-empty string"})
        if not isinstance(goal, str) or not goal.strip():
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "goal must be a non-empty string"})
        if not isinstance(specs, list) or not specs:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "specs must be a non-empty list"})
        try:
            plan_ref, subgraph = planner.plan(
                package_id.strip(), goal.strip(), list(specs))
        except ValueError as err:
            raise HTTPException(
                status_code=400,
                detail={"code": "PLAN_REFUSED",
                        "message": str(err)}) from None
        return {"package_id": package_id.strip(),
                "plan_ref": plan_ref,
                "subtasks": subgraph.order()}

    @app.post("/v1/k02next3/dispatch")
    async def post_dispatch(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        agent_task = data.get("agent_task")
        if not isinstance(agent_task, dict):
            raise HTTPException(
                status_code=400,
                detail={"code": "DISPATCH_REJECTED",
                        "message": "agent_task must be an object"})
        package_id = data.get("package_id")
        goal = data.get("goal")
        specs = data.get("specs")
        if not isinstance(package_id, str) or not package_id.strip():
            raise HTTPException(
                status_code=400,
                detail={"code": "DISPATCH_REJECTED",
                        "message": "package_id must be a non-empty string"})
        if not isinstance(goal, str) or not goal.strip():
            raise HTTPException(
                status_code=400,
                detail={"code": "DISPATCH_REJECTED",
                        "message": "goal must be a non-empty string"})
        if not isinstance(specs, list) or not specs:
            raise HTTPException(
                status_code=400,
                detail={"code": "DISPATCH_REJECTED",
                        "message": "specs must be a non-empty list"})
        try:
            _, subgraph = _q_graph.TaskPlanner().plan(
                package_id.strip(), goal.strip(), list(specs))
        except ValueError as err:
            raise HTTPException(
                status_code=400,
                detail={"code": "PLAN_REFUSED",
                        "message": str(err)}) from None
        try:
            dispatched = _q_graph.validate_dispatch(agent_task, subgraph)
        except _q_graph.DispatchRejected as err:
            raise HTTPException(
                status_code=400,
                detail={"code": "DISPATCH_REJECTED",
                        "message": str(err)}) from None
        return {"agent_task_id": dispatched.agent_task_id,
                "subtask_id": dispatched.subtask_id,
                "status": dispatched.status}

    @app.post("/v1/k02next3/issue")
    async def post_issue(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        package_id = data.get("package_id")
        goal = data.get("goal")
        context_refs = data.get("context_refs")
        max_parts = data.get("max_parts")
        corrections = data.get("corrections", [])
        expected = data.get("expected_corrections_hash")
        if not isinstance(package_id, str) or not package_id.strip():
            raise HTTPException(
                status_code=400,
                detail={"code": "ISSUE_REFUSED",
                        "message": "package_id must be a non-empty string"})
        if not isinstance(goal, str) or not goal.strip():
            raise HTTPException(
                status_code=400,
                detail={"code": "ISSUE_REFUSED",
                        "message": "goal must be a non-empty string"})
        if not isinstance(context_refs, list) or not context_refs:
            raise HTTPException(
                status_code=400,
                detail={"code": "ISSUE_REFUSED",
                        "message": "context_refs must be a non-empty list"})
        if isinstance(max_parts, bool) or not isinstance(max_parts, int):
            raise HTTPException(
                status_code=400,
                detail={"code": "ISSUE_REFUSED",
                        "message": "max_parts must be an integer"})
        if not isinstance(corrections, list):
            raise HTTPException(
                status_code=400,
                detail={"code": "ISSUE_REFUSED",
                        "message": "corrections must be a list"})
        if expected is not None and not isinstance(expected, str):
            raise HTTPException(
                status_code=400,
                detail={"code": "ISSUE_REFUSED",
                        "message": "expected_corrections_hash must be a string"})
        try:
            parts = _q_split.split_package(
                package_id.strip(), goal.strip(), list(context_refs),
                max_parts, list(corrections), expected)
        except ValueError as err:
            text = str(err)
            code = "CORRECTIONS_MISMATCH" \
                if "does not match issuance" in text else "ISSUE_REFUSED"
            raise HTTPException(
                status_code=400,
                detail={"code": code, "message": text}) from None
        return {"package_id": package_id.strip(),
                "parts": [{"package_id": part.package_id,
                           "contract_hash": part.contract_hash,
                           "gate_verdict_ref": part.gate_verdict_ref,
                           "audit_verdict_ref": part.audit_verdict_ref}
                          for part in parts],
                "corrections_hash": _q_split.issued_corrections_hash(
                    package_id.strip())}

    return app
