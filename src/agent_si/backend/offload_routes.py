"""Routine-offload served surface (R-333): per-project switch + hand-overs.

register_offload_routes(app) mounts onto the seam app (additions-only):

- GET /api/v1/projects/{project_id}/offload?role= (open read) served
  only through the frozen offload.offload_enabled reader.
- PUT /api/v1/projects/{project_id}/offload (USER_WRITE guard: 401
  missing x-actor, 403 bad token) delegates ALL validation to the
  frozen apply_offload_config_change writer (applied=false -> HTTP 400
  carrying outcome.reason); authority/reason/statement are server-owned.
- POST /api/v1/offload/maybe (open probe) runs the frozen
  offload.maybe_offload for {task_id, role, routine} and returns the
  recorded HandoverRecord (or null when nothing offloads: not routine,
  switch off, unknown task, auditor role).
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

_OWNER_AUTHORITY = "project-owner"
_UPDATE_REASON = "update routine offload switch"


def register_offload_routes(app: Any) -> Any:
    """Mount the R-333 offload routes; returns the app."""

    @app.get("/api/v1/projects/{project_id}/offload")
    def get_offload_switch(project_id: str, role: str = "") -> dict:
        from agent_si.backend.orchestration import offload as _offload

        if not role.strip():
            raise HTTPException(
                status_code=400,
                detail="POLICY_CONFLICT: query needs a role",
            )
        return {
            "project_id": project_id,
            "role": role,
            "enabled": _offload.offload_enabled(project_id, role),
        }

    @app.put("/api/v1/projects/{project_id}/offload")
    async def put_offload_switch(project_id: str, request: Request) -> dict:
        from agent_si.backend import (
            console_projects_write as _console_write,
        )
        from agent_si.backend.orchestration import offload as _offload

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
        if "role" not in body or "enabled" not in body:
            raise HTTPException(
                status_code=400,
                detail="POLICY_CONFLICT: body must carry role and enabled",
            ) from None
        change = {
            "project_id": project_id,
            "role": body["role"],
            "enabled": body["enabled"],
            "authority": _OWNER_AUTHORITY,
            "reason": _UPDATE_REASON,
            "statement": "routine offload for role %s in project %s"
            % (body["role"], project_id),
        }
        for key in ("to_role", "handover_reason", "task_ids"):
            if key in body:
                change[key] = body[key]
        outcome = _offload.apply_offload_config_change(change)
        if not outcome.applied:
            raise HTTPException(status_code=400, detail=outcome.reason)
        role = str(body["role"])
        return {
            "project_id": project_id,
            "role": role,
            "enabled": _offload.offload_enabled(project_id, role),
            "decision_ref": outcome.decision_ref,
        }

    @app.post("/api/v1/offload/maybe")
    async def post_offload_maybe(request: Request) -> dict:
        from agent_si.backend.orchestration import offload as _offload

        try:
            body = await request.json()
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="probe needs a JSON body",
            ) from None
        if not isinstance(body, dict):
            raise HTTPException(
                status_code=400,
                detail="probe needs a JSON object body",
            ) from None
        record = _offload.maybe_offload(
            str(body.get("task_id") or ""),
            str(body.get("role") or ""),
            body.get("routine") is True,
        )
        if record is None:
            return {"handover": None}
        return {
            "handover": {
                "task_id": record.task_id,
                "from_role": record.from_role,
                "to_role": record.to_role,
                "reason": record.reason,
                "created_at": record.created_at,
            }
        }

    return app
