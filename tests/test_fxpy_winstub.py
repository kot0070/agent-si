"""FXPY RED: WindowsApps Store stub is NOT a python (neighbour of fxwin)."""
import os
import shutil
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.runtime.devrun import actions as _actions


def _make_stub_dir(tmp_path):
    d = tmp_path / "WindowsApps"
    d.mkdir()
    for name in ("python.exe", "python3.exe"):
        (d / name).write_bytes(b"")
    return str(d)


def test_fxpy_stub_only_is_missing(tmp_path, monkeypatch):
    stub = _make_stub_dir(tmp_path)
    monkeypatch.setenv("PATH", stub)
    # shutil.which finds the stub today (bug): resolve must NOT return it
    found = shutil.which("python")
    assert found is not None, "test setup: stub not on PATH"
    resolved = _actions.resolve_argv(["python", "--version"])
    assert "WindowsApps" not in resolved[0], "stub leaked: %r" % (resolved,)
    assert os.path.getsize(found) == 0 or "WindowsApps" in found
    missing = _actions._missing_head(["python", "--version"], str(tmp_path))
    assert missing == "python", missing
    # nothing is spawned: Popen must never run
    import subprocess as _sp

    def _boom(*a, **k):
        raise AssertionError("stub must never spawn")

    monkeypatch.setattr(_sp, "Popen", _boom)
    try:
        _actions.spawn_checked(
            "p", "r", str(tmp_path),
            ["python", "--version"],
            str(tmp_path / "x.log"), "x.log")
    except _actions.SpawnNotInstalled as exc:
        assert "python" in str(exc).lower(), str(exc)
    else:
        raise AssertionError("expected SpawnNotInstalled")


def test_fxpy_real_wins_over_stub(tmp_path, monkeypatch):
    stub = _make_stub_dir(tmp_path)
    realdir = tmp_path / "realbin"
    realdir.mkdir()
    import shutil as _sh

    _sh.copy(sys.executable, str(realdir / "python.exe"))
    monkeypatch.setenv("PATH", os.pathsep.join([str(realdir), stub]))
    resolved = _actions.resolve_argv(["python", "--version"])
    assert "WindowsApps" not in resolved[0], resolved
    assert resolved[0].lower().endswith("python.exe"), resolved


def test_fxpy_stub_falls_back_to_py(monkeypatch):
    def _fake(cmd, *a, **k):
        low = str(cmd).lower()
        if low in ("python", "python3", "pytest"):
            return "C:\\Users\\t\\AppData\\Local\\Microsoft\\WindowsApps\\python.exe"
        if low == "py":
            return "C:\\Windows\\py.exe"
        return None

    monkeypatch.setattr(shutil, "which", _fake)
    assert _actions.resolve_argv(["python", "--version"]) == [
        "C:\\Windows\\py.exe", "--version"]
    assert _actions.resolve_argv(["pytest", "-q"]) == [
        "C:\\Windows\\py.exe", "-m", "pytest", "-q"]
