"""K02NEXT8 served proof: rows 1-5 (chain-guard + schema + project + disk + gate lane).

testid k02next8-served; one behaviour test per BUILD_PLAN row via
create_app + HTTP client over the real served app (lane seam
register_k02next8_routes; every route delegates its row decision to
the real module; writes keep the frozen USER_WRITE guard shape
(401 missing x-actor, 403 bad token).

Rows (CODER-1 Tern owns rows 1-5; one served test per row):
- R1 B0B-UNCOVERED_BP06-30: route POST /hierarchy/chain-guard,
  test test_k02next8_served_r1_bp06_30. Block activation on invalid
  hierarchy chain shapes without mutating stored configuration.
- R2 LIVE0-07: route GET /hierarchy/schema,
  test test_k02next8_served_r2_live0_07. The OpenAPI and docs schema
  answer, no 500.
- R3 LIVE0B-02: routes POST /hierarchy/project +
  GET /hierarchy/projects,
  test test_k02next8_served_r3_live0b_02. POST stores the chosen
  folder and GET returns it.
- R4 LIVE0B-03: routes POST /hierarchy/project-disk-write +
  GET /hierarchy/project-disk-read,
  test test_k02next8_served_r4_live0b_03. A created project is
  written to disk and survives a restart.
- R5 MH-2: routes POST /hierarchy/gate-threshold +
  POST /hierarchy/gate-verdict,
  test test_k02next8_served_r5_mh_2. Each milestone/part gate
  carries a configurable verification threshold param;
  below-threshold cannot PASS, triggers correction/escalation.
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

try:
    from agent_si.backend.orchestration import (
        hierarchy_routes as _seam,
    )
    _SEAM_ERROR = None
except Exception as err:  # seam unserved: every test below fails RED
    _seam = None
    _SEAM_ERROR = err

TEST_TOKEN = "k02next8-served-token"


def make_client():
    if _seam is None or not hasattr(_seam, "register_k02next8_routes"):
        raise AssertionError(
            f"K02NEXT8 seam unserved: {_SEAM_ERROR!r}")
    app = create_app({"testing": True, "ui_session_token": TEST_TOKEN})
    _seam.register_k02next8_routes(app)
    headers = {"x-actor": "manager-1", "x-ui-session-token": TEST_TOKEN}
    return TestClient(app), headers


def test_k02next8_served_r1_bp06_30():
    """R1 B0B-UNCOVERED_BP06-30: invalid chain blocked, stored unchanged."""
    client, headers = make_client()
    establish = {
        "director_id": "director-1",
        "manager_id": "manager-1",
        "tool_agent_ids": ["tool-1", "tool-2"],
    }
    invalid_attempt = {
        "director_id": "  ",
        "manager_id": "manager-1",
        "tool_agent_ids": [],
    }
    refused = client.post(
        "/hierarchy/chain-guard",
        json={"establish": establish, "attempt": invalid_attempt},
        headers=headers,
    )
    assert refused.status_code == 400, refused.text
    detail = refused.json()["detail"]
    assert detail["blocked"] is True
    assert detail["stored_unchanged"] is True
    assert detail["stored"]["director"] == "director-1"
    assert detail["stored"]["manager"] == "manager-1"
    served = client.post(
        "/hierarchy/chain-guard",
        json={"establish": establish, "attempt": {
            "director_id": "director-1",
            "manager_id": "manager-1",
            "tool_agent_ids": ["tool-1"],
        }},
        headers=headers,
    )
    assert served.status_code == 200, served.text
    assert served.json()["blocked"] is False
    assert served.json()["stored"]["tool_agents"] == ["tool-1"]
    no_actor = client.post(
        "/hierarchy/chain-guard",
        json={"establish": establish, "attempt": establish},
        headers={"x-ui-session-token": TEST_TOKEN},
    )
    assert no_actor.status_code == 401


def test_k02next8_served_r2_live0_07():
    """R2 LIVE0-07: the OpenAPI and docs schema answer, no 500."""
    client, headers = make_client()
    resp = client.get("/hierarchy/schema", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body["openapi"], str) and body["openapi"]
    assert body["paths"] > 0
    assert body["docs_url"] == "/docs"
    assert body["openapi_url"] == "/openapi.json"
    openapi_resp = client.get("/openapi.json", headers=headers)
    assert openapi_resp.status_code == 200, openapi_resp.text
    assert openapi_resp.json()["openapi"] == body["openapi"]
    docs_resp = client.get("/docs", headers=headers)
    assert docs_resp.status_code == 200, docs_resp.text


def test_k02next8_served_r3_live0b_02():
    """R3 LIVE0B-02: POST stores the chosen folder, GET returns it."""
    client, headers = make_client()
    created = client.post(
        "/hierarchy/project",
        json={"name": "K02NEXT8 folder proof",
              "folder_ref": "/work/k02next8-proof"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    project = created.json()["project"]
    assert project["folder_ref"] == "/work/k02next8-proof"
    assert project["name"] == "K02NEXT8 folder proof"
    assert project["project_id"]
    listed = client.get("/hierarchy/projects", headers=headers)
    assert listed.status_code == 200, listed.text
    rows = listed.json()["projects"]
    match = [row for row in rows
             if row["project_id"] == project["project_id"]]
    assert len(match) == 1
    assert match[0]["folder_ref"] == "/work/k02next8-proof"
    bad = client.post(
        "/hierarchy/project",
        json={"name": "no folder"},
        headers=headers,
    )
    assert bad.status_code == 400


def test_k02next8_served_r4_live0b_03(tmp_path):
    """R4 LIVE0B-03: written to disk, readable after a restart."""
    client, headers = make_client()
    store_dir = str(tmp_path / "k02next8-store")
    os.makedirs(store_dir, exist_ok=True)
    snapshot = {"name": "restart proof", "folder_ref": "/work/restart"}
    saved = client.post(
        "/hierarchy/project-disk-write",
        json={"store_dir": store_dir, "project_id": "proj-restart-1",
              "snapshot": snapshot},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["saved"] is True
    assert saved.json()["project_id"] == "proj-restart-1"
    restarted, _headers = make_client()
    found = restarted.get(
        "/hierarchy/project-disk-read",
        params={"store_dir": store_dir, "project_id": "proj-restart-1"},
    )
    assert found.status_code == 200, found.text
    assert found.json()["snapshot"] == snapshot
    missing = restarted.get(
        "/hierarchy/project-disk-read",
        params={"store_dir": store_dir, "project_id": "no-such-project"},
    )
    assert missing.status_code == 404


def test_k02next8_served_r5_mh_2():
    """R5 MH-2: threshold gates the verdict; below cannot PASS."""
    client, headers = make_client()
    stored = client.post(
        "/hierarchy/gate-threshold",
        json={"project_id": "proj-mh2-1", "threshold": 0.7},
        headers=headers,
    )
    assert stored.status_code == 200, stored.text
    assert stored.json()["threshold"] == 0.7
    first = client.post(
        "/hierarchy/gate-verdict",
        json={"project_id": "proj-mh2-1", "part_id": "part-mh2-a",
              "score": 0.2},
        headers=headers,
    )
    assert first.status_code == 409, first.text
    assert first.json()["detail"]["action"] == "correction"
    second = client.post(
        "/hierarchy/gate-verdict",
        json={"project_id": "proj-mh2-1", "part_id": "part-mh2-a",
              "score": 0.2},
        headers=headers,
    )
    assert second.status_code == 409, second.text
    assert second.json()["detail"]["action"] == "escalation"
    above = client.post(
        "/hierarchy/gate-verdict",
        json={"project_id": "proj-mh2-1", "part_id": "part-mh2-a",
              "score": 0.9},
        headers=headers,
    )
    assert above.status_code == 200, above.text
    assert above.json()["passed"] is True
    assert above.json()["verdict"] == "PASS"
    bad = client.post(
        "/hierarchy/gate-threshold",
        json={"project_id": "proj-mh2-1", "threshold": 7},
        headers=headers,
    )
    assert bad.status_code == 400
