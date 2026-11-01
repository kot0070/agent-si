"""Replay logins against a loopback mapping fixture and compare statuses."""
import ipaddress
import json
import os
import re
import sys
import urllib.parse

RUNNER_ID = "auth_probe"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {"tools": [], "network": True, "project_tooling": False,
                "local_subprocess": False}
RUNNER_DESCRIPTION = "Replay account logins against a loopback fixture."

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


def _fetch_json(url, timeout):
    import urllib.request
    req = urllib.request.Request(url,
                                 headers={"User-Agent": "qa-catalog-runner"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
    accounts = params.get("accounts")
    if not accounts:
        res["status"] = "UNSUPPORTED"
        res["reason"] = "no_accounts"
        return res
    if not isinstance(accounts, list):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    replay_url = params.get("replay_url")
    if not replay_url or not isinstance(replay_url, str):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    if not _loopback_url(replay_url):
        res["status"] = "BLOCKED"
        res["reason"] = "non_loopback"
        return res
    expected = params.get("expected_status")
    if not isinstance(expected, dict):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    timeout = budgets.get("timeout_s") or 30
    try:
        timeout = min(float(timeout), 20.0)
    except (TypeError, ValueError):
        timeout = 20.0
    try:
        mapping = _fetch_json(replay_url, timeout)
    except Exception:
        res["status"] = "FAIL"
        res["reason"] = "replay_unavailable"
        res["assertions"] = 1
        return res
    if not isinstance(mapping, dict):
        res["status"] = "FAIL"
        res["reason"] = "replay_unavailable"
        res["assertions"] = 1
        return res
    checked = 0
    mismatched = []
    for account in accounts:
        if not isinstance(account, dict):
            mismatched.append("bad_account")
            continue
        user = account.get("user")
        role = account.get("role")
        actual = mapping.get(user, mapping.get(role))
        want = expected.get(role)
        checked += 1
        try:
            same = int(actual) == int(want)
        except (TypeError, ValueError):
            same = False
        if not same:
            mismatched.append(str(user))
    res["assertions"] = checked
    try:
        os.makedirs(evidence_dir, exist_ok=True)
        out = os.path.abspath(os.path.join(evidence_dir,
                                            "auth_result.json"))
        if _within(out, [evidence_dir]):
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"checked": checked,
                                     "mismatched": mismatched}))
            res["evidence"] = ["auth_result.json"]
    except OSError:
        pass
    if mismatched:
        res["status"] = "FAIL"
        res["reason"] = "status_mismatch:" + ",".join(mismatched)
    else:
        res["status"] = "PASS"
        res["reason"] = "all_statuses_match"
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
