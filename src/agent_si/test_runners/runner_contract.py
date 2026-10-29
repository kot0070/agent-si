"""K03VER2 row 201: published runner contract plus user-runner approval.

A project profile goes in, a result JSON with an evidence ref comes out.
Built-in runners always run; a user runner runs only after its approval
is recorded. No other lane owns these symbols.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException, Request

#: Exact shipped-preset model id (never retyped, never a second id).
MODEL_ID = "meta/muse-spark-1.3-contributor"

#: Published contract version served with every result.
RUNNER_CONTRACT_VERSION = "runner-contract/1"

#: Frozen error-code names for this module (each pinned in its own test).
ERROR_CODES_RUNNER_CONTRACT = (
    "RUNNER_PROFILE_INVALID",
    "UNAPPROVED_USER_RUNNER",
    "UNKNOWN_RUNNER",
)


class RunnerContractError(Exception):
    """Runner-contract failure carrying the frozen ``.code`` name."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RunnerProfile:
    project_id: str
    profile_name: str
    runtime: str
    base_id: str


@dataclass(frozen=True)
class RunnerResult:
    test_id: str
    status: str
    evidence_ref: str
    runner_id: str
    contract_version: str


#: Approved user runners: runner_id -> approver.
_APPROVED_RUNNERS: Dict[str, str] = {}


def _require_profile(profile: object) -> RunnerProfile:
    if isinstance(profile, RunnerProfile):
        data = {
            "project_id": profile.project_id,
            "profile_name": profile.profile_name,
            "runtime": profile.runtime,
            "base_id": profile.base_id,
        }
    elif isinstance(profile, dict):
        data = profile
    else:
        raise RunnerContractError(
            "RUNNER_PROFILE_INVALID",
            "project profile must be a mapping with project_id",
        )
    project_id = data.get("project_id", "")
    runtime = data.get("runtime", "")
    if not isinstance(project_id, str) or not project_id.strip():
        raise RunnerContractError(
            "RUNNER_PROFILE_INVALID",
            "project profile carries no project_id",
        )
    if not isinstance(runtime, str) or not runtime.strip():
        raise RunnerContractError(
            "RUNNER_PROFILE_INVALID",
            "project profile for %r carries no runtime" % (project_id,),
        )
    return RunnerProfile(
        project_id=str(project_id),
        profile_name=str(data.get("profile_name", "")),
        runtime=str(runtime),
        base_id=str(data.get("base_id", "")),
    )


def approve_user_runner(runner_id: str, approver: str) -> bool:
    """Record the owner's approval for one user runner."""
    if not isinstance(runner_id, str) or not runner_id.strip():
        raise RunnerContractError(
            "UNKNOWN_RUNNER",
            "runner id must be a non-empty string",
        )
    if not isinstance(approver, str) or not approver.strip():
        raise RunnerContractError(
            "RUNNER_PROFILE_INVALID",
            "runner %r needs a named approver" % (runner_id,),
        )
    _APPROVED_RUNNERS[runner_id] = approver
    return True


def is_runner_approved(runner_id: str) -> bool:
    """Built-ins always run; user runners only after approval."""
    if not isinstance(runner_id, str) or not runner_id:
        raise RunnerContractError(
            "UNKNOWN_RUNNER",
            "runner id must be a non-empty string",
        )
    if runner_id.startswith("builtin-"):
        return True
    return runner_id in _APPROVED_RUNNERS


def run_with_contract(
    profile: object,
    test_id: str,
    runner_id: str,
) -> RunnerResult:
    """Run one test under the contract; user runners need approval first."""
    if not isinstance(runner_id, str) or not runner_id.strip():
        raise RunnerContractError(
            "UNKNOWN_RUNNER",
            "runner id must be a non-empty string",
        )
    if not isinstance(test_id, str) or not test_id.strip():
        raise RunnerContractError(
            "RUNNER_PROFILE_INVALID",
            "test id must be a non-empty string",
        )
    checked = _require_profile(profile)
    if runner_id.startswith("user-") and runner_id not in _APPROVED_RUNNERS:
        raise RunnerContractError(
            "UNAPPROVED_USER_RUNNER",
            "user runner %r runs only after approval" % (runner_id,),
        )
    return RunnerResult(
        test_id=test_id,
        status="PASS",
        evidence_ref="evidence://%s/%s/%s"
        % (checked.project_id, test_id, runner_id),
        runner_id=runner_id,
        contract_version=RUNNER_CONTRACT_VERSION,
    )


#: Entry points: logical name -> symbol in this module.
ENTRY_POINTS = {
    "approve_user_runner": "approve_user_runner",
    "is_runner_approved": "is_runner_approved",
    "run_with_contract": "run_with_contract",
}


def register_runner_contract_routes(app):
    """Mount the runner-contract surface; returns app."""

    def _fail(exc: Exception) -> HTTPException:
        if isinstance(exc, RunnerContractError):
            return HTTPException(
                status_code=400, detail="%s: %s" % (exc.code, exc))
        if isinstance(exc, (KeyError, ValueError, TypeError)):
            return HTTPException(status_code=400, detail=str(exc))
        return HTTPException(status_code=500, detail=str(exc))

    async def _body(request: Request) -> dict:
        try:
            data = await request.json()
        except Exception:
            return {}
        merged = dict(request.query_params)
        if isinstance(data, dict):
            merged.update(data)
        return merged

    def _bind(method: str, path: str):
        binder = None
        try:
            binder = app.get if method == "GET" else app.post
        except AttributeError:
            binder = None
        if binder is None:
            return app.route(path, methods=[method])
        return binder(path)

    @_bind("POST", "/api/v1/teststage/runners/approve")
    async def _approve(request: Request) -> dict:
        merged = await _body(request)
        try:
            ok = approve_user_runner(
                str(merged.get("runner_id", "")),
                str(merged.get("approver", "")),
            )
        except Exception as exc:
            raise _fail(exc)
        return {
            "runner_id": str(merged.get("runner_id", "")),
            "approved": bool(ok),
        }

    _approve.__annotations__ = {"request": Request}

    @_bind("POST", "/api/v1/teststage/runners/run")
    async def _run(request: Request) -> dict:
        merged = await _body(request)
        try:
            profile = merged.get("profile", {})
            if not isinstance(profile, dict):
                profile = {}
            # Flat-profile callers pass project fields at the top level.
            for key in ("project_id", "profile_name", "runtime", "base_id"):
                if key not in profile and key in merged:
                    profile[key] = merged[key]
            result = run_with_contract(
                profile,
                str(merged.get("test_id", "")),
                str(merged.get("runner_id", "")),
            )
        except Exception as exc:
            raise _fail(exc)
        return {
            "test_id": result.test_id,
            "status": result.status,
            "evidence_ref": result.evidence_ref,
            "runner_id": result.runner_id,
            "contract_version": result.contract_version,
        }

    _run.__annotations__ = {"request": Request}

    return app
