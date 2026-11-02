"""BEDEF1: default budget state + step limits for created/loaded projects.

(a) create -> GET /api/v1/budget is 200 with the starting limits.
(b) budget change survives a rebuild on the same store_dir (not reset).
(c) a stored project without budget state gets the default at start.
(d) create -> chat/task step limits equal the defaults.
(e) rebuild on the same store_dir restores step limits after memory loss.
(f) a chat stream with missing limits ends with exactly one error event.
"""

import json
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
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from agent_si.providers.adapters.base import (  # noqa: E402
    AdapterConfig,
    make_secret_ref,
)
from agent_si.providers.adapters.mock_provider import (  # noqa: E402
    MockProviderAdapter,
)

TEST_TOKEN = "bedef1-token"
ACTOR = "tester-bedef1"

CANNED = ("Mock bedef1 reply.",)


def _auth(token=TEST_TOKEN, actor=ACTOR):
    headers = {}
    if actor is not None:
        headers["x-actor"] = actor
    if token is not None:
        headers["x-ui-session-token"] = token
    return headers


def _settings(store_dir=None):
    settings = {"testing": True, "ui_session_token": TEST_TOKEN}
    if store_dir is not None:
        settings["store_dir"] = str(store_dir)
    return settings


def _setup_function(_func=None):
    _steplimits._reset_state()


def setup_function(_func):
    _steplimits._reset_state()


def teardown_function(_func):
    _steplimits._reset_state()


def _create_project(client, name="harbor", folder="dock-7"):
    resp = client.post(
        "/api/v1/projects",
        json={"name": name, "folder_ref": folder},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["project"]


def _mock_adapter():
    config = AdapterConfig(
        provider_id="mock",
        instance_id="bedef1-test",
        model="mock-canned",
        secret_ref=make_secret_ref(
            secret_id="mock-secret", provider_id="mock"),
    )
    return MockProviderAdapter(config, transport=None, canned=CANNED)


def _parse_sse(text):
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


def test_a_create_configures_default_budget(tmp_path):
    _steplimits._reset_state()
    client = TestClient(create_app(_settings(tmp_path)))
    created = _create_project(client)
    pid = created["project_id"]
    resp = client.get("/api/v1/budget", params={"project_id": pid})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["project_id"] == pid
    budget = payload["budget"]
    assert budget["currency"] == "USD"
    assert budget["budget_limit"] == "5.00"
    assert budget["soft_limit"] == "4.00"
    assert budget["hard_limit"] == "5.00"


def test_b_budget_change_survives_rebuild(tmp_path):
    _steplimits._reset_state()
    app1 = create_app(_settings(tmp_path))
    client1 = TestClient(app1)
    created = _create_project(client1)
    pid = created["project_id"]
    app1.state.k04_ctx.budget_state.update_limits(pid, budget_limit="7.00")
    app2 = create_app(_settings(tmp_path))
    client2 = TestClient(app2)
    resp = client2.get("/api/v1/budget", params={"project_id": pid})
    assert resp.status_code == 200, resp.text
    assert resp.json()["budget"]["budget_limit"] == "7.00"


def test_c_stored_project_without_budget_gets_default_at_start(tmp_path):
    import shutil

    _steplimits._reset_state()
    app1 = create_app(_settings(tmp_path))
    client1 = TestClient(app1)
    created = _create_project(client1)
    pid = created["project_id"]
    budget_dir = os.path.join(str(tmp_path), "budget")
    shutil.rmtree(budget_dir, ignore_errors=True)
    _steplimits._reset_state()
    app2 = create_app(_settings(tmp_path))
    client2 = TestClient(app2)
    resp = client2.get("/api/v1/budget", params={"project_id": pid})
    assert resp.status_code == 200, resp.text
    assert resp.json()["budget"]["budget_limit"] == "5.00"


def test_d_create_configures_default_step_limits(tmp_path):
    _steplimits._reset_state()
    client = TestClient(create_app(_settings(tmp_path)))
    created = _create_project(client)
    pid = created["project_id"]
    assert _steplimits.limits_for("task", pid) == 40
    assert _steplimits.limits_for("chat", pid) == 15


def test_e_step_limits_restored_after_restart(tmp_path):
    _steplimits._reset_state()
    client1 = TestClient(create_app(_settings(tmp_path)))
    created = _create_project(client1)
    pid = created["project_id"]
    assert _steplimits.limits_for("chat", pid) == 15
    _steplimits._reset_state()
    create_app(_settings(tmp_path))
    assert _steplimits.limits_for("task", pid) == 40
    assert _steplimits.limits_for("chat", pid) == 15


def test_f_stream_without_limits_self_heals_then_fails_on_roles(tmp_path):
    # Folder-bound chats run the dev engine, which self-heals wiped step
    # limits to the project defaults and then fails honestly on the next
    # real problem (no provider bound for the director role): start plus
    # a terminal done naming it. The no-limits single-error contract
    # itself still holds on the manager path (livewire L0B-13).
    _steplimits._reset_state()
    app = create_app(_settings(tmp_path))
    app.state.chat_provider_adapter = _mock_adapter()
    client = TestClient(app)
    created = _create_project(client)
    pid = created["project_id"]
    _steplimits._reset_state()
    resp = client.post(
        "/api/v1/chat/stream",
        json={
            "project": pid,
            "task": "task-bed",
            "message": "hello bedef1",
            "profile": "profile:default",
            "pool": "pool:default",
        },
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    assert events, "expected SSE events, got none"
    assert events[0].get("type") == "start"
    assert _steplimits.limits_for("task", pid) == 40
    assert _steplimits.limits_for("chat", pid) == 15
    assert events[-1].get("type") == "done"
    assert "has no provider" in str(events[-1].get("text", ""))
