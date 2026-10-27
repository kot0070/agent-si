import os, sys; sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__),"..","..","..","src")))
"""K02 APP-SEAM: FastAPI routes served from real orchestration state + router guard."""

from fastapi.testclient import TestClient

from agent_si.backend.app import create_app
from agent_si.backend.orchestration.parts import PartRow, register_part

TEST_TOKEN = "k02-seam-test-token"
TEST_SETTINGS = {"testing": True, "ui_session_token": TEST_TOKEN}


def make_client(**kwargs):
    settings = dict(TEST_SETTINGS)
    app = create_app(settings, **kwargs)
    return app, TestClient(app)


def seed_parts(prefix="seam-live"):
    rows = [
        PartRow(agent="seam-agent-1", scope=prefix + "-0001",
                deliverable="artifact://seam/%s-0001" % prefix),
        PartRow(agent="seam-agent-2", scope=prefix + "-0002",
                deliverable="artifact://seam/%s-0002" % prefix,
                status="RUNNING"),
    ]
    for row in rows:
        register_part(row)
    return rows


def seed_ledger(app, project_id="proj-seam"):
    ledger = app.state.ledger_for(project_id)
    ledger.record_row("pkg-seam-1", 3, 2, 12.5)
    ledger.record_row("pkg-seam-2", 1, 1, 2.0)
    return ledger


def test_agents_live_serves_registered_rows():
    app, client = make_client()
    rows = seed_parts()
    resp = client.get("/api/v1/agents/live")
    assert resp.status_code == 200
    served = {item["scope"]: item for item in resp.json()["agents"]}
    for row in rows:
        item = served[row.scope]
        assert (item["agent"], item["scope"],
                item["deliverable"], item["status"]) == (
            row.agent, row.scope, row.deliverable, row.status)


def test_runs_ledger_serves_recorded_rows():
    app, client = make_client()
    seed_ledger(app)
    resp = client.get("/api/v1/runs/ledger", params={"project_id": "proj-seam"})
    assert resp.status_code == 200
    served = {item["package_id"]: item for item in resp.json()["rows"]}
    assert served["pkg-seam-1"] == {
        "package_id": "pkg-seam-1", "agents": 3,
        "peak_concurrency": 2, "wall_time_s": 12.5}
    assert served["pkg-seam-2"] == {
        "package_id": "pkg-seam-2", "agents": 1,
        "peak_concurrency": 1, "wall_time_s": 2.0}


def test_runs_ledger_unknown_project_empty_and_missing_param_rejected():
    _, client = make_client()
    resp = client.get("/api/v1/runs/ledger",
                      params={"project_id": "proj-never-recorded"})
    assert resp.status_code == 200
    assert resp.json() == {"rows": []}
    resp = client.get("/api/v1/runs/ledger")
    assert resp.status_code == 422


def test_next_package_nudge_names_next_package():
    app, client = make_client()
    ledger = app.state.ledger_for("proj-nudge")
    ledger.record_row("pkg-nudge-a", 2, 2, 5.0)
    ledger.record_row("pkg-nudge-b", 4, 3, 9.0)
    resp = client.get("/api/v1/reports/next-package-nudge",
                      params={"package_id": "pkg-nudge-a"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["package_id"] == "pkg-nudge-a"
    assert body["load"] == {
        "package_id": "pkg-nudge-a", "agents": 2,
        "peak_concurrency": 2, "wall_time_s": 5.0}
    assert "pkg-nudge-a" in body["nudge"]
    assert "pkg-nudge-b" in body["nudge"]
    assert body["auto_push"] is False


def test_next_package_nudge_scoped_and_missing_cases():
    app, client = make_client()
    ledger = app.state.ledger_for("proj-nudge-scoped")
    ledger.record_row("pkg-scoped-a", 2, 2, 5.0)
    ledger.record_row("pkg-scoped-b", 1, 1, 1.0)
    resp = client.get("/api/v1/reports/next-package-nudge",
                      params={"package_id": "pkg-scoped-a",
                              "project_id": "proj-nudge-scoped"})
    assert resp.status_code == 200
    assert "pkg-scoped-b" in resp.json()["nudge"]
    resp = client.get("/api/v1/reports/next-package-nudge",
                      params={"package_id": "pkg-no-such"})
    assert resp.status_code == 404
    resp = client.get("/api/v1/reports/next-package-nudge")
    assert resp.status_code == 422


def test_reads_need_no_token():
    app, client = make_client()
    seed_parts(prefix="seam-open")
    seed_ledger(app, project_id="proj-open")
    assert client.get("/api/v1/agents/live").status_code == 200
    resp = client.get("/api/v1/runs/ledger",
                      params={"project_id": "proj-open"})
    assert resp.status_code == 200
    assert len(resp.json()["rows"]) == 2
    resp = client.get("/api/v1/reports/next-package-nudge",
                      params={"package_id": "pkg-seam-1"})
    assert resp.status_code == 200


def test_post_write_without_actor_refused():
    _, client = make_client()
    assert client.post("/api/v1/chat/stream").status_code == 401
    resp = client.post("/api/v1/chat/stream",
                       headers={"x-ui-session-token": TEST_TOKEN})
    assert resp.status_code == 401


def test_post_user_write_without_token_refused():
    _, client = make_client()
    resp = client.post("/api/v1/chat/stream",
                       headers={"x-actor": "tester-1"})
    assert resp.status_code == 403
    resp = client.post("/api/v1/chat/stream",
                       headers={"x-actor": "tester-1",
                                "x-ui-session-token": "wrong-token"})
    assert resp.status_code == 403


def test_post_with_actor_and_token_accepted_with_real_count():
    _, client = make_client()
    rows = seed_parts(prefix="seam-chat")
    resp = client.post("/api/v1/chat/stream",
                       headers={"x-actor": "tester-1",
                                "x-ui-session-token": TEST_TOKEN})
    assert resp.status_code == 200
    assert resp.json() == {"status": "accepted",
                           "actor": "tester-1",
                           "live_parts": len(rows)}


def test_injected_denying_auth_hook_refuses_with_token():
    seen = []

    def deny_auth(token, actor, action):
        seen.append((token, actor, action))
        return False

    _, client = make_client(auth_hook=deny_auth)
    resp = client.post("/api/v1/chat/stream",
                       headers={"x-actor": "tester-1",
                                "x-ui-session-token": TEST_TOKEN})
    assert resp.status_code == 403
    assert seen == [(TEST_TOKEN, "tester-1", "USER_WRITE")]


def test_injected_denying_rate_hook_limits_with_token():
    _, client = make_client(rate_hook=lambda key: False)
    resp = client.post("/api/v1/chat/stream",
                       headers={"x-actor": "tester-1",
                                "x-ui-session-token": TEST_TOKEN})
    assert resp.status_code == 429
