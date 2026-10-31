"""K02NEXT4 hierarchy seam: 8 rows served on production routes.

register_hierarchy_routes(app) mounts onto the seam app (additions-only;
call it on the real app built by agent_si.backend.app.create_app, then
drive it with an HTTP client):

- POST /hierarchy/emergency-restore (R1 UI_DELTA-23): emergency
  restoration rebinds each role to its configured RoleModelProfile
  (real routing.types.RoleModelProfile validation) while keeping the
  completed work refs untouched. A role without a configured profile
  refuses with HTTP 400.
- POST /hierarchy/scopes/validate (R2 BP01-65): pairwise agent-scope
  overlap check over real scope sets; any intersection refuses with
  HTTP 409 carrying REJECTED_SCOPE_OVERLAP.
- POST /hierarchy/parent-close (R3 BP01-73): delegates to the real
  graph.HierarchyConfigStore.close_parent; a missing integration task
  (or any other blocked closure) answers HTTP 409.
- GET /hierarchy/contributor-bindings?env=dev|prod (R4 BP06-68):
  contributor bindings are active dev-only; prod answers HTTP 403 and
  the served payload never carries a production contributor binding.
- GET /hierarchy/role-authority?role=<name> (R5 BP06-78): delegates to
  the hierarchy_claims.role_authority provider with this module's
  configured role models; an unconfigured role answers HTTP 403.
- POST /hierarchy/scopes/distinct (R6 ARCH-456): delegates to the
  hierarchy_claims.check_scopes_distinct provider; an overlap answers
  HTTP 409 carrying REJECTED_SCOPE_OVERLAP.
- POST /hierarchy/route-plan (R7 ARCH-461): delegates to the
  hierarchy_claims.route_plan provider with the plan plus the Manager
  hierarchy; a plan that bypasses the Manager answers HTTP 422.
- POST /hierarchy/demand-queue (R8 ARCH-755): delegates to the
  hierarchy_claims.queue_demand provider with demand plus caps; demand
  beyond caps answers HTTP 409.

R5-R8 import hierarchy_claims LAZILY inside their handlers so this
module loads before the provider module lands; while it is absent they
answer HTTP 503 ROW_UNSERVED (never a double: no canned provider
lives here or in any mount file). Writes keep the frozen USER_WRITE
guard shape (401 missing x-actor, 403 bad token).

K02NEXT5 adds 8 routes (additive-only; every R1-R8 path, handler
name and orchestration signature above stays unchanged):

- POST /hierarchy/cap-queue (ARCH-762): split.split_package then
  split.capped_queue; every slot carries its serial position and
  estimated start, newcomers past the cap queue with positions.
- POST /hierarchy/chain-activate (ARCH-766): the real
  graph.HierarchyConfigStore.activate_chain; a manager running as a
  tool agent or duplicated tool agents refuse with HTTP 409.
- POST /hierarchy/parts-disjoint (BP01-72): split.split_package then
  split.validate_disjoint; overlapping part scopes refuse with
  HTTP 409 carrying SCOPE_OVERLAP before any fan-out.
- POST /hierarchy/user-correction (ARCH-704): the real
  graph.HierarchyConfigStore.append_user_correction; only the USER
  appends, any other actor refuses with HTTP 403.
- POST /hierarchy/offload-switch (UI_DELTA-57): the real
  offload.apply_offload_config_change plus the live
  offload_enabled/maybe_offload state; unknown pairs stay off and the
  auditor never offloads.
- POST /hierarchy/combined-flow (UI_DELTA-59): one served run of the
  real primitives in order -- split.split_package (project
  creation), activate_chain (hierarchy), grant_role_authority
  (binding), apply_offload_config_change (offload toggle),
  delta.apply_config_change (pause/archive lifecycle); the first
  refusing step names itself in the HTTP error.
- POST /hierarchy/decision-record (UI_DELTA-60): the real
  delta.apply_config_change; an accepted change persists exactly one
  decision row carrying actor and timestamp.
- POST /hierarchy/rejection-surface (UI_DELTA-62): the real
  offload.apply_offload_config_change with a violating change; the
  refusal reason code is surfaced and no decision row is added.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from agent_si.backend.orchestration import graph as _graph
from agent_si.routing import types as _types

#: Served code while a K02NEXT4 provider module is still absent.
ROW_UNSERVED = "ROW_UNSERVED"

#: Frozen overlap code shared by R2 and R6 on the served path.
REJECTED_SCOPE_OVERLAP = "REJECTED_SCOPE_OVERLAP"

#: Contributor model bound for development use only.
CONTRIBUTOR_MODEL = "meta/muse-spark-1.3-contributor"

#: Configured role models: role -> RoleModelProfile payload. Populated
#: by emergency restoration (R1) and read by role authority (R5).
_ROLE_MODELS: dict[str, dict[str, Any]] = {}


def _reset_state() -> None:
    """Clear module state (test helper; never a product path)."""
    _ROLE_MODELS.clear()


def _write_guard(request: Request) -> str:
    """Refuse served K02NEXT4 writes without actor plus live token."""
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
    """HTTP 503 until the named provider entry point lands."""
    return HTTPException(
        status_code=503,
        detail={"code": ROW_UNSERVED,
                "message": "row unserved until %s lands" % entry})


def _non_empty_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "ROW_REFUSED",
                    "message": "%s must be a non-empty string" % field})
    return value.strip()


def _scope_tokens(scope: str) -> frozenset[str]:
    """Split one agent scope into its addressable tokens."""
    return frozenset(
        token for token in (part.strip() for part in scope.split(","))
        if token
    )


def find_scope_overlap(scopes: list[str]) -> list[str]:
    """Return the sorted overlapping scope tokens, or [] when disjoint.

    Real pairwise check: every scope contributes its token set and any
    token claimed by two scopes is an overlap (an exact duplicate
    scope always overlaps itself).
    """
    seen: dict[str, int] = {}
    for scope in scopes:
        for token in _scope_tokens(scope):
            seen[token] = seen.get(token, 0) + 1
    return sorted(token for token, count in seen.items() if count > 1)


def _profile_ref(project_id: str, role: str, version: int) -> str:
    return "ROLE_PROFILE:%s/%s#v%d" % (project_id, role, version)


def register_hierarchy_routes(app: Any) -> Any:
    """Mount the K02NEXT4 hierarchy routes; returns the app."""

    @app.post("/hierarchy/emergency-restore")
    async def post_emergency_restore(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        project_raw = data.get("project_id", "k02next4")
        project_id = (str(project_raw).strip()
                      if isinstance(project_raw, str)
                      and str(project_raw).strip()
                      else "k02next4")
        roles = data.get("roles")
        if not isinstance(roles, list) or not roles:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "roles must be a non-empty list"})
        profiles = data.get("profiles")
        if not isinstance(profiles, dict):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "profiles must be a role-keyed mapping"})
        completed = data.get("completed", [])
        if not isinstance(completed, list):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "completed must be a list"})
        missing = [role for role in roles
                   if not isinstance(role, str) or not role.strip()
                   or role.strip() not in profiles]
        if missing:
            raise HTTPException(
                status_code=400,
                detail={"code": "EMERGENCY_PROFILE_MISSING",
                        "message": "no configured RoleModelProfile for "
                                   "roles: %s" % sorted(str(role).strip()
                                                        for role in roles
                                                        if not isinstance(
                                                            role, str)
                                                        or not role.strip()
                                                        or role.strip()
                                                        not in profiles)})
        refs: dict[str, str] = {}
        for raw_role in roles:
            role = str(raw_role).strip()
            spec = profiles[role]
            if not isinstance(spec, dict):
                raise HTTPException(
                    status_code=400,
                    detail={"code": "ROW_REFUSED",
                            "message": "profile for %s must be a mapping"
                                       % role})
            try:
                profile = _types.RoleModelProfile(
                    role=role,
                    project_id=project_id,
                    mode=str(spec.get("mode", "PINNED")),
                    provider=spec.get("provider"),
                    model=spec.get("model"),
                    binding=str(spec.get("binding", "DEFAULT")),
                    version=int(spec.get("version", 1)),
                )
            except (ValueError, TypeError) as err:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "ROW_REFUSED",
                            "message": "bad profile for %s: %s"
                                       % (role, err)}) from None
            _ROLE_MODELS[role] = {
                "role": profile.role,
                "project_id": profile.project_id,
                "mode": profile.mode,
                "provider": profile.provider,
                "model": profile.model,
                "binding": profile.binding,
                "version": profile.version,
            }
            refs[role] = _profile_ref(
                project_id, role, int(spec.get("version", 1)))
        return {
            "restored": [str(role).strip() for role in roles],
            "profiles": refs,
            "completed_kept": list(completed),
        }

    @app.post("/hierarchy/scopes/validate")
    async def post_scopes_validate(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        scopes = data.get("scopes")
        if not isinstance(scopes, list) or not scopes or not all(
                isinstance(scope, str) and scope.strip()
                for scope in scopes):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "scopes must be a non-empty list of "
                                   "non-empty strings"})
        clash = find_scope_overlap(
            [scope.strip() for scope in scopes])
        if clash:
            raise HTTPException(
                status_code=409,
                detail={"code": REJECTED_SCOPE_OVERLAP,
                        "message": "overlapping agent scopes: %s"
                                   % ", ".join(clash)})
        return {"distinct": True,
                "scopes": [scope.strip() for scope in scopes]}

    @app.post("/hierarchy/parent-close")
    async def post_parent_close(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        part_results = data.get("part_results")
        if not isinstance(part_results, dict) or not part_results:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "part_results must be a non-empty "
                                   "mapping"})
        record = data.get("integration_record")
        try:
            outcome = _graph.HierarchyConfigStore().close_parent(
                {str(key): str(value)
                 for key, value in part_results.items()},
                record if isinstance(record, dict) else None,
            )
        except _graph.ParentClosureBlocked as err:
            raise HTTPException(
                status_code=409,
                detail={"code": "PARENT_CLOSURE_BLOCKED",
                        "message": str(err)}) from None
        return dict(outcome)

    @app.get("/hierarchy/contributor-bindings")
    def get_contributor_bindings(env: str = "") -> dict[str, Any]:
        cleaned = (env or "").strip().lower()
        if cleaned not in ("dev", "prod"):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "env must be dev or prod"})
        if cleaned == "prod":
            raise HTTPException(
                status_code=403,
                detail={"code": "CONTRIBUTOR_PROD_REFUSED",
                        "message": "contributor bindings are "
                                   "development-only: production refused"})
        return {
            "env": "dev",
            "active": True,
            "bindings": [
                {"role": "contributor",
                 "model": CONTRIBUTOR_MODEL,
                 "purpose": "development"},
            ],
        }

    @app.get("/hierarchy/role-authority")
    def get_role_authority(role: str = "") -> dict[str, Any]:
        name = (role or "").strip()
        if not name:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "role must be a non-empty string"})
        try:
            from agent_si.backend.orchestration import (  # noqa: E402
                hierarchy_claims as _claims,
            )
            provider = _claims.role_authority
        except (ImportError, AttributeError) as err:
            raise _unserved("hierarchy_claims.role_authority") from err
        try:
            authority = provider(name, role_models=dict(_ROLE_MODELS))
        except _claims.RoleAuthorityError as err:
            raise HTTPException(
                status_code=403,
                detail={"code": getattr(err, "code",
                                       "ROLE_AUTHORITY_REFUSED"),
                        "message": str(err)}) from None
        return {"role": name, "authority": authority, "ok": True}

    @app.post("/hierarchy/scopes/distinct")
    async def post_scopes_distinct(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        scopes = data.get("scopes")
        if not isinstance(scopes, list) or not scopes or not all(
                isinstance(scope, str) and scope.strip()
                for scope in scopes):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "scopes must be a non-empty list of "
                                   "non-empty strings"})
        try:
            from agent_si.backend.orchestration import (  # noqa: E402
                hierarchy_claims as _claims,
            )
            check = _claims.check_scopes_distinct
        except (ImportError, AttributeError) as err:
            raise _unserved(
                "hierarchy_claims.check_scopes_distinct") from err
        try:
            check([scope.strip() for scope in scopes])
        except _claims.ScopeOverlapError as err:
            raise HTTPException(
                status_code=409,
                detail={"code": getattr(err, "code",
                                       REJECTED_SCOPE_OVERLAP),
                        "message": str(err)}) from None
        return {"distinct": True,
                "scopes": [scope.strip() for scope in scopes]}

    @app.post("/hierarchy/route-plan")
    async def post_route_plan(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        plan = data.get("plan")
        hierarchy = data.get("manager_hierarchy")
        if not isinstance(plan, dict) or not isinstance(hierarchy, dict):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "plan and manager_hierarchy must be "
                                   "mappings"})
        try:
            from agent_si.backend.orchestration import (  # noqa: E402
                hierarchy_claims as _claims,
            )
            route = _claims.route_plan
        except (ImportError, AttributeError) as err:
            raise _unserved("hierarchy_claims.route_plan") from err
        try:
            routed = route(dict(plan), manager_hierarchy=dict(hierarchy))
        except _claims.RoutingError as err:
            raise HTTPException(
                status_code=422,
                detail={"code": getattr(err, "code", "ROUTING_REFUSED"),
                        "message": str(err)}) from None
        return {"ok": True, "route": routed}

    @app.post("/hierarchy/demand-queue")
    async def post_demand_queue(request: Request) -> dict[str, Any]:
        _write_guard(request)
        data = await _json_body(request)
        demand = data.get("demand")
        caps = data.get("caps")
        if not isinstance(demand, dict) or not isinstance(caps, dict):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "demand and caps must be mappings"})
        try:
            from agent_si.backend.orchestration import (  # noqa: E402
                hierarchy_claims as _claims,
            )
            enqueue = _claims.queue_demand
        except (ImportError, AttributeError) as err:
            raise _unserved("hierarchy_claims.queue_demand") from err
        try:
            queued = enqueue(dict(demand), caps=dict(caps))
        except _claims.CapsExceededError as err:
            raise HTTPException(
                status_code=409,
                detail={"code": getattr(err, "code", "CAPS_EXCEEDED"),
                        "message": str(err)}) from None
        return {"ok": True, "queue": queued}

    @app.post("/hierarchy/cap-queue")
    async def post_cap_queue(request: Request) -> dict[str, Any]:
        """K02NEXT5 ARCH-762: capped queue slots carry position + start."""
        from agent_si.backend.orchestration import split as _split

        _write_guard(request)
        data = await _json_body(request)
        package_id = data.get("package_id")
        goal = data.get("goal")
        refs = data.get("context_refs")
        max_parts = data.get("max_parts")
        cap = data.get("max_parallel_managers")
        wall = data.get("wall_time_s", 1.0)
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
        if not isinstance(refs, list) or not refs:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "context_refs must be a non-empty list"})
        if (not isinstance(max_parts, int)
                or isinstance(max_parts, bool) or max_parts < 1):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "max_parts must be an int >= 1"})
        if (not isinstance(cap, int)
                or isinstance(cap, bool) or cap < 1):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "max_parallel_managers must be "
                                   "an int >= 1"})
        try:
            parts = _split.split_package(
                package_id.strip(), goal.strip(), refs, max_parts)
        except ValueError as err:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": str(err)}) from None
        settings = _split.MultiManagerSettings(
            multi_manager_mode=cap > 1,
            max_parallel_managers=cap,
            overlap=False,
            integration_policy="manager-integrates",
        )
        try:
            slots = _split.capped_queue(parts, settings, wall)
        except ValueError as err:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": str(err)}) from None
        running, queued = _split.fanout(parts, settings)
        running_refs = [part.gate_verdict_ref for part in running]
        queued_refs = [part.gate_verdict_ref for part in queued]
        return {
            "slots": [{"gate_ref": slot.part.gate_verdict_ref,
                       "position": slot.position,
                       "estimated_start_s": slot.estimated_start_s}
                      for slot in slots],
            "running": running_refs,
            "queued": queued_refs,
        }

    @app.post("/hierarchy/chain-activate")
    async def post_chain_activate(request: Request) -> dict[str, Any]:
        """K02NEXT5 ARCH-766: distinct Manager agents, no duplication."""
        actor = _write_guard(request)
        data = await _json_body(request)
        chain_data = data.get("chain")
        if not isinstance(chain_data, dict):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "chain must be a mapping"})
        tools = chain_data.get("tool_agent_ids")
        if not isinstance(tools, list) or not tools or not all(
                isinstance(entry, str) and entry.strip() for entry in tools):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "chain.tool_agent_ids must be a "
                                   "non-empty list of non-empty strings"})
        try:
            chain = _graph.HierarchyChain(
                director_id=str(chain_data.get("director_id") or ""),
                manager_id=str(chain_data.get("manager_id") or ""),
                tool_agent_ids=[str(entry).strip() for entry in tools],
            )
        except (ValueError, TypeError) as err:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": str(err)}) from None
        store = _graph.HierarchyConfigStore()
        try:
            outcome = store.activate_chain(chain, actor)
        except _graph.HierarchyRefused as err:
            raise HTTPException(
                status_code=409,
                detail={"code": "CHAIN_REFUSED",
                        "message": str(err)}) from None
        return {"accepted": outcome.accepted, "reason": outcome.reason,
                "surfaced": outcome.surfaced}

    @app.post("/hierarchy/parts-disjoint")
    async def post_parts_disjoint(request: Request) -> dict[str, Any]:
        """K02NEXT5 BP01-72: overlapping part scopes refused pre fan-out."""
        from agent_si.backend.orchestration import split as _split

        _write_guard(request)
        data = await _json_body(request)
        package_id = data.get("package_id")
        goal = data.get("goal")
        refs = data.get("context_refs")
        max_parts = data.get("max_parts")
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
        if not isinstance(refs, list) or not refs:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "context_refs must be a non-empty list"})
        if (not isinstance(max_parts, int)
                or isinstance(max_parts, bool) or max_parts < 1):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "max_parts must be an int >= 1"})
        try:
            parts = _split.split_package(
                package_id.strip(), goal.strip(), refs, max_parts)
        except ValueError as err:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": str(err)}) from None
        try:
            _split.validate_disjoint(parts)
        except _split.SCOPE_OVERLAP as err:
            raise HTTPException(
                status_code=409,
                detail={"code": "SCOPE_OVERLAP",
                        "message": str(err)}) from None
        except ValueError as err:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": str(err)}) from None
        return {"disjoint": True,
                "parts": [part.gate_verdict_ref for part in parts]}

    @app.post("/hierarchy/user-correction")
    async def post_user_correction(request: Request) -> dict[str, Any]:
        """K02NEXT5 ARCH-704: only the USER appends user corrections."""
        actor = _write_guard(request)
        data = await _json_body(request)
        text = data.get("text")
        if not isinstance(text, str) or not text.strip():
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "text must be a non-empty string"})
        store = _graph.HierarchyConfigStore()
        try:
            outcome = store.append_user_correction(actor, text.strip())
        except _graph.HierarchyRefused as err:
            raise HTTPException(
                status_code=403,
                detail={"code": "USER_CORRECTION_USER_ONLY",
                        "message": str(err)}) from None
        corrections = list(store.config.get("user_corrections", ()))
        entry = dict(corrections[-1]) if corrections else {
            "actor": actor, "text": text.strip(), "created_at": ""}
        return {"recorded": outcome.accepted, "reason": outcome.reason,
                "entry": entry}

    @app.post("/hierarchy/offload-switch")
    async def post_offload_switch(request: Request) -> dict[str, Any]:
        """K02NEXT5 UI_DELTA-57: routine handoff switch per project+role."""
        from agent_si.backend.orchestration import offload as _offload

        _write_guard(request)
        data = await _json_body(request)
        change = data.get("change")
        if not isinstance(change, dict):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "change must be a mapping"})
        outcome = _offload.apply_offload_config_change(change)
        project_id = change.get("project_id")
        role = change.get("role")
        if isinstance(project_id, str) and isinstance(role, str):
            enabled = _offload.offload_enabled(project_id, role)
            unknown = _offload.offload_enabled(project_id, "__unconfigured__")
        else:
            enabled = False
            unknown = False
        handover: dict[str, Any] | None = None
        probe_task = data.get("probe_task")
        probe_role = data.get("probe_role")
        if (outcome.applied and isinstance(probe_task, str)
                and isinstance(probe_role, str)):
            record = _offload.maybe_offload(probe_task, probe_role, True)
            if record is not None:
                handover = {"task_id": record.task_id,
                            "from_role": record.from_role,
                            "to_role": record.to_role,
                            "reason": record.reason,
                            "created_at": record.created_at}
        return {"applied": outcome.applied, "reason": outcome.reason,
                "decision_ref": outcome.decision_ref,
                "offload_enabled": enabled, "handover": handover,
                "unknown_pair_enabled": unknown}

    @app.post("/hierarchy/combined-flow")
    async def post_combined_flow(request: Request) -> dict[str, Any]:
        """K02NEXT5 UI_DELTA-59: project+hierarchy+binding+offload+life."""
        from agent_si.backend.orchestration import delta as _delta
        from agent_si.backend.orchestration import offload as _offload
        from agent_si.backend.orchestration import split as _split

        actor = _write_guard(request)
        data = await _json_body(request)
        project_id = data.get("project_id")
        goal = data.get("goal")
        refs = data.get("context_refs")
        max_parts = data.get("max_parts")
        chain_data = data.get("chain")
        role_models = data.get("role_models")
        binding_data = data.get("binding")
        offload_change = data.get("offload_change")
        lifecycle = data.get("lifecycle")
        if not isinstance(project_id, str) or not project_id.strip():
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "project_id must be a non-empty string"})
        if not isinstance(goal, str) or not goal.strip():
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "goal must be a non-empty string"})
        if not isinstance(refs, list) or not refs:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "context_refs must be a non-empty list"})
        if (not isinstance(max_parts, int)
                or isinstance(max_parts, bool) or max_parts < 1):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "max_parts must be an int >= 1"})
        if not isinstance(chain_data, dict):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "chain must be a mapping"})
        if not isinstance(role_models, dict) or not role_models:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "role_models must be a non-empty mapping"})
        if not isinstance(binding_data, dict):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "binding must be a mapping"})
        if not isinstance(offload_change, dict):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "offload_change must be a mapping"})
        if not isinstance(lifecycle, dict):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "lifecycle must be a mapping"})
        clean_project = project_id.strip()
        try:
            parts = _split.split_package(
                clean_project, goal.strip(), refs, max_parts)
        except ValueError as err:
            raise HTTPException(
                status_code=400,
                detail={"code": "COMBINED_SPLIT_REFUSED",
                        "step": "project-creation",
                        "message": str(err)}) from None
        tools = chain_data.get("tool_agent_ids")
        if not isinstance(tools, list) or not tools:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "chain.tool_agent_ids must be "
                                   "a non-empty list"})
        try:
            chain = _graph.HierarchyChain(
                director_id=str(chain_data.get("director_id") or ""),
                manager_id=str(chain_data.get("manager_id") or ""),
                tool_agent_ids=[str(entry) for entry in tools],
            )
        except (ValueError, TypeError) as err:
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": str(err)}) from None
        store = _graph.HierarchyConfigStore()
        try:
            chain_outcome = store.activate_chain(chain, actor)
        except _graph.HierarchyRefused as err:
            raise HTTPException(
                status_code=409,
                detail={"code": "COMBINED_CHAIN_REFUSED",
                        "step": "hierarchy",
                        "message": str(err)}) from None
        bind_role = binding_data.get("role")
        bind_mapping = binding_data.get("binding")
        if not isinstance(bind_role, str) or not bind_role.strip():
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "binding.role must be a non-empty "
                                   "string"})
        if not isinstance(bind_mapping, dict):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "binding.binding must be a mapping"})
        bind_store = _graph.HierarchyConfigStore(
            config={"role_models": dict(role_models)})
        try:
            bind_outcome = bind_store.grant_role_authority(
                bind_role.strip(), dict(bind_mapping), actor)
        except _graph.HierarchyRefused as err:
            raise HTTPException(
                status_code=409,
                detail={"code": "COMBINED_BINDING_REFUSED",
                        "step": "binding",
                        "message": str(err)}) from None
        full_change = dict(offload_change)
        full_change.setdefault("project_id", clean_project)
        off_outcome = _offload.apply_offload_config_change(full_change)
        if not off_outcome.applied:
            raise HTTPException(
                status_code=409,
                detail={"code": "COMBINED_OFFLOAD_REFUSED",
                        "step": "offload-toggle",
                        "message": off_outcome.reason}) from None
        paused = lifecycle.get("paused", False)
        archived = lifecycle.get("archived", False)
        if not isinstance(paused, bool) or not isinstance(archived, bool):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "lifecycle.paused/archived must be "
                                   "booleans"})
        life_log: list = []
        life_result = _delta.apply_config_change(
            {}, life_log, "project:lifecycle",
            f"pause and archive flags for {clean_project}",
            "lifecycle recorded", actor,
            {"paused": paused, "archived": archived})
        if not life_result["applied"]:
            raise HTTPException(
                status_code=409,
                detail={"code": "COMBINED_LIFECYCLE_REFUSED",
                        "step": "lifecycle",
                        "message": life_result["reason"]}) from None
        return {
            "project_id": clean_project,
            "parts": [part.gate_verdict_ref for part in parts],
            "chain": {"accepted": chain_outcome.accepted},
            "binding": {"accepted": bind_outcome.accepted},
            "offload": {"applied": off_outcome.applied,
                        "decision_ref": off_outcome.decision_ref},
            "lifecycle": {"applied": life_result["applied"],
                          "decision_ref": life_result["decision_ref"]},
        }

    @app.post("/hierarchy/decision-record")
    async def post_decision_record(request: Request) -> dict[str, Any]:
        """K02NEXT5 UI_DELTA-60: validated change persists one row."""
        from agent_si.backend.orchestration import delta as _delta

        _write_guard(request)
        data = await _json_body(request)
        rows: list = []
        result = _delta.apply_config_change(
            {}, rows, data.get("scope"), data.get("statement"),
            data.get("reason"), data.get("authority"), data.get("patch"))
        return {"applied": result["applied"], "reason": result["reason"],
                "decision_ref": result["decision_ref"], "rows": rows}

    @app.post("/hierarchy/rejection-surface")
    async def post_rejection_surface(request: Request) -> dict[str, Any]:
        """K02NEXT5 UI_DELTA-62: rejections surfaced, nothing mutates."""
        from agent_si.backend.orchestration import offload as _offload

        _write_guard(request)
        data = await _json_body(request)
        change = data.get("change")
        if not isinstance(change, dict):
            raise HTTPException(
                status_code=400,
                detail={"code": "ROW_REFUSED",
                        "message": "change must be a mapping"})
        before = len(_offload._DECISIONS)
        outcome = _offload.apply_offload_config_change(change)
        after = len(_offload._DECISIONS)
        return {"applied": outcome.applied, "reason": outcome.reason,
                "decision_ref": outcome.decision_ref,
                "decisions_before": before, "decisions_after": after,
                "surfaced": outcome.reason}

    return app
