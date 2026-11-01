"""K03 FXCATALOG set-A runner: build_check.

Verifies build recipes exist, are non-empty, carry no absolute paths
and fit a total size budget. Explicitly named recipes that are missing
or empty are FAIL; in auto mode with no recipe files the project gives
no input (UNSUPPORTED, never PASS).

Stdlib only. No DATA reads at runtime. No hardcoded PASS.
"""

from __future__ import annotations

import json
import os
import re
import sys

RUNNER_ID = "build_check"
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
    "Verifies build recipes exist, are non-empty, carry no absolute "
    "paths and fit a size budget."
)

_AUTO_RECIPES = (
    "Makefile",
    "makefile",
    "GNUmakefile",
    "package.json",
    "build.sh",
    "build.bat",
    "build.ps1",
)

_ABS_RE = re.compile(r"(?:[A-Za-z]:[\\/])|(?:(?<=[\s=:\"'(])/(?=[\w.]))")


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
    recipes = params.get("recipes")
    explicit = recipes is not None
    if recipes is None:
        recipes = []
        seen_paths = set()
        for item in _AUTO_RECIPES:
            full = os.path.join(project_root, item)
            if not os.path.isfile(full):
                continue
            key = os.path.normcase(os.path.abspath(full))
            if key in seen_paths:
                continue
            seen_paths.add(key)
            recipes.append(item)
    if not isinstance(recipes, list) or not all(
        isinstance(item, str) for item in recipes
    ):
        _emit(test_id, "BLOCKED", "bad_params recipes", 0, [])
        return 0
    try:
        max_bytes = int(params.get("max_bytes", 1000000))
    except (TypeError, ValueError):
        _emit(test_id, "BLOCKED", "bad_params max_bytes", 0, [])
        return 0
    if max_bytes <= 0:
        _emit(test_id, "BLOCKED", "bad_params max_bytes", 0, [])
        return 0

    if not recipes and not explicit:
        name = RUNNER_ID + ".json"
        with open(os.path.join(evidence_dir, name), "w", encoding="utf-8") as handle:
            json.dump({"recipes": [], "issues": [], "total_bytes": 0}, handle, indent=2)
        _emit(test_id, "UNSUPPORTED", "no_recipes", 0, [name])
        return 0

    issues = []
    checked = 0
    total = 0
    seen = []
    for rel in recipes:
        full = os.path.abspath(os.path.join(project_root, rel))
        if full != project_root and not full.startswith(project_root + os.sep):
            issues.append({"recipe": rel, "kind": "outside_project"})
            continue
        if not os.path.isfile(full):
            issues.append({"recipe": rel, "kind": "missing"})
            continue
        try:
            with open(full, "rb") as handle:
                data = handle.read()
        except OSError:
            issues.append({"recipe": rel, "kind": "unreadable"})
            continue
        checked += 1
        total += len(data)
        seen.append(rel)
        if not data:
            issues.append({"recipe": rel, "kind": "empty"})
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for num, line in enumerate(text.splitlines(), 1):
            if _ABS_RE.search(line):
                issues.append(
                    {
                        "recipe": rel,
                        "kind": "absolute_path",
                        "line": num,
                        "detail": line.strip()[:160],
                    }
                )
    if total > max_bytes:
        issues.append(
            {
                "recipe": "(total)",
                "kind": "size_budget",
                "detail": "%d bytes > %d" % (total, max_bytes),
            }
        )
    name = RUNNER_ID + ".json"
    with open(os.path.join(evidence_dir, name), "w", encoding="utf-8") as handle:
        json.dump(
            {"recipes": seen, "issues": issues, "total_bytes": total},
            handle,
            indent=2,
        )
    if not checked and explicit:
        _emit(test_id, "FAIL", "no recipes readable", 0, [name])
    elif issues:
        basis = checked if checked else len(recipes)
        _emit(
            test_id,
            "FAIL",
            "%d finding(s)" % len(issues),
            basis if basis else 1,
            [name],
        )
    else:
        _emit(
            test_id,
            "PASS",
            "%d recipe(s) %d bytes" % (checked, total),
            checked,
            [name],
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
