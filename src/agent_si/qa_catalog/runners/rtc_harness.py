"""POST messages to a loopback echo fixture and check exact echo in budget."""
import ipaddress
import json
import os
import re
import sys
import time
import urllib.parse

RUNNER_ID = "rtc_harness"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {"tools": [], "network": True, "project_tooling": False,
                "local_subprocess": False}
RUNNER_DESCRIPTION = "Echo messages off a loopback peer within budget."

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


def _post(url, text, timeout):
    import urllib.request
    data = text.encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "text/plain",
                                          "Content-Length": str(len(data)),
                                          "User-Agent": "qa-catalog-runner"})
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return None, (time.monotonic() - start) * 1000.0, type(exc).__name__
    return body, (time.monotonic() - start) * 1000.0, ""


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
    messages = params.get("messages")
    if not messages:
        res["status"] = "UNSUPPORTED"
        res["reason"] = "no_messages"
        return res
    if not isinstance(messages, list):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    peer_url = params.get("peer_url")
    if not peer_url or not isinstance(peer_url, str):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    if not _loopback_url(peer_url):
        res["status"] = "BLOCKED"
        res["reason"] = "non_loopback"
        return res
    try:
        budget_ms = float(params.get("latency_budget_ms", 5000))
    except (TypeError, ValueError):
        budget_ms = 5000.0
    timeout = budgets.get("timeout_s") or 30
    try:
        timeout = min(float(timeout), 20.0)
    except (TypeError, ValueError):
        timeout = 20.0
    checked = 0
    problems = []
    worst_ms = 0.0
    for item in messages:
        if not isinstance(item, dict):
            problems.append("bad_message")
            continue
        send = str(item.get("send", ""))
        want = str(item.get("expect", ""))
        body, elapsed_ms, error = _post(peer_url, send, timeout)
        checked += 1
        worst_ms = max(worst_ms, elapsed_ms)
        if error or body is None:
            problems.append("send_failed")
        elif body != want:
            problems.append("echo_mismatch")
        elif elapsed_ms > budget_ms:
            problems.append("over_budget")
    res["assertions"] = checked
    try:
        os.makedirs(evidence_dir, exist_ok=True)
        out = os.path.abspath(os.path.join(evidence_dir, "rtc_result.json"))
        if _within(out, [evidence_dir]):
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"checked": checked,
                                     "worst_ms": worst_ms,
                                     "problems": problems}))
            res["evidence"] = ["rtc_result.json"]
    except OSError:
        pass
    if problems:
        res["status"] = "FAIL"
        res["reason"] = problems[0]
    else:
        res["status"] = "PASS"
        res["reason"] = "all_echoes_match"
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
