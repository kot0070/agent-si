"""OC-K03: M-P3-120 four built-in bases + kinds, M-P4-154 global default ON.

Served proof through create_app only (loopback TestClient, no network/keys).
"""
from __future__ import annotations

import os
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from agent_si.backend.app import create_app
from agent_si.test_runners import test_bases as _bases
from agent_si.test_runners import test_planner as _planner

TEST_TOKEN = "ock03-token"
TEST_SETTINGS = {"testing": True, "ui_session_token": TEST_TOKEN}


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    app = create_app(dict(TEST_SETTINGS))
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc


def test_m_p3_120_planner_mirrors_four_bases():
    assert _planner.BUILTIN_TEST_BASES == (
        "base-code-fast",
        "base-code-full",
        "base-ai-judge",
        "base-human-operated",
    )
    assert _planner.BUILTIN_BASE_KINDS == ("CODE", "CODE", "AI", "HUMAN")
    assert _planner.EXECUTION_KINDS == ("CODE", "AI", "HUMAN")
    assert _bases.BUILTIN_TEST_BASES == _planner.BUILTIN_TEST_BASES
    assert _bases.BUILTIN_BASE_KINDS == _planner.BUILTIN_BASE_KINDS
    rows = _planner.planner_bases()
    assert [b for b, _k in rows] == list(_planner.BUILTIN_TEST_BASES)
    assert [k for _b, k in rows] == ["CODE", "CODE", "AI", "HUMAN"]
    assert _planner.kind_for_base("base-code-fast") == "CODE"
    assert _planner.kind_for_base("base-ai-judge") == "AI"
    assert _planner.kind_for_base("base-human-operated") == "HUMAN"
    with pytest.raises(Exception) as exc:
        _planner.kind_for_base("base-nope-ock03")
    assert getattr(exc.value, "code", "") == "UNKNOWN_TEST_ID"
    plan = _planner.derive_plan(
        ["t-login", "t-chat", "t-export"],
        "proj-ock03", "run-ock03", "catalog-frozen-v1",
        "meta/muse-spark-1.3-contributor",
    )
    assert _planner.kind_total(plan) == len(plan.test_ids) == 3
    assert set(plan.kind_counts) <= set(_planner.EXECUTION_KINDS)
    with pytest.raises(Exception) as exc2:
        _planner.derive_plan(
            [], "proj-ock03", "run-ock03", "catalog-frozen-v1",
            "meta/muse-spark-1.3-contributor",
        )
    assert getattr(exc2.value, "code", "") == "EMPTY_TEST_PLAN"


def test_m_p3_120_bases_served(client):
    resp = client.get("/api/v1/teststage/bases")
    assert resp.status_code == 200, resp.text
    rows = resp.json()["bases"]
    builtin = [r for r in rows if r["origin"] == "builtin"]
    assert len(builtin) == 4, rows
    assert [r["kind"] for r in builtin] == ["CODE", "CODE", "AI", "HUMAN"]
    resp = client.post(
        "/api/v1/teststage/bases/attach",
        json={"base_id": "user-ock03-base", "kind": "QUANTUM"},
    )
    assert resp.status_code == 400, resp.text
    assert "UNKNOWN_EXECUTION_KIND" in resp.text
    resp = client.post(
        "/api/v1/teststage/bases/attach",
        json={"base_id": "user-ock03-base", "kind": "CODE"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["origin"] == "attached"
    resp = client.post(
        "/api/v1/teststage/bases/attach",
        json={"base_id": "user-ock03-base", "kind": "CODE"},
    )
    assert resp.status_code == 400, resp.text
    assert "BASE_ALREADY_ATTACHED" in resp.text


def test_m_p4_154_global_default_switch_view_served(client):
    project = "ock03-proj154-fresh"
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
        params={"plan_id": "plan-ock03", "run_id": "run-ock03"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["settings_controls"] == []
