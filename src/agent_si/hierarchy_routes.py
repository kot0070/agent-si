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
