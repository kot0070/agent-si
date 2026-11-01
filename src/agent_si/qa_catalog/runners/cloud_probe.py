"""Check service markers exist and loopback health URLs return 2xx."""
import ipaddress
import json
import os
import re
import sys
import urllib.parse

RUNNER_ID = "cloud_probe"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {"tools": [], "network": True, "project_tooling": False,
                "local_subprocess": False}
RUNNER_DESCRIPTION = "Verify service markers and loopback health checks."

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


def _health(url, timeout):
    import urllib.request
    req = urllib.request.Request(url,
                                 headers={"User-Agent": "qa-catalog-runner"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        resp.read()
        return resp.status


def _run(payload):
    params = payload.get("params")
    if not isinstance(params, dict):
        params = {}
    budgets = payload.get("budgets")
    if not isinstance(budgets, dict):
        budgets = {}
    project_root = payload.get("project_root") or ""
    evidence_dir = budgets.get("evidence_dir") or project_root or "."
    test_id = payload.get("test_id", "unknown")
    res = _fresh(test_id)
    services = params.get("services")
    if not services:
        res["status"] = "UNSUPPORTED"
        res["reason"] = "no_services"
        return res
    if not isinstance(services, list):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    timeout = budgets.get("timeout_s") or 30
    try:
        timeout = min(float(timeout), 20.0)
    except (TypeError, ValueError):
        timeout = 20.0
    checked = 0
    unhealthy = []
    for service in services:
        if not isinstance(service, dict):
            unhealthy.append("bad_service")
            continue
        name = str(service.get("name", "unnamed"))
        marker = service.get("marker", "")
        health_url = service.get("health_url", "")
        marker_ok = False
        if isinstance(marker, str) and marker:
            full = os.path.abspath(os.path.join(project_root, marker))
            if _within(full, [project_root]):
                marker_ok = os.path.isfile(full)
        checked += 1
        health_ok = False
        if isinstance(health_url, str) and health_url:
            if not _loopback_url(health_url):
                res["status"] = "BLOCKED"
                res["reason"] = "non_loopback"
                return res
            try:
                health_ok = 200 <= _health(health_url, timeout) < 300
            except Exception:
                health_ok = False
        checked += 1
        if not (marker_ok and health_ok):
            unhealthy.append(name)
    res["assertions"] = checked
    try:
        os.makedirs(evidence_dir, exist_ok=True)
        out = os.path.abspath(os.path.join(evidence_dir,
                                            "cloud_result.json"))
        if _within(out, [evidence_dir]):
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"checked": checked,
                                     "unhealthy": unhealthy}))
            res["evidence"] = ["cloud_result.json"]
    except OSError:
        pass
    if unhealthy:
        res["status"] = "FAIL"
        res["reason"] = "unhealthy:" + ",".join(unhealthy)
    else:
        res["status"] = "PASS"
        res["reason"] = "all_services_healthy"
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
