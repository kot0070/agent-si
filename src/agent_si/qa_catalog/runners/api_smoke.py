"""K03 FXCATALOG set-A runner: api_smoke.

Issues HTTP GETs against a loopback base_url (http.client, no third
parties) and checks status codes, JSON body keys and latency budgets.
The target host must resolve to loopback only; anything else is
BLOCKED with reason non_loopback and is never contacted. Failed
checks are FAIL; no checks configured is UNSUPPORTED, never PASS.

Stdlib only. Never real services: loopback only. No hardcoded PASS.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import os
import socket
import ssl
import sys
import time
import urllib.parse

RUNNER_ID = "api_smoke"
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
    "Loopback HTTP smoke checks: status, JSON keys, latency budgets; "
    "non-loopback targets BLOCKED."
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
    """Resolve host; return (ok, reason): ok only for loopback literals."""
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


def _lookup(data, dotted):
    current = data
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


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

    base_url = params.get("base_url")
    if base_url is None:
        report({}, "UNSUPPORTED", "no_base_url", 0)
        return 0
    if not isinstance(base_url, str):
        report({}, "BLOCKED", "bad_params base_url", 0)
        return 0
    try:
        parts = urllib.parse.urlsplit(base_url)
    except ValueError:
        report({}, "BLOCKED", "bad_params base_url", 0)
        return 0
    if parts.scheme not in ("http", "https") or not parts.hostname:
        report({}, "BLOCKED", "bad_params base_url", 0)
        return 0
    ok, why = _loopback_ok(parts.hostname)
    if not ok:
        report({"base_url": base_url}, "BLOCKED", why, 0)
        return 0
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        report({}, "BLOCKED", "bad_params base_url", 0)
        return 0
    checks = params.get("checks", [{"path": "/"}])
    if not isinstance(checks, list) or not all(
        isinstance(item, dict) for item in checks
    ):
        report({}, "BLOCKED", "bad_params checks", 0)
        return 0
    if not checks:
        report({}, "UNSUPPORTED", "no_checks", 0)
        return 0

    deadline = time.perf_counter() + max(1.0, timeout_s)
    results = []
    failures = []
    for check in checks:
        path = check.get("path", "/")
        if not isinstance(path, str) or not path.startswith("/"):
            report({}, "BLOCKED", "bad_params check path", 0)
            return 0
        try:
            expect_status = int(check.get("expect_status", 200))
        except (TypeError, ValueError):
            report({}, "BLOCKED", "bad_params expect_status", 0)
            return 0
        keys = check.get("expect_keys", [])
        if not isinstance(keys, list) or not all(
            isinstance(item, str) for item in keys
        ):
            report({}, "BLOCKED", "bad_params expect_keys", 0)
            return 0
        try:
            max_ms = float(check.get("max_ms", 5000.0))
        except (TypeError, ValueError):
            report({}, "BLOCKED", "bad_params max_ms", 0)
            return 0
        remaining = max(0.5, min(10.0, deadline - time.perf_counter()))
        started = time.perf_counter()
        try:
            if parts.scheme == "https":
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                connection = http.client.HTTPSConnection(
                    parts.hostname, port, timeout=remaining, context=context
                )
            else:
                connection = http.client.HTTPConnection(
                    parts.hostname, port, timeout=remaining
                )
            try:
                connection.request("GET", path)
                response = connection.getresponse()
                body = response.read(262144)
                status = response.status
            finally:
                connection.close()
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            results.append(
                {"path": path, "status": None, "latency_ms": round(elapsed_ms, 1),
                 "ok": False, "error": "connect_error: %s" % exc}
            )
            failures.append("%s connect_error" % path)
            continue
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        problems = []
        if status != expect_status:
            problems.append("status %s != %s" % (status, expect_status))
        if keys:
            try:
                data = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                data = None
            if data is None:
                problems.append("body_not_json")
            else:
                missing = [key for key in keys if not _lookup(data, key)]
                if missing:
                    problems.append("missing_keys %s" % ",".join(missing))
        if elapsed_ms > max_ms:
            problems.append("too_slow %.1fms > %.1fms" % (elapsed_ms, max_ms))
        entry = {
            "path": path,
            "status": status,
            "latency_ms": round(elapsed_ms, 1),
            "ok": not problems,
        }
        if problems:
            entry["problems"] = problems
            failures.append("%s %s" % (path, "; ".join(problems)))
        results.append(entry)
    payload = {"base_url": base_url, "checks": results}
    if failures:
        report(
            payload,
            "FAIL",
            "%d failing check(s): %s" % (len(failures), failures[0]),
            len(results),
        )
    else:
        report(
            payload, "PASS", "%d check(s) ok" % len(results), len(results)
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
