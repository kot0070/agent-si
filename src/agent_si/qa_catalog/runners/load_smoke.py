"""GET loopback routes concurrently and judge p95 latency against an SLO."""
import ipaddress
import json
import os
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

RUNNER_ID = "load_smoke"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {"tools": [], "network": True, "project_tooling": False,
                "local_subprocess": False}
RUNNER_DESCRIPTION = "Concurrent GET smoke test of loopback routes."

_PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy",
               "https_proxy", "all_proxy")
_SECRET_RE = re.compile(
    r"secret|token|passwd|password|credential|api[_-]?key", re.IGNORECASE)


def _scrub_env():
    for key in list(os.environ):
        if _SECRET_RE.search(key):
            del os.environ[key]
    for key in _PROXY_VARS:
        os.environ[key] = ""


def _fresh(test_id):
    return {"test_id": test_id, "runner_id": RUNNER_ID, "status": "BLOCKED",
            "reason": "input_not_provided", "assertions": 0, "evidence": [],
            "child_pid": os.getpid(), "child_env_keys": sorted(os.environ),
            "proxies_emptied": all(os.environ.get(k, "") == ""
                                   for k in _PROXY_VARS)}


def _within(path, roots):
    target = os.path.realpath(os.path.abspath(path))
    for root in roots:
        base = os.path.realpath(os.path.abspath(root))
        if target == base or target.startswith(base + os.sep):
            return True
    return False


def _loopback_url(url):
    try:
        parts = urllib.parse.urlsplit(url)
    except Exception:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    host = (parts.hostname or "").strip().lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _one_get(url, timeout):
    import urllib.request
    start = time.monotonic()
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "qa-catalog-runner"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            status = resp.status
        elapsed_ms = (time.monotonic() - start) * 1000.0
        return status, elapsed_ms, None
    except Exception as exc:
        elapsed_ms = (time.monotonic() - start) * 1000.0
        return None, elapsed_ms, type(exc).__name__


def _run(payload):
    params = payload.get("params")
    if not isinstance(params, dict):
        params = {}
    budgets = payload.get("budgets")
    if not isinstance(budgets, dict):
        budgets = {}
    evidence_dir = budgets.get("evidence_dir") or payload.get(
        "project_root") or "."
    test_id = payload.get("test_id", "unknown")
    res = _fresh(test_id)
    routes = params.get("routes")
    if not routes:
        res["status"] = "UNSUPPORTED"
        res["reason"] = "no_routes"
        return res
    if not isinstance(routes, list):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    for route in routes:
        if not isinstance(route, str) or not _loopback_url(route):
            res["status"] = "BLOCKED"
            res["reason"] = "non_loopback"
            return res
    try:
        per_route = max(1, min(int(params.get("requests_per_route", 1)), 50))
    except (TypeError, ValueError):
        per_route = 1
    try:
        threads = max(1, min(int(params.get("max_threads", 4)), 8))
    except (TypeError, ValueError):
        threads = 4
    try:
        slo_ms = float(params.get("slo_ms", float("inf")))
    except (TypeError, ValueError):
        slo_ms = float("inf")
    try:
        budget_s = float(budgets.get("timeout_s") or 60.0)
    except (TypeError, ValueError):
        budget_s = 60.0
    sock_timeout = max(60.0, budget_s)
    targets = [r for r in routes for _ in range(per_route)]
    latencies = []
    errors = 0
    bad_status = 0
    with ThreadPoolExecutor(max_workers=threads) as pool:
        futures = [pool.submit(_one_get, url, sock_timeout)
                   for url in targets]
        for future in futures:
            status, elapsed_ms, error = future.result()
            latencies.append(elapsed_ms)
            if error is not None:
                errors += 1
            elif status is None or not 200 <= status < 300:
                bad_status += 1
    done = len(latencies)
    ordered = sorted(latencies)
    index = max(0, (len(ordered) * 95 + 99) // 100 - 1)
    p95 = ordered[index] if ordered else 0.0
    res["assertions"] = done
    try:
        os.makedirs(evidence_dir, exist_ok=True)
        out = os.path.abspath(os.path.join(evidence_dir,
                                            "load_result.json"))
        if _within(out, [evidence_dir]):
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"requests": done, "errors": errors,
                                     "bad_status": bad_status,
                                     "p95_ms": p95, "slo_ms": slo_ms}))
            res["evidence"] = ["load_result.json"]
    except OSError:
        pass
    if errors or bad_status:
        res["status"] = "FAIL"
        res["reason"] = "request_errors:%d" % (errors + bad_status)
    elif p95 > slo_ms:
        res["status"] = "FAIL"
        res["reason"] = "slo_breach:%.1fms" % p95
    else:
        res["status"] = "PASS"
        res["reason"] = "within_slo"
    return res


def main():
    _scrub_env()
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    test_id = payload.get("test_id", "unknown")
    try:
        result = _run(payload)
    except Exception as exc:
        result = _fresh(test_id)
        result["reason"] = "exception:" + type(exc).__name__
    result["test_id"] = test_id
    result["runner_id"] = RUNNER_ID
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
