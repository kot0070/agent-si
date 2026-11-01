"""Check schedules fire exactly once inside a window on an integer clock."""
import json
import os
import re
import sys

RUNNER_ID = "notify_harness"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {"tools": [], "network": False, "project_tooling": False,
                "local_subprocess": False}
RUNNER_DESCRIPTION = "Verify fake-clock notification schedules."

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
    schedules = params.get("schedules")
    if not schedules:
        res["status"] = "UNSUPPORTED"
        res["reason"] = "no_schedules"
        return res
    if not isinstance(schedules, list):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    window = params.get("window")
    if not isinstance(window, dict):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    try:
        start = int(window["start"])
        end = int(window["end"])
    except (KeyError, TypeError, ValueError):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    seen = set()
    problems = []
    fired = []
    for item in schedules:
        if not isinstance(item, dict):
            problems.append("bad_schedule")
            continue
        sid = item.get("id")
        try:
            at = int(item.get("at"))
        except (TypeError, ValueError):
            problems.append("bad_time:%s" % (sid,))
            continue
        if sid in seen:
            problems.append("duplicate:%s" % (sid,))
            continue
        seen.add(sid)
        if not start <= at <= end:
            problems.append("outside_window:%s" % (sid,))
            continue
        fired.append({"id": sid, "at": at})
    res["assertions"] = len(schedules)
    try:
        os.makedirs(evidence_dir, exist_ok=True)
        out = os.path.abspath(os.path.join(evidence_dir,
                                            "notify_result.json"))
        if _within(out, [evidence_dir]):
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"fired": fired, "problems": problems}))
            res["evidence"] = ["notify_result.json"]
    except OSError:
        pass
    if problems:
        res["status"] = "FAIL"
        res["reason"] = "schedule_problem:" + problems[0]
    else:
        res["status"] = "PASS"
        res["reason"] = "all_schedules_fire_once"
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
