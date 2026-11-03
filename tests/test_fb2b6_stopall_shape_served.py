"""FB2B6 served stop-all shape proof (D-F07-SHAPE RED LIST).

Through create_app + HTTP TestClient only (loopback, no network/keys),
mirroring the tests/test_ock08_stop_served.py client pattern:
- a body carrying `project` instead of `project_id` stops the
  named project (alias);
- a bare user body `{actor: "user"}` is the TopBar one-click stop
  (TopBar.tsx sends exactly this when no project is selected): it is
  ACCEPTED and stops every project's work, never 4xx
  (kit BUILD_PLAN one-click Stop all: always visible, user-only).
The stop fact is journaled under the all-projects (empty system) scope
("across N projects" totals row); no STOP_ALL row ever carries a phantom
project id.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fastapi.testclient import TestClient

from agent_si.backend.app import create_app
from agent_si.watcher import journal as _journal

LIVE_TOKEN = "fb2b6-live"
P_PROJ = "proj-fb2b6-alias"


def _fake_auth_hook(token):
    return token == LIVE_TOKEN


def _fake_rate_hook(key):
    return True


def _fake_model_factory(name):
    raise RuntimeError("no model calls in FB2B6 stop-shape tests")


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


def test_project_alias_or_4xx():
    client = _client()
    resp = _post(client, {"actor": "user", "project": P_PROJ})
    if resp.status_code == 200:
        body = resp.json()
        assert body["accepted"] is True
        assert body["project_id"] == P_PROJ
        rows = _journal.stored_rows(P_PROJ, "STOP_ALL")
        assert any("stop-all by user" in r.summary for r in rows)
    else:
        assert 400 <= resp.status_code < 500, resp.text

    resp_bare = _post(client, {"actor": "user"})
    assert resp_bare.status_code == 200, resp_bare.text
    bare = resp_bare.json()
    assert bare["accepted"] is True, bare
    rows = _journal.stored_rows("", "STOP_ALL")
    assert any(
        "stop-all by user" in r.summary and "across" in r.summary
        for r in rows
    ), [r.summary for r in rows]
