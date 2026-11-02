"""K03 FXCATALOG set-A runner: suite_invoke.

Runs one project test command (pytest/npm style) bounded: the tool is
resolved via shutil.which (python, py, node, npm), never sys.executable;
an unknown tool is BLOCKED naming the tool. The command runs with no
shell, cwd=project_root, and the host timeout. Exit 0 is PASS, any other
exit is FAIL. No test target discovered is UNSUPPORTED, never PASS.

Stdlib only. No DATA reads at runtime. No hardcoded PASS.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time

RUNNER_ID = "suite_invoke"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 180
RUNNER_NEEDS = {
    "tools": ["python", "py", "node", "npm"],
    "network": False,
    "project_tooling": False,
    "local_subprocess": True,
    "env": [],
}
RUNNER_DESCRIPTION = (
    "Runs a project test command (pytest/npm style) bounded: tool "
    "resolved via shutil.which, no shell, cwd is project_root."
)


def _read_input():
    raw = sys.stdin.buffer.read().decode("utf-8")
    request = json.loads(raw)
    project_root = os.path.abspath(request.get("project_root", "") or ".")
    budgets = request.get("budgets", {}) or {}
    try:
        timeout_s = float(budgets.get("timeout_s", 60.0))
    except (TypeError, ValueError):
        timeout_s = 60.0
    if not timeout_s > 0:
        timeout_s = 60.0
    timeout_s = min(timeout_s, 300.0)
    evidence_dir = os.path.abspath(budgets.get("evidence_dir", "") or ".")
    params = request.get("params", {}) or {}
    return project_root, request.get("test_id", ""), params, timeout_s, evidence_dir


def _emit(test_id, status, reason, assertions, evidence):
    sys.stdout.write(
        json.dumps(
            {
                "test_id": test_id,
                "runner_id": RUNNER_ID,
                "status": status,
                "reason": reason,
                "assertions": assertions,
                "evidence": evidence,
            }
        )
        + "\n"
    )
    sys.stdout.flush()


def _discover(project_root):
    """Auto tool+args when params name none: pytest, npm test, or nothing."""
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [
            item
            for item in dirnames
            if item not in (".git", "node_modules", "__pycache__", ".venv", "venv")
        ]
        for name in filenames:
            if name.startswith("test_") and name.endswith(".py"):
                return "python", ["-m", "pytest", "-q"]
            if name == "package.json":
                try:
                    with open(
                        os.path.join(dirpath, name), "r", encoding="utf-8"
                    ) as handle:
                        data = json.load(handle)
                except (OSError, ValueError):
                    continue
                scripts = data.get("scripts", {}) if isinstance(data, dict) else {}
                if isinstance(scripts, dict) and "test" in scripts:
                    return "npm", ["test"]
        break
    return None, []


def main() -> int:
    try:
        project_root, test_id, params, timeout_s, evidence_dir = _read_input()
    except Exception as exc:
        _emit("", "BLOCKED", "bad_input: %s" % exc, 0, [])
        return 0
    os.makedirs(evidence_dir, exist_ok=True)

    def fail(reason):
        path = os.path.join(evidence_dir, RUNNER_ID + ".json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"tool": None, "args": [], "reason": reason}, handle)
        return path

    tool = params.get("tool")
    args = params.get("args")
    if tool is None and args is None:
        tool, args = _discover(project_root)
        if tool is None:
            path = fail("no test target discovered")
            _emit(test_id, "UNSUPPORTED", "no_test_target", 0, [RUNNER_ID + ".json"])
            return 0
    if not isinstance(tool, str) or not tool:
        path = fail("bad tool param")
        _emit(test_id, "BLOCKED", "bad_params tool", 0, [RUNNER_ID + ".json"])
        return 0
    if args is None:
        args = []
    if (
        not isinstance(args, list)
        or not all(isinstance(item, str) for item in args)
    ):
        path = fail("bad args param")
        _emit(test_id, "BLOCKED", "bad_params args", 0, [RUNNER_ID + ".json"])
        return 0
    resolved = shutil.which(tool)
    if resolved is not None:
        try:
            _low = str(resolved).lower()
        except Exception:
            _low = ""
        _is_stub = ("windowsapps" in _low)
        if not _is_stub:
            try:
                import os as _os
                if _os.path.isfile(resolved) and _os.path.getsize(resolved) == 0:
                    _is_stub = True
            except OSError:
                _is_stub = False
        if _is_stub:
            resolved = None
    if resolved is None:
        path = fail("tool not installed: %s" % tool)
        _emit(
            test_id,
            "BLOCKED",
            "tool_not_installed: %s" % tool,
            0,
            [RUNNER_ID + ".json"],
        )
        return 0
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [resolved] + args,
            cwd=project_root,
            capture_output=True,
            timeout=timeout_s,
            shell=False,
        )
        duration_ms = (time.perf_counter() - started) * 1000.0
        tail = (completed.stdout or b"")[-65536:].decode("utf-8", "replace")
        tail += (completed.stderr or b"")[-65536:].decode("utf-8", "replace")
        record = {
            "tool": tool,
            "resolved": resolved,
            "args": args,
            "returncode": completed.returncode,
            "duration_ms": round(duration_ms, 1),
            "output_tail": tail[-8000:],
        }
        path = os.path.join(evidence_dir, RUNNER_ID + ".json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2)
        if completed.returncode == 0:
            _emit(test_id, "PASS", "exit 0", 1, [RUNNER_ID + ".json"])
        else:
            _emit(
                test_id,
                "FAIL",
                "exit %s" % completed.returncode,
                1,
                [RUNNER_ID + ".json"],
            )
        return 0
    except subprocess.TimeoutExpired:
        duration_ms = (time.perf_counter() - started) * 1000.0
        record = {
            "tool": tool,
            "resolved": resolved,
            "args": args,
            "returncode": None,
            "duration_ms": round(duration_ms, 1),
            "output_tail": "timeout",
        }
        path = os.path.join(evidence_dir, RUNNER_ID + ".json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2)
        _emit(test_id, "FAIL", "command_timeout", 1, [RUNNER_ID + ".json"])
        return 0
    except Exception as exc:
        path = fail("spawn failed: %s" % exc)
        _emit(test_id, "BLOCKED", "spawn_failed", 0, [RUNNER_ID + ".json"])
        return 0


if __name__ == "__main__":
    sys.exit(main())
