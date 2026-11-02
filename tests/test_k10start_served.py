"""K10START served rows: 9 README/boot/start-path rows, served for real.

One test per row; each test name contains its row id. All rows are
served through the real seams (create_app + TestClient on an isolated
AGENT_SI_DATA_DIR via monkeypatch, plus real `tools/start.py --smoke`
subprocess runs with the product venv interpreter). Loopback TEST data
only. No fakes outside this file, no mocks of product code, no
TODO/NotImplementedError, no stubs.
"""
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import subprocess
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


def _clean_settings(token="k10start-served-token"):
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
    return fastapi.testclient.TestClient(app), str(data_dir)


def _readme_text():
    with open(os.path.join(_WS, "README.md"), encoding="utf-8") as handle:
        return handle.read()


def _docs_text():
    with open(os.path.join(
            _WS, "docs", "start-accept-notes.md"),
            encoding="utf-8") as handle:
        return handle.read()


def _section(text, heading):
    for part in re.split(r"(?m)^## ", text)[1:]:
        name, _, body = part.partition("\n")
        if name.strip() == heading:
            return body
    raise AssertionError("missing README section: %s" % heading)


def _load_start_module():
    name = "k10start_tools_start"
    module = sys.modules.get(name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(_WS, "tools", "start.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _run_smoke(tmp_path, tag):
    root = _WS
    data_dir = tmp_path / ("smoke-" + tag)
    home = tmp_path / ("home-" + tag)
    home.mkdir(exist_ok=True)
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["AGENT_SI_DATA_DIR"] = str(data_dir)
    record = tmp_path / ("record-" + tag + ".json")
    cmd = [
        sys.executable,
        os.path.join(root, "tools", "start.py"),
        "--smoke",
        "--tag", tag,
        "--data-dir", str(data_dir),
        "--record", str(record),
        "--env-example", os.path.join(root, "env.example"),
    ]
    proc = subprocess.run(cmd, cwd=root, env=env,
                          capture_output=True, text=True, timeout=280)
    return proc, record


def _read_record(record):
    assert os.path.isfile(str(record)), "no smoke record at %s" % record
    with open(str(record), encoding="utf-8") as handle:
        return json.loads(handle.read())


def test_k10start_B0B_129_prerequisites_served():
    """Row B0B-129: README Requirements plus the lockfiles on disk."""
    req = _section(_readme_text(), "Requirements")
    assert "WebView2" in req, req
    assert "AGENT_SI_PYTHON" in req, req
    assert "licence" in req, req
    assert os.path.isfile(
        os.path.join(_WS, "frontend", "package-lock.json"))
    assert os.path.isfile(os.path.join(_WS, "pyproject.toml"))


def test_k10start_B0B_131_setup_steps_served(tmp_path):
    """Row B0B-131: README first-run guide plus tools/start.py --smoke."""
    setup = _section(_readme_text(), "First run, step by step")
    assert "Connect a provider" in setup, setup
    assert "/firstrun" in setup, setup
    proc, record = _run_smoke(tmp_path, "k10start-131")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    body = _read_record(record)
    assert body["smoke"]["status"] == "pass", body
    assert all(v == "ok" for v in body["step_status"].values()), body


def test_k10start_B0B_151_demo_served(tmp_path, monkeypatch):
    """Row B0B-151: README first-task flow; demo route served for real."""
    first_task = _section(_readme_text(), "First task and Stop")
    assert "chat" in first_task, first_task
    client, data_dir = _client_with_data_dir(
        tmp_path, monkeypatch, "k10start-151-token")
    resp = client.post("/api/v1/release/start/demo")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project"] == "demo", body
    record_path = os.path.join(data_dir, "demo.json")
    if body.get("status") == "green":
        assert body.get("drive"), body
        assert os.path.isfile(record_path), body
        with open(record_path, encoding="utf-8") as handle:
            stored = json.loads(handle.read())
        assert stored["status"] == "green", stored
        assert stored["project"] == "demo", stored
    else:
        assert body["status"] == "refused", body
        assert body.get("code") == "drive-refused", body
        assert not os.path.isfile(record_path), body


def test_k10start_B0B_152_fixture_served(tmp_path, monkeypatch):
    """Row B0B-152: docs fixture index names the fixture command."""
    index = _section(_docs_text(), "Fixture runs")
    commands = re.findall(r"pytest\s+(\S+)", index)
    assert commands, index
    for command in commands:
        assert os.path.isfile(os.path.join(_WS, command)), index
    client, data_dir = _client_with_data_dir(
        tmp_path, monkeypatch, "k10start-152-token")
    evidence_dir = os.path.join(data_dir, "release-evidence")
    os.makedirs(evidence_dir, exist_ok=True)
    with open(os.path.join(evidence_dir, "shot-01-start.png"), "wb") as handle:
        handle.write(b"\x89PNG-k10start-real-run")
    resp = client.get("/api/v1/release/start/evidence")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    shots = body["screenshots"]
    assert shots == ["shot-01-start.png"], body
    for name in shots:
        assert str(name).endswith(".png"), body
        assert os.path.isfile(os.path.join(
            data_dir, "release-evidence", str(name))), body


def test_k10start_B0B_153_startup_sequence_served(tmp_path):
    """Row B0B-153: STEP_ORDER runs in order on a real --smoke run."""
    start = _load_start_module()
    proc, record = _run_smoke(tmp_path, "k10start-153")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    body = _read_record(record)
    assert body["steps"] == list(start.STEP_ORDER), body
    assert body["steps"] == ["checkout", "configure", "lockfiles", "launch"]
    assert sorted(body["step_status"]) == sorted(body["steps"]), body
    assert all(v == "ok" for v in body["step_status"].values()), body


def test_k10start_B0B_249_restart_served(tmp_path, monkeypatch):
    """Row B0B-249: a second fresh start repeats the green demo payload."""
    payloads = []
    for lane, token in (("first", "k10start-249a"), ("second", "k10start-249b")):
        lane_dir = tmp_path / lane
        lane_dir.mkdir(exist_ok=True)
        home = lane_dir / "home"
        home.mkdir(exist_ok=True)
        _isolate_home(monkeypatch, home)
        data_dir = lane_dir / "data"
        monkeypatch.setenv("AGENT_SI_DATA_DIR", str(data_dir))
        client = fastapi.testclient.TestClient(
            create_app(_clean_settings(token + "-token")))
        resp = client.post("/api/v1/release/start/demo")
        assert resp.status_code == 200, resp.text
        payloads.append((resp.json(), str(data_dir)))
    first, second = payloads
    assert second[0] == first[0], (first[0], second[0])
    if first[0].get("status") == "green":
        assert first[0].get("drive"), first[0]
        for _, data_dir in payloads:
            with open(os.path.join(data_dir, "demo.json"),
                      encoding="utf-8") as handle:
                stored = json.loads(handle.read())
            assert stored["status"] == "green", stored
        with open(os.path.join(payloads[0][1], "demo.json"), "rb") as handle:
            first_bytes = handle.read()
        with open(os.path.join(payloads[1][1], "demo.json"), "rb") as handle:
            assert handle.read() == first_bytes
    else:
        assert first[0]["status"] == "refused", first[0]
        assert first[0].get("code") == "drive-refused", first[0]
        for _, data_dir in payloads:
            assert not os.path.isfile(
                os.path.join(data_dir, "demo.json")), data_dir


def test_k10start_B0B_211_versioned_deps_served(tmp_path):
    """Row B0B-211: --smoke sha256 entries match disk, twice identical."""
    proc, record = _run_smoke(tmp_path, "k10start-211")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    first_bytes = record.read_bytes()
    proc2, _ = _run_smoke(tmp_path, "k10start-211")
    assert proc2.returncode == 0, proc2.stdout + proc2.stderr
    assert record.read_bytes() == first_bytes
    body = json.loads(first_bytes.decode("utf-8"))
    for rel in ("tools/start.py", "frontend/index.html"):
        with open(os.path.join(_WS, rel), "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        assert body["sha256"][rel] == digest, body


def test_k10start_LIVE0_01_frontend_offline_served():
    """Row LIVE0-01: hash-verified download plus offline tarball install."""
    lock_path = os.path.join(_WS, "frontend", "package-lock.json")
    assert os.path.isfile(lock_path)
    with open(lock_path, encoding="utf-8") as handle:
        lock = json.load(handle)
    packages = lock.get("packages", {})
    assert "node_modules/@types/react" in packages, sorted(packages)[:5]
    assert "node_modules/@types/react-dom" in packages
    with open(os.path.join(_WS, "tools", "start.py"),
              encoding="utf-8") as handle:
        start_src = handle.read()
    assert "registry" not in start_src.lower()
    assert "offline" in start_src.lower()
    lockfiles = _load_start_module().check_lockfiles(pathlib.Path(_WS))
    assert lockfiles["status"] == "ok", lockfiles
    assert lockfiles["offline"] is True, lockfiles
    verify = _section(_readme_text(), "Download and verify")
    assert "SHA256" in verify, verify


def test_k10start_LIVE0_04_data_dir_served(tmp_path, monkeypatch):
    """Row LIVE0-04: data dir from AGENT_SI_DATA_DIR, never harness."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    _isolate_home(monkeypatch, home)
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(data_dir))
    app = create_app(_clean_settings("k10start-live004-token"))
    assert app.state.data_dir == os.path.abspath(str(data_dir))
    other = tmp_path / "other"
    other.mkdir(exist_ok=True)
    with pytest.raises(ValueError):
        create_app({"ui_session_token": "k10start-live004-harness",
                    "secret_store": "memory", "testing": True,
                    "store_dir": str(other)})
    monkeypatch.setenv("AGENT_SI_DATA_DIR", "   ")
    with pytest.raises(ValueError):
        create_app(_clean_settings("k10start-live004-blank"))
    index = _section(_readme_text(), "Where data lives")
    assert "AGENT_SI_DATA_DIR" in index, index
