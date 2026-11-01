"""FXLEFTOVER served rows: real leftover list/delete plus journal facts.

Live HTTP through create_app + TestClient on an isolated store dir
(secret store memory only): the budget leftover-keys GET plus
leftover-delete POST rows, and the watcher journal GET row carrying
the stored kind after a real stop-all. No fakes outside this file,
no mocks of product code, loopback TestClient only.
"""
import os
import sys

import pytest

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend import stop_all as _stop  # noqa: E402
from agent_si.watcher import journal as _journal  # noqa: E402

TOKEN = "fxleftover-served-token"
PREFIX = "agent_si/provider/"
OLD = "agent_si/provider/old"
OTHER = "agent_si/provider/other"


def _headers():
    return {"x-actor": "ui-fxleftover", "x-ui-session-token": TOKEN}


def _client(tmp_path):
    _journal.reset_state()
    _stop.reset_state()
    app = create_app(
        {"store_dir": str(tmp_path / "appdata"),
         "secret_store": "memory",
         "ui_session_token": TOKEN})
    return fastapi.testclient.TestClient(app)


def _seed(client, entries, live=()):
    resp = client.post(
        "/api/v1/budget/providers/leftover-seed",
        json={"app_prefix": PREFIX,
              "entries": entries, "live": list(live)},
        headers=_headers())
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_fxleftover_unlinked_listed_and_deleted_over_http(tmp_path, monkeypatch):
    """Row L1: an isolated-store unlinked key is listed then deleted
    over HTTP; names plus dates only, never the value."""
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    client = _client(tmp_path)
    _seed(client, [{"name": OLD, "last_used_at": "2026-01-01T00:00:00Z"},
                   {"name": OTHER, "last_used_at": "2026-02-02T00:00:00Z"}])
    listed = client.get("/api/v1/budget/providers/leftover-keys",
                        params={"app_prefix": PREFIX})
    assert listed.status_code == 200, listed.text
    assert listed.json() == {
        "entries": [{"name": OLD, "last_used_at": "2026-01-01T00:00:00Z"},
                    {"name": OTHER, "last_used_at": "2026-02-02T00:00:00Z"}]}, listed.text
    assert "value" not in listed.text
    removed = client.post(
        "/api/v1/budget/providers/leftover-delete",
        json={"app_prefix": PREFIX, "name": OLD,
              "confirmed": True, "session_token": TOKEN},
        headers=_headers())
    assert removed.status_code == 200, removed.text
    assert removed.json().get("removed") is True, removed.text
    again = client.get("/api/v1/budget/providers/leftover-keys",
                       params={"app_prefix": PREFIX})
    assert again.status_code == 200, again.text
    assert again.json() == {
        "entries": [{"name": OTHER,
                     "last_used_at": "2026-02-02T00:00:00Z"}]}, again.text


def test_fxleftover_linked_delete_refused_over_http(tmp_path, monkeypatch):
    """Row L1: deleting a live-provider-linked entry refuses with
    LIVE_LINKED and the entry stays listed."""
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    client = _client(tmp_path)
    _seed(client, [{"name": OLD, "last_used_at": "2026-01-01T00:00:00Z"}],
          live=[OLD])
    refused = client.post(
        "/api/v1/budget/providers/leftover-delete",
        json={"app_prefix": PREFIX, "name": OLD,
              "confirmed": True, "session_token": TOKEN},
        headers=_headers())
    assert refused.status_code == 409, refused.text
    assert refused.json().get("reason") == "LIVE_LINKED", refused.text
    listed = client.get("/api/v1/budget/providers/leftover-keys",
                        params={"app_prefix": PREFIX})
    assert listed.status_code == 200, listed.text
    assert [row["name"] for row in listed.json()["entries"]] == [OLD]


def test_fxleftover_stop_all_then_journal_carries_kind(tmp_path, monkeypatch):
    """Row L2: Stop all then GET journal carries kind STOP_ALL on the
    served row; receipt names entry_id, timestamp and hash stay."""
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    client = _client(tmp_path)
    project = "fxleftover-proj"
    stopped = client.post(
        "/api/v1/stop-all",
        json={"actor": "user", "project_id": project},
        headers=_headers())
    assert stopped.status_code == 200, stopped.text
    journal = client.get("/api/v1/watcher/journal",
                         params={"project_id": project})
    assert journal.status_code == 200, journal.text
    rows = journal.json()
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["entry_id"] == stopped.json()["journal_entry_id"], rows
    assert row["timestamp"], rows
    assert row["hash"], rows
    assert row["kind"] == "STOP_ALL", rows
    assert row["source"] == "backend", rows
    assert "stop-all by user" in row["summary"], rows
    assert project in row["refs"], rows
