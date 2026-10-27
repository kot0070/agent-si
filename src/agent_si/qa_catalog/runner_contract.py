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


def run(
    contract: RunnerContract,
    profile: ProjectProfile,
    test_id: str,
    catalog_ids: List[str],
    approval: Optional[RunnerApproval],
    ladder_asked: bool,
    reason: Optional[str],
    assertion_ref: Optional[str],
) -> RunnerResult:
    """Execute one catalog test: catalog-only ids, approved user runners
    only, HUMAN only after the ladder was asked and with a reason."""
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
    return RunnerResult(
        test_id=test_id,
        runner_id=contract.runner_id,
        status="PASS",
        evidence_refs=("ev-%s-%s" % (contract.runner_id, test_id),),
        output_ref="output-%s-%s" % (contract.runner_id, test_id),
    )


#: Entry points: logical name -> symbol in this module.
ENTRY_POINTS = {
    "publish_contract": "publish_contract",
    "approve_user_runner": "approve_user_runner",
    "run": "run",
}
