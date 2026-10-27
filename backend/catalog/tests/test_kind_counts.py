"""K03 STEP1 behaviour contract: kind counts plus status rules (rows 199,
R-368 kinds/status, M-P3-120). MUST FAIL on stubs.

Entry points: real stub symbols are loaded from
``src/agent_si/qa_catalog/{qa_catalog,catalog_validator,runner_library}.py``
via the loader below (no copies). STEP2 error types must expose ``.code``
with the frozen name; each code below is asserted in its own test. STEP1 RED
mechanism per test: stub bodies return None / raise nothing, so every
behaviour test below is marked strict-xfail (reason 'laneB: <row>'): the
frozen suite runs green-with-xfail and each marker flips when STEP2 lands.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_CATALOG_PKG = (
    pathlib.Path(__file__).resolve().parents[3]
    / "src"
    / "agent_si"
    / "qa_catalog"
)


def _load(name):
    spec = importlib.util.spec_from_file_location(
        "k03_%s" % name, _CATALOG_PKG / ("%s.py" % name)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


catalog = _load("qa_catalog")
validator = _load("catalog_validator")
library = _load("runner_library")

# FAKE-OF: catalog test data (catalog ref, test ids, platform, project and
# run ids, timestamps; test-only values).
CATALOG_REF = "catalog-frozen-v1"
CATALOG_IDS = ["t-boot", "t-chat", "t-export"]
PROJECT = "proj-k03-catalog1"
RUN = "run-k03-catalog1"
MODEL = "meta/muse-spark-1.3-contributor"


def test_plan_derivation_uses_catalog_ids_only():
    plan = catalog.derive_plan(
        catalog_ref=CATALOG_REF,
        platform="windows",
        feature_flags=["chat"],
        risk_class="LOW",
    )
    assert plan.catalog_ref == CATALOG_REF
    assert set(plan.test_ids) <= set(CATALOG_IDS)


def test_kind_counts_sum_to_plan_total():
    plan = catalog.derive_plan(
        catalog_ref=CATALOG_REF,
        platform="windows",
        feature_flags=["chat"],
        risk_class="LOW",
    )
    counts = catalog.kind_counts(plan=plan)
    assert set(counts) <= set(catalog.EXECUTION_KINDS)
    assert sum(counts.values()) == len(plan.test_ids)


def test_kind_count_probe_accepts_matching_counts():
    outcome = validator.validate_kind_counts(
        kind_counts={"CODE": 2, "AI": 1}, total=3
    )
    assert outcome.ok is True


def test_kind_mismatch_refused():
    with pytest.raises(Exception) as exc_info:
        validator.validate_kind_counts(kind_counts={"CODE": 2}, total=5)
    assert exc_info.value.code == "KIND_COUNT_MISMATCH"


def test_pass_recorded_only_after_assertion():
    outcome = validator.validate_result(
        reported_status="PASS",
        observed_status="PASS",
        assertion_ref="attest-1",
        reason=None,
    )
    assert outcome.ok is True


def test_pass_without_assertion_refused():
    with pytest.raises(Exception) as exc_info:
        validator.validate_result(
            reported_status="PASS",
            observed_status="PASS",
            assertion_ref=None,
            reason=None,
        )
    assert exc_info.value.code == "PASS_WITHOUT_ASSERTION"


def test_flaky_never_counts_as_pass():
    with pytest.raises(Exception) as exc_info:
        validator.validate_result(
            reported_status="PASS",
            observed_status="FLAKY",
            assertion_ref="attest-1",
            reason=None,
        )
    assert exc_info.value.code == "FLAKY_AS_PASS"


def test_blocked_without_reason_refused():
    with pytest.raises(Exception) as exc_info:
        validator.validate_result(
            reported_status="BLOCKED",
            observed_status="BLOCKED",
            assertion_ref=None,
            reason=None,
        )
    assert exc_info.value.code == "STATUS_REASON_MISSING"


def test_manual_required_without_reason_refused():
    with pytest.raises(Exception) as exc_info:
        validator.validate_result(
            reported_status="MANUAL_REQUIRED",
            observed_status="MANUAL_REQUIRED",
            assertion_ref=None,
            reason=None,
        )
    assert exc_info.value.code == "STATUS_REASON_MISSING"


def test_skip_na_without_reason_refused():
    with pytest.raises(Exception) as exc_info:
        validator.validate_result(
            reported_status="SKIP_NA",
            observed_status="SKIP_NA",
            assertion_ref=None,
            reason=None,
        )
    assert exc_info.value.code == "STATUS_REASON_MISSING"


def test_plan_ids_must_come_from_catalog():
    outcome = validator.validate_plan_ids(
        plan_ids=list(CATALOG_IDS), catalog_ids=list(CATALOG_IDS)
    )
    assert outcome.ok is True


def test_unknown_plan_id_refused():
    with pytest.raises(Exception) as exc_info:
        validator.validate_plan_ids(
            plan_ids=["no-such-test"], catalog_ids=list(CATALOG_IDS)
        )
    assert exc_info.value.code == "UNKNOWN_TEST_ID"


def test_report_checked_against_plan():
    outcome = validator.validate_report(
        plan_ids=list(CATALOG_IDS),
        catalog_ids=list(CATALOG_IDS),
        kind_counts={"CODE": 2, "AI": 1},
        results=[
            validator.ReportedResult(
                test_id=test_id,
                reported_status="PASS",
                observed_status="PASS",
                assertion_ref="attest-%s" % test_id,
                reason=None,
                evidence_refs=("ev-%s" % test_id,),
            )
            for test_id in CATALOG_IDS
        ],
    )
    assert outcome.ok is True


def test_four_builtin_bases_plus_attached():
    runners = library.list_builtin_runners()
    assert len(runners) == 4
    assert [runner.base for runner in runners] == list(library.BUILTIN_BASES)
    assert {runner.kind for runner in runners} <= set(catalog.EXECUTION_KINDS)
    attached = library.attached_runners(project_id=PROJECT)
    assert isinstance(attached, list)


def test_unknown_runner_refused():
    with pytest.raises(Exception) as exc_info:
        library.get_runner(runner_id="runner-no-such")
    assert exc_info.value.code == "UNKNOWN_RUNNER"
