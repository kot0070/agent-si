"""Score a candidate text on required substrings, length and threshold."""
import json
import os
import re
import sys

RUNNER_ID = "eval_harness"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {"tools": [], "network": False, "project_tooling": False,
                "local_subprocess": False}
RUNNER_DESCRIPTION = "Score candidate text against required content."

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
    candidate = params.get("candidate")
    if candidate is None:
        name = params.get("candidate_file")
        if isinstance(name, str) and name:
            full = os.path.abspath(os.path.join(project_root, name))
            if not _within(full, [project_root]):
                res["status"] = "BLOCKED"
                res["reason"] = "path_escape"
                return res
            try:
                with open(full, "r", encoding="utf-8",
                          errors="replace") as fh:
                    candidate = fh.read()
            except OSError:
                candidate = None
    must = params.get("must_contain") or []
    if not isinstance(must, list):
        must = [must]
    if candidate is None and not must:
        res["status"] = "UNSUPPORTED"
        res["reason"] = "no_candidate"
        return res
    if candidate is None:
        candidate = ""
    if not isinstance(candidate, str):
        candidate = str(candidate)
    try:
        max_len = params.get("max_len")
        max_len = None if max_len is None else int(max_len)
    except (TypeError, ValueError):
        max_len = None
    try:
        threshold = float(params.get("threshold", 1.0))
    except (TypeError, ValueError):
        threshold = 1.0
    found = sum(1 for item in must if str(item) in candidate)
    total = len(must)
    share = (found / total) if total else 1.0
    length_ok = max_len is None or len(candidate) <= max_len
    res["assertions"] = total + 1
    try:
        os.makedirs(evidence_dir, exist_ok=True)
        out = os.path.abspath(os.path.join(evidence_dir, "eval_result.json"))
        if _within(out, [evidence_dir]):
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"found": found, "total": total,
                                     "share": share, "length": len(candidate),
                                     "length_ok": length_ok}))
            res["evidence"] = ["eval_result.json"]
    except OSError:
        pass
    if length_ok and share >= threshold:
        res["status"] = "PASS"
        res["reason"] = "candidate_scores_above_threshold"
    else:
        res["status"] = "FAIL"
        res["reason"] = "candidate_below_threshold"
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
