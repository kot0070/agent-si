"""K10PH2D served map: one proving test per open row.

Rows (all OPEN per lane task):
129 setup instructions plus demo and fixture command index (README).
131 prerequisites plus setup plus demo, fixture and task commands (README).
153 startup idempotence note (repeat start is a no-op).
249 restart note (restart from a clean state repeats working startup).
HC-4 LICENSE MIT plus copyright plus third-party notices.
LIVE0-01 frontend installs offline from cached tarballs only.
LIVE0-04 product start path supplies the data dir from the env read.
Each row is listed by agent_si.k10_start.served_rows_ph2d() and proven here
through its serving route mounted on the real create_app app with real
state (temp data dir, memory secret store). Loopback TEST data only; no
network, no installs, no mocks in product code.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import fastapi.testclient  # noqa: E402

from agent_si import k10_accept  # noqa: E402
from agent_si import k10_start  # noqa: E402
from agent_si.backend.app import (  # noqa: E402
    create_app,
    get_data_dir,
)

TAG = "tests/test_k10ph2d_served.py"


def _served():
    return {row["row"]: row for row in k10_start.served_rows_ph2d()}


def _client_on_temp_dir(tmp_path, monkeypatch, token):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(data_dir))
    app = create_app(
        {"ui_session_token": token, "secret_store": "memory", "testing": True}
    )
    k10_start.register_k10ph2d_routes(app)
    return fastapi.testclient.TestClient(app), app, data_dir


def _check_entry(row_id, route, test_name):
    entry = _served()[row_id]
    assert entry["route"] == route, entry
    assert entry["test"] == TAG + "::" + test_name, entry
    return entry


def _get_route(client, route):
    path = route.split(" ", 1)[1]
    resp = client.get(path)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == "k10ph2d-served", body
    return body


def test_k10ph2d_129_setup_demo_fixture_index(tmp_path, monkeypatch):
    """Row B0B-UNCOVERED_MVP_ACCEPT-129 served through GET /api/v1/release/ph2d/setup-index."""
    _check_entry(
        "B0B-UNCOVERED_MVP_ACCEPT-129",
        "GET /api/v1/release/ph2d/setup-index",
        "test_k10ph2d_129_setup_demo_fixture_index",
    )
    client, _app, _data_dir = _client_on_temp_dir(
        tmp_path, monkeypatch, "k10ph2d-129")
    body = _get_route(client, "GET /api/v1/release/ph2d/setup-index")
    assert body["row"] == "B0B-UNCOVERED_MVP_ACCEPT-129", body
    assert body["records"] == k10_start.setup_demo_fixture_index(), body
    sections = [row["section"] for row in body["records"]]
    assert sections == [
        "setup-instructions",
        "demo-command-index",
        "fixture-command-index",
        "install-content-guard",
    ], body
    for row in body["records"]:
        for key in ("section", "claim", "source", "snippet"):
            assert row.get(key), row
        assert "recorded" in row["source"], row
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "## Prerequisites" in readme, readme
    assert "## Setup" in readme, readme
    assert "## Demo and fixture command index" in readme, readme
    assert readme.index("## Prerequisites") < readme.index("## Setup"), readme
    for row in body["records"]:
        if row["section"] == "install-content-guard":
            continue
        assert row["command"] in readme, (row, readme)


def test_k10ph2d_131_prerequisites_setup_demo(tmp_path, monkeypatch):
    """Row B0B-UNCOVERED_MVP_ACCEPT-131 served through GET /api/v1/release/ph2d/prerequisites."""
    _check_entry(
        "B0B-UNCOVERED_MVP_ACCEPT-131",
        "GET /api/v1/release/ph2d/prerequisites",
        "test_k10ph2d_131_prerequisites_setup_demo",
    )
    client, _app, _data_dir = _client_on_temp_dir(
        tmp_path, monkeypatch, "k10ph2d-131")
    body = _get_route(client, "GET /api/v1/release/ph2d/prerequisites")
    assert body["row"] == "B0B-UNCOVERED_MVP_ACCEPT-131", body
    assert body["records"] == k10_start.checkout_prerequisites_record(), body
    assert [row["topic"] for row in body["records"]] == [
        "prerequisites",
        "setup-steps",
        "demo-commands",
        "fixture-commands",
        "task-commands",
    ], body
    for row in body["records"]:
        for key in ("topic", "claim", "source", "snippet"):
            assert row.get(key), row
        assert "recorded" in row["source"], row
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "## Prerequisites" in readme, readme
    assert "prerequisites, setup steps, demo commands" in readme, readme


def test_k10ph2d_153_startup_idempotence(tmp_path, monkeypatch):
    """Row B0B-UNCOVERED_MVP_ACCEPT-153 served through GET /api/v1/release/ph2d/startup-note."""
    _check_entry(
        "B0B-UNCOVERED_MVP_ACCEPT-153",
        "GET /api/v1/release/ph2d/startup-note",
        "test_k10ph2d_153_startup_idempotence",
    )
    client, _app, _data_dir = _client_on_temp_dir(
        tmp_path, monkeypatch, "k10ph2d-153")
    body = _get_route(client, "GET /api/v1/release/ph2d/startup-note")
    assert body["row"] == "B0B-UNCOVERED_MVP_ACCEPT-153", body
    assert body["records"] == k10_start.startup_idempotence_note(), body
    assert body["records"]["note"] == "startup-idempotence", body
    assert "idempotent" in body["records"]["claim"], body
    note_path = ROOT / "docs" / "start-accept-notes.md"
    notes = note_path.read_text(encoding="utf-8")
    assert "idempotent" in notes, notes
    assert body["records"]["claim"] in notes, (body, notes)
    home = tmp_path / "legacy153"
    legacy = home / ".agent_si"
    legacy.mkdir(parents=True)
    (legacy / "settings.json").write_text('{"theme": "dark"}', encoding="utf-8")
    (legacy / "keys.json").write_text('{"loopback": "t"}', encoding="utf-8")
    data_dir = tmp_path / "data153"
    first = k10_start.migrate_first_start(str(data_dir), str(legacy))
    assert first == {"settings.json": "copied", "keys.json": "copied"}, first
    second = k10_start.migrate_first_start(str(data_dir), str(legacy))
    assert second == {
        "settings.json": "skipped-present",
        "keys.json": "skipped-present",
    }, second


def test_k10ph2d_249_restart_note(tmp_path, monkeypatch):
    """Row B0B-UNCOVERED_MVP_ACCEPT-249 served through GET /api/v1/release/ph2d/restart-note."""
    _check_entry(
        "B0B-UNCOVERED_MVP_ACCEPT-249",
        "GET /api/v1/release/ph2d/restart-note",
        "test_k10ph2d_249_restart_note",
    )
    client, _app, _data_dir = _client_on_temp_dir(
        tmp_path, monkeypatch, "k10ph2d-249")
    body = _get_route(client, "GET /api/v1/release/ph2d/restart-note")
    assert body["row"] == "B0B-UNCOVERED_MVP_ACCEPT-249", body
    assert body["records"] == k10_start.restart_note(), body
    assert body["records"]["note"] == "restart", body
    assert "restart" in body["records"]["claim"].lower(), body
    note_path = ROOT / "docs" / "start-accept-notes.md"
    notes = note_path.read_text(encoding="utf-8")
    assert body["records"]["claim"] in notes, (body, notes)
    first = k10_start.drive_demo_to_green(None)
    second = k10_start.drive_demo_to_green(None)
    assert first == second, (first, second)
    assert first["status"] == "green", first


def test_k10ph2d_HC_4_license_notices(tmp_path, monkeypatch):
    """Row HC-4 served through GET /api/v1/release/ph2d/license."""
    _check_entry(
        "HC-4",
        "GET /api/v1/release/ph2d/license",
        "test_k10ph2d_HC_4_license_notices",
    )
    client, _app, _data_dir = _client_on_temp_dir(
        tmp_path, monkeypatch, "k10ph2d-hc4")
    body = _get_route(client, "GET /api/v1/release/ph2d/license")
    assert body["row"] == "HC-4", body
    assert body["records"] == k10_accept.license_notice_record(), body
    assert body["records"]["license"] == "MIT", body
    assert body["records"]["third_party"], body
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in license_text, license_text
    assert "Copyright" in license_text, license_text
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "## License and third-party notices" in readme, readme
    assert "MIT" in readme, readme
    for item in body["records"]["third_party"]:
        assert item["name"] in readme, (item, readme)
        assert item["version"] in readme, (item, readme)


def test_k10ph2d_LIVE0_01_cached_tarballs(tmp_path, monkeypatch):
    """Row LIVE0-01 served through GET /api/v1/release/ph2d/frontend-offline."""
    _check_entry(
        "LIVE0-01",
        "GET /api/v1/release/ph2d/frontend-offline",
        "test_k10ph2d_LIVE0_01_cached_tarballs",
    )
    client, _app, _data_dir = _client_on_temp_dir(
        tmp_path, monkeypatch, "k10ph2d-live001")
    body = _get_route(client, "GET /api/v1/release/ph2d/frontend-offline")
    assert body["row"] == "LIVE0-01", body
    assert body["records"] == k10_accept.frontend_offline_record(), body
    assert body["records"]["procedure"] == (
        "offline-install-from-cached-tarballs"
    ), body
    import json

    package = json.loads(
        (ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert package["devDependencies"]["@types/react"] == "19.3.0", package
    assert package["devDependencies"]["@types/react-dom"] == "19.3.0", package
    lock = (ROOT / "frontend" / "package-lock.json").read_text(
        encoding="utf-8")
    assert "node_modules/@types/react\"" in lock, lock
    assert "node_modules/@types/react-dom\"" in lock, lock
    note_path = ROOT / "docs" / "start-accept-notes.md"
    notes = note_path.read_text(encoding="utf-8")
    assert "cached tarballs" in notes, notes


def test_k10ph2d_LIVE0_04_data_dir_start(tmp_path, monkeypatch):
    """Row LIVE0-04 served through GET /api/v1/release/ph2d/data-dir."""
    _check_entry(
        "LIVE0-04",
        "GET /api/v1/release/ph2d/data-dir",
        "test_k10ph2d_LIVE0_04_data_dir_start",
    )
    client, _app, data_dir = _client_on_temp_dir(
        tmp_path, monkeypatch, "k10ph2d-live004")
    body = _get_route(client, "GET /api/v1/release/ph2d/data-dir")
    assert body["row"] == "LIVE0-04", body
    assert body["records"] == k10_start.data_dir_start_path_note(), body
    assert body["records"]["env_var"] == "AGENT_SI_DATA_DIR", body
    expected = os.path.abspath(str(data_dir))
    assert _app.state.data_dir == expected, _app.state.data_dir
    resp = client.get("/api/v1/release/start/migrate")
    assert resp.status_code == 200, resp.text
    assert resp.json()["testid"] == "k10open4-start", resp.text
    note_path = ROOT / "docs" / "start-accept-notes.md"
    notes = note_path.read_text(encoding="utf-8")
    assert "AGENT_SI_DATA_DIR" in notes, notes
    monkeypatch.setenv("AGENT_SI_DATA_DIR", "   ")
    try:
        k10_start.resolve_env_data_dir()
    except ValueError:
        pass
    else:
        raise AssertionError("blank AGENT_SI_DATA_DIR must fail loud")
    monkeypatch.delenv("AGENT_SI_DATA_DIR")
    assert get_data_dir(
        {"ui_session_token": "k10ph2d-live004", "secret_store": "memory",
         "testing": True}) is None
