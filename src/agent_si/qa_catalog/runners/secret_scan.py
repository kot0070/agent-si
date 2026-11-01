"""K03 FXCATALOG set-A runner: secret_scan.

Scans text files for committed secret patterns (cloud keys, provider
tokens, private-key blocks, password-style assignments). Findings are
reported by location and pattern name only; values are never copied to
evidence. params.allow holds exemption regexes matched per line. Any
unallowlisted hit is FAIL; a clean tree is PASS; no scannable file is
UNSUPPORTED, never PASS.

Stdlib only. No DATA reads at runtime. No hardcoded PASS.
"""

from __future__ import annotations

import json
import os
import re
import sys

RUNNER_ID = "secret_scan"
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
    "Scans text files for secret patterns with an allowlist; any "
    "unallowlisted hit FAILs."
)

_SKIP_DIRS = (".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build")

_PATTERNS = (
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\b(ghp_|gho_|ghu_|ghs_|ghr_|github_pat_)[A-Za-z0-9_]{8,}")),
    ("slack_token", re.compile(r"\bxox[bpras]-[A-Za-z0-9-]{8,}")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH )?PRIVATE KEY")),
    ("password_assign", re.compile(
        r"(?i)(?:password|passwd|pwd|secret|api[_-]?key|auth[_-]?token)\s*[:=]\s*['\"][^'\"]+['\"]"
    )),
    ("bearer_literal", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]{16,}")),
)

_MAX_BYTES = 2097152


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
    allow = params.get("allow", [])
    if not isinstance(allow, list) or not all(
        isinstance(item, str) for item in allow
    ):
        _emit(test_id, "BLOCKED", "bad_params allow", 0, [])
        return 0
    try:
        allow_res = [re.compile(item) for item in allow]
    except re.error as exc:
        _emit(test_id, "BLOCKED", "bad_params allow regex: %s" % exc, 0, [])
        return 0

    roots = []
    for rel in paths:
        full = os.path.abspath(os.path.join(project_root, rel))
        if full != project_root and not full.startswith(project_root + os.sep):
            continue
        if os.path.exists(full):
            roots.append(full)
    findings = []
    scanned = 0
    for root in roots:
        if os.path.isfile(root):
            candidates = [root]
        else:
            candidates = []
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [item for item in dirnames if item not in _SKIP_DIRS]
                for name in filenames:
                    candidates.append(os.path.join(dirpath, name))
        for full in sorted(candidates):
            rel = os.path.relpath(full, project_root)
            try:
                if os.path.getsize(full) > _MAX_BYTES:
                    continue
                with open(full, "r", encoding="utf-8") as handle:
                    text = handle.read()
            except (OSError, UnicodeError):
                continue
            scanned += 1
            for num, line in enumerate(text.splitlines(), 1):
                if any(item.search(line) for item in allow_res):
                    continue
                for pname, pattern in _PATTERNS:
                    if pattern.search(line):
                        findings.append(
                            {
                                "path": rel,
                                "line": num,
                                "pattern": pname,
                            }
                        )
                        break
    name = RUNNER_ID + ".json"
    with open(os.path.join(evidence_dir, name), "w", encoding="utf-8") as handle:
        json.dump(
            {"files_scanned": scanned, "findings": findings}, handle, indent=2
        )
    if not scanned:
        _emit(test_id, "UNSUPPORTED", "no_scannable_files", 0, [name])
    elif findings:
        _emit(
            test_id,
            "FAIL",
            "%d secret finding(s) in %d file(s)"
            % (len(findings), scanned),
            scanned,
            [name],
        )
    else:
        _emit(test_id, "PASS", "clean %d file(s)" % scanned, scanned, [name])
    return 0


if __name__ == "__main__":
    sys.exit(main())
