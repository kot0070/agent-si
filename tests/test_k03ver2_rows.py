"""K03VER2 RED LIST: rows 200, 201, M-P3-120, M-P4-154 via served app.

Behaviour tests through create_app + HTTP client; every route reaches its
real lane entry. Fails on the old code (routes unregistered -> 404).
"""

from __future__ import annotations

import os
import sys

import pytest

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app

TEST_TOKEN = "k03ver2-token"
TEST_SETTINGS = {"testing": True, "ui_session_token": TEST_TOKEN}


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    app = create_app(dict(TEST_SETTINGS))
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_row200_versions_changelog_proposal_approval(client):
    """Row 200: versions + changelog + proposal approval flow on the app."""
    ref = "k03ver2-catalog-row200"
    resp = client.post(
        "/api/v1/teststage/catalog/versions/record",
        json={"catalog_ref": ref, "version": 1,
              "change_notes": "initial frozen set",
              "recorded_at": "2026-10-29T00:00:00+00:00"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["version"] == 1

    resp = client.get(
        "/api/v1/teststage/catalog/changelog", params={"catalog_ref": ref})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["rows"]) == 1

    # Missing change note is refused in its own condition.
    resp = client.post(
        "/api/v1/teststage/catalog/versions/record",
        json={"catalog_ref": ref, "version": 2, "change_notes": "  ",
              "recorded_at": "2026-10-29T00:00:00+00:00"},
    )
    assert resp.status_code == 400, resp.text
    assert "CHANGELOG_ENTRY_MISSING" in resp.text

    resp = client.post(
        "/api/v1/teststage/catalog/proposals",
        json={"catalog_ref": ref, "from_version": 1, "to_version": 2,
              "changes": ["add t-k03ver2 probe"],
              "proposed_at": "2026-10-29T00:00:00+00:00"},
    )
    assert resp.status_code == 200, resp.text
    proposal = resp.json()
    assert proposal["status"] == "PENDING"
    assert "t-k03ver2" in proposal["changelog"]

    # Unknown proposal is refused in its own condition.
    resp = client.post(
        "/api/v1/teststage/catalog/proposals/approve",
        json={"proposal_id": "prop-nope-row200", "approver": "owner",
              "approved": True, "decided_at": "2026-10-29T00:00:00+00:00"},
    )
    assert resp.status_code == 400, resp.text
    assert "PROPOSAL_NOT_FOUND" in resp.text

    resp = client.post(
        "/api/v1/teststage/catalog/proposals/approve",
        json={"proposal_id": proposal["proposal_id"], "approver": "owner",
              "approved": True, "decided_at": "2026-10-29T00:00:00+00:00"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "APPROVED"

    # Decided proposals cannot be decided again.
    resp = client.post(
        "/api/v1/teststage/catalog/proposals/approve",
        json={"proposal_id": proposal["proposal_id"], "approver": "owner",
              "approved": True, "decided_at": "2026-10-29T00:00:00+00:00"},
    )
    assert resp.status_code == 400, resp.text
    assert "PROPOSAL_ALREADY_DECIDED" in resp.text

    resp = client.get(
        "/api/v1/teststage/catalog/changelog", params={"catalog_ref": ref})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["rows"]) == 2


def test_row201_runner_contract_and_approval(client):
    """Row 201: project profile in, evidence out; user runners need approval."""
    profile = {"project_id": "k03ver2-proj201", "profile_name": "default",
               "runtime": "local", "base_id": "base-code-fast"}
    resp = client.post(
        "/api/v1/teststage/runners/run",
        json={"profile": profile, "test_id": "t-boot",
              "runner_id": "builtin-code"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["evidence_ref"].startswith("evidence://k03ver2-proj201/")
    assert body["contract_version"] == "runner-contract/1"

    # User runner without approval is refused in its own condition.
    resp = client.post(
        "/api/v1/teststage/runners/run",
        json={"profile": profile, "test_id": "t-boot",
              "runner_id": "user-k03ver2-custom"},
    )
    assert resp.status_code == 400, resp.text
    assert "UNAPPROVED_USER_RUNNER" in resp.text

    resp = client.post(
        "/api/v1/teststage/runners/approve",
        json={"runner_id": "user-k03ver2-custom", "approver": "owner"},
    )
    assert resp.status_code == 200, resp.text

    resp = client.post(
        "/api/v1/teststage/runners/run",
        json={"profile": profile, "test_id": "t-boot",
              "runner_id": "user-k03ver2-custom"},
    )
    assert resp.status_code == 200, resp.text
    assert "user-k03ver2-custom" in resp.json()["evidence_ref"]

    # Empty runner id is refused in its own condition.
    resp = client.post(
        "/api/v1/teststage/runners/run",
        json={"profile": profile, "test_id": "t-boot", "runner_id": ""},
    )
    assert resp.status_code == 400, resp.text
    assert "UNKNOWN_RUNNER" in resp.text

    # Profile without a project is refused in its own condition.
    resp = client.post(
        "/api/v1/teststage/runners/run",
        json={"profile": {"project_id": "", "runtime": "local"},
              "test_id": "t-boot", "runner_id": "builtin-code"},
    )
    assert resp.status_code == 400, resp.text
    assert "RUNNER_PROFILE_INVALID" in resp.text


def test_row_m_p3_120_four_bases_and_kinds(client):
    """M-P3-120: four built-in bases with CODE/AI/HUMAN kinds, plus attach."""
    from agent_si.test_runners import test_bases as _bases

    resp = client.get("/api/v1/teststage/bases")
    assert resp.status_code == 200, resp.text
    rows = resp.json()["bases"]
    builtin = [row for row in rows if row["origin"] == "builtin"]
    assert len(builtin) == 4, rows
    assert [row["kind"] for row in builtin] == ["CODE", "CODE", "AI", "HUMAN"]

    # Unknown kind is refused in its own condition.
    resp = client.post(
        "/api/v1/teststage/bases/attach",
        json={"base_id": "user-k03ver2-base", "kind": "QUANTUM"},
    )
    assert resp.status_code == 400, resp.text
    assert "UNKNOWN_EXECUTION_KIND" in resp.text

    resp = client.post(
        "/api/v1/teststage/bases/attach",
        json={"base_id": "user-k03ver2-base", "kind": "CODE"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["origin"] == "attached"

    # Re-attaching the same base is refused in its own condition.
    resp = client.post(
        "/api/v1/teststage/bases/attach",
        json={"base_id": "user-k03ver2-base", "kind": "CODE"},
    )
    assert resp.status_code == 400, resp.text
    assert "BASE_ALREADY_ATTACHED" in resp.text

    with pytest.raises(Exception) as exc_info:
        _bases.base_kind("base-nope-k03ver2")
    assert getattr(exc_info.value, "code", "") == "UNKNOWN_TEST_BASE"


def test_row_m_p4_154_global_default_switch_tests_view(client):
    """M-P4-154: local tests default ON, per-project switch, TESTS view."""
    project = "k03ver2-proj154-fresh"
    resp = client.get(
        "/api/v1/teststage/local-tests", params={"project_id": project})
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is True

    resp = client.post(
        "/api/v1/teststage/local-tests",
        json={"project_id": project, "enabled": False,
              "updated_at": "2026-10-29T00:00:00+00:00"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is False

    resp = client.get(
        "/api/v1/teststage/local-tests", params={"project_id": project})
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is False

    resp = client.post(
        "/api/v1/teststage/local-tests",
        json={"project_id": project, "enabled": True,
              "updated_at": "2026-10-29T00:00:00+00:00"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is True

    resp = client.get(
        "/api/v1/teststage/tests-view",
        params={"plan_id": "plan-k03ver2", "run_id": "run-k03ver2"},
    )
    assert resp.status_code == 200, resp.text
    view = resp.json()
    assert view["settings_controls"] == []
    assert view["remaining"] == view["active"] - view["passed"]
