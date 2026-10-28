"""K03 STEP1 behaviour contract: runner contract plus user approval plus
ladder (rows 201, R-338). MUST FAIL on stubs.

Entry points: real stub symbols are loaded from
``src/agent_si/qa_catalog/runner_contract.py`` (and the stage-lane
permission ladder, read-only) via the loader below (no copies). STEP2 error
types must expose ``.code`` with the frozen name; each code below is
asserted in its own test. STEP1 RED mechanism per test: stub bodies return
None / raise nothing, so every behaviour test below is marked strict-xfail
(reason 'laneB: <row>'): the frozen suite runs green-with-xfail and each
marker flips when STEP2 lands.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_QA_CATALOG_PKG = (
    pathlib.Path(__file__).resolve().parents[3]
    / "src"
    / "agent_si"
    / "qa_catalog"
)
_STAGE_PKG = (
    pathlib.Path(__file__).resolve().parents[3]
    / "src"
    / "agent_si"
    / "test_runners"
)


def _load(pkg, name):
    spec = importlib.util.spec_from_file_location(
        "k03_%s" % name, pkg / ("%s.py" % name)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


contract = _load(_QA_CATALOG_PKG, "runner_contract")
ladder = _load(_STAGE_PKG, "permission_ladder")

# FAKE-OF: runner test data (catalog ref, test ids, project profile values,
# runner ids, timestamps; test-only values).
CATALOG_REF = "catalog-frozen-v1"
CATALOG_IDS = ["t-boot", "t-chat", "t-export"]
PROJECT = "proj-k03-catalog1"
APPROVED_AT = "2026-10-26T00:00:00Z"
MODEL = "meta/muse-spark-1.3-contributor"

EXPECTED_RUNGS = (
    "UI_AUTOMATION",
    "SCREEN_CAPTURE_AI_VISION",
    "EMULATORS_SIMULATORS",
    "BROWSER_PROFILES",
    "TEST_ACCOUNTS",
    "TEST_SERVER",
    "DEVICE_LOGS",
    "SANDBOX_INSTALL",
)


def _profile():
    return contract.ProjectProfile(
        project_id=PROJECT,
        platform="windows",
        features=("chat",),
        risk_class="LOW",
    )


def _code_contract():
    return contract.publish_contract(
        runner_id="runner-pytest",
        kind="CODE",
        user_runner=False,
        catalog_ref=CATALOG_REF,
    )


def test_contract_run_returns_evidence_result():
    result = contract.run(
        contract=_code_contract(),
        profile=_profile(),
        test_id="t-boot",
        catalog_ids=list(CATALOG_IDS),
        approval=None,
        ladder_asked=False,
        reason=None,
        assertion_ref="attest-t-boot",
    )
    assert result.test_id == "t-boot"
    assert result.runner_id == "runner-pytest"
    assert len(result.evidence_refs) >= 1
    assert result.output_ref is not None


def test_catalog_only_ids():
    with pytest.raises(Exception) as exc_info:
        contract.run(
            contract=_code_contract(),
            profile=_profile(),
            test_id="no-such-test",
            catalog_ids=list(CATALOG_IDS),
            approval=None,
            ladder_asked=False,
            reason=None,
            assertion_ref="attest-no-such",
        )
    assert exc_info.value.code == "UNKNOWN_TEST_ID"


def test_user_runner_approval_recorded():
    approval = contract.approve_user_runner(
        runner_id="runner-user-1",
        approved_by_user=True,
        approved_at=APPROVED_AT,
    )
    assert approval.runner_id == "runner-user-1"
    assert approval.approved is True


def test_user_runner_without_approval_refused():
    user_contract = contract.publish_contract(
        runner_id="runner-user-1",
        kind="CODE",
        user_runner=True,
        catalog_ref=CATALOG_REF,
    )
    with pytest.raises(Exception) as exc_info:
        contract.run(
            contract=user_contract,
            profile=_profile(),
            test_id="t-boot",
            catalog_ids=list(CATALOG_IDS),
            approval=None,
            ladder_asked=False,
            reason=None,
            assertion_ref="attest-t-boot",
        )
    assert exc_info.value.code == "USER_RUNNER_NOT_APPROVED"


def test_approved_user_runner_runs():
    user_contract = contract.publish_contract(
        runner_id="runner-user-1",
        kind="CODE",
        user_runner=True,
        catalog_ref=CATALOG_REF,
    )
    approval = contract.approve_user_runner(
        runner_id="runner-user-1",
        approved_by_user=True,
        approved_at=APPROVED_AT,
    )
    result = contract.run(
        contract=user_contract,
        profile=_profile(),
        test_id="t-boot",
        catalog_ids=list(CATALOG_IDS),
        approval=approval,
        ladder_asked=False,
        reason=None,
        assertion_ref="attest-t-boot",
    )
    assert result.test_id == "t-boot"


def test_ladder_rung_names_in_exact_order():
    assert tuple(ladder.ladder_rungs()) == EXPECTED_RUNGS


def test_human_run_needs_ladder_first():
    human_contract = contract.publish_contract(
        runner_id="runner-human-1",
        kind="HUMAN",
        user_runner=False,
        catalog_ref=CATALOG_REF,
    )
    with pytest.raises(Exception) as exc_info:
        contract.run(
            contract=human_contract,
            profile=_profile(),
            test_id="t-export",
            catalog_ids=list(CATALOG_IDS),
            approval=None,
            ladder_asked=False,
            reason="needs hands on device",
            assertion_ref=None,
        )
    assert exc_info.value.code == "HUMAN_BEFORE_LADDER"


def test_human_run_needs_reason():
    human_contract = contract.publish_contract(
        runner_id="runner-human-1",
        kind="HUMAN",
        user_runner=False,
        catalog_ref=CATALOG_REF,
    )
    with pytest.raises(Exception) as exc_info:
        contract.run(
            contract=human_contract,
            profile=_profile(),
            test_id="t-export",
            catalog_ids=list(CATALOG_IDS),
            approval=None,
            ladder_asked=True,
            reason=None,
            assertion_ref=None,
        )
    assert exc_info.value.code == "HUMAN_REASON_MISSING"


def test_human_run_after_ladder_with_reason():
    human_contract = contract.publish_contract(
        runner_id="runner-human-1",
        kind="HUMAN",
        user_runner=False,
        catalog_ref=CATALOG_REF,
    )
    result = contract.run(
        contract=human_contract,
        profile=_profile(),
        test_id="t-export",
        catalog_ids=list(CATALOG_IDS),
        approval=None,
        ladder_asked=True,
        reason="needs hands on device",
        assertion_ref=None,
    )
    assert result.test_id == "t-export"
