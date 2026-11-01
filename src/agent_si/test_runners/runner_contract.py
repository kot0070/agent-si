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
    "UNKNOWN_TEST_ID",
    "HUMAN_BEFORE_LADDER",
    "HUMAN_REASON_MISSING",
    "HUMAN_ANSWER_MISSING",
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
    reason: Optional[str] = None


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


def _catalog_test_ids() -> Dict[str, Dict[str, str]]:
    """Frozen catalog test ids with kind and intent; {} when unreachable."""
    try:
        from agent_si.qa_catalog.qa_catalog import get_catalog

        catalog = get_catalog("catalog-frozen-v1")
        return {
            test.test_id: {"kind": test.kind, "intent": test.intent}
            for test in catalog.tests
        }
    except Exception:
        return {}


def _resolve_kind(profile: RunnerProfile,
                  runner_id: str) -> tuple:
    """Execution kind for one run: base first, then the runner library.

    Returns ``(kind, blocked_reason)``; a reason means the tool or base
    is unavailable, so the caller reports BLOCKED, never PASS.
    """
    if profile.base_id:
        try:
            from agent_si.test_runners import test_bases as _bases

            return _bases.base_kind(profile.base_id), ""
        except Exception as exc:
            code = getattr(exc, "code", "")
            if code == "UNKNOWN_TEST_BASE":
                return "", (
                    "unknown test base %r for project %r"
                    % (profile.base_id, profile.project_id))
            return "", str(exc)
    try:
        from agent_si.qa_catalog import runner_library as _library

        return _library.get_runner(runner_id).kind, ""
    except Exception:
        return "", (
            "unknown runner %r with no test base for project %r; "
            "no execution kind can be resolved"
            % (runner_id, profile.project_id))


def run_with_contract(
    profile: object,
    test_id: str,
    runner_id: str,
    *,
    argv=None,
    project_dir: Optional[str] = None,
    data_root: Optional[str] = None,
    timeout_s: float = 60.0,
    reason: Optional[str] = None,
    answer: Optional[str] = None,
) -> RunnerResult:
    """Run one test under the contract; user runners need approval first.

    CODE tests start a real child process (argv list, never a shell
    string) and the exit code decides PASS/FAIL per the oracle. AI tests
    judge through the bound product gateway with cost recorded; HUMAN
    tests need the permission ladder, a reason and a real operator
    answer. Unavailable tools, bases, gateways or answers yield BLOCKED
    plus a reason string, never PASS. Unknown test ids are refused.
    """
    from agent_si.test_runners import code_executor as _executor

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
    known = _catalog_test_ids()
    if known and test_id not in known:
        raise RunnerContractError(
            "UNKNOWN_TEST_ID",
            "test id %r is not in the catalog or overlay" % test_id,
        )
    kind, blocked = _resolve_kind(checked, runner_id)
    if blocked:
        return RunnerResult(
            test_id=test_id,
            status="BLOCKED",
            evidence_ref=_executor._pending_ref(
                checked.project_id, test_id, runner_id),
            runner_id=runner_id,
            contract_version=RUNNER_CONTRACT_VERSION,
            reason=blocked,
        )
    if kind == "HUMAN":
        try:
            from agent_si.test_runners import permission_ladder as _ladder

            _ladder.human_allowed(
                checked.project_id, test_id, reason)
        except Exception as exc:
            code = getattr(exc, "code", "") or "HUMAN_REASON_MISSING"
            if code not in ERROR_CODES_RUNNER_CONTRACT:
                code = "HUMAN_REASON_MISSING"
            raise RunnerContractError(code, str(exc))
        if not answer:
            raise RunnerContractError(
                "HUMAN_ANSWER_MISSING",
                "HUMAN test %r of project %r carries no operator "
                "answer; no PASS without a real answer"
                % (test_id, checked.project_id),
            )
    if argv is not None and isinstance(argv, (str, bytes)):
        raise RunnerContractError(
            "RUNNER_PROFILE_INVALID",
            "argv must be a list of program arguments, "
            "never a shell string",
        )
    if kind == "CODE" and argv is not None:
        try:
            _executor._check_argv(argv)
        except _executor.ExecutorError as exc:
            raise RunnerContractError(
                "RUNNER_PROFILE_INVALID", str(exc))
    outcome = _executor.execute_catalog_test(
        test_id=test_id,
        kind=kind,
        intent=(known.get(test_id, {}) or {}).get("intent", test_id),
        project_id=checked.project_id,
        data_root=data_root,
        argv=argv,
        project_dir=project_dir,
        gateway=None,
        answer=answer,
        assertion_ref=None,
        runner_id=runner_id,
        timeout_s=timeout_s if timeout_s else 60.0,
    )
    if outcome["status"] == "BLOCKED":
        return RunnerResult(
            test_id=test_id,
            status="BLOCKED",
            evidence_ref=_executor._pending_ref(
                checked.project_id, test_id, runner_id),
            runner_id=runner_id,
            contract_version=RUNNER_CONTRACT_VERSION,
            reason=outcome["reason"],
        )
    return RunnerResult(
        test_id=test_id,
        status=outcome["status"],
        evidence_ref=outcome["evidence_ref"],
        runner_id=runner_id,
        contract_version=RUNNER_CONTRACT_VERSION,
    )


#: Entry points: logical name -> symbol in this module.
ENTRY_POINTS = {
    "approve_user_runner": "approve_user_runner",
    "is_runner_approved": "is_runner_approved",
    "run_with_contract": "run_with_contract",
}


def _tail_output(evidence_ref: str, data_root: Optional[str]) -> str:
    """Last lines of the staged output file; "" when nothing is staged."""
    try:
        from agent_si.test_runners import code_executor as _executor

        full = _executor.resolve_evidence_ref(evidence_ref, data_root)
        with open(full, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except Exception:
        return ""
    if len(text) > 4000:
        return text[-4000:]
    return text


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
            try:
                state = request.app.state
            except AttributeError:
                state = None
            data_root = None
            if state is not None:
                data_root = getattr(state, "k02r3_store_dir", None)
                if not data_root:
                    data_root = getattr(state, "data_dir", None)
            argv = merged.get("argv")
            project_dir = merged.get("project_dir")
            if project_dir is not None and not isinstance(project_dir, str):
                raise RunnerContractError(
                    "RUNNER_PROFILE_INVALID",
                    "project_dir must be a folder path string",
                )
            try:
                timeout_s = float(merged.get("timeout_s", 60.0))
            except (TypeError, ValueError):
                raise RunnerContractError(
                    "RUNNER_PROFILE_INVALID",
                    "timeout_s must be a number of seconds",
                )
            checked = _require_profile(profile)
            result = run_with_contract(
                profile,
                str(merged.get("test_id", "")),
                str(merged.get("runner_id", "")),
                argv=argv,
                project_dir=project_dir,
                data_root=data_root,
                timeout_s=timeout_s,
                reason=merged.get("reason"),
                answer=merged.get("answer"),
            )
        except Exception as exc:
            raise _fail(exc)
        body = {
            "test_id": result.test_id,
            "status": result.status,
            "evidence_ref": result.evidence_ref,
            "runner_id": result.runner_id,
            "contract_version": result.contract_version,
        }
        body["reason"] = result.reason
        body["output"] = _tail_output(result.evidence_ref, data_root)
        return body

    _run.__annotations__ = {"request": Request}

    return app
