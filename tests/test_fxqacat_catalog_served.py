"""FXQACAT served proof: Settings Test-catalog reads serve real lane data.

testids fxqacat-*; drives the real seam app (create_app) plus the real
lane entries. RED on the hollow tree: the catalog summary/tests/versions
reads do not exist and runs/latest carries no start time. GREEN after:
summary serves the active catalog version plus short sha and honest
counters (bases/tests/by-kind); tests serves one row per catalog test;
versions serves one active plus the changelog; runs/latest serves the
served start time recorded by the real start_stage entry.
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

from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "fxqacat-served-token"


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "store"
    root.mkdir()
    return root


@pytest.fixture
def client(store):
    from fastapi.testclient import TestClient

    settings = {"ui_session_token": TEST_TOKEN, "store_dir": str(store)}
    app = create_app(dict(settings))
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def clean_stage():
    """Snapshot-restore the stage latest-run index this proof touches."""
    from agent_si.test_runners import stage_runner as _stage

    saved = dict(_stage._LATEST_RUN)
    saved_runs = dict(_stage._RUNS)
    try:
        yield
    finally:
        _stage._LATEST_RUN.clear()
        _stage._LATEST_RUN.update(saved)
        for key in [key for key in _stage._RUNS if key not in saved_runs]:
            del _stage._RUNS[key]


def test_summary_serves_version_sha_and_counters(client):
    """Summary serves the active catalog version, short sha and counters."""
    from agent_si.qa_catalog import catalog_v2 as _c2
    from agent_si.test_runners import test_bases as _bases

    resp = client.get("/api/v1/teststage/catalog/summary")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["catalog_ref"] == "catalog-v2", body
    assert body["version"] == _c2.CATALOG_VERSION, body
    sha = body["version_sha_short"]
    assert isinstance(sha, str) and len(sha) == 8, body
    assert all(item in "0123456789abcdef" for item in sha), body
    assert body["bases"] == len(_bases.list_bases()), body
    assert body["tests_total"] == _c2.catalog_total() >= 300, body
    kinds = body["kinds"]
    assert set(kinds) == {"CODE", "AI", "HUMAN"}, body
    assert kinds["CODE"] + kinds["AI"] + kinds["HUMAN"] == body["tests_total"], body
    split = _c2.split_summary()
    assert kinds["CODE"] == split["code"], body
    assert kinds["AI"] == split["ai"], body
    assert kinds["HUMAN"] == split["human"], body


def test_tests_serves_one_row_per_test(client):
    """Effective catalog serves one row per test with filterable fields."""
    resp = client.get("/api/v1/teststage/catalog/tests")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    rows = body["tests"]
    assert body["total"] == len(rows) >= 300, body
    ids = [row["id"] for row in rows]
    assert len(set(ids)) == len(ids), "one row per test, no doubles"
    for row in rows:
        assert set(row) == {"id", "group", "intent", "kind", "priority",
                            "runner"}, row
        assert row["id"].startswith(row["group"] + "-"), row


def test_versions_serves_one_active_plus_changelog(client):
    """Versions serve one active version, older kept, plus the changelog."""
    resp = client.get("/api/v1/teststage/catalog/history")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["catalog_ref"] == "catalog-frozen-v1", body
    active = body["active"]
    assert active["version"] >= 1, body
    assert len(active["sha_short"]) == 8, body
    flagged = [row for row in body["versions"] if row["active"]]
    assert len(flagged) == 1 and flagged[0]["version"] == active["version"], body
    assert body["changelog"], body
    assert all(set(row) == {"version", "change", "changed_at", "changed_by"}
               for row in body["changelog"]), body


def test_runs_latest_serves_served_start_time(client, clean_stage):
    """runs/latest serves the start time the real start_stage recorded."""
    from agent_si.test_runners import stage_runner as _stage

    project_id = "fxqacat-time"
    run = _stage.start_stage(project_id, "plan-fxqacat-time-r1", "r1")
    assert run.run_id == "r1", run
    resp = client.get("/api/v1/teststage/runs/latest",
                      params={"project_id": project_id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run_id"] == "r1", body
    assert body["plan_id"] == "plan-fxqacat-time-r1", body
    assert isinstance(body.get("started_at"), str) and body["started_at"], body
