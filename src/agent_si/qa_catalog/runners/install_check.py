"""K03 FXCATALOG set-A runner: install_check.

Verifies install readiness without ever installing: dependency
manifests must parse, required tools must resolve via shutil.which (a
missing tool is BLOCKED naming it), and params.files entries must
exist. Unparseable manifests or missing files are FAIL; no manifests
and no required files is UNSUPPORTED, never PASS.

Stdlib only. No DATA reads at runtime. No hardcoded PASS.
"""

from __future__ import annotations

import json
import os
import shutil
import sys

RUNNER_ID = "install_check"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {
    "tools": ["python", "pip", "node", "npm"],
    "network": False,
    "project_tooling": False,
    "local_subprocess": False,
    "env": [],
}
RUNNER_DESCRIPTION = (
    "Verifies install readiness without installing: manifests parse, "
    "tools resolve, required files exist."
)

_MANIFEST_NAMES = ("requirements.txt", "pyproject.toml", "package.json")


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
    manifests = params.get("manifests")
    if manifests is None:
        manifests = [
            item
            for item in _MANIFEST_NAMES
            if os.path.isfile(os.path.join(project_root, item))
        ]
    if not isinstance(manifests, list) or not all(
        isinstance(item, str) for item in manifests
    ):
        _emit(test_id, "BLOCKED", "bad_params manifests", 0, [])
        return 0
    files = params.get("files", [])
    if not isinstance(files, list) or not all(
        isinstance(item, str) for item in files
    ):
        _emit(test_id, "BLOCKED", "bad_params files", 0, [])
        return 0
    tools = params.get("tools")
    if tools is None:
        tools = ["python"]
        if os.path.isfile(os.path.join(project_root, "package.json")):
            tools += ["node", "npm"]
    if not isinstance(tools, list) or not all(
        isinstance(item, str) for item in tools
    ):
        _emit(test_id, "BLOCKED", "bad_params tools", 0, [])
        return 0

    name = RUNNER_ID + ".json"
    checks = []
    issues = []
    for rel in manifests:
        full = os.path.abspath(os.path.join(project_root, rel))
        if full != project_root and not full.startswith(project_root + os.sep):
            issues.append({"manifest": rel, "kind": "outside_project"})
            continue
        if not os.path.isfile(full):
            issues.append({"manifest": rel, "kind": "missing"})
            continue
        try:
            with open(full, "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            issues.append({"manifest": rel, "kind": "unreadable"})
            continue
        checks.append({"check": "manifest_present", "target": rel})
        lower = rel.lower()
        if lower.endswith(".json"):
            try:
                json.loads(text)
            except ValueError:
                issues.append({"manifest": rel, "kind": "unparseable"})
                continue
        elif lower.endswith(".toml"):
            try:
                import tomllib

                tomllib.loads(text)
            except ImportError:
                if "dependencies" not in text and "[" not in text:
                    issues.append({"manifest": rel, "kind": "unparseable"})
                    continue
            except ValueError:
                issues.append({"manifest": rel, "kind": "unparseable"})
                continue
        checks.append({"check": "manifest_parse", "target": rel})
    for tool in tools:
        _hit = shutil.which(tool)
        _is_stub = False
        if _hit is not None:
            try:
                _is_stub = ("windowsapps" in str(_hit).lower())
            except Exception:
                _is_stub = False
            if not _is_stub:
                try:
                    import os as _os2
                    if _os2.path.isfile(_hit) and _os2.path.getsize(_hit) == 0:
                        _is_stub = True
                except OSError:
                    _is_stub = False
        if _hit is None or _is_stub:
            with open(os.path.join(evidence_dir, name), "w", encoding="utf-8") as handle:
                json.dump({"checks": checks, "issues": issues}, handle, indent=2)
            _emit(
                test_id,
                "BLOCKED",
                "tool_not_installed: %s" % tool,
                0,
                [name],
            )
            return 0
        checks.append({"check": "tool_resolves", "target": tool})
    for rel in files:
        full = os.path.abspath(os.path.join(project_root, rel))
        if full != project_root and not full.startswith(project_root + os.sep):
            issues.append({"file": rel, "kind": "outside_project"})
            continue
        if not os.path.exists(full):
            issues.append({"file": rel, "kind": "missing"})
            continue
        checks.append({"check": "file_present", "target": rel})
    with open(os.path.join(evidence_dir, name), "w", encoding="utf-8") as handle:
        json.dump({"checks": checks, "issues": issues}, handle, indent=2)
    if not manifests and not files:
        _emit(test_id, "UNSUPPORTED", "no_manifests", 0, [name])
    elif issues:
        _emit(
            test_id,
            "FAIL",
            "%d finding(s) in %d check(s)" % (len(issues), len(checks)),
            len(checks) if checks else 1,
            [name],
        )
    else:
        _emit(
            test_id,
            "PASS",
            "%d check(s) ok" % len(checks),
            len(checks),
            [name],
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
