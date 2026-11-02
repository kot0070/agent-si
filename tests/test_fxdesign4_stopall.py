"""FXDESIGN4 T4: stop-all served proof for the button path.

POST /api/v1/stop-all with actor "user" stops the attached children
first and only then cancels the live stream bridge, journaling one
STOP_ALL row "by user". A refused actor stops nothing, cancels nothing,
and journals the refusal.
"""

import os
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from fastapi.testclient import TestClient  # noqa: E402

from agent_si.backend import stop_all as _stop_all  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.watcher import journal as _journal  # noqa: E402

TEST_TOKEN = "fxdesign4-stopall-token"
TEST_SETTINGS = {"testing": True, "ui_session_token": TEST_TOKEN}


class _ReapedProc:
    """An already-reaped child: counts stopped without any signal."""

    def poll(self):
        return 0

    def terminate(self):
        raise AssertionError("a reaped child needs no terminate")

    def wait(self, timeout=None):
        return 0


class _Bridge:
    """Test-only live-stream bridge: records cancel calls."""

    def __init__(self):
        self.project_calls = []
        self.all_calls = 0

    def cancel_project(self, project_id):
        self.project_calls.append(project_id)

    def cancel_all(self):
        self.all_calls += 1


def setup_function(_func):
    _stop_all.reset_state()
    _journal.reset_state()


def teardown_function(_func):
    _stop_all.reset_state()
    _journal.reset_state()


def make_client():
    app = create_app(dict(TEST_SETTINGS))
    bridge = _Bridge()
    app.state.chat_stream_bridge = bridge
    return TestClient(app), bridge


def test_button_path_stops_children_then_cancels_stream_by_user():
    client, bridge = make_client()
    _stop_all.attach_child("p-stop", "run-1", _ReapedProc())
    resp = client.post(
        "/api/v1/stop-all",
        json={"project_id": "p-stop", "actor": "user"},
        headers={"x-ui-session-token": TEST_TOKEN},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is True
    assert body["stopped_count"] == 1
    assert bridge.project_calls == ["p-stop"]
    assert _stop_all.attached("p-stop") == ()
    rows = _journal.stored_rows("p-stop", "STOP_ALL")
    assert rows, "an accepted stop journals one STOP_ALL row"
    assert "by user" in rows[-1].summary


def test_refused_actor_stops_nothing_and_cancels_nothing():
    client, bridge = make_client()
    _stop_all.attach_child("p-ref", "run-9", _ReapedProc())
    resp = client.post(
        "/api/v1/stop-all",
        json={"project_id": "p-ref", "actor": ""},
        headers={"x-ui-session-token": TEST_TOKEN},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is False
    assert "actor refused" in body["reason"]
    assert _stop_all.attached("p-ref") == ("run-9",)
    assert bridge.project_calls == []
    assert bridge.all_calls == 0
    rows = _journal.stored_rows("p-ref", "STOP_ALL")
    assert rows, "a refused stop journals the refusal"
    assert "refused" in rows[-1].summary
