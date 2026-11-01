"""K03 catalog lane STEP2: QA catalog shapes plus frozen catalog data.

The catalog owns the EXECUTION_KINDS and TEST_STATUSES vocabulary consumed
by the test stage (the stage lane checks it; the catalog lane owns it).
Catalog text is data (selected test intents only), never instructions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

#: Exact shipped-preset model id (never retyped, never a second id).
MODEL_ID = "meta/muse-spark-1.3-contributor"

#: Execution kinds; per-kind counts sum to the catalog total.
EXECUTION_KINDS = ("CODE", "AI", "HUMAN")

#: Per-test terminal statuses (FLAKY never counts as PASS; BLOCKED,
#: MANUAL_REQUIRED and SKIP_NA always carry a reason).
TEST_STATUSES = ("PASS", "FAIL", "BLOCKED", "MANUAL_REQUIRED", "SKIP_NA", "FLAKY")

#: Frozen error-code names for this module (each pinned in its own test).
ERROR_CODES_CATALOG = (
    "UNKNOWN_CATALOG",
)


class CatalogError(Exception):
    """Catalog failure carrying the frozen ``.code`` name."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CatalogTest:
    test_id: str
    intent: str
    kind: str
    oracle: str
    priority: str


@dataclass(frozen=True)
class QACatalog:
    catalog_ref: str
    version: int
    tests: Tuple[CatalogTest, ...]


@dataclass(frozen=True)
class PlanDraft:
    plan_id: str
    catalog_ref: str
    test_ids: Tuple[str, ...]
    kind_counts: Dict[str, int]
    priority: Tuple[str, ...]
    oracle_refs: Tuple[str, ...]


@dataclass(frozen=True)
class LocalTestsConfig:
    project_id: str
    enabled: bool
    updated_at: str


@dataclass(frozen=True)
class TestStatusRow:
    test_id: str
    status: str
    output_ref: Optional[str]


@dataclass(frozen=True)
class TestsView:
    plan_id: str
    run_id: str
    active: int
    passed: int
    remaining: int
    rows: Tuple[TestStatusRow, ...]
    settings_controls: Tuple[str, ...]


#: The frozen v1 catalog: every id below is a valid plan member and every
#: overlay id must avoid these ids (see user_overlay).
_FROZEN_V1_TESTS: Tuple[CatalogTest, ...] = (
    CatalogTest(
        test_id="t-boot",
        intent="application boots to a ready state",
        kind="CODE",
        oracle="exit code",
        priority="ROUTINE",
    ),
    CatalogTest(
        test_id="t-chat",
        intent="chat round-trip keeps context",
        kind="AI",
        oracle="judge approval",
        priority="ROUTINE",
    ),
    CatalogTest(
        test_id="t-export",
        intent="export matches the on-screen data",
        kind="HUMAN",
        oracle="operator sign-off",
        priority="ROUTINE",
    ),
    CatalogTest(
        test_id="t-login",
        intent="login signs in with valid credentials",
        kind="CODE",
        oracle="exit code",
        priority="ROUTINE",
    ),
    CatalogTest(
        test_id="t-offline",
        intent="offline mode keeps saved work available",
        kind="CODE",
        oracle="exit code",
        priority="ROUTINE",
    ),
    CatalogTest(
        test_id="t-perf",
        intent="perf budget holds on the main list scroll",
        kind="CODE",
        oracle="exit code",
        priority="ROUTINE",
    ),
)

#: Feature flags each frozen test needs beyond platform support.
_TEST_REQUIRES = {
    "t-boot": (),
    "t-chat": ("chat",),
    "t-export": (),
    "t-login": ("login",),
    "t-offline": ("offline",),
    "t-perf": ("perf",),
}

_CATALOGS: Dict[str, QACatalog] = {
    "catalog-frozen-v1": QACatalog(
        catalog_ref="catalog-frozen-v1",
        version=1,
        tests=_FROZEN_V1_TESTS,
    ),
}

#: Per-project local-tests overrides; the global default is ON.
_LOCAL_TESTS_OVERRIDES: Dict[str, bool] = {}

#: Recorded status rows per (plan_id, run_id); recording happens in the
#: stage lane, so unknown runs read back as an empty view.
_RUN_ROWS: Dict[Tuple[str, str], Tuple[TestStatusRow, ...]] = {}


def _counts_for(test_ids: Tuple[str, ...]) -> Dict[str, int]:
    known = {test.test_id: test.kind for test in _FROZEN_V1_TESTS}
    counts: Dict[str, int] = {}
    for test_id in test_ids:
        if test_id not in known:
            raise CatalogError(
                "UNKNOWN_TEST_ID",
                "test id %r is not in the catalog or a user overlay" % test_id,
            )
        kind = known[test_id]
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def get_catalog(catalog_ref: str) -> QACatalog:
    """Return the frozen catalog for a ref; else raises UNKNOWN_CATALOG."""
    try:
        return _CATALOGS[catalog_ref]
    except KeyError:
        raise CatalogError(
            "UNKNOWN_CATALOG", "unknown catalog ref %r" % catalog_ref
        )


#: Frozen F1 route.
CATALOG_RUN_ROUTE = "/api/v1/catalog/run"


class CatalogRunError(Exception):
    """Refusal carrying its HTTP status plus signal code."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def get_catalog_json(suite: str) -> Dict[str, Any]:
    """Return the plain-JSON catalog for a suite name.

    Raises CatalogRunError for a missing suite and keeps the real
    entry's UNKNOWN_CATALOG code for an unknown suite name.
    """
    if not isinstance(suite, str) or not suite.strip():
        raise CatalogRunError(
            400, "DEMOF13F1_SUITE_MISSING",
            "catalog run needs a non-empty suite string")
    ref = suite.strip()
    try:
        catalog = get_catalog(ref)
    except CatalogError as exc:
        raise CatalogRunError(400, exc.code, str(exc)) from None
    return {
        "suite": catalog.catalog_ref,
        "version": catalog.version,
        "tests": [
            {
                "test_id": entry.test_id,
                "kind": entry.kind,
                "priority": entry.priority,
                "intent": entry.intent,
                "oracle": entry.oracle,
            }
            for entry in catalog.tests
        ],
    }


def run_suite(
    suite: str,
    *,
    data_root: Optional[str] = None,
    project_id: Optional[str] = None,
    argv_map: Optional[Dict[str, List[str]]] = None,
    gateway: Any = None,
    answers: Optional[Dict[str, str]] = None,
    timeout_s: float = 60.0,
) -> Dict[str, Any]:
    """Run every test of the named suite for real; report per-test results.

    Each CODE test starts a real child process (exit code decides
    PASS/FAIL per its oracle); AI tests judge through the product
    gateway; HUMAN tests need an operator sign-off and never PASS without
    one. Unavailable tools, gateways or sign-offs yield BLOCKED plus a
    reason, never PASS. ``ran`` counts the tests with a real terminal
    result (PASS or FAIL); ``results`` carries one row per catalog test.
    """
    from agent_si.test_runners import code_executor as _executor

    catalog = get_catalog_json(suite)
    pid = project_id if project_id else "suite-%s" % catalog["suite"]
    rows: List[Dict[str, Any]] = []
    ran = 0
    for entry in catalog["tests"]:
        test_id = entry["test_id"]
        kind = entry["kind"]
        argv = None
        if argv_map is not None:
            argv = argv_map.get(test_id)
        sign_off = None
        if answers is not None:
            sign_off = answers.get(test_id)
        outcome = _executor.execute_catalog_test(
            test_id=test_id,
            kind=kind,
            intent=entry.get("intent", test_id),
            project_id=pid,
            data_root=data_root,
            argv=argv,
            project_dir=None,
            gateway=gateway,
            answer=sign_off,
            assertion_ref=None,
            timeout_s=timeout_s if timeout_s else 60.0,
        )
        if outcome["status"] in ("PASS", "FAIL"):
            ran += 1
        rows.append({
            "test_id": test_id,
            "kind": outcome["kind"],
            "status": outcome["status"],
            "evidence_ref": outcome["evidence_ref"],
            "reason": outcome["reason"],
        })
    return {"ok": True, "ran": ran, "results": rows}


def record_status_row(
    plan_id: str,
    run_id: str,
    test_id: str,
    status: str,
    output_ref: Optional[str],
) -> TestStatusRow:
    """Record one per-test status row for the Tests view."""
    row = TestStatusRow(
        test_id=test_id, status=status, output_ref=output_ref)
    key = (plan_id, run_id)
    _RUN_ROWS[key] = _RUN_ROWS.get(key, ()) + (row,)
    return row


def derive_plan(
    catalog_ref: str,
    platform: str,
    feature_flags: List[str],
    risk_class: str,
) -> PlanDraft:
    """Derive the applicable tests (platform, features, risk) into a plan."""
    catalog = get_catalog(catalog_ref)
    flags = set(feature_flags)
    applicable = tuple(
        test.test_id
        for test in catalog.tests
        if all(flag in flags for flag in _TEST_REQUIRES[test.test_id])
        and platform
        and risk_class
    )
    oracles = tuple(
        test.oracle for test in catalog.tests if test.test_id in applicable
    )
    return PlanDraft(
        plan_id="plan-%s-%s-%s" % (catalog_ref, platform, risk_class.lower()),
        catalog_ref=catalog_ref,
        test_ids=applicable,
        kind_counts=_counts_for(applicable),
        priority=applicable,
        oracle_refs=oracles,
    )


def kind_counts(plan: PlanDraft) -> Dict[str, int]:
    """Per-kind counts; must sum to the plan total."""
    counts = _counts_for(plan.test_ids)
    if sum(counts.values()) != len(plan.test_ids):
        raise CatalogError(
            "KIND_COUNT_MISMATCH", "per-kind counts do not sum to the plan"
        )
    return counts


def local_tests_enabled(project_id: str) -> bool:
    """Global default ON; the one per-project switch overrides it."""
    return _LOCAL_TESTS_OVERRIDES.get(project_id, True)


def set_local_tests_enabled(
    project_id: str,
    enabled: bool,
    updated_at: str,
) -> LocalTestsConfig:
    """The single switch that turns local tests on/off for a project."""
    _LOCAL_TESTS_OVERRIDES[project_id] = bool(enabled)
    return LocalTestsConfig(
        project_id=project_id,
        enabled=bool(enabled),
        updated_at=updated_at,
    )


def build_tests_view(plan_id: str, run_id: str) -> TestsView:
    """Informational Tests tab: counters, per-test status, openable results."""
    rows = _RUN_ROWS.get((plan_id, run_id), ())
    passed = sum(1 for row in rows if row.status == "PASS")
    active = len(rows)
    return TestsView(
        plan_id=plan_id,
        run_id=run_id,
        active=active,
        passed=passed,
        remaining=active - passed,
        rows=rows,
        settings_controls=(),
    )


#: Entry points: logical name -> symbol in this module.
ENTRY_POINTS = {
    "get_catalog": "get_catalog",
    "derive_plan": "derive_plan",
    "kind_counts": "kind_counts",
    "local_tests_enabled": "local_tests_enabled",
    "set_local_tests_enabled": "set_local_tests_enabled",
    "build_tests_view": "build_tests_view",
}
