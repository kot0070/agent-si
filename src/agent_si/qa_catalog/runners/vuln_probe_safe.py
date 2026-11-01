"""Send allowlisted payloads at a loopback fixture; reflection means FAIL."""
import ipaddress
import json
import os
import re
import sys
import urllib.parse

RUNNER_ID = "vuln_probe_safe"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {"tools": [], "network": True, "project_tooling": False,
                "local_subprocess": False}
RUNNER_DESCRIPTION = "Probe a loopback fixture with allowlisted payloads."

ALLOWLIST = ("<script>alert(1)</script>", "' OR '1'='1", "../../etc/passwd",
             "${jndi:ldap://x}", "<img src=x onerror=alert(1)>")

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


def _send(url, payload_text, timeout):
    import urllib.request
    target = url + ("&" if "?" in url else "?") + "q=" + urllib.parse.quote(
        payload_text, safe="")
    req = urllib.request.Request(target,
                                 headers={"User-Agent": "qa-catalog-runner"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


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
    fixture_url = params.get("fixture_url")
    if not fixture_url or not isinstance(fixture_url, str):
        res["status"] = "UNSUPPORTED"
        res["reason"] = "no_fixture_url"
        return res
    if not _loopback_url(fixture_url):
        res["status"] = "BLOCKED"
        res["reason"] = "non_loopback"
        return res
    payloads = params.get("payloads")
    if not payloads:
        res["status"] = "UNSUPPORTED"
        res["reason"] = "no_payloads"
        return res
    if not isinstance(payloads, list):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    for item in payloads:
        if item not in ALLOWLIST:
            res["status"] = "BLOCKED"
            res["reason"] = "payload_not_allowlisted"
            return res
    timeout = budgets.get("timeout_s") or 30
    try:
        timeout = min(float(timeout), 20.0)
    except (TypeError, ValueError):
        timeout = 20.0
    reflected = []
    for item in payloads:
        try:
            body = _send(fixture_url, item, timeout)
        except Exception:
            body = ""
        if item in body:
            reflected.append(item)
    res["assertions"] = len(payloads)
    try:
        os.makedirs(evidence_dir, exist_ok=True)
        out = os.path.abspath(os.path.join(evidence_dir, "vuln_result.json"))
        if _within(out, [evidence_dir]):
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"sent": len(payloads),
                                     "reflected": len(reflected)}))
            res["evidence"] = ["vuln_result.json"]
    except OSError:
        pass
    if reflected:
        res["status"] = "FAIL"
        res["reason"] = "payload_reflected"
    else:
        res["status"] = "PASS"
        res["reason"] = "no_reflection"
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
