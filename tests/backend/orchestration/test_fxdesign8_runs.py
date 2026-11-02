import os, sys; sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__),"..","..","..","src")))
"""FXDESIGN8: one FAKE run through the real routes. A stored devrun record
(4912 tokens + hello.txt, finished) must ride the runs key of
GET /api/v1/runs/ledger with verdict, tokens and files, so the rail and
the chat Total line read the same served number."""

from fastapi.testclient import TestClient

from agent_si.backend.app import create_app

TEST_TOKEN = "fxdesign8-fake-run-token"
TEST_SETTINGS = {"testing": True, "ui_session_token": TEST_TOKEN}


def test_fake_finished_run_rides_ledger_runs_key():
    app = create_app(dict(TEST_SETTINGS))
    client = TestClient(app)
    app.state.devrun_runs = {
        "run-7": {
            "run_id": "run-7",
            "project": "p-fx8",
            "task": "say hi",
            "started_at": "2026-02-11T06:40:00Z",
            "ended_at": "2026-02-11T06:42:44Z",
            "success": True,
            "stopped": False,
            "summary": "greeted the owner",
            "parts": [{"part_id": "part-1", "verdict": "accepted",
                       "attempts": 1, "reason": ""}],
            "files": ["hello.txt"],
            "ledger": [{"tokens": {"input": 4000, "output": 912},
                        "cost": "UNKNOWN"}],
            "cost": "UNKNOWN",
        },
    }
    resp = client.get("/api/v1/runs/ledger", params={"project_id": "p-fx8"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"] == []
    assert len(body["runs"]) == 1
    run = body["runs"][0]
    assert run["run_id"] == "run-7"
    assert run["success"] is True
    assert run["summary"] == "greeted the owner"
    assert run["tokens"] == 4912
    assert run["files"] == ["hello.txt"]
    assert run["verdicts"] == {"part-1": "accepted"}
