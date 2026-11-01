"""K03 FXCATALOG set-A runner: net_probe.

Opens TCP connections to loopback targets (host, port) and compares
the outcome with params expect_open. Every host must resolve to
loopback only; anything else is BLOCKED with reason non_loopback and
is never contacted. Mismatches are FAIL; no targets is UNSUPPORTED,
never PASS.

Stdlib only. Never real services: loopback only. No hardcoded PASS.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import sys
import time

RUNNER_ID = "net_probe"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 120
RUNNER_NEEDS = {
    "tools": [],
    "network": True,
    "project_tooling": False,
    "local_subprocess": False,
    "env": [],
}
RUNNER_DESCRIPTION = (
    "TCP open/closed probes against loopback targets; non-loopback "
    "targets BLOCKED."
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


def _loopback_ok(host):
    try:
        parsed = ipaddress.ip_address(host)
        if parsed.is_loopback:
            return True, ""
        return False, "non_loopback"
    except ValueError:
        pass
    if host.lower() == "localhost":
        return True, ""
    try:
        infos = socket.getaddrinfo(host, None, family=socket.AF_UNSPEC)
    except socket.gaierror:
        return False, "unresolvable_host"
    if not infos:
        return False, "unresolvable_host"
    for info in infos:
        try:
            if not ipaddress.ip_address(info[4][0]).is_loopback:
                return False, "non_loopback"
        except ValueError:
            return False, "non_loopback"
    return True, ""


def main() -> int:
    try:
        project_root, test_id, params, timeout_s, evidence_dir = _read_input()
    except Exception as exc:
        _emit("", "BLOCKED", "bad_input: %s" % exc, 0, [])
        return 0
    os.makedirs(evidence_dir, exist_ok=True)
    name = RUNNER_ID + ".json"

    def report(payload, status, reason, assertions):
        with open(os.path.join(evidence_dir, name), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        _emit(test_id, status, reason, assertions, [name])

    targets = params.get("targets")
    if targets is None:
        report({}, "UNSUPPORTED", "no_targets", 0)
        return 0
    if not isinstance(targets, list) or not all(
        isinstance(item, dict) for item in targets
    ):
        report({}, "BLOCKED", "bad_params targets", 0)
        return 0
    if not targets:
        report({}, "UNSUPPORTED", "no_targets", 0)
        return 0

    deadline = time.perf_counter() + max(1.0, timeout_s)
    results = []
    failures = []
    for target in targets:
        host = target.get("host", "127.0.0.1")
        try:
            port = int(target.get("port", 0))
        except (TypeError, ValueError):
            report({}, "BLOCKED", "bad_params target port", 0)
            return 0
        if not isinstance(host, str) or not host or not 0 < port < 65536:
            report({}, "BLOCKED", "bad_params target host/port", 0)
            return 0
        want_open = target.get("expect_open", True)
        if not isinstance(want_open, bool):
            report({}, "BLOCKED", "bad_params expect_open", 0)
            return 0
        ok, why = _loopback_ok(host)
        if not ok:
            report({"host": host, "port": port}, "BLOCKED", why, 0)
            return 0
        try:
            per_call = float(target.get("timeout_s", 3.0))
        except (TypeError, ValueError):
            report({}, "BLOCKED", "bad_params timeout_s", 0)
            return 0
        remaining = max(0.2, min(max(0.2, per_call), deadline - time.perf_counter(), 10.0))
        started = time.perf_counter()
        is_open = False
        error = ""
        try:
            sock = socket.create_connection((host, port), timeout=remaining)
        except OSError as exc:
            error = str(exc)
        else:
            is_open = True
            try:
                sock.close()
            except OSError:
                pass
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        match = is_open == want_open
        entry = {
            "host": host,
            "port": port,
            "open": is_open,
            "expect_open": want_open,
            "latency_ms": round(elapsed_ms, 1),
            "ok": match,
        }
        if error and not is_open:
            entry["error"] = error[:200]
        results.append(entry)
        if not match:
            failures.append(
                "%s:%d open=%s want=%s" % (host, port, is_open, want_open)
            )
    payload = {"targets": results}
    if failures:
        report(
            payload,
            "FAIL",
            "%d mismatch(es): %s" % (len(failures), failures[0]),
            len(results),
        )
    else:
        report(payload, "PASS", "%d target(s) ok" % len(results), len(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
