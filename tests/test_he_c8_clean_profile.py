"""HE-C8: clean-profile leftover roundtrip on the served path (RED-first).

Write a fake key to the REAL credential store, read it back through
the served leftover-keys route, delete it through the served
leftover-delete route, and prove it is gone. No seed bucket: this is
the clean-profile proof the Providers page legs need
(write/read/delete fake key).
"""
import os
import sys
import urllib.request as _urlreq

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest
from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402

TOKEN = "he-c8-clean-profile-token"
ACTOR = "he-c8-tester"
PREFIX = "agent_si/provider/"
NAME = "agent_si/provider/he-c8-fake"


def _headers():
    return {"x-actor": ACTOR, "x-ui-session-token": TOKEN}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")

    class _Resp:
        def read(self):
            return b'{"data": [{"id": "gpt-4o"}]}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        _urlreq, "urlopen",
        lambda request, timeout=None: _Resp())
    app = create_app({"store_dir": str(tmp_path / "appdata"),
                      "secret_store": "memory",
                      "testing": True, "ui_session_token": TOKEN})
    return TestClient(app, raise_server_exceptions=False)


def test_clean_profile_write_read_delete_fake_key(client):
    """Fake key: saved, listed by the route, deleted, gone."""
    saved = client.post(
        "/api/v1/providers/keys",
        json={"preset_id": "openai", "key_value": "FAKE-HEC8-0000"},
        headers=_headers())
    assert saved.status_code in (200, 201), saved.text

    listed = client.get("/api/v1/budget/providers/leftover-keys",
                        params={"app_prefix": PREFIX})
    assert listed.status_code == 200, listed.text
    names = [row["name"] for row in listed.json()["entries"]]
    assert any(name.startswith(PREFIX) for name in names), names

    target = next(name for name in names if name.startswith(PREFIX))
    removed = client.post(
        "/api/v1/budget/providers/leftover-delete",
        json={"app_prefix": PREFIX, "name": target,
              "confirmed": True, "session_token": TOKEN},
        headers=_headers())
    assert removed.status_code == 200, removed.text
    assert removed.json().get("removed") is True, removed.text

    again = client.get("/api/v1/budget/providers/leftover-keys",
                       params={"app_prefix": PREFIX})
    assert again.status_code == 200, again.text
    assert [row["name"] for row in again.json()["entries"]] == []
