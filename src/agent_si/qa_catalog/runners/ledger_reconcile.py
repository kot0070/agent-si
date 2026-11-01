"""Reconcile debit/credit entries: positive finite amounts, balanced sums."""
import json
import math
import os
import re
import sys

RUNNER_ID = "ledger_reconcile"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {"tools": [], "network": False, "project_tooling": False,
                "local_subprocess": False}
RUNNER_DESCRIPTION = "Reconcile a debit/credit ledger to balance."

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
    entries = params.get("entries")
    if entries is None:
        name = params.get("ledger_file")
        if isinstance(name, str) and name:
            full = os.path.abspath(os.path.join(project_root, name))
            if not _within(full, [project_root]):
                res["status"] = "BLOCKED"
                res["reason"] = "path_escape"
                return res
            try:
                with open(full, "r", encoding="utf-8") as fh:
                    entries = json.load(fh)
            except (OSError, ValueError):
                entries = None
    if not entries:
        res["status"] = "UNSUPPORTED"
        res["reason"] = "no_entries"
        return res
    if not isinstance(entries, list):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    debit = []
    credit = []
    valid = True
    for entry in entries:
        if not isinstance(entry, dict):
            valid = False
            break
        side = entry.get("side")
        amount = entry.get("amount")
        if side not in ("debit", "credit"):
            valid = False
            break
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            valid = False
            break
        if not math.isfinite(amount) or amount <= 0:
            valid = False
            break
        (debit if side == "debit" else credit).append(float(amount))
    res["assertions"] = len(entries) + 1
    sum_debit = math.fsum(debit)
    sum_credit = math.fsum(credit)
    try:
        os.makedirs(evidence_dir, exist_ok=True)
        out = os.path.abspath(os.path.join(evidence_dir,
                                            "ledger_result.json"))
        if _within(out, [evidence_dir]):
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"debit": sum_debit,
                                     "credit": sum_credit,
                                     "balanced": sum_debit == sum_credit,
                                     "valid": valid}))
            res["evidence"] = ["ledger_result.json"]
    except OSError:
        pass
    if valid and sum_debit == sum_credit:
        res["status"] = "PASS"
        res["reason"] = "ledger_balanced"
    else:
        res["status"] = "FAIL"
        res["reason"] = "ledger_out_of_balance"
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
