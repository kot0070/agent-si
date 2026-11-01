"""K03 FXCATALOG set-A runner: static_lint.

Syntax plus style lint over project sources: .py files must compile
and meet style (line length, no trailing whitespace, no tab indent);
.json files must parse; .yaml/.yml files must not use tab indentation.
Any violation is FAIL. No checkable file is UNSUPPORTED, never PASS.

Stdlib only. No DATA reads at runtime. No hardcoded PASS.
"""

from __future__ import annotations

import json
import os
import sys

RUNNER_ID = "static_lint"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 120
RUNNER_NEEDS = {
    "tools": [],
    "network": False,
    "project_tooling": False,
    "local_subprocess": False,
    "env": [],
}
RUNNER_DESCRIPTION = (
    "Syntax plus style lint: py compile, json parse, yaml tab check, "
    "line length and trailing whitespace style."
)

_SKIP_DIRS = (".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build")


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


def _iter_files(project_root, rel_paths):
    seen = []
    for rel in rel_paths:
        full = os.path.abspath(os.path.join(project_root, rel))
        if not full.startswith(project_root + os.sep) and full != project_root:
            continue
        if os.path.isfile(full):
            seen.append(full)
        elif os.path.isdir(full):
            for dirpath, dirnames, filenames in os.walk(full):
                dirnames[:] = [item for item in dirnames if item not in _SKIP_DIRS]
                for name in filenames:
                    lower = name.lower()
                    if lower.endswith((".py", ".json", ".yaml", ".yml")):
                        seen.append(os.path.join(dirpath, name))
    return sorted(set(seen))


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
    try:
        max_len = int(params.get("max_line_len", 120))
    except (TypeError, ValueError):
        _emit(test_id, "BLOCKED", "bad_params max_line_len", 0, [])
        return 0
    check_style = params.get("check_style", True)
    if not isinstance(check_style, bool):
        _emit(test_id, "BLOCKED", "bad_params check_style", 0, [])
        return 0

    files = _iter_files(project_root, paths)
    issues = []
    checked = 0
    for full in files:
        rel = os.path.relpath(full, project_root)
        try:
            with open(full, "r", encoding="utf-8") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError):
            continue
        lower = full.lower()
        checked += 1
        if lower.endswith(".py"):
            try:
                compile(text, rel, "exec")
            except SyntaxError as exc:
                issues.append(
                    {
                        "path": rel,
                        "line": exc.lineno or 0,
                        "kind": "syntax",
                        "detail": "python syntax error: %s" % exc.msg,
                    }
                )
                continue
            if check_style:
                for num, line in enumerate(text.splitlines(), 1):
                    stripped = line.rstrip("\n")
                    if len(stripped) > max_len:
                        issues.append(
                            {
                                "path": rel,
                                "line": num,
                                "kind": "style",
                                "detail": "line too long (%d > %d)"
                                % (len(stripped), max_len),
                            }
                        )
                    if stripped != stripped.rstrip():
                        issues.append(
                            {
                                "path": rel,
                                "line": num,
                                "kind": "style",
                                "detail": "trailing whitespace",
                            }
                        )
                    if stripped.startswith("\t") or "\t" in stripped[: len(stripped) - len(stripped.lstrip())]:
                        issues.append(
                            {
                                "path": rel,
                                "line": num,
                                "kind": "style",
                                "detail": "tab indentation",
                            }
                        )
        elif lower.endswith(".json"):
            try:
                json.loads(text)
            except ValueError as exc:
                issues.append(
                    {
                        "path": rel,
                        "line": 0,
                        "kind": "syntax",
                        "detail": "json parse error: %s" % exc,
                    }
                )
        else:
            for num, line in enumerate(text.splitlines(), 1):
                if "\t" in line:
                    issues.append(
                        {
                            "path": rel,
                            "line": num,
                            "kind": "syntax",
                            "detail": "yaml tab indentation",
                        }
                    )
                    break
    name = RUNNER_ID + ".json"
    with open(os.path.join(evidence_dir, name), "w", encoding="utf-8") as handle:
        json.dump(
            {"files_checked": checked, "issues": issues}, handle, indent=2
        )
    if not checked:
        _emit(test_id, "UNSUPPORTED", "no_checkable_files", 0, [name])
    elif issues:
        _emit(
            test_id,
            "FAIL",
            "%d lint issue(s) in %d file(s)" % (len(issues), checked),
            checked,
            [name],
        )
    else:
        _emit(test_id, "PASS", "clean %d file(s)" % checked, checked, [name])
    return 0


if __name__ == "__main__":
    sys.exit(main())
