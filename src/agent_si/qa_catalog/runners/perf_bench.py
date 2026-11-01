"""K03 FXCATALOG set-A runner: perf_bench.

Measures CPU micro-ops with perf_counter against per-op budgets
(params.ops entries: sleep_ms, sort_n, sha256_kb, json_items with
ms/n/kb sizes and budget_ms). Any op over budget is FAIL; all within
budget is PASS; an explicitly empty op list is UNSUPPORTED.

Stdlib only. No DATA reads at runtime. No hardcoded PASS.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time

RUNNER_ID = "perf_bench"
RUNNER_VERSION = "1.0.0"
RUNNER_TIMEOUT_S = 120
RUNNER_NEEDS = {
    "tools": [],
    "network": False,
    "project_tooling": False,
    "local_subprocess": False,
    "env": [],
}
RUNNER_DESCRIPTION = (
    "Measures CPU micro-ops with perf_counter against budgets; "
    "over-budget ops FAIL."
)

_DEFAULT_BUDGET_MS = 5000.0


def _read_input():
    raw = sys.stdin.buffer.read().decode("utf-8")
    request = json.loads(raw)
    project_root = os.path.abspath(request.get("project_root", "") or ".")
    budgets = request.get("budgets", {}) or {}
    try:
        timeout_s = float(budgets.get("timeout_s", 60.0))
    except (TypeError, ValueError):
        timeout_s = 60.0
    evidence_dir = os.path.abspath(budgets.get("evidence_dir", "") or ".")
    params = request.get("params", {}) or {}
    return project_root, request.get("test_id", ""), params, timeout_s, evidence_dir


def _emit(test_id, status, reason, assertions, evidence):
    sys.stdout.write(
        json.dumps(
            {
                "test_id": test_id,
                "runner_id": RUNNER_ID,
                "status": status,
                "reason": reason,
                "assertions": assertions,
                "evidence": evidence,
            }
        )
        + "\n"
    )
    sys.stdout.flush()


def _run_op(kind, size):
    if kind == "sleep_ms":
        time.sleep(max(0.0, size) / 1000.0)
    elif kind == "sort_n":
        items = list(range(int(size), 0, -1))
        items.sort()
    elif kind == "sha256_kb":
        blob = os.urandom(max(1, int(size)) * 1024)
        hashlib.sha256(blob).hexdigest()
    elif kind == "json_items":
        items = [{"i": i, "s": "x" * 16} for i in range(max(0, int(size)))]
        json.dumps(items)
    else:
        raise ValueError("unknown op kind: %s" % kind)


_SIZE_KEY = {
    "sleep_ms": "ms",
    "sort_n": "n",
    "sha256_kb": "kb",
    "json_items": "n",
}


def main() -> int:
    try:
        project_root, test_id, params, timeout_s, evidence_dir = _read_input()
    except Exception as exc:
        _emit("", "BLOCKED", "bad_input: %s" % exc, 0, [])
        return 0
    os.makedirs(evidence_dir, exist_ok=True)
    name = RUNNER_ID + ".json"

    def report(payload, status, reason, assertions):
        with open(os.path.join(evidence_dir, name), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        _emit(test_id, status, reason, assertions, [name])

    ops = params.get("ops")
    if ops is None:
        ops = [{"name": "default_sort", "kind": "sort_n", "n": 2000}]
    if not isinstance(ops, list) or not all(
        isinstance(item, dict) for item in ops
    ):
        report({}, "BLOCKED", "bad_params ops", 0)
        return 0
    if not ops:
        report({}, "UNSUPPORTED", "no_ops", 0)
        return 0

    deadline = time.perf_counter() + max(1.0, timeout_s)
    results = []
    over = []
    for index, op in enumerate(ops):
        label = op.get("name", "op%d" % index)
        kind = op.get("kind")
        if kind not in ("sleep_ms", "sort_n", "sha256_kb", "json_items"):
            report({}, "BLOCKED", "bad_params op kind", 0)
            return 0
        try:
            size = float(op.get(_SIZE_KEY[kind], 0))
        except (TypeError, ValueError):
            report({}, "BLOCKED", "bad_params op size", 0)
            return 0
        if size < 0 or size > 10000000:
            report({}, "BLOCKED", "bad_params op size", 0)
            return 0
        try:
            budget = float(op.get("budget_ms", params.get("budget_ms", _DEFAULT_BUDGET_MS)))
        except (TypeError, ValueError):
            report({}, "BLOCKED", "bad_params budget_ms", 0)
            return 0
        if budget < 0:
            report({}, "BLOCKED", "bad_params budget_ms", 0)
            return 0
        if time.perf_counter() >= deadline:
            report(
                {"ops": results},
                "FAIL",
                "bench_timeout",
                len(results) if results else 1,
            )
            return 0
        started = time.perf_counter()
        try:
            _run_op(kind, size)
        except Exception as exc:
            report({"ops": results}, "FAIL", "op_error %s: %s" % (label, exc), len(results) + 1)
            return 0
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        ok = elapsed_ms <= budget
        results.append(
            {
                "name": label,
                "kind": kind,
                "elapsed_ms": round(elapsed_ms, 2),
                "budget_ms": budget,
                "ok": ok,
            }
        )
        if not ok:
            over.append(label)
    payload = {"ops": results}
    if over:
        report(
            payload,
            "FAIL",
            "over budget: %s" % ", ".join(over),
            len(results),
        )
    else:
        report(
            payload,
            "PASS",
            "%d op(s) within budget" % len(results),
            len(results),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
