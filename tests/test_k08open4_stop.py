"""K08OPEN4 stop-all served behaviour tests (testid k08open4-stop).

Lane MGR-A CODER-A, rows R-323 plus R-326. Every test drives the served
POST /api/v1/stop-all entry via create_app plus an HTTP client only: no
doubles, no monkeypatching, no skip/xfail, loopback TEST data only. The
app is built with default settings and the test reads the served session
token from app.state, so no hook doubles enter the app mount. The final
alerts test consumes MANAGER-2's GET /api/v1/watcher/alerts endpoint
read-only; until that route lands it stays RED-EXPECTED-PENDING-M2.
"""

import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend import stop_all  # noqa: E402
from agent_si.watcher import journal  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def served():
    """Fresh served app plus HTTP client on reset real lane state."""
    journal.reset_state()
    stop_all.reset_state()
    app = create_app()
    token = app.state.ui_session_token
    assert isinstance(token, str) and token
    yield TestClient(app), token
    journal.reset_state()
    stop_all.reset_state()


def _spawn_sleeper():
    """One real endless child process for stop tests (portable)."""
    return subprocess.Popen(
        [sys.executable, "-c", "import time\nwhile True: time.sleep(0.05)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _reap(proc):
    """Stop one test child if it is still running."""
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()
                proc.wait(timeout=10)
    except Exception:
        pass


def _post_stop(client, token, body):
    """POST /api/v1/stop-all with the live served session token."""
    return client.post(
        "/api/v1/stop-all", json=body,
        headers={"x-ui-session-token": token})


def test_user_stop_all_accepted_and_journaled(served):
    """R-323: one-click stop-all by actor=user is accepted and journaled."""
    client, token = served
    proj = "proj-k08open4-user"
    proc = _spawn_sleeper()
    try:
        stop_all.attach_child(proj, "run-k08open4-user-1", proc)
        before = len(journal.stored_rows(proj, "STOP_ALL"))
        resp = _post_stop(client, token, {"actor": "user", "project_id": proj})
        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] is True
        assert body["stopped_count"] >= 1
        assert body["journal_entry_id"] != ""
        assert proc.poll() is not None
        assert stop_all.attached(proj) == ()
        after = journal.stored_rows(proj, "STOP_ALL")
        assert len(after) - before == 1
        assert any("stop-all by user" in row.summary for row in after)
    finally:
        _reap(proc)


def test_director_stop_without_grant_refused(served):
    """R-323: actor=director with no live grant is refused, nothing stops."""
    client, token = served
    proj = "proj-k08open4-director"
    proc = _spawn_sleeper()
    try:
        stop_all.attach_child(proj, "run-k08open4-dir-1", proc)
        before = len(journal.stored_rows(proj, "STOP_ALL"))
        resp = _post_stop(
            client, token, {"actor": "director", "project_id": proj})
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "STOP_REASON_MISSING"
        assert proc.poll() is None
        assert stop_all.attached(proj) != ()
        after = journal.stored_rows(proj, "STOP_ALL")
        assert len(after) - before == 1
    finally:
        _reap(proc)


def test_hierarchy_stop_all_stops_everything(served):
    """R-326: one user stop-all stops a whole project hierarchy."""
    client, token = served
    proj = "proj-k08open4-hierarchy"
    parent = _spawn_sleeper()
    child = _spawn_sleeper()
    try:
        stop_all.attach_child(proj, "run-k08open4-parent", parent)
        stop_all.attach_child(proj, "run-k08open4-child", child)
        assert len(stop_all.attached(proj)) == 2
        resp = _post_stop(client, token, {"actor": "user", "project_id": proj})
        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] is True
        assert body["stopped_count"] >= 2
        assert parent.poll() is not None
        assert child.poll() is not None
        assert stop_all.attached(proj) == ()
    finally:
        _reap(parent)
        _reap(child)


def test_watcher_alerts_consumed_read_only(served):
    """Alerts consumption: GET /api/v1/watcher/alerts is 200 read-only."""
    client, token = served
    proj = "proj-k08open4-alerts"
    proc = _spawn_sleeper()
    try:
        stop_all.attach_child(proj, "run-k08open4-alert-1", proc)
        before = len(journal.stored_rows(proj))
        resp = client.get(
            "/api/v1/watcher/alerts", params={"project_id": proj},
            headers={"x-ui-session-token": token})
        assert resp.status_code == 200
        payload = resp.json()
        assert isinstance(payload, (dict, list))
        assert proc.poll() is None
        assert stop_all.attached(proj) != ()
        assert len(journal.stored_rows(proj)) == before
    finally:
        _reap(proc)
