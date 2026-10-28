"""K03 STEP1 behaviour contract: versions plus proposal flow plus local
switch plus Tests tab (rows 200, M-P4-154, R-347). MUST FAIL on stubs.

Entry points: real stub symbols are loaded from
``src/agent_si/qa_catalog/{qa_catalog,catalog_versions,user_overlay}.py``
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
versions = _load("catalog_versions")
overlay = _load("user_overlay")

# FAKE-OF: catalog test data (catalog ref, project and run ids, plan id,
# timestamps; test-only values).
CATALOG_REF = "catalog-frozen-v1"
PROJECT = "proj-k03-catalog1"
RUN = "run-k03-catalog1"
PLAN = "plan-k03-catalog1"
UPDATED_AT = "2026-10-26T00:00:00Z"
MODEL = "meta/muse-spark-1.3-contributor"


def test_proposal_flow_versions_and_changelog():
    current = versions.current_version(catalog_ref=CATALOG_REF)
    proposal = versions.propose_update(
        catalog_ref=CATALOG_REF,
        base_version=current.version,
        draft_changes=["add t-boot"],
        updated_by_model=MODEL,
    )
    assert proposal.base_version == current.version
    applied = versions.apply_proposal(
        proposal_id=proposal.proposal_id, approved_by_user=True
    )
    assert applied.version == current.version + 1
    log = versions.get_changelog(catalog_ref=CATALOG_REF)
    assert any(entry.version == applied.version for entry in log)


def test_proposal_needs_owner_approval():
    proposal = versions.propose_update(
        catalog_ref=CATALOG_REF,
        base_version=1,
        draft_changes=["add t-boot"],
        updated_by_model=MODEL,
    )
    with pytest.raises(Exception) as exc_info:
        versions.apply_proposal(
            proposal_id=proposal.proposal_id, approved_by_user=False
        )
    assert exc_info.value.code == "PROPOSAL_NOT_APPROVED"


def test_apply_unknown_proposal_refused():
    with pytest.raises(Exception) as exc_info:
        versions.apply_proposal(
            proposal_id="proposal-no-such", approved_by_user=True
        )
    assert exc_info.value.code == "UNKNOWN_PROPOSAL"


def test_import_unknown_base_refused():
    with pytest.raises(Exception) as exc_info:
        versions.import_newer_version(catalog_ref=CATALOG_REF, version=9999)
    assert exc_info.value.code == "UNKNOWN_BASE_VERSION"


def test_overlay_carries_audit_trail():
    created = overlay.create_overlay(project_id=PROJECT, base_version=1)
    assert created.project_id == PROJECT
    with_test = overlay.add_overlay_test(
        overlay=created,
        test=overlay.OverlayTest(
            test_id="t-user-1",
            intent="user check",
            kind="CODE",
            oracle="exit code",
            reason="project-specific",
        ),
    )
    assert with_test.tests[-1].test_id == "t-user-1"
    trail = overlay.overlay_audit_trail(overlay=with_test)
    assert len(trail) >= 1


def test_overlay_duplicate_refused():
    created = overlay.create_overlay(project_id=PROJECT, base_version=1)
    test = overlay.OverlayTest(
        test_id="t-user-1",
        intent="user check",
        kind="CODE",
        oracle="exit code",
        reason="project-specific",
    )
    with_test = overlay.add_overlay_test(overlay=created, test=test)
    with pytest.raises(Exception) as exc_info:
        overlay.add_overlay_test(overlay=with_test, test=test)
    assert exc_info.value.code == "DUPLICATE_TEST_ID"


def test_overlay_unknown_version_refused():
    with pytest.raises(Exception) as exc_info:
        overlay.create_overlay(project_id=PROJECT, base_version=-1)
    assert exc_info.value.code == "OVERLAY_ON_UNKNOWN_VERSION"


def test_local_tests_default_on_globally():
    assert catalog.local_tests_enabled(project_id=PROJECT) is True


def test_one_switch_toggles_local_tests():
    off = catalog.set_local_tests_enabled(
        project_id=PROJECT, enabled=False, updated_at=UPDATED_AT
    )
    assert off.enabled is False
    on = catalog.set_local_tests_enabled(
        project_id=PROJECT, enabled=True, updated_at=UPDATED_AT
    )
    assert on.enabled is True


def test_tests_view_is_informational():
    view = catalog.build_tests_view(plan_id=PLAN, run_id=RUN)
    assert view.settings_controls == ()
    assert view.passed + view.remaining == view.active


def test_unknown_catalog_refused():
    with pytest.raises(Exception) as exc_info:
        catalog.get_catalog(catalog_ref="catalog-no-such")
    assert exc_info.value.code == "UNKNOWN_CATALOG"
