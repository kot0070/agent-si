"""K03 catalog lane STEP2: catalog validation.

A validator returns a ValidationOutcome on success and raises a STEP2 error
type exposing ``.code`` with the frozen name on violation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

#: Frozen error-code names for this module (each pinned in its own test).
ERROR_CODES_VALIDATOR = (
    "UNKNOWN_TEST_ID",
    "KIND_COUNT_MISMATCH",
    "PASS_WITHOUT_ASSERTION",
    "FLAKY_AS_PASS",
    "STATUS_REASON_MISSING",
)

#: Statuses that always carry a reason; never silently dropped.
_REASON_REQUIRED = ("BLOCKED", "MANUAL_REQUIRED", "SKIP_NA")

#: Results that must point at stored evidence; there is no accepted-risk
#: bypass that skips this check.
_EVIDENCE_REQUIRED = ("PASS", "FAIL")


class CatalogValidationError(Exception):
    """Validation failure carrying the frozen ``.code`` name."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ValidationOutcome:
    check: str
    ok: bool


@dataclass(frozen=True)
class ReportedResult:
    test_id: str
    reported_status: str
    observed_status: str
    assertion_ref: Optional[str]
    reason: Optional[str]
    evidence_refs: Tuple[str, ...]


def validate_plan_ids(
    plan_ids: List[str],
    catalog_ids: List[str],
) -> ValidationOutcome:
    """Every planned test id exists in the catalog or a user overlay."""
    known = set(catalog_ids)
    for test_id in plan_ids:
        if test_id not in known:
            raise CatalogValidationError(
                "UNKNOWN_TEST_ID",
                "planned test id %r is not in the catalog or overlay"
                % test_id,
            )
    return ValidationOutcome(check="plan_ids", ok=True)


def validate_kind_counts(
    kind_counts: Dict[str, int],
    total: int,
) -> ValidationOutcome:
    """Per-kind counts sum to the total; else raises KIND_COUNT_MISMATCH."""
    if any(count < 0 for count in kind_counts.values()):
        raise CatalogValidationError(
            "KIND_COUNT_MISMATCH", "per-kind counts must not be negative"
        )
    if sum(kind_counts.values()) != total:
        raise CatalogValidationError(
            "KIND_COUNT_MISMATCH",
            "per-kind counts sum to %d, expected total %d"
            % (sum(kind_counts.values()), total),
        )
    return ValidationOutcome(check="kind_counts", ok=True)


def validate_result(
    reported_status: str,
    observed_status: str,
    assertion_ref: Optional[str],
    reason: Optional[str],
) -> ValidationOutcome:
    """Status rules: PASS needs an executed assertion; a FLAKY observation
    never validates as PASS; BLOCKED, MANUAL_REQUIRED and SKIP_NA need a
    reason."""
    if reported_status == "PASS":
        if observed_status == "FLAKY":
            raise CatalogValidationError(
                "FLAKY_AS_PASS",
                "a FLAKY observation never validates as PASS",
            )
        if not assertion_ref:
            raise CatalogValidationError(
                "PASS_WITHOUT_ASSERTION",
                "PASS needs an executed assertion ref",
            )
        if observed_status != "PASS":
            raise CatalogValidationError(
                "PASS_WITHOUT_ASSERTION",
                "PASS needs a passing observation behind the claim",
            )
        return ValidationOutcome(check="result", ok=True)
    if reported_status in _REASON_REQUIRED and not reason:
        raise CatalogValidationError(
            "STATUS_REASON_MISSING",
            "status %r needs a reason" % reported_status,
        )
    return ValidationOutcome(check="result", ok=True)


def validate_report(
    plan_ids: List[str],
    catalog_ids: List[str],
    kind_counts: Dict[str, int],
    results: List[ReportedResult],
) -> ValidationOutcome:
    """Whole-report check: coverage versus the plan, counts, statuses and
    evidence; raises the first violated code."""
    validate_plan_ids(plan_ids, catalog_ids)
    planned = set(plan_ids)
    seen = [result.test_id for result in results]
    for test_id in seen:
        if test_id not in planned:
            raise CatalogValidationError(
                "UNKNOWN_TEST_ID",
                "reported test id %r is not in the plan" % test_id,
            )
    if len(results) != len(plan_ids) or set(seen) != planned:
        raise CatalogValidationError(
            "KIND_COUNT_MISMATCH",
            "report covers %d of %d planned tests"
            % (len(set(seen) & planned), len(plan_ids)),
        )
    validate_kind_counts(kind_counts, len(plan_ids))
    for result in results:
        validate_result(
            result.reported_status,
            result.observed_status,
            result.assertion_ref,
            result.reason,
        )
        if result.reported_status in _EVIDENCE_REQUIRED and not result.evidence_refs:
            raise CatalogValidationError(
                "EVIDENCE_MISSING",
                "result for %r has no evidence refs" % result.test_id,
            )
    return ValidationOutcome(check="report", ok=True)


#: Entry points: logical name -> symbol in this module.
ENTRY_POINTS = {
    "validate_plan_ids": "validate_plan_ids",
    "validate_kind_counts": "validate_kind_counts",
    "validate_result": "validate_result",
    "validate_report": "validate_report",
}
