"""FXPANEL run record: served RED/GREEN proof for R3/R5.

POST /api/v1/hierarchy/run answers the frozen ids plus a per-level
list of role/agent_id/provider/model from the pinned profiles used
for that run. A run naming a foreign agent at the tool level is
refused with HTTP 400.
"""

import os
import sys

from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import graph as _graph  # noqa: E402
from agent_si.routing.types import RoleModelProfile  # noqa: E402
from tests.test_fxautodev_served import (  # noqa: E402
    bind_canned_hierarchy_adapter as _bind_canned,
)

TEST_TOKEN = "fxpanel-run-token"

PINNED = {
    "director": ("prov-director", "model-director-1"),
    "manager": ("prov-manager", "model-manager-1"),
    "worker": ("prov-worker", "model-worker-1"),
}


def _refs(n):
    return [f"artifact://pkg-{i}/blob" for i in range(n)]


def make_client(tmp_path):
    settings = {"testing": True, "ui_session_token": TEST_TOKEN,
                "store_dir": str(tmp_path)}
    app = create_app(settings)
    headers = {"x-actor": "fxp-tester", "x-ui-session-token": TEST_TOKEN}
    return app, TestClient(app), headers


def pin_profiles(app, project_id):
    table = app.state.k04_ctx.role_table
    for role, (provider, model) in PINNED.items():
        table.set_profile(RoleModelProfile(
            role=role, project_id=project_id, mode="PINNED",
            provider=provider, model=model, binding="DEFAULT",
            version=1, hash="fxp-test"))
    return table


def _run_body(**overrides):
    body = {
        "package_id": "fxp-pkg",
        "goal": "prove run record identity",
        "context_refs": _refs(4),
        "max_parts": 2,
        "director_id": "director-fxp",
        "manager_id": "manager-fxp",
        "tool_agent_ids": ["tool-a", "tool-b"],
    }
    body.update(overrides)
    return body


def test_run_record_carries_per_level_identity(tmp_path):
    app, client, headers = make_client(tmp_path)
    pin_profiles(app, "fxp-proj")
    _canned_patch = _bind_canned(project_id="fxp-proj")
    resp = client.post(
        "/api/v1/hierarchy/run",
        json=_run_body(project_id="fxp-proj"),
        headers=headers,
    )
    _canned_patch.stop()
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["director"] == "director-fxp"
    assert payload["manager"] == "manager-fxp"
    assert len(payload["parts"]) == 2
    assert "levels" in payload, "run record carries per-level identity"
    assert payload["levels"] == [
        {"role": "director", "agent_id": "director-fxp",
         "provider": "prov-director", "model": "model-director-1"},
        {"role": "manager", "agent_id": "manager-fxp",
         "provider": "prov-manager", "model": "model-manager-1"},
        {"role": "worker", "agent_id": "tool-a",
         "provider": "prov-worker", "model": "model-worker-1"},
        {"role": "worker", "agent_id": "tool-b",
         "provider": "prov-worker", "model": "model-worker-1"},
    ]


def test_run_record_without_profiles_has_null_identity(tmp_path):
    _app, client, headers = make_client(tmp_path)
    _canned_patch = _bind_canned()
    resp = client.post(
        "/api/v1/hierarchy/run",
        json=_run_body(),
        headers=headers,
    )
    _canned_patch.stop()
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert [entry["role"] for entry in payload["levels"]] == [
        "director", "manager", "worker", "worker"]
    assert [entry["agent_id"] for entry in payload["levels"]] == [
        "director-fxp", "manager-fxp", "tool-a", "tool-b"]
    assert all(entry["provider"] is None and entry["model"] is None
               for entry in payload["levels"])


def test_run_record_foreign_agent_is_400(tmp_path):
    _app, client, headers = make_client(tmp_path)
    resp = client.post(
        "/api/v1/hierarchy/run",
        json=_run_body(tool_agent_ids=["manager-fxp"]),
        headers=headers,
    )
    assert resp.status_code == 400, resp.text


def test_run_keeps_control_plane_static(tmp_path):
    _app, client, headers = make_client(tmp_path)
    _canned_patch = _bind_canned()
    before = client.get("/api/v1/hierarchy/control-plane")
    assert before.status_code == 200, before.text
    resp = client.post(
        "/api/v1/hierarchy/run",
        json=_run_body(),
        headers=headers,
    )
    _canned_patch.stop()
    assert resp.status_code == 200, resp.text
    after = client.get("/api/v1/hierarchy/control-plane")
    assert after.status_code == 200, after.text
    assert after.json() == before.json() == _graph.control_plane_map()
