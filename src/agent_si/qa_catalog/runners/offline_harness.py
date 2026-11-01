"""Replay queued set/delete ops onto a dict and compare with expected."""
import json
import os
import re
import sys

RUNNER_ID = "offline_harness"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {"tools": [], "network": False, "project_tooling": False,
                "local_subprocess": False}
RUNNER_DESCRIPTION = "Replay an offline op queue and compare state."

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
    queue = params.get("queue")
    if not queue:
        res["status"] = "UNSUPPORTED"
        res["reason"] = "no_queue"
        return res
    if not isinstance(queue, list):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    expected = params.get("expected", {})
    if isinstance(expected, list):
        try:
            expected = {str(i.get("key")): i.get("value") for i in expected
                        if isinstance(i, dict) and "key" in i}
        except Exception:
            expected = {}
    if not isinstance(expected, dict):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    state = {}
    broken = []
    for op in queue:
        if not isinstance(op, dict):
            broken.append("bad_op")
            continue
        kind = op.get("op")
        key = op.get("key")
        if not isinstance(key, str):
            broken.append("bad_key")
            continue
        if kind == "set":
            state[key] = op.get("value")
        elif kind == "delete":
            state.pop(key, None)
        else:
            broken.append("unknown_op:%s" % (kind,))
    res["assertions"] = max(1, len(queue))
    try:
        os.makedirs(evidence_dir, exist_ok=True)
        out = os.path.abspath(os.path.join(evidence_dir,
                                            "offline_result.json"))
        if _within(out, [evidence_dir]):
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"state": state, "expected": expected,
                                     "broken": broken}))
            res["evidence"] = ["offline_result.json"]
    except OSError:
        pass
    if not broken and state == expected:
        res["status"] = "PASS"
        res["reason"] = "state_matches"
    else:
        res["status"] = "FAIL"
        res["reason"] = "state_mismatch"
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
