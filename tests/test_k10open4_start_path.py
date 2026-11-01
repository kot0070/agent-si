"""K10OPEN4 start path: release evidence, demo-to-green, first-start migrate.

testid: k10open4-start (lives ONLY in this file).

Row 166: a clean start from a copy of int keeps release evidence
(screenshots) from the human-like end-to-end run.
Row R-328: a clean start brings the demo project to green inside the
acceptance drive.
Row M-P4-138: first start migrates settings plus keys, originals kept
(copy, never move; repeat starts never overwrite).
All three rows are served through create_app plus HTTP client on temp
copies, loopback TEST data only.
"""
import json
import os
import sys

_TESTID = "k10open4-start"

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402

_TEST_SETTINGS = b'{"theme": "dark", "lane": "k10open4-start"}'
_TEST_KEYS = b'{"loopback": "test-only-keys"}'


def _clean_settings(token="k10open4-start-token"):
    return {
        "ui_session_token": token,
        "secret_store": "memory",
        "testing": True,
    }


def _isolate_home(monkeypatch, home):
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))


def _client_with_data_dir(tmp_path, monkeypatch, token):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    _isolate_home(monkeypatch, home)
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(data_dir))
    app = create_app(_clean_settings(token))
    assert app.state.data_dir == os.path.abspath(str(data_dir))
    return fastapi.testclient.TestClient(app), data_dir, home


def test_k10open4_start_evidence_keeps_screenshots(tmp_path, monkeypatch):
    """Row 166: clean start keeps release evidence (screenshots)."""
    client, data_dir, _home = _client_with_data_dir(
        tmp_path, monkeypatch, "k10open4-evidence-token")
    resp = client.get("/api/v1/release/start/evidence")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == _TESTID, body
    shots = body["screenshots"]
    assert isinstance(shots, list) and len(shots) >= 1, body
    for name in shots:
        assert str(name).endswith(".png"), body
        assert os.path.isfile(
            os.path.join(str(data_dir), "release-evidence", str(name))), body


def test_k10open4_start_demo_brought_to_green(tmp_path, monkeypatch):
    """Row R-328: clean start brings the demo project to green."""
    client, data_dir, _home = _client_with_data_dir(
        tmp_path, monkeypatch, "k10open4-demo-token")
    resp = client.post("/api/v1/release/start/demo")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == _TESTID, body
    assert body["status"] == "green", body
    assert body["project"] == "demo", body
    record_path = os.path.join(str(data_dir), "demo.json")
    assert os.path.isfile(record_path), body
    with open(record_path, "rb") as handle:
        stored = json.loads(handle.read().decode("utf-8"))
    assert stored["status"] == "green", stored
    assert stored["project"] == "demo", stored


def test_k10open4_start_migrates_settings_keys(tmp_path, monkeypatch):
    """Row M-P4-138: first start migrates settings plus keys, originals kept."""
    legacy_home = tmp_path / "home"
    legacy_home.mkdir(exist_ok=True)
    legacy = legacy_home / ".agent_si"
    legacy.mkdir(exist_ok=True)
    (legacy / "settings.json").write_bytes(_TEST_SETTINGS)
    (legacy / "keys.json").write_bytes(_TEST_KEYS)
    _isolate_home(monkeypatch, legacy_home)
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(data_dir))

    create_app(_clean_settings("k10open4-migrate-token"))

    for name, payload in (
        ("settings.json", _TEST_SETTINGS),
        ("keys.json", _TEST_KEYS),
    ):
        assert (data_dir / name).read_bytes() == payload
        assert (legacy / name).read_bytes() == payload

    client = fastapi.testclient.TestClient(
        create_app(_clean_settings("k10open4-migrate-token")))
    resp = client.get("/api/v1/release/start/migrate")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == _TESTID, body
    assert body["migrated"]["settings.json"] in ("copied", "skipped-present")
    assert body["migrated"]["keys.json"] in ("copied", "skipped-present")

    (data_dir / "settings.json").write_bytes(b'{"theme": "edited"}')
    (data_dir / "keys.json").write_bytes(b'{"loopback": "edited-keys"}')
    create_app(_clean_settings("k10open4-migrate-token"))
    assert (data_dir / "settings.json").read_bytes() == b'{"theme": "edited"}'
    assert (data_dir / "keys.json").read_bytes() == b'{"loopback": "edited-keys"}'
    assert (legacy / "settings.json").read_bytes() == _TEST_SETTINGS
    assert (legacy / "keys.json").read_bytes() == _TEST_KEYS
