"""FXR1B served proof: per-project installer grants.

Drives the real seam app (create_app + TestClient,
raise_server_exceptions=False) over a real tmp store dir. No provider,
no network, no keys. RED: the project-grant routes do not exist yet.

  POST /api/v1/permissions/project-grant {project_id, tool_id}
    records installer+subcommand from the pinned ask argv next to the
    decision ledger, and records allow so the parked run replays.
  GET  /api/v1/permissions/install-request?tool_id= returns the pinned
    argv for the dialog display.
  GET  /api/v1/permissions/project-grants?project_id= lists grants.
  DELETE /api/v1/permissions/project-grant removes one grant.
  spawn_checked: a grant lets later installs by the same installer head
    through without asking; widening flags, other projects and unknown
    installers still ask; grants survive a rebuild (restart).
"""

import os
import sys

from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.runtime.devrun import actions as _actions  # noqa: E402
from agent_si.runtime.devrun.actions import InstallAskNeeded  # noqa: E402
from agent_si.toolguard import permissions as _permissions  # noqa: E402

TEST_TOKEN = "fxr1b-served-token"
PROJECT = "p-grant"
OTHER_PROJECT = "p-other"
TOOL = "install:%s:npm" % PROJECT


def _auth(token=TEST_TOKEN):
    return {"x-ui-session-token": token}


def _settings(store_dir):
    return {"testing": True, "ui_session_token": TEST_TOKEN,
            "store_dir": str(store_dir)}


def _served_client(store_dir):
    app = create_app(_settings(store_dir))
    return TestClient(app, raise_server_exceptions=False)


def _pin_request(tool_id=TOOL, argv=None, project_id=PROJECT):
    argv = ["npm", "install", "lodash"] if argv is None else argv
    return _permissions.record_install_request(
        tool_id=tool_id, argv=argv, project_id=project_id)


def _grant(client, tool_id=TOOL, project_id=PROJECT):
    _pin_request(tool_id=tool_id, project_id=project_id)
    return client.post(
        "/api/v1/permissions/project-grant",
        json={"project_id": project_id, "tool_id": tool_id},
        headers=_auth(),
    )


def test_project_grant_route_records_installer_and_subcommand(tmp_path):
    client = _served_client(tmp_path)
    resp = _grant(client)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == PROJECT, body
    assert body["installer"] == "npm", body
    assert body["subcommand"] == "install", body


def test_install_request_returns_pinned_argv(tmp_path):
    client = _served_client(tmp_path)
    _pin_request()
    got = client.get(
        "/api/v1/permissions/install-request",
        params={"tool_id": TOOL}, headers=_auth())
    assert got.status_code == 200, got.text
    assert got.json()["argv"] == ["npm", "install", "lodash"], got.text


def test_install_request_unknown_tool_id_is_404(tmp_path):
    client = _served_client(tmp_path)
    got = client.get(
        "/api/v1/permissions/install-request",
        params={"tool_id": "install:p-x:nope"}, headers=_auth())
    assert got.status_code == 404, got.text


def test_grant_lets_later_same_head_installs_through(monkeypatch, tmp_path):
    client = _served_client(tmp_path)
    assert _grant(client).status_code == 200
    seen = []

    def _fake_dispatch(words, *_args, **_kwargs):
        seen.append(list(words))
        return {"ok": True}

    monkeypatch.setattr(
        "agent_si.worker_tools.dispatcher.guarded_dispatch",
        _fake_dispatch)
    row = _actions.spawn_checked(
        PROJECT, "run-1", str(tmp_path), ["npm", "install", "other"],
        str(tmp_path / "l1.log"), "l1.log")
    assert row["argv"][0] == "npm", row
    assert [list(call) for call in seen] == [["npm", "install", "other"]]
    # A widening flag still asks.
    try:
        _actions.spawn_checked(
            PROJECT, "run-2", str(tmp_path),
            ["npm", "install", "other", "--force"],
            str(tmp_path / "l2.log"), "l2.log")
    except InstallAskNeeded:
        pass
    else:
        raise AssertionError("--force must ask again")
    # A global flag still asks.
    try:
        _actions.spawn_checked(
            PROJECT, "run-3", str(tmp_path),
            ["npm", "install", "-g", "other"],
            str(tmp_path / "l3.log"), "l3.log")
    except InstallAskNeeded:
        pass
    else:
        raise AssertionError("-g must ask again")


def test_grant_is_project_scoped_and_other_installers_ask(tmp_path):
    client = _served_client(tmp_path)
    assert _grant(client).status_code == 200
    # Another project has no grant: asks.
    try:
        _actions.spawn_checked(
            OTHER_PROJECT, "run-9", str(tmp_path),
            ["npm", "install", "other"],
            str(tmp_path / "l9.log"), "l9.log")
    except InstallAskNeeded:
        pass
    else:
        raise AssertionError("another project must ask again")
    # Another installer head asks too.
    _permissions.record_install_request(
        tool_id="install:%s:pip" % PROJECT,
        argv=["pip", "install", "req"], project_id=PROJECT)
    try:
        _actions.spawn_checked(
            PROJECT, "run-8", str(tmp_path),
            ["pip", "install", "req"],
            str(tmp_path / "l8.log"), "l8.log")
    except InstallAskNeeded:
        pass
    else:
        raise AssertionError("another installer head must ask again")


def test_grant_survives_rebuild_and_remove_revokes(tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    first = _served_client(store)
    assert _grant(first).status_code == 200
    listed = first.get(
        "/api/v1/permissions/project-grants",
        params={"project_id": PROJECT})
    assert listed.status_code == 200, listed.text
    rows = listed.json()["grants"]
    assert len(rows) == 1, rows
    assert rows[0]["project_id"] == PROJECT, rows
    assert rows[0]["installer"] == "npm", rows
    assert rows[0]["subcommand"] == "install", rows
    assert rows[0]["time"], rows
    # Restart: a rebuilt app over the same store dir keeps the grant.
    second = _served_client(store)
    assert _permissions.install_grant_allows(
        PROJECT, ["npm", "install", "fresh"]) is True
    removed = second.request(
        "DELETE", "/api/v1/permissions/project-grant",
        json={"project_id": PROJECT, "installer": "npm",
              "subcommand": "install"},
        headers=_auth())
    assert removed.status_code == 200, removed.text
    assert removed.json() == {"removed": True}, removed.text
    assert _permissions.install_grant_allows(
        PROJECT, ["npm", "install", "fresh"]) is False
    # After removal the spawn asks again.
    try:
        _actions.spawn_checked(
            PROJECT, "run-7", str(store),
            ["npm", "install", "fresh"],
            str(store / "l7.log"), "l7.log")
    except InstallAskNeeded:
        pass
    else:
        raise AssertionError("removed grant must ask again")


def test_grant_needs_pinned_ask_argv(tmp_path):
    client = _served_client(tmp_path)
    resp = client.post(
        "/api/v1/permissions/project-grant",
        json={"project_id": PROJECT, "tool_id": TOOL},
        headers=_auth())
    assert resp.status_code == 409, resp.text


def test_grant_rejects_foreign_tool_id(tmp_path):
    client = _served_client(tmp_path)
    _pin_request(tool_id="install:p-evil:npm", project_id="p-evil")
    resp = client.post(
        "/api/v1/permissions/project-grant",
        json={"project_id": PROJECT, "tool_id": "install:p-evil:npm"},
        headers=_auth())
    assert resp.status_code == 400, resp.text
