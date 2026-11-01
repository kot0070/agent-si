# CODER-1 Kanapka: INSTALLB freeze RED->GREEN gate (lane-authored).
"""Frozen AgentSI.exe plus portable bundle gate for the INSTALLB lane.

RED before the lane delivers the freeze (no exe, no manifests);
GREEN after. Every assert measures a real lane output: no canned
values, no fakes, no stand-ins.

Static legs (fast, stdlib only):
- SMOKE.json carries the writer envelope with every check passing.
- MANIFEST.json/HASH.json hold the frozen canonical hash chain, and
  every files[] payload on disk re-hashes to its entry.
- the frozen exe sha matches across the exe file, the MANIFEST entry,
  HASH.json, and the recomputed canonical hash (hash x4).
- the sidecar spec freezes console=False windowed output.
- NOTICES.md names the frozen sidecar bundle components.
- the portable zip plus the held hidden-window launcher are present.

Live leg (real frozen exe, fresh store, neutral cwd, scrubbed env):
- the exe boots with no venv on PATH, serves / plus the provider
  matrix, holds no plaintext secrets in the fresh store, then stops
  by PID. The portable launcher resolves the bundled exe and its
  DryRun leaves a fresh data dir empty with the marker beside it.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = ROOT / "packaging" / "installer_manifest"
MANIFEST_PATH = MANIFEST_DIR / "MANIFEST.json"
HASH_PATH = MANIFEST_DIR / "HASH.json"
SMOKE_PATH = MANIFEST_DIR / "SMOKE.json"
GEN_SMOKE = MANIFEST_DIR / "gen_smoke.py"
SPEC_PATH = ROOT / "packaging" / "sidecar" / "agent_si_sidecar.spec"
NOTICES_PATH = ROOT / "docs" / "third_party_notices" / "NOTICES.md"
STAGE_EXE = ROOT / "dist" / "sidecar" / "AgentSI.exe"
PORTABLE_DIR = ROOT / "dist" / "portable"
PORTABLE_EXE = PORTABLE_DIR / "app" / "AgentSI.exe"
PORTABLE_LAUNCHER = PORTABLE_DIR / "start_agent_si.ps1"
PORTABLE_ZIP = ROOT / "dist" / "AgentSI-portable-0.1.0.zip"

EXE_NAME = "AgentSI.exe"
VERSION = "0.1.0"
SHA256_RE = re.compile(r"[0-9a-f]{64}")

EXPECTED_CHECKS = [
    "manifest-parse",
    "exe-present",
    "hash-match",
    "migrations-staged",
    "locale-staged",
    "kb-data-staged",
    "watcher-staged",
    "license-staged",
    "notices-staged",
]

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?[\w\-]{8,}"),
    re.compile(r"(?i)\bsecret\s*[:=]\s*['\"][^'\"]+['\"]"),
    re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
]

POWERSHELL = shutil.which("powershell.exe") or shutil.which("powershell")


def canonical_manifest_bytes(manifest):
    """Frozen canonical form: sorted keys, compact separators, UTF-8."""
    return json.dumps(
        manifest, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")


def load_json(path):
    assert path.is_file(), f"lane output missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def exe_manifest_entry(manifest):
    for entry in manifest.get("files", []):
        rel = entry.get("path", "")
        if rel.replace("\\", "/").endswith("sidecar/" + EXE_NAME):
            return entry
    return None


def test_smoke_generator_passes_on_lane_tree(tmp_path):
    """gen_smoke --root . exits 0 and writes SMOKE.json."""
    proc = subprocess.run(
        [sys.executable, str(GEN_SMOKE), "--root", str(ROOT),
         "--out", str(tmp_path / "SMOKE.json")],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    smoke = json.loads((tmp_path / "SMOKE.json").read_text(
        encoding="utf-8"))
    assert list(smoke.keys()) == ["exe", "checks", "started_clean"]
    assert smoke["exe"] == EXE_NAME
    assert [c["name"] for c in smoke["checks"]] == EXPECTED_CHECKS


def test_smoke_committed_all_pass():
    """Committed SMOKE.json: every check passes with exit_code 0."""
    smoke = load_json(SMOKE_PATH)
    assert smoke["exe"] == EXE_NAME
    assert smoke.get("started_clean") == {
        "projects": 0, "runs": 0, "keys": 0}
    assert [c["name"] for c in smoke["checks"]] == EXPECTED_CHECKS
    for check in smoke["checks"]:
        assert set(check.keys()) == {"name", "result", "exit_code"}
        assert check["result"] == "pass", check["name"]
        assert check["exit_code"] == 0, check["name"]


def test_hash_chain_x4_exe_manifest_hash_canonical():
    """Exe sha matches across file, MANIFEST entry, HASH, canonical."""
    manifest = load_json(MANIFEST_PATH)
    assert manifest.get("version") == VERSION
    assert manifest.get("exe") == EXE_NAME
    files = manifest.get("files")
    assert isinstance(files, list) and files != []
    assert STAGE_EXE.is_file(), f"frozen exe missing: {STAGE_EXE}"
    exe_sha = hashlib.sha256(STAGE_EXE.read_bytes()).hexdigest()
    entry = exe_manifest_entry(manifest)
    assert entry is not None, "MANIFEST has no sidecar exe entry"
    assert entry["sha256"] == exe_sha
    assert entry["bytes"] == STAGE_EXE.stat().st_size
    for other in files:
        assert SHA256_RE.fullmatch(other["sha256"]), other
        payload = ROOT / other["path"].replace("/", os.sep)
        assert payload.is_file(), f"payload absent: {other['path']}"
        data = payload.read_bytes()
        assert hashlib.sha256(data).hexdigest() == other["sha256"]
        assert len(data) == other["bytes"]
    envelope = load_json(HASH_PATH)
    recorded = envelope.get("sha256")
    assert SHA256_RE.fullmatch(recorded or "")
    actual = hashlib.sha256(
        canonical_manifest_bytes(manifest)).hexdigest()
    assert recorded == actual
    assert envelope.get("signature", {}).get("status") == \
        "UNSIGNED-BLOCKED"
    assert MANIFEST_PATH.read_bytes() == \
        canonical_manifest_bytes(manifest)


def test_sidecar_spec_freezes_windowed_exe():
    """Spec names the exe plus entry and freezes console=False."""
    assert SPEC_PATH.is_file(), f"sidecar spec missing: {SPEC_PATH}"
    text = SPEC_PATH.read_text(encoding="utf-8")
    assert EXE_NAME in text
    assert "ENTRY_SCRIPT" in text
    assert "sidecar.py" in text
    assert "console=False" in text


def test_notices_name_frozen_bundle_components():
    """NOTICES.md lists the frozen sidecar bundle components."""
    assert NOTICES_PATH.is_file()
    text = NOTICES_PATH.read_text(encoding="utf-8")
    for component in ("pywebview", "pythonnet", "clr_loader", "bottle",
                      "proxy_tools"):
        assert component in text, f"notices miss {component}"


def test_portable_bundle_layout():
    """Portable zip plus hidden-window launcher plus staged copies."""
    assert PORTABLE_ZIP.is_file() and PORTABLE_ZIP.stat().st_size > 0
    assert PORTABLE_EXE.is_file()
    assert PORTABLE_EXE.read_bytes() == STAGE_EXE.read_bytes()
    text = PORTABLE_LAUNCHER.read_text(encoding="utf-8")
    assert "AgentSI.exe" in text
    assert "Start-Process" in text
    assert "-WindowStyle Hidden" in text
    assert ".agent-si-portable-migrated" in text
    assert (PORTABLE_DIR / "MANIFEST.json").is_file()
    assert (PORTABLE_DIR / "LICENSE").is_file()
    assert (PORTABLE_DIR / "SHA256SUMS.txt").is_file()


def _scrubbed_env(store_dir):
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV",
                        "AGENT_SI_DATA_DIR")}
    env["AGENT_SI_DATA_DIR"] = str(store_dir)
    env["AGENT_SI_SECRET_STORE"] = "memory"
    return env


def _wait_for_port_listening(proc, timeout_s=280):
    """Read the sidecar listening line; return (port, child output).

    A one-file cold start extracts before serving. A reader thread
    drains the pipe without blocking; EOF with a dead child ends the
    wait instead of spinning. The caller must never read the pipe
    again (the pump owns it); use the returned output for failure
    tails.
    """
    import queue
    import threading
    pending: queue.Queue = queue.Queue()
    seen: list = []

    def pump():
        try:
            for line in iter(proc.stderr.readline, ""):
                seen.append(line)
                pending.put(line)
        finally:
            pending.put(None)

    worker = threading.Thread(target=pump, daemon=True)
    worker.start()
    deadline = time.time() + timeout_s
    port = None
    while time.time() < deadline:
        try:
            line = pending.get(timeout=2)
        except queue.Empty:
            if proc.poll() is not None and pending.empty():
                break
            continue
        if line is None:
            break
        if "listening on http://" in line:
            port = line.rsplit(":", 1)[1].strip().rstrip("/")
            try:
                port = int(port)
            except ValueError:
                port = None
            break
        if proc.poll() is not None and pending.empty():
            break
    tail = "".join(seen)[-2000:]
    return port, tail


def _get(port, path):
    with urllib.request.urlopen(
            f"http://127.0.0.1:{port}{path}",
            timeout=30) as resp:
        return resp.status, resp.read().decode("utf-8")


def _scan_store_for_secrets(store_dir):
    hits = []
    for path in sorted(Path(store_dir).rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, ValueError):
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                hits.append(f"{path.name} matches {pattern.pattern}")
    return hits


@pytest.mark.timeout(290)
def test_live_frozen_exe_clean_profile_fresh_store(tmp_path):
    """Frozen exe boots clean, serves, keeps a secret-free store."""
    assert STAGE_EXE.is_file(), f"frozen exe missing: {STAGE_EXE}"
    store = tmp_path / "fresh-store"
    store.mkdir()
    neutral = tmp_path / "neutral-cwd"
    neutral.mkdir()
    proc = subprocess.Popen(
        [str(STAGE_EXE)],
        cwd=str(neutral),
        env=_scrubbed_env(store),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=(subprocess.CREATE_NO_WINDOW
                       if os.name == "nt" else 0),
    )
    try:
        port, tail = _wait_for_port_listening(proc)
        rc = proc.poll()
        assert port is not None and rc is None, (
            f"exe did not serve; exit={rc!r} stderr={tail!r}")
        status, body = _get(port, "/")
        assert status == 200, body
        root_doc = json.loads(body)
        assert root_doc.get("version") == VERSION
        assert root_doc.get("status") == "ok"
        status, body = _get(port, "/api/v1/providers")
        assert status == 200, body
        assert _scan_store_for_secrets(store) == []
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=30)
    assert proc.returncode is not None


def test_portable_launcher_dryrun_clean_install(tmp_path):
    """Held launcher DryRun on real bundle bytes: empty data, marker."""
    if POWERSHELL is None:
        pytest.skip("no powershell on PATH")
    bundle = tmp_path / "bundle"
    (bundle / "app").mkdir(parents=True)
    shutil.copyfile(PORTABLE_EXE, bundle / "app" / EXE_NAME)
    shutil.copyfile(PORTABLE_LAUNCHER,
                    bundle / "start_agent_si.ps1")
    home = tmp_path / "home-no-legacy"
    home.mkdir()
    proc = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive",
         "-ExecutionPolicy", "Bypass", "-File",
         str(bundle / "start_agent_si.ps1"), "-DryRun"],
        cwd=str(bundle),
        env={**os.environ, "APPDATA": str(home)},
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    data = bundle / "data"
    assert data.is_dir()
    assert list(data.iterdir()) == []
    assert (bundle / ".agent-si-portable-migrated").is_file()
