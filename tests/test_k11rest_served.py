"""K11REST served rows (CODER-1 Quay).

testid k11rest-served. One behaviour test per row, each through the
served K11REST entry (create_app + HTTP client):

- R-329: GET /api/k11rest/health -> display-only provider cards.
- R-330: POST /api/k11rest/retry-sim -> visible same-model retry ledger.
- R-331: GET /api/k11rest/prompt-factory/selftest -> offline selftest.
- R-352: POST /api/k11rest/launch -> parallel fan-out with gates.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402

TESTID = "k11rest-served"
TEST_SETTINGS = {"testing": True, "ui_session_token": "k11rest-served-token"}


@pytest.fixture
def client():
    """Fresh served app per test."""
    yield TestClient(create_app(dict(TEST_SETTINGS)))


def test_k11rest_r329_health_served(client):
    """R-329: health cards served display-only through the served entry."""
    assert TESTID == "k11rest-served"
    resp = client.get("/api/k11rest/health")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    cards = body["cards"]
    assert isinstance(cards, list) and cards
    for card in cards:
        assert set(card) == {"provider", "preset", "model", "fresh_ts",
                             "stale_warn"}
        assert isinstance(card["provider"], str) and card["provider"]
        assert isinstance(card["preset"], str) and card["preset"]
        assert isinstance(card["model"], str)
        assert isinstance(card["fresh_ts"], (int, float))
        assert isinstance(card["stale_warn"], bool)
    by_preset = {card["preset"]: card for card in cards}
    assert "meta" in by_preset
    assert by_preset["meta"]["provider"] == "meta"
    assert (by_preset["meta"]["model"]
            == "meta/muse-spark-1.3-contributor")


def test_k11rest_r330_retry_sim_served(client):
    """R-330: retry ledger served for each of 429/503/529."""
    assert TESTID == "k11rest-served"
    from agent_si.routing import k11rest_retry as _retry

    for code in (429, 503, 529):
        resp = client.post("/api/k11rest/retry-sim", json={"code": code})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body) == {"attempts", "final_model", "provider_same",
                             "role_default_off"}
        attempts = body["attempts"]
        assert isinstance(attempts, list) and attempts
        first = attempts[0]
        assert set(first) == {"model", "visible", "after"}
        assert first["visible"] is True
        assert first["after"] == _retry.RETRY_AFTER[code]
        assert first["after"] > 0
        assert body["final_model"] == attempts[-1]["model"]
        assert body["provider_same"] is True
        assert body["role_default_off"] is True
    refused = client.post("/api/k11rest/retry-sim", json={"code": 418})
    assert refused.status_code == 400, refused.text


def test_k11rest_r331_prompt_factory_selftest_served(client):
    """R-331: offline prompt-factory selftest served; client is injected."""
    assert TESTID == "k11rest-served"
    resp = client.get("/api/k11rest/prompt-factory/selftest")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "offline": True}

    from agent_si.prompt_factory import selftest as _selftest

    seen = []

    class RecordingClient:
        def render(self, text):
            seen.append(text)
            return "rendered:%s" % text

    result = _selftest.run_selftest(RecordingClient())
    assert result == {"ok": True, "offline": True}
    assert len(seen) == 1 and seen[0]


def test_k11rest_r352_launch_served(client):
    """R-352: launch fans parts out in parallel behind gates."""
    assert TESTID == "k11rest-served"
    parts = [{"action": "service.check", "with": {"service_id": "svc-api"}},
             {"action": "service.watch", "with": {}},
             {"action": "journal.notify", "with": {"kind": "AUTOMATION_RUN"}}]
    resp = client.post("/api/k11rest/launch", json={"parts": parts})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"fanout", "gates", "run_id", "resume_token"}
    assert body["fanout"] == 3
    assert isinstance(body["gates"], list) and len(body["gates"]) == 3
    assert all(entry["allowed"] is True for entry in body["gates"])
    assert isinstance(body["run_id"], str) and body["run_id"]
    assert isinstance(body["resume_token"], str) and body["resume_token"]

    from agent_si.automation import templates as _templates

    resumed = _templates.resume_launch(body["resume_token"])
    assert resumed["run_id"] == body["run_id"]
    assert resumed["fanout"] == 3
    assert resumed["state"] == "RUNNING"

    refused = client.post("/api/k11rest/launch", json={"parts": []})
    assert refused.status_code == 400, refused.text
