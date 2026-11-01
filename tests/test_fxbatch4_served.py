"""FXBATCH4 served stop-all both branches (P19 RED->GREEN).

Through create_app + HTTP TestClient only (loopback, no network/keys),
mirroring the tests/test_ock08_stop_served.py client pattern:
- with project_id -> 200, only that project's runs stopped (others alive
  and still attached), same StopReceipt shape as the frozen route;
- without project_id (bare body) -> 200 with counts, every project's
  runs stopped;
- the token guard is unchanged (401 without token, 403 on a bad token);
- a Director call without a grant is refused with 400 on either branch.
"""

import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fastapi.testclient import TestClient  # noqa: E402

from agent_si.backend import stop_all as _stop_all  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.watcher import journal as _journal  # noqa: E402

LIVE_TOKEN = "fxbatch4-live"
PROJ_A = "proj-fxb4-a"
PROJ_B = "proj-fxb4-b"

RECEIPT_KEYS = {
    "project_id",
    "accepted",
    "reason",
    "stopped_count",
    "journal_entry_id",
    "stopped_at",
}


def _fake_auth_hook(token):
    return token == LIVE_TOKEN


def _fake_rate_hook(key):
    return True


def _fake_model_factory(name):
    raise RuntimeError("no model calls in FXBATCH4 stop tests")


def _settings():
    return {
        "env": "test",
        "auth_hook": _fake_auth_hook,
        "rate_hook": _fake_rate_hook,
        "model_factory": _fake_model_factory,
    }


def _client():
    _stop_all.reset_state()
    _journal.reset_state()
    return TestClient(create_app(_settings()))


def _post(client, body, token=LIVE_TOKEN):
    headers = {} if token is None else {"x-ui-session-token": token}
    return client.post("/api/v1/stop-all", json=body, headers=headers)


def _endless():
    return subprocess.Popen(
        [sys.executable, "-c", "import time\nwhile True: time.sleep(0.05)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _reap(procs):
    for proc in procs:
        try:
            if proc.poll() is None:
                proc.terminate()
        except Exception:
            pass
    for proc in procs:
        try:
            proc.wait(timeout=10)
        except Exception:
            pass


def test_fxbatch4_project_branch_stops_only_named_project():
    client = _client()
    procs_a = [_endless()]
    procs_b = [_endless(), _endless()]
    try:
        for proc in procs_a:
            _stop_all.attach_child(PROJ_A, "run-fxb4-a", proc)
        for proc in procs_b:
            _stop_all.attach_child(PROJ_B, "run-fxb4-b", proc)
        resp = _post(client, {"actor": "user", "project_id": PROJ_A})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body.keys()) == RECEIPT_KEYS, body
        assert body["accepted"] is True
        assert body["project_id"] == PROJ_A
        assert body["stopped_count"] == 1, body
        assert all(proc.poll() is not None for proc in procs_a)
        assert _stop_all.attached(PROJ_A) == ()
        assert all(proc.poll() is None for proc in procs_b)
        assert len(_stop_all.attached(PROJ_B)) == 2
        rows = _journal.stored_rows(PROJ_A, "STOP_ALL")
        assert any("stopped 1 of 1" in row.summary for row in rows)
        assert tuple(_journal.stored_rows(PROJ_B, "STOP_ALL")) == ()
    finally:
        _reap(procs_a + procs_b)


def test_fxbatch4_empty_branch_stops_every_project():
    client = _client()
    procs = [_endless(), _endless(), _endless()]
    try:
        _stop_all.attach_child(PROJ_A, "run-fxb4-a", procs[0])
        _stop_all.attach_child(PROJ_B, "run-fxb4-b1", procs[1])
        _stop_all.attach_child(PROJ_B, "run-fxb4-b2", procs[2])
        resp = _post(client, {"actor": "user"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body.keys()) == RECEIPT_KEYS, body
        assert body["accepted"] is True
        assert body["stopped_count"] == 3, body
        assert all(proc.poll() is not None for proc in procs)
        assert _stop_all.attached(PROJ_A) == ()
        assert _stop_all.attached(PROJ_B) == ()
        rows = _journal.stored_rows("", "STOP_ALL")
        assert any("across 2 projects" in row.summary for row in rows)
    finally:
        _reap(procs)


def test_fxbatch4_literal_empty_body_answers_200_without_stopping():
    client = _client()
    procs = [_endless()]
    try:
        _stop_all.attach_child(PROJ_A, "run-fxb4-a", procs[0])
        resp = _post(client, {})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body.keys()) == RECEIPT_KEYS, body
        assert body["accepted"] is False
        assert body["stopped_count"] == 0, body
        assert all(proc.poll() is None for proc in procs)
        assert len(_stop_all.attached(PROJ_A)) == 1
    finally:
        _reap(procs)


def test_fxbatch4_token_guard_kept():
    client = _client()
    try:
        resp = _post(client, {"actor": "user", "project_id": PROJ_A},
                     token=None)
        assert resp.status_code == 401, resp.text
        resp = _post(client, {"actor": "user"}, token=None)
        assert resp.status_code == 401, resp.text
        resp = _post(client, {"actor": "user", "project_id": PROJ_A},
                     token="wrong-token")
        assert resp.status_code == 403, resp.text
        resp = _post(client, {"actor": "user"}, token="wrong-token")
        assert resp.status_code == 403, resp.text
    finally:
        _reap([])


def test_fxbatch4_director_grant_missing_refused_on_both_branches():
    client = _client()
    try:
        resp = _post(client, {"actor": "director", "project_id": PROJ_A})
        assert resp.status_code == 400, resp.text
        resp = _post(client, {"actor": "director"})
        assert resp.status_code == 400, resp.text
    finally:
        _reap([])
