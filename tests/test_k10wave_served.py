"""K10WAVE served map: one proving test per open row.

Row R-328: POST /k10/start/demo brings the demo project to green.
Row 166: GET /k10/start/evidence keeps release evidence (screenshots).
Row R-343: tools/start.py --smoke on a fresh profile seeds no test data.
Row 165: tools/start.py --smoke writes hashes matching disk plus smoke pass.
Row 167: tools/start.py --smoke validates served entries on a clean profile.
Row M-P3-89: tools/start.py --smoke runs identically from a portable copy.
Row R-345: tools/start.py --serve starts quietly and closes stdin-quiet.
Row M-P4-134: first start migrates settings plus credentials, originals kept.
Row M-P4-138: GET /k10/start/migrate reports settings plus keys migration.
Row M-P4-162: GET /k10/accept returns the final acceptance status.
Each row is listed by agent_si.k10_compet.served_rows() and proven here
through its serving seam. Loopback TEST data only; no network, no installs.
"""
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import fastapi.testclient  # noqa: E402

from agent_si import k10_compet  # noqa: E402
from agent_si.backend.app import (  # noqa: E402
    create_app,
    migrate_legacy_data,
)

START = ROOT / "tools" / "start.py"
TAG = "k10wave-served"


def _served():
    return {row["row"]: row for row in k10_compet.served_rows()}


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
    return fastapi.testclient.TestClient(app), data_dir


def _run_start(args, cwd=None, env=None, timeout=120):
    return subprocess.run(
        [sys.executable, str(START), *args],
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_k10wave_r328_demo_green(tmp_path, monkeypatch):
    """Row R-328 served through POST /k10/start/demo."""
    entry = _served()["R-328"]
    assert entry["route"] == "POST /k10/start/demo", entry
    assert entry["test"] == (
        "tests/test_k10open4_start_path.py::"
        "test_k10open4_start_demo_brought_to_green"
    ), entry
    client, data_dir = _client_on_temp_dir(tmp_path, monkeypatch, "kw-r328")
    resp = client.post("/k10/start/demo")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == "k10open4-start", body
    assert body["status"] == "green", body
    assert body["project"] == "demo", body
    assert (data_dir / "demo.json").is_file(), body


def test_k10wave_166_evidence_screenshots(tmp_path, monkeypatch):
    """Row 166 served through GET /k10/start/evidence."""
    entry = _served()["166"]
    assert entry["route"] == "GET /k10/start/evidence", entry
    assert entry["test"] == (
        "tests/test_k10open4_start_path.py::"
        "test_k10open4_start_evidence_keeps_screenshots"
    ), entry
    client, data_dir = _client_on_temp_dir(tmp_path, monkeypatch, "kw-166")
    resp = client.get("/k10/start/evidence")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == "k10open4-start", body
    shots = body["screenshots"]
    assert isinstance(shots, list) and len(shots) >= 1, body
    for name in shots:
        assert str(name).endswith(".png"), body
        assert (data_dir / "release-evidence" / str(name)).is_file(), body


def test_k10wave_r343_fresh_no_test_data(tmp_path):
    """Row R-343 served through tools/start.py --smoke fresh profile."""
    entry = _served()["R-343"]
    assert entry["route"] == "tools/start.py --smoke fresh profile", entry
    assert entry["test"] == (
        "tests/test_k10st1_clean_boot.py::test_rowR343_fresh_install_no_test_data"
    ), entry
    data_dir = tmp_path / "fresh-data"
    record_path = tmp_path / "record343.json"
    proc = _run_start(
        ["--smoke", "--tag", TAG, "--data-dir", str(data_dir),
         "--record", str(record_path)]
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["fresh"]["seeded"] is False, record
    found = sorted(p for p in data_dir.rglob("*") if p.is_file()) \
        if data_dir.exists() else []
    expected = sorted(p.relative_to(data_dir).as_posix() for p in found)
    assert record["fresh"]["files"] == expected, record


def test_k10wave_165_hash_plus_smoke(tmp_path):
    """Row 165 served through tools/start.py --smoke hash plus smoke."""
    entry = _served()["165"]
    assert entry["route"] == "tools/start.py --smoke hash plus smoke", entry
    assert entry["test"] == (
        "tests/test_k10st1_clean_boot.py::test_row165_exe_from_script_hash_smoke"
    ), entry
    data_dir = tmp_path / "profile165"
    record_path = tmp_path / "record165.json"
    proc = _run_start(
        ["--smoke", "--tag", TAG, "--data-dir", str(data_dir),
         "--record", str(record_path)]
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["tag"] == TAG, record
    assert record["smoke"]["status"] == "pass", record
    assert record["smoke"]["openapi_status"] == 200, record
    for name in ("tools/start.py", "frontend/index.html"):
        digest = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        assert record["sha256"][name] == digest, record


def test_k10wave_167_clean_profile(tmp_path):
    """Row 167 served through tools/start.py --smoke clean profile."""
    entry = _served()["167"]
    assert entry["route"] == "tools/start.py --smoke clean profile", entry
    assert entry["test"] == (
        "tests/test_k10st1_clean_boot.py::"
        "test_row167_installed_app_check_clean_profile"
    ), entry
    data_dir = tmp_path / "clean-profile"
    record_path = tmp_path / "record167.json"
    proc = _run_start(
        ["--smoke", "--tag", TAG, "--data-dir", str(data_dir),
         "--record", str(record_path)]
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["steps"] == ["checkout", "configure", "lockfiles", "launch"]
    assert all(record["step_status"][s] == "ok" for s in record["steps"])
    for key in ("backend_app", "frontend_index", "frontend_entry",
                "frontend_lockfile", "pyproject"):
        assert record["entries"][key] == "ok", record


def test_k10wave_mp389_portable_identical(tmp_path):
    """Row M-P3-89 served through tools/start.py portable copy identical."""
    entry = _served()["M-P3-89"]
    assert entry["route"] == "tools/start.py portable copy identical", entry
    assert entry["test"] == (
        "tests/test_k10st1_clean_boot.py::test_rowMP389_portable_start_identical"
    ), entry
    port = tmp_path / "portable"
    (port / "tools").mkdir(parents=True)
    shutil.copy2(ROOT / "tools" / "start.py", port / "tools" / "start.py")
    shutil.copytree(
        ROOT / "src", port / "src",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    shutil.copytree(
        ROOT / "frontend", port / "frontend",
        ignore=shutil.ignore_patterns(
            "node_modules", "dist", "__pycache__", "__tests__", "tests"),
    )
    shutil.copytree(
        ROOT / "iface", port / "iface",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    shutil.copy2(ROOT / "pyproject.toml", port / "pyproject.toml")
    other_cwd = tmp_path / "other-cwd"
    other_cwd.mkdir()
    direct_record = tmp_path / "record-direct.json"
    direct_data = tmp_path / "direct-data"
    direct = _run_start(
        ["--smoke", "--tag", TAG, "--data-dir", str(direct_data),
         "--record", str(direct_record)],
        cwd=str(other_cwd),
    )
    assert direct.returncode == 0, direct.stdout + direct.stderr
    copy_record = tmp_path / "record-copy.json"
    copy_data = tmp_path / "copy-data"
    copied = subprocess.run(
        [sys.executable, str(port / "tools" / "start.py"),
         "--smoke", "--tag", TAG, "--data-dir", str(copy_data),
         "--record", str(copy_record)],
        cwd=str(other_cwd),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert copied.returncode == 0, copied.stdout + copied.stderr
    direct_rec = json.loads(direct_record.read_text(encoding="utf-8"))
    copy_rec = json.loads(copy_record.read_text(encoding="utf-8"))
    for key in ("steps", "step_status", "entries", "smoke", "sha256"):
        assert copy_rec[key] == direct_rec[key], (key, copy_rec, direct_rec)


def _free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _http_get(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.status, resp.read()


def _wait_http_ok(url, deadline_s=30):
    end = time.time() + deadline_s
    last = None
    while time.time() < end:
        try:
            status, body = _http_get(url)
            if status == 200:
                return status, body
            last = status
        except OSError as exc:
            last = exc
        time.sleep(0.2)
    raise AssertionError(f"no HTTP 200 from {url} (last={last!r})")


def test_k10wave_mp162_accept_served(tmp_path, monkeypatch):
    """Row M-P4-162 served through GET /k10/accept."""
    entry = _served()["M-P4-162"]
    assert entry["route"] == "GET /k10/accept", entry
    assert entry["test"] == (
        "tests/test_k10st4_accept_compet.py::test_k10st4_accept_served"
    ), entry
    client, _data_dir = _client_on_temp_dir(tmp_path, monkeypatch, "kw-mp162")
    resp = client.get("/k10/accept")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == "k10st4-accept", body
    for key in ("ok", "docker", "services", "powershell"):
        assert key in body, body


def test_k10wave_mp138_start_migrate(tmp_path, monkeypatch):
    """Row M-P4-138 served through GET /k10/start/migrate."""
    entry = _served()["M-P4-138"]
    assert entry["route"] == "GET /k10/start/migrate", entry
    assert entry["test"] == (
        "tests/test_k10open4_start_path.py::"
        "test_k10open4_start_migrates_settings_keys"
    ), entry
    settings_payload = b'{"theme": "dark", "lane": "k10wave-mp138"}'
    keys_payload = b'{"loopback": "test-only-keys"}'
    legacy_home = tmp_path / "home"
    legacy_home.mkdir()
    legacy = legacy_home / ".agent_si"
    legacy.mkdir()
    (legacy / "settings.json").write_bytes(settings_payload)
    (legacy / "keys.json").write_bytes(keys_payload)
    monkeypatch.setenv("HOME", str(legacy_home))
    monkeypatch.setenv("USERPROFILE", str(legacy_home))
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(data_dir))
    settings = {
        "ui_session_token": "kw-mp138",
        "secret_store": "memory",
        "testing": True,
    }
    create_app(settings)
    for name, payload in (
        ("settings.json", settings_payload),
        ("keys.json", keys_payload),
    ):
        assert (data_dir / name).read_bytes() == payload
        assert (legacy / name).read_bytes() == payload
    client = fastapi.testclient.TestClient(create_app(settings))
    resp = client.get("/k10/start/migrate")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == "k10open4-start", body
    assert body["migrated"]["settings.json"] in ("copied", "skipped-present"), body
    assert body["migrated"]["keys.json"] in ("copied", "skipped-present"), body


def test_k10wave_mp134_migrate_datadir(tmp_path, monkeypatch):
    """Row M-P4-134 served through the consumer-layer data-dir call site."""
    entry = _served()["M-P4-134"]
    assert entry["route"] == "create_app consumer-layer data-dir call site", entry
    assert entry["test"] == (
        "tests/test_k10st1_migrate_datadir.py::"
        "test_k10st1_migrate_first_start_copies_settings_credentials"
    ), entry
    settings_payload = b'{"theme": "dark", "lane": "k10wave-mp134"}'
    credentials_payload = b'{"loopback": "test-only"}'
    legacy_home = tmp_path / "home"
    legacy_home.mkdir()
    legacy = legacy_home / ".agent_si"
    legacy.mkdir()
    (legacy / "settings.json").write_bytes(settings_payload)
    (legacy / "credentials.json").write_bytes(credentials_payload)
    monkeypatch.setenv("HOME", str(legacy_home))
    monkeypatch.setenv("USERPROFILE", str(legacy_home))
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    data_dir = tmp_path / "data"
    report = migrate_legacy_data(str(data_dir), legacy_dir=str(legacy))
    assert report == {
        "settings.json": "copied",
        "credentials.json": "copied",
    }, report
    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(data_dir))
    settings = {
        "ui_session_token": "kw-mp134",
        "secret_store": "memory",
        "testing": True,
    }
    app = create_app(settings)
    assert app.state.data_dir == os.path.abspath(str(data_dir))
    for name, payload in (
        ("settings.json", settings_payload),
        ("credentials.json", credentials_payload),
    ):
        assert (data_dir / name).read_bytes() == payload
        assert (legacy / name).read_bytes() == payload
    (data_dir / "settings.json").write_bytes(b'{"theme": "edited"}')
    create_app(settings)
    assert (data_dir / "settings.json").read_bytes() == b'{"theme": "edited"}'
    assert (legacy / "settings.json").read_bytes() == settings_payload

def test_k10wave_r345_serve_quiet_close(tmp_path):
    """Row R-345 served through tools/start.py --serve quiet close."""
    entry = _served()["R-345"]
    assert entry["route"] == "tools/start.py --serve quiet close", entry
    assert entry["test"] == (
        "tests/test_k10st1_clean_boot.py::"
        "test_rowR345_no_console_flash_quiet_close"
    ), entry
    text = (ROOT / "tools" / "start.py").read_text(encoding="utf-8")
    for marker in (
        "CREATE_NEW_CONSOLE",
        "STARTUPINFO",
        "ShowWindow",
        "ShellExecute",
        "fullscreen",
        "os.system",
        "Popen",
        "subprocess",
        "SW_HIDE",
    ):
        assert marker not in text, marker
    port = _free_port()
    frontend_port = _free_port()
    data_dir = tmp_path / "serve-data"
    proc = subprocess.Popen(
        [sys.executable, str(START), "--serve", "--port", str(port),
         "--frontend-port", str(frontend_port), "--data-dir", str(data_dir),
         "--tag", TAG],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(tmp_path),
    )
    try:
        status, _ = _wait_http_ok(f"http://127.0.0.1:{port}/openapi.json")
        assert status == 200
        status, body = _wait_http_ok(f"http://127.0.0.1:{frontend_port}/")
        assert status == 200, status
        assert b"/src/app/main.tsx" in body, body[:200]
        proc.stdin.close()
        out, err = proc.communicate(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=30)
    assert proc.returncode == 0, out + err
    assert "traceback" not in err.lower(), err
    assert "ready " in out, out[-500:]
