"""OC-K08 served stop-all proof (R-323/R-326 RED LIST, VERDICT12).

Through create_app + HTTP TestClient only (loopback, no network/keys):
- R-323 user-only accept is journaled;
- R-323 expired Director grant is refused + journaled;
- R-326 hierarchy stop over the served entry stops >=2 attached children.
"""

import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fastapi.testclient import TestClient

from agent_si.backend.app import create_app
from agent_si.watcher import journal as _journal

LIVE_TOKEN = "ock08-live"
W_PROJ = "proj-ock08-stop"


def _fake_auth_hook(token):
    return token == LIVE_TOKEN


def _fake_rate_hook(key):
    return True


def _fake_model_factory(name):
    raise RuntimeError("no model calls in OC-K08 stop tests")


def _settings():
    return {
        "env": "test",
        "auth_hook": _fake_auth_hook,
        "rate_hook": _fake_rate_hook,
        "model_factory": _fake_model_factory,
    }


def _client():
    from agent_si.backend import stop_all as _stop_all

    _stop_all.reset_state()
    _journal.reset_state()
    return TestClient(create_app(_settings()))


def _post(client, body):
    return client.post(
        "/api/v1/stop-all",
        json=body,
        headers={"x-ui-session-token": LIVE_TOKEN},
    )


def _endless():
    return subprocess.Popen(
        [sys.executable, "-c", "import time\nwhile True: time.sleep(0.05)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_ock08_r323_user_accept_journaled():
    client = _client()
    resp = _post(client, {"actor": "user", "project_id": W_PROJ})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is True
    rows = _journal.stored_rows(W_PROJ, "STOP_ALL")
    assert any("stop-all by user" in r.summary for r in rows)


def test_ock08_r323_expired_grant_refused_journaled():
    from agent_si.backend import stop_all as _stop_all

    client = _client()
    expired = _stop_all.issue_grant("ock08-old", ttl_s=-1.0)
    resp = _post(
        client,
        {"actor": "director", "project_id": W_PROJ, "grant_ref": expired},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is False
    assert "expired" in body["reason"]
    rows = _journal.stored_rows(W_PROJ, "STOP_ALL")
    assert any("expired" in r.summary for r in rows)


def test_ock08_r326_hierarchy_stop_served():
    from agent_si.backend import stop_all as _stop_all

    client = _client()
    procs = [_endless(), _endless()]
    try:
        for p in procs:
            _stop_all.attach_child(W_PROJ, "run-ock08", p)
        assert len(_stop_all.attached(W_PROJ)) == 2
        resp = _post(client, {"actor": "user", "project_id": W_PROJ})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["accepted"] is True
        assert body["stopped_count"] >= 2
        assert all(p.poll() is not None for p in procs)
        assert _stop_all.attached(W_PROJ) == ()
        rows = _journal.stored_rows(W_PROJ, "STOP_ALL")
        assert any("stopped 2 of 2" in r.summary for r in rows)
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
                p.wait(timeout=10)
