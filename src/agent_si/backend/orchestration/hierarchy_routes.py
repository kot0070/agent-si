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

    return app
