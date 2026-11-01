"""K03 FXCATALOG set-A runner: policy_gate.

Denies dangerous shell content: destructive commands (recursive forced
deletes of roots, fork bombs, raw-disk writes, shutdowns) anywhere, and
pipe-to-shell / remote-fetch-pipe patterns in scanned files. Files
under params.allow_paths are trusted and skipped. Any violation is
FAIL; no shell-ish files is UNSUPPORTED, never PASS.

Stdlib only. No DATA reads at runtime. No hardcoded PASS.
"""

from __future__ import annotations

import json
import os
import re
import sys

RUNNER_ID = "policy_gate"
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
    "Denies destructive commands and pipe-to-shell patterns with a "
    "path allowlist for trusted files."
)

_SKIP_DIRS = (".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build")

_SCAN_SUFFIXES = (".sh", ".bash", ".ps1", ".bat", ".cmd", ".mk")
_SCAN_NAMES = ("Makefile", "makefile", "GNUmakefile")

_DENY = (
    ("rm_root", re.compile(r"\brm\s+-[a-z]*r[a-z]*f\s+/(?:\s|$)")),
    ("rm_home", re.compile(r"\brm\s+-[a-z]*r[a-z]*f\s+~(?:\s|/|$)")),
    ("fork_bomb", re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;?\s*:")),
    ("raw_disk", re.compile(r"\bdd\s+[^|\n]*\bof=/dev/")),
    ("mkfs", re.compile(r"(?<![\w-])mkfs(?:\s|$)")),
    ("shutdown", re.compile(r"(?<![\w-])(shutdown|halt|poweroff|reboot)(?:\s|$)")),
    ("windows_wipe", re.compile(r"(?i)\b(?:del|rd)\s+/s\s+/q\s+[A-Za-z]:\\?")),
    ("format_drive", re.compile(r"(?i)(?<![\w-])format\s+[A-Za-z]:")),
    ("pipe_to_shell", re.compile(r"\|\s*(?:sh|bash|zsh|dash|powershell|pwsh|cmd)(?:\s|;|$|&)")),
    ("curl_pipe", re.compile(r"(?i)\bcurl\b[^|\n]*\|\s*(?:sh|bash)")),
    ("wget_pipe", re.compile(r"(?i)\bwget\b[^|\n]*\|\s*(?:sh|bash)")),
    ("download_exec", re.compile(r"(?i)\b(?:curl|wget)\b[^|\n]*\|\s*")),
    ("invoke_expr", re.compile(r"(?i)\bInvoke-Expression\b")),
)


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
    wanted = params.get("paths")
    if wanted is not None and (
        not isinstance(wanted, list)
        or not all(isinstance(item, str) for item in wanted)
    ):
        _emit(test_id, "BLOCKED", "bad_params paths", 0, [])
        return 0
    allow = params.get("allow_paths", [])
    if not isinstance(allow, list) or not all(
        isinstance(item, str) for item in allow
    ):
        _emit(test_id, "BLOCKED", "bad_params allow_paths", 0, [])
        return 0
    allow_abs = {
        os.path.abspath(os.path.join(project_root, item)) for item in allow
    }

    candidates = []
    if wanted is not None:
        for rel in wanted:
            full = os.path.abspath(os.path.join(project_root, rel))
            if full != project_root and not full.startswith(project_root + os.sep):
                continue
            if os.path.isfile(full):
                candidates.append(full)
    else:
        for dirpath, dirnames, filenames in os.walk(project_root):
            dirnames[:] = [item for item in dirnames if item not in _SKIP_DIRS]
            for filename in filenames:
                lower = filename.lower()
                if lower.endswith(_SCAN_SUFFIXES) or filename in _SCAN_NAMES:
                    candidates.append(os.path.join(dirpath, filename))
    candidates = sorted(set(candidates))
    candidates = [
        item for item in candidates if item not in allow_abs
    ]

    name = RUNNER_ID + ".json"
    violations = []
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
            for rule, pattern in _DENY:
                if pattern.search(line):
                    violations.append(
                        {
                            "path": rel,
                            "line": num,
                            "rule": rule,
                            "detail": line.strip()[:160],
                        }
                    )
                    break
    with open(os.path.join(evidence_dir, name), "w", encoding="utf-8") as handle:
        json.dump(
            {"files_scanned": scanned, "violations": violations},
            handle,
            indent=2,
        )
    if not scanned:
        _emit(test_id, "UNSUPPORTED", "no_shell_files", 0, [name])
    elif violations:
        _emit(
            test_id,
            "FAIL",
            "%d violation(s) in %d file(s)" % (len(violations), scanned),
            scanned,
            [name],
        )
    else:
        _emit(test_id, "PASS", "clean %d file(s)" % scanned, scanned, [name])
    return 0


if __name__ == "__main__":
    sys.exit(main())
