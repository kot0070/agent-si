"""FXWIN: Windows reality for child runs (pair coder, RED first).

W1 cmd-shim metacharacters (& |) refused at the spawn gate.
W2 python resolve falls back to the py launcher.
W3 project .venv wins for bare python/python3/pytest; child PATH
  gets the venv bin first; missing tools are still named.
W4 worker child env is scrubbed (SECRET_X hidden).
W5 antivirus-lock PermissionError retried 3x, 0.2 s apart.
W6 console bytes decode utf-8-sig, console code page, cp1251, cp866.
  NOTE: cp866 has no U+0456 (Ukrainian i), so "Привіт" cannot be
  cp866 bytes; the cp866 leg uses "Привет", the cp1251 leg carries
  "Привіт".
W7 a run waiting on stdin gets DEVNULL (EOF at once, rc 0).
"""
import os
import shutil
import subprocess
import sys
import time

import pytest

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.k10_accept import (  # noqa: E402
    _probe_docker,
    _probe_powershell,
)
from agent_si.runtime.devrun import actions as _actions  # noqa: E402
from agent_si.worker_tools import command_runner as _runner  # noqa: E402


# W1: npm.cmd runs through cmd.exe: & and | must refuse at the gate.
@pytest.mark.parametrize("frag", ["x&echo PWNED", "x|echo PWNED"])
def test_w1_cmd_shim_metacharacters_refused(tmp_path, monkeypatch, frag):
    orig_which = shutil.which

    def _fake_which(cmd, *args, **kwargs):
        if str(cmd).lower() == "npm":
            return "C:\\faketools\\npm.cmd"
        return orig_which(cmd, *args, **kwargs)

    monkeypatch.setattr(shutil, "which", _fake_which)
    job = {
        "log_path": str(tmp_path / "w1.log"),
        "log_rel": "w1.log",
        "project_id": "proj-fxwin-w1",
        "check_run_id": "run-w1",
    }
    run = _actions._ExecTool(str(tmp_path), job).load()
    with pytest.raises(PermissionError, match="cmd metacharacters"):
        run(["npm", "--version", frag], "R0",
            {"subject": "p", "task": "t", "scopes": ["tools:exec"]})


# W2: a PC with only py.exe still resolves python and pytest.
def test_w2_py_launcher_fallback(monkeypatch):
    orig_which = shutil.which

    def _only_py(cmd, *args, **kwargs):
        if str(cmd).lower() in ("python", "python3", "pytest"):
            return None
        if str(cmd).lower() == "py":
            return "C:\\Windows\\py.exe"
        return orig_which(cmd, *args, **kwargs)

    monkeypatch.setattr(shutil, "which", _only_py)
    assert _actions.resolve_argv(
        ["python", "--version"]) == ["C:\\Windows\\py.exe", "--version"]
    assert _actions.resolve_argv(
        ["python3", "--version"]) == ["C:\\Windows\\py.exe", "--version"]
    assert _actions.resolve_argv(
        ["pytest", "-q"]) == ["C:\\Windows\\py.exe", "-m", "pytest", "-q"]


def _make_venv(folder):
    venv_dir = os.path.join(folder, ".venv")
    proc = subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", venv_dir],
        capture_output=True, timeout=180)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    if os.name == "nt":
        interp = os.path.join(venv_dir, "Scripts", "python.exe")
        site = os.path.join(venv_dir, "Lib", "site-packages")
    else:
        interp = os.path.join(venv_dir, "bin", "python")
        libs = [d for d in os.listdir(os.path.join(venv_dir, "lib"))
                if d.startswith("python")]
        site = os.path.join(venv_dir, "lib", libs[0], "site-packages")
    assert os.path.isfile(interp), interp
    return venv_dir, interp, site


# W3: project .venv wins for bare python/python3/pytest.
def test_w3_venv_wins_resolve(tmp_path):
    folder = str(tmp_path / "proj")
    os.makedirs(folder)
    _venv_dir, interp, site = _make_venv(folder)
    with open(os.path.join(site, "fxwin_venv_marker_xyz.py"),
              "w", encoding="utf-8") as handle:
        handle.write('MARKER = "fxwin-venv-marker-1"\n')
    assert _actions.resolve_argv(
        ["python", "s.py"], folder) == [interp, "s.py"]
    assert _actions.resolve_argv(
        ["python3", "s.py"], folder) == [interp, "s.py"]
    assert _actions.resolve_argv(
        ["pytest", "-q"], folder) == [interp, "-m", "pytest", "-q"]


# W3 end to end: the venv interpreter runs the check, its bin is
# first on the child PATH, and a missing tool still names itself.
def test_w3_venv_wins_run_and_path(tmp_path):
    folder = str(tmp_path / "proj")
    os.makedirs(folder)
    _venv_dir, interp, site = _make_venv(folder)
    with open(os.path.join(site, "fxwin_venv_marker_xyz.py"),
              "w", encoding="utf-8") as handle:
        handle.write('MARKER = "fxwin-venv-marker-1"\n')
    script = os.path.join(folder, "venv_probe_win.py")
    with open(script, "w", encoding="utf-8") as handle:
        handle.write(
            "import os\n"
            "import fxwin_venv_marker_xyz\n"
            "print('MARKER:' + fxwin_venv_marker_xyz.MARKER)\n"
            "print('PATH0:' + os.environ['PATH'].split(os.pathsep)[0])\n")
    log = os.path.join(folder, "logs", "venv.log")
    row = _actions.spawn_checked(
        "proj-fxwin-w3", "run-w3", folder, ["python", "venv_probe_win.py"],
        log, "logs/venv.log")
    assert _actions.wait_proc(row["proc"], 90.0) == "exited"
    assert row["proc"].returncode == 0, log
    with open(log, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    assert "MARKER:fxwin-venv-marker-1" in text, text
    want = os.path.normcase(os.path.dirname(interp))
    got = [line for line in text.splitlines()
           if line.startswith("PATH0:")]
    assert got and os.path.normcase(got[0][6:]) == want, text
    with pytest.raises(_actions.SpawnNotInstalled,
                       match="fxwin-no-such-tool"):
        _actions.spawn_checked(
            "proj-fxwin-w3", "run-w3b", folder,
            ["fxwin-no-such-tool", "--version"],
            os.path.join(folder, "logs", "missing.log"),
            "logs/missing.log")


# W4: the worker child env is scrubbed (SECRET_X hidden from child).
def test_w4_worker_child_env_scrubbed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SECRET_X_FXWIN", "top-secret-value")
    _runner.reset_state()
    try:
        code = ("__import__('pathlib').Path('fxwin_secret_probe.txt')"
                ".write_text(str(__import__('os').environ.get("
                "'SECRET_X_FXWIN','ABSENT')),encoding='utf-8')")
        row = _runner.start_command(
            "proj-fxwin-w4", "run-w4", ["python", "-c", code])
        assert row["run_id"] == "run-w4"
        probe = tmp_path / "fxwin_secret_probe.txt"
        for _ in range(100):
            if probe.exists():
                break
            time.sleep(0.2)
        assert probe.exists(), "worker child never wrote the probe file"
        assert probe.read_text(encoding="utf-8") == "ABSENT"
    finally:
        _runner.reset_state()


# W5: antivirus-lock PermissionError is retried, then the write wins.
def test_w5_write_file_av_lock_retry(tmp_path, monkeypatch):
    calls = {"n": 0}
    real_replace = os.replace

    def _flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError(13, "resource busy (AV lock)")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _flaky)
    out = _actions.write_file(
        str(tmp_path), "part/a.txt", "av-ok",
        allowed=["part/a.txt"], run_id="r", part_id="p", attempt=1)
    assert out["path"] == "part/a.txt"
    with open(tmp_path / "part" / "a.txt", encoding="utf-8") as handle:
        assert handle.read() == "av-ok"
    assert calls["n"] == 2


def test_w5_av_retry_gives_up_after_three():
    calls = {"n": 0}

    def _always():
        calls["n"] += 1
        raise PermissionError(13, "busy")

    with pytest.raises(PermissionError):
        _actions._retry_av_lock(_always)
    assert calls["n"] == 3


# W6: console bytes decode without mojibake or crash. Python's cp1251
# covers all 256 bytes, so ambiguous bytes resolve at the cp1251 leg
# on a UTF-8 console; the cp866 leg is reached through the console
# code page leg on Russian PCs (simulated here).
def test_w6_finalize_log_cp866_console_roundtrip(tmp_path, monkeypatch):
    text = "Привет"
    blob = text.encode("cp866")
    monkeypatch.setattr(
        _actions, "_console_code_page", lambda: "cp866")
    log = tmp_path / "cp866.log"
    log.write_bytes(blob)
    assert _actions.finalize_log(str(log)) == text


def test_w6_finalize_log_cp1251_ukrainian(tmp_path):
    text = "Привіт"
    log = tmp_path / "cp1251.log"
    log.write_bytes(text.encode("cp1251"))
    assert _actions.finalize_log(str(log)) == text


def test_w6_finalize_log_utf8_sig_bom(tmp_path):
    text = "hello Привіт"
    log = tmp_path / "bom.log"
    log.write_bytes(text.encode("utf-8-sig"))
    assert _actions.finalize_log(str(log)) == text


def test_w6_finalize_log_garbage_never_crashes(tmp_path):
    log = tmp_path / "garbage.log"
    log.write_bytes(bytes(range(256)))
    assert isinstance(_actions.finalize_log(str(log)), str)


def test_w6_read_file_cp1251_ukrainian(tmp_path):
    text = "Привіт"
    with open(tmp_path / "u.txt", "wb") as handle:
        handle.write(text.encode("cp1251"))
    assert _actions.read_file(str(tmp_path), "u.txt") == text


# W6: k10_accept probes pass encoding="utf-8", errors="replace".
def test_w6_accept_probes_utf8_replace(tmp_path, monkeypatch):
    import shutil as _shutil

    for name in ("docker.exe", "powershell.exe"):
        _shutil.copy(sys.executable, tmp_path / name)
    # A copied venv interpreter needs its exe-adjacent pyvenv.cfg
    # (one per directory covers both names here).
    cfg = ""
    for cand in (os.path.join(os.path.dirname(sys.executable),
                              "pyvenv.cfg"),
                 os.path.join(os.path.dirname(
                     os.path.dirname(sys.executable)), "pyvenv.cfg")):
        if os.path.isfile(cand):
            cfg = cand
            break
    if cfg:
        _shutil.copy(cfg, tmp_path / "pyvenv.cfg")
    monkeypatch.setenv("PATH", str(tmp_path))
    calls = []
    real_run = subprocess.run

    def _spy(*args, **kwargs):
        calls.append(kwargs)
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _spy)
    assert _probe_docker()["available"] is True
    assert _probe_powershell() is not None
    assert calls, "no child run observed"
    for kwargs in calls:
        assert kwargs.get("encoding") == "utf-8", kwargs
        assert kwargs.get("errors") == "replace", kwargs


# W7: a run waiting on stdin gets DEVNULL (EOF at once, rc 0).
def test_w7_stdin_is_devnull(tmp_path):
    folder = tmp_path / "w"
    folder.mkdir()
    (folder / "stdin_probe_win.py").write_text(
        "import sys\n"
        "data = sys.stdin.read()\n"
        'print("STDIN-LEN:%d" % len(data))\n',
        encoding="utf-8")
    log = folder / "logs" / "stdin.log"
    row = _actions.spawn_checked(
        "proj-fxwin-w7", "run-w7", str(folder),
        ["python", "stdin_probe_win.py"], str(log), "logs/stdin.log")
    assert _actions.wait_proc(row["proc"], 60.0) == "exited"
    assert row["proc"].returncode == 0, log
    assert "STDIN-LEN:0" in log.read_text(
        encoding="utf-8", errors="replace")
