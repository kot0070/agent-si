"""K03 FXCATALOG set-A runner: dep_audit.

Audits dependency manifests (requirements*.txt, pyproject.toml,
package.json): every entry must be pinned to an exact version over a
secure reference. Unpinned entries, wildcards/ranges and insecure
(http://) URLs are FAIL. A clean manifest set is PASS; no manifests is
UNSUPPORTED, never PASS.

Stdlib only. No DATA reads at runtime. No hardcoded PASS.
"""

from __future__ import annotations

import json
import os
import re
import sys

RUNNER_ID = "dep_audit"
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
    "Audits dependency manifests: pinned exact versions only; "
    "unpinned, wildcard or insecure-URL entries FAIL."
)

_SKIP_DIRS = (".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build")

_PIP_SPEC_RE = re.compile(r"^(?P<name>[A-Za-z0-9_.\-]+(?:\[[^\]]*\])?)\s*(?P<spec>.*)$")
_NPM_EXACT_RE = re.compile(r"^=?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?$")


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


def _find_manifests(project_root, wanted):
    found = []
    if wanted is not None:
        for rel in wanted:
            full = os.path.abspath(os.path.join(project_root, rel))
            if full != project_root and not full.startswith(project_root + os.sep):
                continue
            if os.path.isfile(full):
                found.append(full)
        return sorted(set(found))
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [item for item in dirnames if item not in _SKIP_DIRS]
        for name in filenames:
            lower = name.lower()
            if (
                lower == "requirements.txt"
                or (lower.startswith("requirements") and lower.endswith(".txt"))
                or lower in ("pyproject.toml", "package.json")
            ):
                found.append(os.path.join(dirpath, name))
    return sorted(set(found))


def _pip_entries(lines):
    entries = []
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if text.startswith("-"):
            continue
        text = text.split("#", 1)[0].strip()
        if not text:
            continue
        entries.append(text)
    return entries


def _classify_pip(entry):
    low = entry.lower()
    if "http://" in low or low.startswith("git+http://"):
        return "insecure_url"
    if "://" in entry or entry.startswith("git+"):
        return "unpinned"
    match = _PIP_SPEC_RE.match(entry)
    if not match:
        return "unpinned"
    spec = match.group("spec").strip()
    if not spec:
        return "unpinned"
    if "*" in spec:
        return "wildcard"
    if "==" in spec and "*" not in spec:
        return None
    return "unpinned"


def _classify_npm(version):
    text = (version or "").strip()
    if not text:
        return "unpinned"
    low = text.lower()
    if low.startswith("http://") or low.startswith("git+http://"):
        return "insecure_url"
    if low.startswith(("http://", "https://", "git+", "file:", "npm:", "workspace:")):
        return "unpinned"
    if text in ("*", "latest", "next"):
        return "wildcard"
    if any(char in text for char in "^~xX<>|"):
        return "wildcard"
    if _NPM_EXACT_RE.match(text):
        return None
    return "unpinned"


def _pyproject_dependencies(text):
    try:
        import tomllib

        data = tomllib.loads(text)
        project = data.get("project", {}) if isinstance(data, dict) else {}
        deps = project.get("dependencies", [])
        if isinstance(deps, list) and all(isinstance(item, str) for item in deps):
            return deps, True
        return [], True
    except Exception:
        pass
    match = re.search(
        r"dependencies\s*=\s*\[(?P<body>.*?)\]", text, re.DOTALL
    )
    if not match:
        return [], False
    return re.findall(r"['\"]([^'\"]+)['\"]", match.group("body")), True


def main() -> int:
    try:
        project_root, test_id, params, evidence_dir = _read_input()
    except Exception as exc:
        _emit("", "BLOCKED", "bad_input: %s" % exc, 0, [])
        return 0
    os.makedirs(evidence_dir, exist_ok=True)
    wanted = params.get("manifests")
    if wanted is not None and (
        not isinstance(wanted, list)
        or not all(isinstance(item, str) for item in wanted)
    ):
        _emit(test_id, "BLOCKED", "bad_params manifests", 0, [])
        return 0
    manifests = _find_manifests(project_root, wanted)
    checked = 0
    issues = []
    for full in manifests:
        rel = os.path.relpath(full, project_root)
        try:
            with open(full, "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            issues.append(
                {"manifest": rel, "entry": "", "kind": "unreadable"}
            )
            continue
        lower = full.lower()
        if lower.endswith(".txt"):
            for entry in _pip_entries(text.splitlines()):
                checked += 1
                kind = _classify_pip(entry)
                if kind:
                    issues.append(
                        {"manifest": rel, "entry": entry, "kind": kind}
                    )
        elif lower.endswith("package.json"):
            try:
                data = json.loads(text)
            except ValueError:
                issues.append(
                    {"manifest": rel, "entry": "", "kind": "unparseable"}
                )
                continue
            if not isinstance(data, dict):
                issues.append(
                    {"manifest": rel, "entry": "", "kind": "unparseable"}
                )
                continue
            for section in ("dependencies", "devDependencies"):
                deps = data.get(section, {})
                if not isinstance(deps, dict):
                    continue
                for name, version in deps.items():
                    checked += 1
                    kind = _classify_npm(str(version))
                    if kind:
                        issues.append(
                            {
                                "manifest": rel,
                                "entry": "%s@%s" % (name, version),
                                "kind": kind,
                            }
                        )
        elif lower.endswith("pyproject.toml"):
            deps, parsed = _pyproject_dependencies(text)
            if not parsed:
                issues.append(
                    {"manifest": rel, "entry": "", "kind": "unparseable"}
                )
                continue
            for entry in deps:
                checked += 1
                kind = _classify_pip(entry)
                if kind:
                    issues.append(
                        {"manifest": rel, "entry": entry, "kind": kind}
                    )
    name = RUNNER_ID + ".json"
    with open(os.path.join(evidence_dir, name), "w", encoding="utf-8") as handle:
        json.dump(
            {
                "manifests": [os.path.relpath(item, project_root) for item in manifests],
                "entries_checked": checked,
                "issues": issues,
            },
            handle,
            indent=2,
        )
    if not manifests:
        _emit(test_id, "UNSUPPORTED", "no_manifests", 0, [name])
    elif not checked:
        _emit(test_id, "UNSUPPORTED", "no_entries", 0, [name])
    elif issues:
        _emit(
            test_id,
            "FAIL",
            "%d finding(s) in %d entr(ies)" % (len(issues), checked),
            checked,
            [name],
        )
    else:
        _emit(
            test_id, "PASS", "pinned %d entr(ies)" % checked, checked, [name]
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
