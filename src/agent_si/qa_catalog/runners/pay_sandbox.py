"""Post one idempotent charge row to a sandbox ledger file in the jail."""
import json
import math
import os
import re
import sys

RUNNER_ID = "pay_sandbox"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {"tools": [], "network": False, "project_tooling": False,
                "local_subprocess": False}
RUNNER_DESCRIPTION = "Record an idempotent sandbox charge, never real money."

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
    project_root = payload.get("project_root") or ""
    evidence_dir = budgets.get("evidence_dir") or project_root or "."
    test_id = payload.get("test_id", "unknown")
    res = _fresh(test_id)
    charge = params.get("charge")
    if not charge:
        res["status"] = "UNSUPPORTED"
        res["reason"] = "no_charge"
        return res
    if not isinstance(charge, dict):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    key = charge.get("key")
    amount = charge.get("amount")
    if not isinstance(key, str) or not key:
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    rel = params.get("ledger", "pay_ledger.json")
    if not isinstance(rel, str) or not rel:
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    full = os.path.abspath(os.path.join(project_root, rel))
    if not _within(full, [project_root, evidence_dir]):
        res["status"] = "BLOCKED"
        res["reason"] = "path_escape"
        return res
    res["assertions"] = 1
    ok_amount = (isinstance(amount, (int, float))
                 and not isinstance(amount, bool)
                 and math.isfinite(amount) and amount > 0)
    rows = []
    if os.path.exists(full):
        try:
            with open(full, "r", encoding="utf-8") as fh:
                rows = json.load(fh)
            if not isinstance(rows, list):
                rows = []
        except (OSError, ValueError):
            rows = []
    if not ok_amount:
        try:
            os.makedirs(evidence_dir, exist_ok=True)
            out = os.path.abspath(os.path.join(evidence_dir,
                                                "pay_result.json"))
            if _within(out, [evidence_dir]):
                with open(out, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps({"key": key, "posted": False,
                                         "reason": "bad_amount"}))
                res["evidence"] = ["pay_result.json"]
        except OSError:
            pass
        res["status"] = "FAIL"
        res["reason"] = "bad_amount"
        return res
    if not any(isinstance(r, dict) and r.get("key") == key for r in rows):
        rows.append({"key": key, "amount": amount})
        try:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(rows))
        except OSError:
            res["status"] = "FAIL"
            res["reason"] = "ledger_unwritable"
            return res
    count = sum(1 for r in rows
                if isinstance(r, dict) and r.get("key") == key)
    names = []
    try:
        os.makedirs(evidence_dir, exist_ok=True)
        out = os.path.abspath(os.path.join(evidence_dir, "pay_result.json"))
        if _within(out, [evidence_dir]):
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"key": key, "rows_for_key": count}))
            names.append("pay_result.json")
    except OSError:
        pass
    res["evidence"] = names
    if count == 1:
        res["status"] = "PASS"
        res["reason"] = "single_charge_row"
    else:
        res["status"] = "FAIL"
        res["reason"] = "duplicate_charge_rows:%d" % count
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
