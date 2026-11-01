"""FX-PLANKIND: derive_plan must use the catalog kind, not the id substring.

RED before fix: t-chat/t-export guess CODE by substring -> kind_counts
{CODE: 3}. GREEN after: catalog kinds {CODE:1, AI:1, HUMAN:1}.
Served proof: seam call + real POST /api/v1/teststage/plans route.
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

from agent_si.test_runners import test_planner

IDS = ["t-boot", "t-chat", "t-export"]
EXPECTED = {"CODE": 1, "AI": 1, "HUMAN": 1}


def test_derive_plan_uses_catalog_kind():
    plan = test_planner.derive_plan(
        list(IDS),
        "proj-fxplankind",
        "run-fxplankind",
        "catalog-frozen-v1",
        "meta/muse-spark-1.3-contributor",
    )
    assert dict(plan.kind_counts) == EXPECTED
    assert test_planner.kind_total(plan) == len(plan.test_ids) == 3


def test_derive_plan_catalog_kind_served():
    from fastapi.testclient import TestClient

    from agent_si.backend.app import create_app

    app = create_app(
        {"testing": True, "ui_session_token": "fxplankind-token"})
    with TestClient(app, raise_server_exceptions=False) as tc:
        resp = tc.post(
            "/api/v1/teststage/plans",
            json={
                "catalog_ids": list(IDS),
                "project_id": "proj-fxplankind",
                "run_id": "run-fxplankind",
                "catalog_ref": "catalog-frozen-v1",
                "derived_by_model": "meta/muse-spark-1.3-contributor",
            },
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["kind_counts"] == EXPECTED
