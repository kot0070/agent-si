"""K03 FXCATALOG set-A runner: file_roundtrip.

Writes random bytes to a payload file in evidence_dir, reads them
back and compares sha256, then writes a JSON sidecar and reparses it.
Any mismatch (or params.corrupt forcing one, or a params.expect_sha256
that differs) is FAIL; a clean roundtrip is PASS.

Stdlib only. No DATA reads at runtime. No hardcoded PASS.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

RUNNER_ID = "file_roundtrip"
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
    "Writes, reads back and sha256-compares a payload file plus a "
    "JSON sidecar reparse."
)

_DEFAULT_SIZE = 4096
_MAX_SIZE = 16777216


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
    name = RUNNER_ID + ".json"

    def report(payload, status, reason, assertions, extra=()):
        with open(os.path.join(evidence_dir, name), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        _emit(test_id, status, reason, assertions, [name] + list(extra))

    filename = params.get("path", "file_roundtrip.bin")
    if not isinstance(filename, str) or not filename:
        report({}, "BLOCKED", "bad_params path", 0)
        return 0
    if (
        os.path.basename(filename) != filename
        or filename in (".", "..")
        or os.path.isabs(filename)
    ):
        report({}, "BLOCKED", "bad_params path", 0)
        return 0
    try:
        size = int(params.get("size", _DEFAULT_SIZE))
    except (TypeError, ValueError):
        report({}, "BLOCKED", "bad_params size", 0)
        return 0
    if size <= 0 or size > _MAX_SIZE:
        report({}, "BLOCKED", "bad_params size", 0)
        return 0
    corrupt = params.get("corrupt", False)
    if not isinstance(corrupt, bool):
        report({}, "BLOCKED", "bad_params corrupt", 0)
        return 0
    expect = params.get("expect_sha256")
    if expect is not None and not isinstance(expect, str):
        report({}, "BLOCKED", "bad_params expect_sha256", 0)
        return 0

    payload_path = os.path.join(evidence_dir, filename)
    sidecar = filename + ".sha256.json"
    sidecar_path = os.path.join(evidence_dir, sidecar)
    try:
        blob = os.urandom(size)
        with open(payload_path, "wb") as handle:
            handle.write(blob)
        if corrupt:
            with open(payload_path, "r+b") as handle:
                first = handle.read(1)
                handle.seek(0)
                handle.write(bytes([first[0] ^ 0xFF]))
        with open(payload_path, "rb") as handle:
            back = handle.read()
    except OSError as exc:
        report({}, "BLOCKED", "unwritable_evidence: %s" % exc, 0)
        return 0
    written_sha = hashlib.sha256(blob).hexdigest()
    read_sha = hashlib.sha256(back).hexdigest()
    if read_sha != written_sha:
        report(
            {"sha256_written": written_sha, "sha256_read": read_sha, "size": size},
            "FAIL",
            "sha_mismatch",
            1,
            (filename,),
        )
        return 0
    if expect is not None and read_sha != expect.lower():
        report(
            {"sha256": read_sha, "size": size},
            "FAIL",
            "expect_sha256_mismatch",
            1,
            (filename,),
        )
        return 0
    record = {"sha256": read_sha, "size": size}
    try:
        with open(sidecar_path, "w", encoding="utf-8") as handle:
            json.dump(record, handle)
        with open(sidecar_path, "r", encoding="utf-8") as handle:
            reparsed = json.load(handle)
    except (OSError, ValueError) as exc:
        report({"sha256": read_sha, "size": size}, "FAIL", "sidecar_error: %s" % exc, 2, (filename,))
        return 0
    if reparsed != record:
        report(
            {"sha256": read_sha, "size": size},
            "FAIL",
            "sidecar_mismatch",
            2,
            (filename, sidecar),
        )
        return 0
    report(
        {"sha256": read_sha, "size": size},
        "PASS",
        "roundtrip ok %d bytes" % size,
        2,
        (filename, sidecar),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
