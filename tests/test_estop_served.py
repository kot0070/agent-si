"""FXESTOP served stop-all proof (FIXBATCH1 lane L4, RED->GREEN).

Through create_app + HTTP TestClient only (loopback, no network/keys):
an endless OS command started through the authed worker-tool route
shows pid/status, then POST /api/v1/stop-all reports stopped_count 1,
the pid is gone and one STOP_ALL journal row is written. The same file
also asserts the honest refusals: oversize/non-str run_id, a
non-allowlisted argv (nothing spawned, nothing attached) and unauthed
calls (401/403, same guard as dispatch).
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fastapi.testclient import TestClient  # noqa: E402

from agent_si.backend import stop_all as _stop_all  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.watcher import journal as _journal  # noqa: E402

try:
    from agent_si.worker_tools import command_runner as _runner
except ImportError:
    _runner = None

LIVE_TOKEN = "estop-live"
ACTOR = "user"
W_PROJ = "proj-estop"
RUN_ID = "run-estop-live"


def _strict_hook(token, actor, action):
    return token == LIVE_TOKEN


def _client():
    _stop_all.reset_state()
    _journal.reset_state()
    if _runner is not None:
        _runner.reset_state()
    return TestClient(
        create_app({"testing": True, "ui_session_token": LIVE_TOKEN},
                   auth_hook=_strict_hook)
    )


def _headers(token=LIVE_TOKEN):
    return {"x-actor": ACTOR, "x-ui-session-token": token}


def _argv():
    return [sys.executable, "-c", "while True: pass"]


def _start(client, project_id=W_PROJ, run_id=RUN_ID, argv=None,
           headers=None):
    if argv is None:
        argv = _argv()
    if headers is None:
        headers = _headers()
    return client.post(
        "/api/v1/tools/tools/command/start",
        json={"project_id": project_id, "run_id": run_id, "argv": argv},
        headers=headers,
    )


def _status(client, run_id=RUN_ID, headers=None):
    if headers is None:
        headers = _headers()
    return client.get(
        "/api/v1/tools/tools/command/status",
        params={"run_id": run_id},
        headers=headers,
    )


def _stop(client):
    return client.post(
        "/api/v1/stop-all",
        json={"actor": "user", "project_id": W_PROJ},
        headers={"x-ui-session-token": LIVE_TOKEN},
    )


def test_estop_kills_live_command():
    client = _client()
    try:
        start = _start(client)
        assert start.status_code == 200, start.text
        body = start.json()
        assert body["run_id"] == RUN_ID
        pid = body["pid"]
        assert isinstance(pid, int) and pid > 0

        seen = _status(client)
        assert seen.status_code == 200, seen.text
        assert seen.json() == {"run_id": RUN_ID, "pid": pid,
                               "alive": True}

        dup = _start(client)
        assert dup.status_code != 200, dup.text

        resp = _stop(client)
        assert resp.status_code == 200, resp.text
        receipt = resp.json()
        assert receipt["stopped_count"] == 1, receipt

        gone = _status(client)
        assert gone.status_code == 200, gone.text
        assert gone.json() == {"run_id": RUN_ID, "pid": pid,
                               "alive": False}
        assert _stop_all.attached(W_PROJ) == ()
        rows = _journal.stored_rows(W_PROJ, "STOP_ALL")
        assert any("stopped 1 of 1" in r.summary for r in rows)
    finally:
        if _runner is not None:
            _runner.reset_state()


def test_estop_rejects_bad_start_requests():
    client = _client()
    try:
        oversize = _start(client, run_id="x" * 129)
        assert oversize.status_code != 200, oversize.text
        assert _stop_all.attached(W_PROJ) == ()
        assert _status(client, run_id="x" * 129).status_code != 200

        non_str = _start(client, run_id=123)
        assert non_str.status_code != 200, non_str.text
        assert _stop_all.attached(W_PROJ) == ()

        denied = _start(client, run_id="run-estop-denied",
                        argv=["curl", "https://example.com"])
        assert denied.status_code != 200, denied.text
        assert _stop_all.attached(W_PROJ) == ()
        assert _status(client, run_id="run-estop-denied").status_code == 404

        no_auth = _start(client, run_id="run-estop-noauth", headers={})
        assert no_auth.status_code in (401, 403), no_auth.text

        bad_token = _start(client, run_id="run-estop-badtoken",
                           headers={"x-actor": ACTOR,
                                    "x-ui-session-token": "wrong-token"})
        assert bad_token.status_code in (401, 403), bad_token.text
        assert _stop_all.attached(W_PROJ) == ()

        no_auth_status = _status(client, headers={})
        assert no_auth_status.status_code in (401, 403), \
            no_auth_status.text
    finally:
        if _runner is not None:
            _runner.reset_state()
