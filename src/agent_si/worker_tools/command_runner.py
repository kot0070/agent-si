"""FXESTOP lane-L4 real subprocess command runner.

Spawns real OS child processes (never threads, fakes or simulations)
for the worker-tool command routes, enforces the real toolguard
allowlist before spawning, and attaches every spawned child to
:func:`agent_si.backend.stop_all.attach_child` so a later
``POST /api/v1/stop-all`` stops it. Product code uses portable APIs
only (:func:`os.getcwd`); no machine paths.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import threading

from agent_si.backend import stop_all as _stop_all

__all__ = (
    "COMMAND_ALLOWLIST",
    "MAX_RUN_ID_LEN",
    "command_status",
    "reset_state",
    "start_command",
    "tracked",
)

#: Portable command names allowed to spawn. The guard below still runs
#: the real ``toolguard.evaluate`` on every spawn; this list only names
#: the tool identities this runner may start (the endless TEST command
#: ``python -c "while True: pass"`` passes it verbatim).
COMMAND_ALLOWLIST: tuple[str, ...] = ("python", "python3")

#: Longest accepted run id; longer values are refused, never truncated.
MAX_RUN_ID_LEN: int = 128

_RUNS: dict[str, subprocess.Popen] = {}
_LOCK = threading.Lock()


def _checked_run_id(run_id: object) -> str:
    """Return ``run_id`` when it is a usable non-empty short string."""
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")
    if len(run_id) > MAX_RUN_ID_LEN:
        raise ValueError("run_id longer than 128 chars is refused")
    return run_id


def _checked_argv(argv: object) -> list[str]:
    """Return ``argv`` as a word list; shell strings are refused."""
    if isinstance(argv, (str, bytes, bytearray)):
        raise TypeError("argv must be a list of words, never a shell string")
    try:
        items = list(argv)  # type: ignore[arg-type]
    except TypeError:
        raise TypeError("argv must be a list of words") from None
    if not items:
        raise ValueError("argv must not be empty")
    for item in items:
        if not isinstance(item, str) or not item:
            raise TypeError("argv must be a list of non-empty words")
    return items


def _portable_tool_name(tool: str) -> str:
    """Derive the portable tool name the real guard evaluates.

    An absolute interpreter path (such as the current interpreter,
    which lives outside the workspace by installation) maps to its
    bare command name; a bare word maps to itself. Only the tool
    identity is normalized — every argument word still reaches the
    real guard verbatim, so shell-fragment, path, installer/fetch and
    permission rules keep refusing exactly as the guard reports them.
    One uniform product rule, never a test-only bypass.
    """
    base = tool.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for suffix in (".exe", ".bat", ".cmd", ".com"):
        if base.endswith(suffix) and len(base) > len(suffix):
            base = base[: -len(suffix)]
    return base


def _guard_allow(argv: list[str], project_id: str, run_id: str) -> None:
    """Run the real toolguard allowlist; refuse closed on any denial."""
    from agent_si.toolguard.guard import evaluate as _evaluate

    head = _portable_tool_name(argv[0])
    if head not in COMMAND_ALLOWLIST:
        raise PermissionError(
            f"tool {argv[0]!r} is outside the command allowlist"
        )
    verdict = _evaluate(
        [head, *argv[1:]],
        "R0",
        {"subject": project_id, "task": f"command:{run_id}"},
    )
    if not isinstance(verdict, dict) or verdict.get("decision") != "allow":
        reason = verdict.get("reason") if isinstance(verdict, dict) else verdict
        raise PermissionError(f"toolguard denied: {reason}")


def start_command(
    project_id: str, run_id: str, argv: list[str]
) -> dict[str, object]:
    """Spawn one real OS command and attach it for stop-all.

    ``run_id`` is a non-empty string of at most 128 chars; a duplicate
    of a still-running command is refused. ``argv`` is a word list
    whose tool identity passes :data:`COMMAND_ALLOWLIST` and the real
    ``toolguard.evaluate`` before anything spawns. The child starts
    with ``cwd=os.getcwd()`` and is synchronously attached via
    :func:`agent_si.backend.stop_all.attach_child`. Returns
    ``{run_id, pid}``.
    """
    if not isinstance(project_id, str) or not project_id:
        raise ValueError("project_id must be a non-empty string")
    rid = _checked_run_id(run_id)
    words = _checked_argv(argv)
    with _LOCK:
        existing = _RUNS.get(rid)
        if existing is not None and existing.poll() is None:
            raise ValueError(f"duplicate run_id {rid!r} is refused")
    _guard_allow(words, project_id, rid)
    try:
        from agent_si.backend import proc_tree as _proc_tree

        proc = _proc_tree.spawn(
            words,
            cwd=os.getcwd(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise ValueError(f"cannot spawn command: {exc}") from exc
    with _LOCK:
        current = _RUNS.get(rid)
        if current is not None and current is not proc \
                and current.poll() is None:
            with contextlib.suppress(Exception):
                if proc.poll() is None:
                    proc.terminate()
            raise ValueError(f"duplicate run_id {rid!r} is refused")
        _RUNS[rid] = proc
    _stop_all.attach_child(project_id, rid, proc)
    return {"run_id": rid, "pid": proc.pid}


def command_status(run_id: str) -> dict[str, object]:
    """Return ``{run_id, pid, alive}`` for one tracked command."""
    rid = _checked_run_id(run_id)
    with _LOCK:
        proc = _RUNS.get(rid)
    if proc is None:
        raise LookupError(f"unknown run_id {rid!r}")
    return {"run_id": rid, "pid": proc.pid, "alive": proc.poll() is None}


def tracked() -> tuple[str, ...]:
    """Return every tracked run id, oldest first."""
    with _LOCK:
        return tuple(_RUNS)


def reset_state() -> None:
    """Terminate every tracked child tree and drop registry (isolation)."""
    from agent_si.backend import proc_tree as _proc_tree

    with _LOCK:
        procs = list(_RUNS.values())
        _RUNS.clear()
    for proc in procs:
        with contextlib.suppress(Exception):
            _proc_tree.terminate_tree(proc)
