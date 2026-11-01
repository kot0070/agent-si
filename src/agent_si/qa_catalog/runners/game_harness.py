"""Deterministic grid walk with a seed-fixed obstacle rule.

Obstacle rule (fixed): cell (x, y) is blocked when it is not the origin
and (x * 3 + y * 7 + seed) % 5 == 0. A move into a blocked cell leaves
the walker in place. Moves are U/D/L/R tokens from (0, 0).
"""
import json
import os
import re
import sys

RUNNER_ID = "game_harness"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 60
RUNNER_NEEDS = {"tools": [], "network": False, "project_tooling": False,
                "local_subprocess": False}
RUNNER_DESCRIPTION = "Replay a deterministic grid walk to an expected cell."

DELTAS = {"U": (0, 1), "D": (0, -1), "L": (-1, 0), "R": (1, 0)}

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


def _blocked(x, y, seed):
    return (x, y) != (0, 0) and (x * 3 + y * 7 + seed) % 5 == 0


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
    moves = params.get("moves")
    if not moves:
        res["status"] = "UNSUPPORTED"
        res["reason"] = "no_moves"
        return res
    if not isinstance(moves, list):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    try:
        seed = int(params.get("seed", 0))
    except (TypeError, ValueError):
        seed = 0
    expected = params.get("expected_final")
    if not isinstance(expected, dict):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    try:
        want_x = int(expected["x"])
        want_y = int(expected["y"])
    except (KeyError, TypeError, ValueError):
        res["status"] = "BLOCKED"
        res["reason"] = "input_not_provided"
        return res
    x, y = 0, 0
    invalid = False
    for token in moves:
        step = DELTAS.get(str(token).upper())
        if step is None:
            invalid = True
            break
        next_x, next_y = x + step[0], y + step[1]
        if not _blocked(next_x, next_y, seed):
            x, y = next_x, next_y
    res["assertions"] = len(moves)
    try:
        os.makedirs(evidence_dir, exist_ok=True)
        out = os.path.abspath(os.path.join(evidence_dir, "game_result.json"))
        if _within(out, [evidence_dir]):
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"final": {"x": x, "y": y},
                                     "invalid": invalid}))
            res["evidence"] = ["game_result.json"]
    except OSError:
        pass
    if not invalid and x == want_x and y == want_y:
        res["status"] = "PASS"
        res["reason"] = "final_matches"
    else:
        res["status"] = "FAIL"
        res["reason"] = "final_mismatch"
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
