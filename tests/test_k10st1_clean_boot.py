"""K10ST1 lane A: clean boot through the new start path (one test per row).

Row 165 (exe from script, hash plus smoke): tools/start.py --smoke writes a
record whose sha256 entries match the files on disk and whose smoke passes.
Row 167 (installed-app check on a clean profile): the start path validates
the served entries against a fresh profile directory.
Row R-343 (fresh install holds no test data): a fresh data dir stays empty.
Row R-345 (no fullscreen or console flash): --serve starts quietly over
loopback and closes stdin-quiet with exit 0 and no traceback.
Row M-P3-89 (portable start identical): the start path runs from a copy of
the tree with identical behaviour.
Row B0B-153 (startup sequence): checkout, configure from env example,
offline install from lockfiles, launch run in order.
TESTID k10st1-boot. Loopback TEST data only; no network, no installs.
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
START = ROOT / "tools" / "start.py"

TESTID = "k10st1-boot"

ENTRY_SCRIPT = "/src/app/main.tsx"

#: Console/window launch markers the start path must never use (R-345).
WINDOW_MARKERS = (
    "CREATE_NEW_CONSOLE",
    "STARTUPINFO",
    "ShowWindow",
    "ShellExecute",
    "fullscreen",
    "os.system",
    "Popen",
    "subprocess",
    "SW_HIDE",
)


def run_script(script, args, cwd=None, env=None, timeout=120):
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def run_start(args, cwd=None, env=None, timeout=120):
    return run_script(START, args, cwd=cwd, env=env, timeout=timeout)


def _carry_node_modules(port):
    """Share the real frontend install inputs with the portable copy.

    tools/start.py check_lockfiles needs the pinned frontend tree; without
    it the copy fails missing-tarball while the direct run passes. A
    directory junction shares the exact bytes (no copy, no network); a full
    copy is the fallback when junctions are unavailable.
    """
    src = os.path.join(str(ROOT), "frontend", "node_modules")
    dst = os.path.join(str(port), "frontend", "node_modules")
    if os.path.isdir(dst) or not os.path.isdir(src):
        return
    try:
        subprocess.run(["cmd", "/c", "mklink", "/J", dst, src],
                       capture_output=True, timeout=60)
    except OSError:
        pass
    if not os.path.isdir(dst):
        shutil.copytree(src, dst)


def _startup_log_line(text):
    """The single startup_log=<path> line tools/start.py prints.

    Only this line carries an abs path that differs per copy, so only it is
    normalised before comparing; every other byte must already match.
    """
    lines = [line for line in text.splitlines()
             if line.startswith("startup_log=")]
    assert len(lines) == 1, text
    return lines[0]


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def http_get(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.status, resp.read()


def wait_http_ok(url, deadline_s=30):
    end = time.time() + deadline_s
    last = None
    while time.time() < end:
        try:
            status, body = http_get(url)
            if status == 200:
                return status, body
            last = status
        except OSError as exc:
            last = exc
        time.sleep(0.2)
    raise AssertionError(f"no HTTP 200 from {url} (last={last!r})")


def test_row165_exe_from_script_hash_smoke(tmp_path):
    helped = run_start(["--help"], timeout=60)
    assert helped.returncode == 0, helped.stderr
    assert "smoke" in helped.stdout and "serve" in helped.stdout, helped.stdout
    data_dir = tmp_path / "profile165"
    record_path = tmp_path / "record165.json"
    proc = run_start(
        ["--smoke", "--tag", TESTID, "--data-dir", str(data_dir),
         "--record", str(record_path)],
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["tag"] == TESTID, record
    expected = {
        "tools/start.py": file_sha256(ROOT / "tools" / "start.py"),
        "frontend/index.html": file_sha256(ROOT / "frontend" / "index.html"),
    }
    assert record["sha256"] == expected, record
    assert record["smoke"]["status"] == "pass", record
    assert record["smoke"]["openapi_status"] == 200, record


def test_row167_installed_app_check_clean_profile(tmp_path):
    data_dir = tmp_path / "clean-profile"
    record_path = tmp_path / "record167.json"
    proc = run_start(
        ["--smoke", "--tag", TESTID, "--data-dir", str(data_dir),
         "--record", str(record_path)],
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["steps"] == ["checkout", "configure", "lockfiles", "launch"]
    assert all(record["step_status"][s] == "ok" for s in record["steps"])
    for entry in ("backend_app", "frontend_index", "frontend_entry",
                  "frontend_lockfile", "pyproject"):
        assert record["entries"][entry] == "ok", record


def test_rowR343_fresh_install_no_test_data(tmp_path):
    data_dir = tmp_path / "fresh-data"
    record_path = tmp_path / "record343.json"
    proc = run_start(
        ["--smoke", "--tag", TESTID, "--data-dir", str(data_dir),
         "--record", str(record_path)],
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    found = sorted(p for p in data_dir.rglob("*") if p.is_file()) \
        if data_dir.exists() else []
    # The serve writes runtime artifacts on boot (kb_catalog.json, the file
    # log and the startup boot log); those exact names are not seeded test
    # data. Any other file -- project, key, run or test data -- still fails.
    seeded = [
        p for p in found
        if p.stat().st_size > 0
        and p.relative_to(data_dir).as_posix() not in (
            "kb_catalog.json", "logs/agent-si.log", "startup.log")
    ]
    assert seeded == [], seeded
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["fresh"]["seeded"] is False, record
    expected = sorted(p.relative_to(data_dir).as_posix() for p in found)
    assert record["fresh"]["files"] == expected, record


def test_rowR345_no_console_flash_quiet_close(tmp_path):
    text = (ROOT / "tools" / "start.py").read_text(encoding="utf-8")
    for marker in WINDOW_MARKERS:
        assert marker not in text, marker
    port = free_port()
    frontend_port = free_port()
    data_dir = tmp_path / "serve-data"
    proc = subprocess.Popen(
        [sys.executable, str(START), "--serve", "--port", str(port),
         "--frontend-port", str(frontend_port), "--data-dir", str(data_dir),
         "--tag", TESTID],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(tmp_path),
    )
    try:
        status, _ = wait_http_ok(f"http://127.0.0.1:{port}/openapi.json")
        assert status == 200
        status, body = wait_http_ok(f"http://127.0.0.1:{frontend_port}/")
        assert status == 200, status
        assert ENTRY_SCRIPT.encode("utf-8") in body, body[:200]
        proc.stdin.close()
        out, err = proc.communicate(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=30)
    assert proc.returncode == 0, out + err
    assert "traceback" not in err.lower(), err
    assert "ready " in out, out[-500:]


def test_rowMP389_portable_start_identical(tmp_path):
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
    _carry_node_modules(port)
    other_cwd = tmp_path / "other-cwd"
    other_cwd.mkdir()
    direct_record = tmp_path / "record-direct.json"
    direct_data = tmp_path / "direct-data"
    direct = run_start(
        ["--smoke", "--tag", TESTID, "--data-dir", str(direct_data),
         "--record", str(direct_record)],
        cwd=str(other_cwd),
        timeout=120,
    )
    assert direct.returncode == 0, direct.stdout + direct.stderr
    copy_record = tmp_path / "record-copy.json"
    copy_data = tmp_path / "copy-data"
    copied = run_script(
        port / "tools" / "start.py",
        ["--smoke", "--tag", TESTID, "--data-dir", str(copy_data),
         "--record", str(copy_record)],
        cwd=str(other_cwd),
        timeout=120,
    )
    assert copied.returncode == 0, copied.stdout + copied.stderr
    direct_rec = json.loads(direct_record.read_text(encoding="utf-8"))
    copy_rec = json.loads(copy_record.read_text(encoding="utf-8"))
    for key in ("steps", "step_status", "entries", "smoke", "sha256"):
        assert copy_rec[key] == direct_rec[key], (key, copy_rec, direct_rec)
    direct_line = _startup_log_line(direct.stdout)
    copy_line = _startup_log_line(copied.stdout)
    assert direct_line.replace(str(direct_data), "<data>") == \
        copy_line.replace(str(copy_data), "<data>"), \
        (direct.stdout, copied.stdout)


def test_rowB0B153_startup_sequence(tmp_path):
    example = tmp_path / "env.example"
    example.write_text(
        "K10ST1_EXAMPLE_ONE=from-example\nK10ST1_EXAMPLE_TWO=from-example\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["K10ST1_EXAMPLE_TWO"] = "preset-keep"
    env["AGENT_SI_DATA_DIR"] = str(tmp_path / "env-data")
    argv_data = tmp_path / "argv-data"
    record_path = tmp_path / "record153.json"
    proc = run_start(
        ["--smoke", "--tag", TESTID, "--env-example", str(example),
         "--data-dir", str(argv_data), "--record", str(record_path)],
        env=env,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["steps"] == ["checkout", "configure", "lockfiles", "launch"]
    applied = record["configure"]["applied"]
    assert applied["K10ST1_EXAMPLE_ONE"] == "from-example", record
    assert applied["K10ST1_EXAMPLE_TWO"] == "preset-keep", record
    assert Path(record["data_dir"]) == argv_data, record
    assert Path(record["record_path"]) == record_path, record
    env_record_path = tmp_path / "record153-env.json"
    env_proc = run_start(
        ["--smoke", "--tag", TESTID, "--record", str(env_record_path)],
        env=env,
        timeout=120,
    )
    assert env_proc.returncode == 0, env_proc.stdout + env_proc.stderr
    env_record = json.loads(env_record_path.read_text(encoding="utf-8"))
    assert Path(env_record["data_dir"]) == tmp_path / "env-data", env_record
