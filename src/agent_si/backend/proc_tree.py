"""Process-tree spawn/stop: Job Object at spawn, taskkill fallback, reap.

One stop timeout (STOP_TIMEOUT_S, 5 s) for every stop path in this lane
set (stop_all, devrun engine/actions, command_runner). Spawns assign the
child to a Windows Job Object with KILL_ON_JOB_CLOSE (best-effort: the
tree dies on Stop and on app close or crash); every stop also kills the
tree via ``taskkill /T /F /PID`` (Windows) or process-group kill
(POSIX). Attached pids plus their creation times persist in a data file
so a restart reaps stale owners after checking the create time (a live
pid with a different create time is a PID reuse and is spared); every
reap is journaled. Standard library plus ctypes only.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import threading
from typing import Any, Dict, List

__all__ = (
    "STOP_TIMEOUT_S",
    "quiet_flags",
    "spawn",
    "job_of",
    "kill_tree",
    "kill_tree_pid",
    "terminate_tree",
    "proc_create_time",
    "proc_alive",
    "record_spawn",
    "drop_records",
    "read_records",
    "record_file",
    "reset_state",
)

#: One stop timeout (seconds) for every stop path in this lane set.
STOP_TIMEOUT_S = 5.0


def quiet_flags() -> int:
    """creationflags hiding the console of every child (Windows only).

    CREATE_NO_WINDOW on Windows, 0 elsewhere: pass as ``creationflags``
    to every subprocess.Popen/run/call (and asyncio
    create_subprocess_*) so a windowless parent never flashes a console
    child. Flag only: streams, stdin and argv are untouched.
    """
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))

#: Open Job Object handles: kept so the job outlives every spawn call.
_JOBS: List[Any] = []
_JOBS_LOCK = threading.Lock()

#: Spawned procs to their job handles (Windows only, introspection).
_PROC_JOBS: Dict[int, Any] = {}


def _keep_job(job: Any) -> None:
    """Retain one job handle for the life of this process."""
    with _JOBS_LOCK:
        _JOBS.append(job)


def job_of(proc: Any) -> Any:
    """Return the Job Object handle assigned at spawn, or None."""
    try:
        return _PROC_JOBS.get(int(proc.pid))
    except Exception:
        return None


def _assign_to_job(proc: Any) -> None:
    """Assign one child to a KILL_ON_JOB_CLOSE job (Windows, best-effort).

    Adapted from the known-good job_object pattern: create plus limit
    plus assign, every failure a silent pass (the taskkill fallback
    still kills the tree on stop).
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes

        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return
        kernel = windll.kernel32
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            return

        class _Limits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class _Extended(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", _Limits),
                ("IoInfo", ctypes.c_byte * 48),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        info = _Extended()
        info.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        ok = kernel.SetInformationJobObject(
            job, 9, ctypes.byref(info), ctypes.sizeof(info)
        )
        if not ok:
            with contextlib.suppress(Exception):
                kernel.CloseHandle(job)
            return
        handle = getattr(proc, "_handle", None)
        if handle is None:
            with contextlib.suppress(Exception):
                kernel.CloseHandle(job)
            return
        assigned = kernel.AssignProcessToJobObject(job, int(handle))
        if not assigned:
            with contextlib.suppress(Exception):
                kernel.CloseHandle(job)
            return
        _keep_job(job)
        with contextlib.suppress(Exception):
            _PROC_JOBS[int(proc.pid)] = job
    except Exception:
        pass


def spawn(argv: List[str], **kwargs: Any) -> "subprocess.Popen":
    """Spawn one child and assign it to a KILL_ON_JOB_CLOSE job.

    Same signature as subprocess.Popen; the job assignment is
    best-effort (a silent pass keeps the plain child, whose tree the
    taskkill fallback still kills on stop). On POSIX the child starts
    a new session so the fallback kills only its own group. On Windows
    quiet_flags() is ORed into creationflags (kept when the caller
    passes its own flags, e.g. CREATE_NEW_PROCESS_GROUP), so the child
    never flashes a console.
    """
    if os.name != "nt":
        kwargs.setdefault("start_new_session", True)
    else:
        kwargs["creationflags"] = (
            int(kwargs.get("creationflags", 0) or 0) | quiet_flags())
    proc = subprocess.Popen(argv, **kwargs)
    _assign_to_job(proc)
    return proc


def kill_tree_pid(pid: int) -> None:
    """Kill one pid plus its child tree by id; never raises, never by name.

    Adapted from the known-good taskkill pattern: ``taskkill /PID /T
    /F`` kills by PID tree (never by name); the POSIX leg kills the
    process group, falling back to the bare pid.
    """
    try:
        ident = int(pid)
    except (TypeError, ValueError):
        return
    if os.name == "nt":
        with contextlib.suppress(Exception):
            subprocess.run(
                ["taskkill", "/PID", str(ident), "/T", "/F"],
                capture_output=True,
                timeout=STOP_TIMEOUT_S,
                creationflags=quiet_flags(),
            )
    else:
        import signal

        with contextlib.suppress(Exception):
            os.killpg(os.getpgid(ident), signal.SIGKILL)
        with contextlib.suppress(Exception):
            os.kill(ident, signal.SIGKILL)


def kill_tree(proc: Any) -> None:
    """Stop one child plus its tree, then reap the handle; never raises."""
    try:
        pid = int(proc.pid)
    except Exception:
        return
    kill_tree_pid(pid)
    with contextlib.suppress(Exception):
        proc.kill()
    with contextlib.suppress(Exception):
        proc.wait(timeout=STOP_TIMEOUT_S)


def terminate_tree(proc: Any, timeout: float = STOP_TIMEOUT_S) -> bool:
    """Terminate plus tree-kill one child; True when it is reaped dead.

    The tree kill runs while the parent is still alive: a parent
    that exits fast on terminate would otherwise orphan its
    grandchildren before taskkill can find the tree.
    """
    try:
        if proc.poll() is not None:
            return True
    except Exception:
        return False
    try:
        pid = int(proc.pid)
    except Exception:
        return proc.poll() is not None
    kill_tree_pid(pid)
    with contextlib.suppress(Exception):
        proc.terminate()
    with contextlib.suppress(Exception):
        proc.kill()
    try:
        proc.wait(timeout=timeout)
    except Exception:
        kill_tree_pid(pid)
        with contextlib.suppress(Exception):
            proc.wait(timeout=timeout)
    return proc.poll() is not None


def proc_alive(pid: int) -> bool:
    """True when one pid names a live process; never raises."""
    try:
        ident = int(pid)
    except (TypeError, ValueError):
        return False
    if os.name == "nt":
        try:
            import ctypes

            kernel = ctypes.windll.kernel32
            handle = kernel.OpenProcess(0x1000, False, ident)
            if not handle:
                return False
            kernel.CloseHandle(handle)
            return True
        except Exception:
            return False
    try:
        os.kill(ident, 0)
    except (OSError, ValueError, OverflowError):
        return False
    return True


def proc_create_time(pid: int) -> str:
    """Creation stamp of one live pid, or empty when unreadable.

    Windows reads GetProcessTimes; POSIX reads /proc/<pid>/stat field
    22 (starttime). Either is only ever compared for equality with the
    stamp stored at spawn, so a PID reuse (different stamp) is spared.
    """
    try:
        ident = int(pid)
    except (TypeError, ValueError):
        return ""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            kernel = ctypes.windll.kernel32
            handle = kernel.OpenProcess(0x1000, False, ident)
            if not handle:
                return ""
            try:
                created = wintypes.FILETIME()
                _exited = wintypes.FILETIME()
                _kern = wintypes.FILETIME()
                _user = wintypes.FILETIME()
                ok = kernel.GetProcessTimes(
                    handle, ctypes.byref(created),
                    ctypes.byref(_exited), ctypes.byref(_kern),
                    ctypes.byref(_user))
                if not ok:
                    return ""
                stamp = (int(created.dwHighDateTime) << 32) | int(
                    created.dwLowDateTime)
                return "nt-%d" % stamp
            finally:
                kernel.CloseHandle(handle)
        except Exception:
            return ""
    try:
        with open("/proc/%d/stat" % ident, encoding="utf-8") as handle:
            stat = handle.read()
        tail = stat.rsplit(")", 1)[-1].split()
        if len(tail) >= 20:
            return "posix-%s" % tail[19]
    except Exception:
        pass
    return ""


def _data_dir() -> str:
    """Data dir: AGENT_SI_DATA_DIR, else %LOCALAPPDATA%/AgentSI/data."""
    raw = os.environ.get("AGENT_SI_DATA_DIR", "")
    if raw.strip():
        return os.path.abspath(raw.strip())
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", "")
        if base.strip():
            return os.path.join(base.strip(), "AgentSI", "data")
    return os.path.join(os.path.expanduser("~"), ".agent_si")


def record_file() -> str:
    """Attached-child record file (pid plus create time, JSON lines)."""
    return os.path.join(_data_dir(), "stop_all_attached.jsonl")


def _record_path() -> str:
    """Record file honoring the probe override env."""
    override = os.environ.get("AGENT_SI_STOPALL_FILE", "")
    if override.strip():
        return os.path.abspath(override.strip())
    return record_file()


def record_spawn(pid: int, create_time: str, project_id: str,
                 run_id: str) -> None:
    """Append one attached pid plus its creation stamp; never raises."""
    try:
        path = _record_path()
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        row = {"pid": int(pid), "create_time": str(create_time),
               "project_id": str(project_id), "run_id": str(run_id)}
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
    except Exception:
        pass


def read_records() -> List[Dict[str, Any]]:
    """Read every recorded row; corrupt lines are skipped, never raised."""
    rows: List[Dict[str, Any]] = []
    try:
        with open(_record_path(), encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict) and "pid" in row:
                    rows.append(row)
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return rows


def drop_records(pids: Any) -> None:
    """Drop recorded rows for finished pids; never raises."""
    try:
        gone = {int(pid) for pid in pids}
    except Exception:
        return
    try:
        path = _record_path()
        kept = [row for row in read_records()
                if int(row.get("pid", -1)) not in gone]
        with open(path, "w", encoding="utf-8") as handle:
            for row in kept:
                handle.write(json.dumps(row) + "\n")
    except Exception:
        pass


def reset_state() -> None:
    """Drop retained job-introspection rows (probe isolation)."""
    with contextlib.suppress(Exception):
        _PROC_JOBS.clear()
