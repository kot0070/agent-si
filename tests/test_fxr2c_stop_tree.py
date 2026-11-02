"""FXR2C-1 RED: stop kills the whole process tree (real processes).

Parent spawns a sleeping grandchild; after Stop-all / run abort / host
kill both must be dead. Also: spawn assigns a Job Object on Windows,
_ATTACHED persists pid+create time, startup reap kills stale owners and
spares PID-reused strangers, one 5 s stop timeout everywhere.
"""

import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

import subprocess as _sp

from agent_si.backend import proc_tree as _tree
from agent_si.backend import stop_all as _stop_all

PARENT_SRC = (
    "import subprocess,sys,time;"
    "gc=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']);"
    "print(gc.pid,flush=True);"
    "gc.wait()"
)


def _alive(pid):
    if os.name == "nt":
        import ctypes

        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return False
        kernel.CloseHandle(handle)
        return True
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError):
        return False
    return True


def _spawn_tracked_parent():
    proc = _tree.spawn(
        [sys.executable, "-c", PARENT_SRC],
        stdout=_sp.PIPE,
        stderr=_sp.DEVNULL,
        text=True,
    )
    line = proc.stdout.readline().strip()
    grandchild_pid = int(line)
    return proc, grandchild_pid


def _reap(proc):
    try:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
    except Exception:
        pass
    try:
        proc.stdout.close()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "AGENT_SI_STOPALL_FILE", str(tmp_path / "attached.jsonl"))
    _stop_all.reset_state()
    _tree.reset_state()
    yield
    _stop_all.reset_state()
    _tree.reset_state()


def test_stop_all_kills_parent_and_grandchild():
    proc, grandchild = _spawn_tracked_parent()
    try:
        assert _alive(grandchild)
        _stop_all.attach_child("fxr2c-p1", "run-1", proc)
        receipt = _stop_all.request_stop_all("user")
        assert receipt.accepted is True
        deadline = time.time() + 15
        while time.time() < deadline:
            if proc.poll() is not None and not _alive(grandchild):
                break
            time.sleep(0.2)
        assert proc.poll() is not None, "parent survived stop-all"
        assert not _alive(grandchild), "grandchild survived stop-all"
    finally:
        _reap(proc)
        try:
            _tree.kill_tree_pid(grandchild)
        except Exception:
            pass


def test_run_abort_kill_procs_kills_tree():
    from agent_si.runtime.devrun import engine as _engine

    proc, grandchild = _spawn_tracked_parent()
    try:
        assert _alive(grandchild)
        lock = __import__("threading").Lock()
        _engine._kill_procs([proc], lock)
        deadline = time.time() + 15
        while time.time() < deadline:
            if proc.poll() is not None and not _alive(grandchild):
                break
            time.sleep(0.2)
        assert proc.poll() is not None, "parent survived run abort"
        assert not _alive(grandchild), "grandchild survived run abort"
    finally:
        _reap(proc)
        try:
            _tree.kill_tree_pid(grandchild)
        except Exception:
            pass


def test_killing_host_kills_grandchild():
    proc, grandchild = _spawn_tracked_parent()
    try:
        assert _alive(grandchild)
        _tree.kill_tree(proc)
        deadline = time.time() + 15
        while time.time() < deadline:
            if proc.poll() is not None and not _alive(grandchild):
                break
            time.sleep(0.2)
        assert proc.poll() is not None, "host survived kill"
        assert not _alive(grandchild), "grandchild survived host kill"
    finally:
        _reap(proc)
        try:
            _tree.kill_tree_pid(grandchild)
        except Exception:
            pass


def test_spawn_assigns_job_on_windows():
    proc, _grandchild = _spawn_tracked_parent()
    try:
        if os.name == "nt":
            assert _tree.job_of(proc) is not None, "no Job Object assigned"
    finally:
        _reap(proc)


def test_single_stop_timeout_constant():
    import inspect

    from agent_si.runtime.devrun import actions as _actions
    from agent_si.runtime.devrun import engine as _engine
    from agent_si.worker_tools import command_runner as _runner

    assert _tree.STOP_TIMEOUT_S == 5.0
    assert _stop_all.STOP_TIMEOUT_S == 5.0
    for module in (_stop_all, _engine, _actions, _runner, _tree):
        text = inspect.getsource(module)
        assert "timeout=5)" not in text and "timeout=5," not in text, (
            "hard-coded 5 s timeout left in %s" % module.__name__)


def test_startup_reap_kills_stale_and_spares_reused():
    proc = _tree.spawn(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
    try:
        pid = proc.pid
        create = _tree.proc_create_time(pid)
        assert create, "no create time for live pid"
        # Stranger with the same pid but a wrong create time (PID reuse).
        _tree.record_spawn(pid, "not-the-real-create-time",
                           "fxr2c-p9", "run-9")
        _stop_all.reset_state()
        killed = _stop_all.reap_stale_at_startup()
        assert killed == 0, "PID-reused stranger must be spared"
        assert proc.poll() is None, "spared stranger was killed"
        # Genuine stale owner: matching create time.
        _tree.record_spawn(pid, create, "fxr2c-p9", "run-9")
        killed = _stop_all.reap_stale_at_startup()
        assert killed == 1, "stale owner was not reaped"
        deadline = time.time() + 15
        while time.time() < deadline and proc.poll() is None:
            time.sleep(0.2)
        assert proc.poll() is not None, "stale owner survived reap"
        from agent_si.watcher import journal as _journal

        rows = _journal.stored_rows("", "STOP_ALL")
        assert any("startup reap" in row.summary for row in rows), (
            "startup reap was not journaled")
    finally:
        _reap(proc)
