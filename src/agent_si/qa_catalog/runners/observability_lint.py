"""K03 FXCATALOG set-A runner: observability_lint.

Scans .py sources for unobservable code: print() calls (use logging)
and bare ``except:`` clauses (they swallow tracebacks). Any occurrence
is FAIL; a clean tree is PASS; no .py files is UNSUPPORTED, never PASS.

Stdlib only. No DATA reads at runtime. No hardcoded PASS.
"""

from __future__ import annotations

import json
import os
import re
import sys

RUNNER_ID = "observability_lint"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {
    "tools": [],
    "network": False,
    "project_tooling": False,
    "local_subprocess": False,
    "env": [],
}
RUNNER_DESCRIPTION = (
    "Flags print() calls and bare except: clauses in .py sources."
)

_SKIP_DIRS = (".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build")

_PRINT_RE = re.compile(r"(?<![\w.])print\s*\(")
_BARE_EXCEPT_RE = re.compile(r"^\s*except\s*:")


def _read_input():
    raw = sys.stdin.buffer.read().decode("utf-8")
    request = json.loads(raw)
    project_root = os.path.abspath(request.get("project_root", "") or ".")
    budgets = request.get("budgets", {}) or {}
    evidence_dir = os.path.abspath(budgets.get("evidence_dir", "") or ".")
    params = request.get("params", {}) or {}
    return project_root, request.get("test_id", ""), params, evidence_dir


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


def main() -> int:
    try:
        project_root, test_id, params, evidence_dir = _read_input()
    except Exception as exc:
        _emit("", "BLOCKED", "bad_input: %s" % exc, 0, [])
        return 0
    os.makedirs(evidence_dir, exist_ok=True)
    paths = params.get("paths", ["."])
    if not isinstance(paths, list) or not all(
        isinstance(item, str) for item in paths
    ):
        _emit(test_id, "BLOCKED", "bad_params paths", 0, [])
        return 0
    skip = params.get("skip", [])
    if not isinstance(skip, list) or not all(
        isinstance(item, str) for item in skip
    ):
        _emit(test_id, "BLOCKED", "bad_params skip", 0, [])
        return 0
    skip_abs = {os.path.abspath(os.path.join(project_root, item)) for item in skip}

    candidates = []
    for rel in paths:
        full = os.path.abspath(os.path.join(project_root, rel))
        if full != project_root and not full.startswith(project_root + os.sep):
            continue
        if os.path.isfile(full) and full.lower().endswith(".py"):
            candidates.append(full)
        elif os.path.isdir(full):
            for dirpath, dirnames, filenames in os.walk(full):
                dirnames[:] = [item for item in dirnames if item not in _SKIP_DIRS]
                for filename in filenames:
                    if filename.lower().endswith(".py"):
                        candidates.append(os.path.join(dirpath, filename))
    candidates = sorted(set(candidates) - skip_abs)

    findings = []
    scanned = 0
    for full in candidates:
        rel = os.path.relpath(full, project_root)
        try:
            with open(full, "r", encoding="utf-8") as handle:
                text = handle.read()
        except (OSError, UnicodeError):
            continue
        scanned += 1
        for num, line in enumerate(text.splitlines(), 1):
            code = line.split("#", 1)[0]
            if _PRINT_RE.search(code):
                findings.append(
                    {"path": rel, "line": num, "rule": "print_call"}
                )
            if _BARE_EXCEPT_RE.match(line):
                findings.append(
                    {"path": rel, "line": num, "rule": "bare_except"}
                )
    name = RUNNER_ID + ".json"
    with open(os.path.join(evidence_dir, name), "w", encoding="utf-8") as handle:
        json.dump(
            {"files_scanned": scanned, "findings": findings}, handle, indent=2
        )
    if not scanned:
        _emit(test_id, "UNSUPPORTED", "no_python_files", 0, [name])
    elif findings:
        _emit(
            test_id,
            "FAIL",
            "%d finding(s) in %d file(s)" % (len(findings), scanned),
            scanned,
            [name],
        )
    else:
        _emit(test_id, "PASS", "clean %d file(s)" % scanned, scanned, [name])
    return 0


if __name__ == "__main__":
    sys.exit(main())
