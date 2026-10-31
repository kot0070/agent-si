"""K02REST2 served rows: hierarchy-routes seam through create_app.

testid k02rest2-served; one behaviour test per frozen row via
create_app + HTTP client. CODER-A rows (116, 117, 87, 22) assert the
served hierarchy-routes seam; CODER-B rows (33, 35, R-301, R-303)
assert orchestration rows still unserved until CODER-B lands.
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
    from agent_si import hierarchy_routes as _seam
    _SEAM_ERROR = None
except Exception as err:  # seam unserved: every test below fails RED
    _seam = None
    _SEAM_ERROR = err

TEST_TOKEN = "k02rest2-served-token"
MODEL_ID = "meta/muse-spark-1.3-contributor"


def make_client():
    if _seam is None:
        raise AssertionError(
            f"K02REST2 seam unserved: {_SEAM_ERROR!r}")
    app = create_app({"testing": True, "ui_session_token": TEST_TOKEN})
    _seam.register_k02rest2_routes(app)
    headers = {"x-actor": "manager-1", "x-ui-session-token": TEST_TOKEN}
    return TestClient(app), headers


def test_k02rest2_116():
    """kit/BUILD_PLAN.md:1289 | 116 | K02 | OPEN.
    clarification opens a bounded delta package."""
    client, headers = make_client()
    resp = client.post(
        "/v1/k02rest2/delta-intake",
        json={"scope": ["k02rest2-clarify-1"], "blocking": False},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["delta_id"].startswith("delta-")
    assert body["scope"] == ["k02rest2-clarify-1"]
    assert body["blocking"] is False
    assert body["keep"] == ["k02rest2-clarify-1"]
    assert body["patch"] == []
    over = client.post(
        "/v1/k02rest2/delta-intake",
        json={"scope": [f"r-{i:02d}" for i in range(17)],
              "blocking": False},
        headers=headers,
    )
    assert over.status_code == 400
    assert over.json()["detail"]["code"] == "DELTA_OVER_BOUND"
    no_actor = client.post(
        "/v1/k02rest2/delta-intake",
        json={"scope": ["k02rest2-clarify-1"], "blocking": False},
    )
    assert no_actor.status_code == 401
    bad_token = client.post(
        "/v1/k02rest2/delta-intake",
        json={"scope": ["k02rest2-clarify-1"], "blocking": False},
        headers={"x-actor": "manager-1",
                 "x-ui-session-token": "wrong-token"},
    )
    assert bad_token.status_code == 403


def test_k02rest2_117():
    """kit/BUILD_PLAN.md:1290 | 117 | K02 | OPEN.
    non-blocking delta runs in parallel with link-check close."""
    client, headers = make_client()
    taken = client.post(
        "/v1/k02rest2/delta-intake",
        json={"scope": ["k02rest2-joint-1"], "blocking": False},
        headers=headers,
    )
    assert taken.status_code == 200, taken.text
    delta = taken.json()
    closed = client.post(
        "/v1/k02rest2/delta-close",
        json={"delta": delta,
              "verdict": {"gate": "PASS", "audit": "PASS",
                          "evidence_refs": ["artifact://k02rest2/joint-1"]}},
        headers=headers,
    )
    assert closed.status_code == 200, closed.text
    body = closed.json()
    assert body["package_id"] == delta["delta_id"]
    assert body["gate"] == "PASS"
    assert body["audit"] == "PASS"
    assert "linkcheck:ok" in body["evidence_refs"]
    dangling = client.post(
        "/v1/k02rest2/delta-close",
        json={"delta": delta,
              "verdict": {"gate": "PASS", "audit": "PASS",
                          "evidence_refs": []}},
        headers=headers,
    )
    assert dangling.status_code == 200
    assert dangling.json()["gate"] == "BLOCKED"
    assert dangling.json()["audit"] == "BLOCKED"
    no_actor = client.post(
        "/v1/k02rest2/delta-close",
        json={"delta": delta,
              "verdict": {"gate": "PASS", "audit": "PASS",
                          "evidence_refs": ["artifact://k02rest2/joint-1"]}},
    )
    assert no_actor.status_code == 401


def test_k02rest2_87():
    """kit/BUILD_PLAN.md:1303 | 87 | K02 | OPEN.
    served phase gate; no next phase until CLOSE."""
    client, headers = make_client()
    package_id = "k02rest2-87-pkg"
    for part_id in (package_id + ":part-a", package_id + ":integration"):
        gate = client.post(
            "/v1/split-gates/part-gate",
            json={"part_id": part_id, "verdict": "PASS"},
            headers=headers,
        )
        assert gate.status_code == 200, gate.text
        audit = client.post(
            "/v1/split-gates/part-audit",
            json={"part_id": part_id, "result": "PASS",
                  "auditor_session_ref": "sess-k02rest2-87-aud",
                  "producer_session_refs": ["sess-k02rest2-87-prod"],
                  "context_integrity": True},
            headers=headers,
        )
        assert audit.status_code == 200, audit.text
    verdict = client.post(
        "/v1/k02rest2/phase-gate",
        json={"package_ids": [package_id]},
        headers=headers,
    )
    assert verdict.status_code == 200, verdict.text
    body = verdict.json()
    assert body["package_id"] == package_id
    assert body["gate"] == "PASS"
    assert body["audit"] == "PASS"
    assert len(body["evidence_refs"]) == 2
    missing = client.post(
        "/v1/k02rest2/phase-gate",
        json={"package_ids": ["k02rest2-87-absent-pkg"]},
        headers=headers,
    )
    assert missing.status_code == 409
    assert missing.json()["detail"]["code"] == "GATE_NOT_PASSED"
    no_actor = client.post(
        "/v1/k02rest2/phase-gate",
        json={"package_ids": [package_id]},
    )
    assert no_actor.status_code == 401


def test_k02rest2_22():
    """kit/BUILD_PLAN.md:1324 | 22 | K02 | PARTIAL.
    control-plane mapping documented."""
    client, headers = make_client()
    resp = client.get("/v1/k02rest2/control-plane")
    assert resp.status_code == 200, resp.text
    mapping = resp.json()
    assert mapping["director.split"] == "split.split_package"
    assert mapping["director.route"] == "graph.route_task"
    assert mapping["director.policy"] == "graph.CONTROL_PLANE_MAP"
    assert (mapping["director.integrate"]
            == "graph.HierarchyConfigStore.close_parent")
    assert mapping["director.decide"] == "teamcard.DecisionLog.append"
    authed = client.get("/v1/k02rest2/control-plane", headers=headers)
    assert authed.status_code == 200


def test_k02rest2_33():
    """kit/BUILD_PLAN.md:1325 | 33 | K02 | PARTIAL.
    served part register, not a markdown file."""
    client, headers = make_client()
    stored = client.post(
        "/v1/k02rest2/part-register",
        json={"agent": "director-1", "scope": "k02rest2-33-a",
              "deliverable": "artifact://k02rest2/part-a",
              "status": "QUEUED"},
        headers=headers,
    )
    assert stored.status_code == 200, stored.text
    assert stored.json()["scope"] == "k02rest2-33-a"
    rows = client.get("/v1/k02rest2/part-register")
    assert rows.status_code == 200, rows.text
    scopes = [row["scope"] for row in rows.json()["rows"]]
    assert "k02rest2-33-a" in scopes
    refused = client.post(
        "/v1/k02rest2/part-register",
        json={"agent": "director-1",
              "deliverable": "artifact://k02rest2/part-b",
              "status": "QUEUED"},
        headers=headers,
    )
    assert refused.status_code == 400
    no_actor = client.post(
        "/v1/k02rest2/part-register",
        json={"agent": "director-1", "scope": "k02rest2-33-guard",
              "deliverable": "artifact://k02rest2/part-g",
              "status": "QUEUED"},
    )
    assert no_actor.status_code == 401


def test_k02rest2_35():
    """kit/BUILD_PLAN.md:1326 | 35 | K02 | PARTIAL.
    ledger report nudge for the next package."""
    client, headers = make_client()
    package_id = "k02rest2-35-pkg"
    nudge = client.post(
        "/v1/k02rest2/ledger-nudge",
        json={"packages": [{"package_id": package_id, "agents": 2,
                            "peak_concurrency": 2, "wall_time_s": 1.5}],
              "package_id": package_id},
        headers=headers,
    )
    assert nudge.status_code == 200, nudge.text
    body = nudge.json()
    assert body["package_id"] == package_id
    assert body["load"]["agents"] == 2
    assert isinstance(body["nudge"], str) and body["nudge"]
    assert body["auto_push"] is False
    unknown = client.post(
        "/v1/k02rest2/ledger-nudge",
        json={"packages": [{"package_id": package_id, "agents": 2,
                            "peak_concurrency": 2, "wall_time_s": 1.5}],
              "package_id": "k02rest2-35-absent-pkg"},
        headers=headers,
    )
    assert unknown.status_code == 404
    no_actor = client.post(
        "/v1/k02rest2/ledger-nudge",
        json={"packages": [{"package_id": package_id, "agents": 2,
                            "peak_concurrency": 2, "wall_time_s": 1.5}],
              "package_id": package_id},
    )
    assert no_actor.status_code == 401


def test_k02rest2_R301():
    """kit/BUILD_PLAN.md:1341 | R-301 | K02 | OPEN.
    team card in context; decomposition names the facts used."""
    client, headers = make_client()
    rec = client.post(
        "/v1/k02rest2/decomposition-record",
        json={"part_id": "k02rest2-r301-part-a", "size_units": 3,
              "provider": "acme",
              "model_kb_facts": {"ctx": "128k"},
              "budget_left": {"units": 100},
              "limits": {"max_agents": 4}},
        headers=headers,
    )
    assert rec.status_code == 200, rec.text
    body = rec.json()
    assert body["record"]["part_id"] == "k02rest2-r301-part-a"
    assert "part-size-vs-model" in body["record"]["facts_used"]
    assert (body["team_card"]["model"] == MODEL_ID)
    assert body["team_card"]["provider"] == "acme"
    refused = client.post(
        "/v1/k02rest2/decomposition-record",
        json={"part_id": "k02rest2-r301-part-b",
              "provider": "acme",
              "model_kb_facts": {"ctx": "128k"},
              "budget_left": {"units": 100},
              "limits": {"max_agents": 4}},
        headers=headers,
    )
    assert refused.status_code == 400
    no_actor = client.post(
        "/v1/k02rest2/decomposition-record",
        json={"part_id": "k02rest2-r301-part-c", "size_units": 3,
              "provider": "acme",
              "model_kb_facts": {"ctx": "128k"},
              "budget_left": {"units": 100},
              "limits": {"max_agents": 4}},
    )
    assert no_actor.status_code == 401


def test_k02rest2_R303():
    """kit/BUILD_PLAN.md:1361 | R-303 | K02 | OPEN.
    team by task: sized and staffed per block with recorded WHY."""
    client, headers = make_client()
    sized = client.post(
        "/v1/k02rest2/team-sizing",
        json={"block_id": "k02rest2-r303-block",
              "subtask_count": 3, "risk": "HIGH"},
        headers=headers,
    )
    assert sized.status_code == 200, sized.text
    body = sized.json()
    assert body["block_id"] == "k02rest2-r303-block"
    assert body["members"] == 3
    assert "manager" in body["roles"]
    assert "k02rest2-r303-block" in body["why"] and "HIGH" in body["why"]
    refused = client.post(
        "/v1/k02rest2/team-sizing",
        json={"block_id": "k02rest2-r303-block",
              "subtask_count": 3, "risk": "EXTREME"},
        headers=headers,
    )
    assert refused.status_code == 400
    no_actor = client.post(
        "/v1/k02rest2/team-sizing",
        json={"block_id": "k02rest2-r303-block",
              "subtask_count": 3, "risk": "HIGH"},
    )
    assert no_actor.status_code == 401
