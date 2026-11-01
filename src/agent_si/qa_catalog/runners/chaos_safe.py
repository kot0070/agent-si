"""Judge a chaos drill plan only: loopback targets, jail paths, rollback."""
import ipaddress
import json
import os
import re
import sys
import urllib.parse

RUNNER_ID = "chaos_safe"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {"tools": [], "network": False, "project_tooling": False,
                "local_subprocess": False}
RUNNER_DESCRIPTION = "Judge a chaos drill plan without touching anything."

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


def _jail_path(project_root, evidence_dir, value):
    if not isinstance(value, str) or not value:
        return False
    if value.lower().startswith(("http://", "https://")):
        return False
    full = os.path.abspath(os.path.join(project_root, value))
    return _within(full, [project_root, evidence_dir])


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
    drill = params.get("drill")
    if not drill:
        res["status"] = "UNSUPPORTED"
        res["reason"] = "no_drill"
        return res
    if not isinstance(drill, dict):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    targets = drill.get("targets", [])
    if not isinstance(targets, list):
        targets = [targets]
    rollback = drill.get("rollback_plan", [])
    if not isinstance(rollback, list):
        rollback = [rollback]
    radius = drill.get("blast_radius", [])
    if not isinstance(radius, list):
        radius = [radius]
    targets_ok = True
    for target in targets:
        if not isinstance(target, str) or not target:
            targets_ok = False
            break
        if target.lower().startswith(("http://", "https://")):
            if not _loopback_url(target):
                targets_ok = False
                break
        elif not _jail_path(project_root, evidence_dir, target):
            targets_ok = False
            break
    rollback_ok = len([s for s in rollback if isinstance(s, str) and s]) > 0
    radius_ok = len(radius) > 0 and all(
        _jail_path(project_root, evidence_dir, entry) for entry in radius)
    res["assertions"] = 3
    record = {"name": drill.get("name", ""), "targets_ok": targets_ok,
              "rollback_ok": rollback_ok, "radius_ok": radius_ok}
    try:
        os.makedirs(evidence_dir, exist_ok=True)
        out = os.path.abspath(os.path.join(evidence_dir,
                                            "chaos_result.json"))
        if _within(out, [evidence_dir]):
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(record))
            res["evidence"] = ["chaos_result.json"]
    except OSError:
        pass
    if targets_ok and rollback_ok and radius_ok:
        res["status"] = "PASS"
        res["reason"] = "drill_plan_safe"
    else:
        res["status"] = "FAIL"
        if not targets_ok:
            res["reason"] = "unsafe_targets"
        elif not rollback_ok:
            res["reason"] = "missing_rollback"
        else:
            res["reason"] = "blast_radius_escapes_jail"
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
