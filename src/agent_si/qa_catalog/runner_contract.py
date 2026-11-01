"""K03 catalog lane STEP2: runner contract.

The contract is the published shape the test stage consumes: a project
profile in, a result JSON with evidence out. User runners run only after
approval; runs use catalog-only ids; a HUMAN test runs only after every
fitting ladder rung was asked (ladder codes keep stage-lane parity: the
permission ladder owns the ask flow, the contract enforces it per run).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

#: Exact shipped-preset model id (never retyped, never a second id).
MODEL_ID = "meta/muse-spark-1.3-contributor"

#: Frozen error-code names for this module (each pinned in its own test).
ERROR_CODES_RUNNER = (
    "UNKNOWN_TEST_ID",
    "USER_RUNNER_NOT_APPROVED",
    "HUMAN_BEFORE_LADDER",
    "HUMAN_REASON_MISSING",
)


class RunnerContractError(Exception):
    """Contract failure carrying the frozen ``.code`` name."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProjectProfile:
    project_id: str
    platform: str
    features: Tuple[str, ...]
    risk_class: str


@dataclass(frozen=True)
class RunnerContract:
    contract_id: str
    runner_id: str
    kind: str
    user_runner: bool
    catalog_ref: str


@dataclass(frozen=True)
class RunnerApproval:
    runner_id: str
    approved: bool
    approved_by_user: bool
    approved_at: str


@dataclass(frozen=True)
class RunnerResult:
    test_id: str
    runner_id: str
    status: str
    evidence_refs: Tuple[str, ...]
    output_ref: Optional[str]


def publish_contract(
    runner_id: str,
    kind: str,
    user_runner: bool,
    catalog_ref: str,
) -> RunnerContract:
    """Publish the contract a runner executes under."""
    return RunnerContract(
        contract_id="contract-%s" % runner_id,
        runner_id=runner_id,
        kind=kind,
        user_runner=bool(user_runner),
        catalog_ref=catalog_ref,
    )


def approve_user_runner(
    runner_id: str,
    approved_by_user: bool,
    approved_at: str,
) -> RunnerApproval:
    """Record the user approval a user runner executes under."""
    approved = bool(approved_by_user)
    return RunnerApproval(
        runner_id=runner_id,
        approved=approved,
        approved_by_user=approved,
        approved_at=approved_at,
    )


def _catalog_entry(test_id: str) -> Tuple[str, str]:
    """Kind and intent for one frozen catalog test id ("" when unknown)."""
    try:
        from agent_si.qa_catalog.qa_catalog import get_catalog

        for entry in get_catalog("catalog-frozen-v1").tests:
            if entry.test_id == test_id:
                return entry.kind, entry.intent
    except Exception:
        pass
    return "", ""


def run(
    contract: RunnerContract,
    profile: ProjectProfile,
    test_id: str,
    catalog_ids: List[str],
    approval: Optional[RunnerApproval],
    ladder_asked: bool,
    reason: Optional[str],
    assertion_ref: Optional[str],
    *,
    argv=None,
    data_root: Optional[str] = None,
    project_dir: Optional[str] = None,
    gateway=None,
    answer: Optional[str] = None,
    timeout_s: float = 60.0,
) -> RunnerResult:
    """Execute one catalog test: catalog-only ids, approved user runners
    only, HUMAN only after the ladder was asked and with a reason.

    CODE tests start a real child process and the exit code decides
    PASS/FAIL; AI tests judge through the product gateway; HUMAN tests
    need an operator sign-off (answer or assertion ref) and never PASS
    without one. Unavailable tools, gateways or sign-offs yield BLOCKED,
    never PASS.
    """
    from agent_si.test_runners import code_executor as _executor

    if test_id not in catalog_ids:
        raise RunnerContractError(
            "UNKNOWN_TEST_ID",
            "test id %r is not in the catalog or overlay" % test_id,
        )
    if contract.user_runner and (
        approval is None
        or not approval.approved
        or not approval.approved_by_user
        or approval.runner_id != contract.runner_id
    ):
        raise RunnerContractError(
            "USER_RUNNER_NOT_APPROVED",
            "user runner %r runs only after owner approval"
            % contract.runner_id,
        )
    if contract.kind == "HUMAN" and not ladder_asked:
        raise RunnerContractError(
            "HUMAN_BEFORE_LADDER",
            "HUMAN test %r runs only after the ladder was asked" % test_id,
        )
    if contract.kind == "HUMAN" and not reason:
        raise RunnerContractError(
            "HUMAN_REASON_MISSING",
            "HUMAN test %r needs a reason" % test_id,
        )
    if contract.kind == "HUMAN" and not (answer or assertion_ref):
        raise RunnerContractError(
            "HUMAN_REASON_MISSING",
            "HUMAN test %r needs an operator sign-off; no PASS "
            "without a real answer" % test_id,
        )
    kind, intent = _catalog_entry(test_id)
    if not kind:
        kind = contract.kind
    if kind not in ("CODE", "AI", "HUMAN"):
        raise RunnerContractError(
            "UNKNOWN_TEST_ID",
            "test id %r carries no executable kind" % test_id,
        )
    outcome = _executor.execute_catalog_test(
        test_id=test_id,
        kind=kind,
        intent=intent or test_id,
        project_id=profile.project_id,
        data_root=data_root,
        argv=argv,
        project_dir=project_dir,
        gateway=gateway,
        answer=answer,
        assertion_ref=assertion_ref,
        runner_id=contract.runner_id,
        timeout_s=timeout_s if timeout_s else 60.0,
    )
    if outcome["evidence_ref"]:
        return RunnerResult(
            test_id=test_id,
            runner_id=contract.runner_id,
            status=outcome["status"],
            evidence_refs=(outcome["evidence_ref"],),
            output_ref=outcome["evidence_ref"],
        )
    return RunnerResult(
        test_id=test_id,
        runner_id=contract.runner_id,
        status=outcome["status"],
        evidence_refs=(),
        output_ref=None,
    )


#: Entry points: logical name -> symbol in this module.
ENTRY_POINTS = {
    "publish_contract": "publish_contract",
    "approve_user_runner": "approve_user_runner",
    "run": "run",
}
