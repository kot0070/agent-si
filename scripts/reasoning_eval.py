"""Reasoning-effort eval for the app's own agent roles (H105).

One command, stdlib only (+ the app's own protocol/prompts modules for
prompts and deterministic grading, never a model as grader):

  python reasoning_eval.py [--workers 1..4] [--probe-only]

GRID: model meta/muse-spark-1.3-contributor over the same base URL the app
uses (provider presets: https://api.meta.ai/v1, chat-completions path).
Reasoning levels: PROBED FIRST against the live API (candidate levels x
two wire shapes); refused values are recorded and never gridded. Plus the
no-parameter-sent baseline (today's app behaviour: the gateway transport
sends only model+messages). 3 repeats per (task, level) cell. Calls run
in a thread pool (sequential default --workers 1, at most 4 parallel).

SET: reasoning_eval_set.json next to this file (FIXED before any run):
director 4 (3 plan tasks with a stated parts range + 1 plain question),
worker 4 (single-turn file tasks through the real action protocol),
auditor 4 (finished parts, 2 seeded-wrong), solo 2 (plain questions).
Graders are deterministic: the app's own protocol parsers
(parse_director_reply / parse_agent_reply / parse_auditor_reply) plus an
exact check (parts count in range / exact path+content / verdict match /
expected word in text). No model grades anything.

PER CELL (level x role): pass@1, median + p90 latency, mean input +
output + reasoning tokens, mean cost at the app's own price table
(model catalog, contributor tier: USD 0.10 input / 0.20 output per 1M;
cost = (in*0.10 + completion*0.20)/1e6 exactly like the app's budget
gate, which bills completion tokens including reasoning), blank count.

DECISION RULE (frozen before the first run; never changed after seeing
numbers):
  cheapest level whose pass@1 per role is within 2 points (percentage
  points) of the best pass@1 for that role; ties go to lower latency
  (median latency for that role+level).
Computed by decide_role() below; the report quotes its output verbatim.

KEY: read ONLY from env AGENT_SI_EVAL_KEY (set by the gateway child's
environment only). Refuses to run without it; never reads key files,
never takes a key by argv, never prints or stores it.
"""
import argparse
import concurrent.futures as _fut
import json
import os
import statistics as _stats
import sys
import time
import urllib.error as _urlerror
import urllib.request as _urlrequest

HERE = os.path.dirname(os.path.abspath(__file__))
# APP copy: this file lives in APP/scripts, the app sources in APP/src.
APP_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(APP_ROOT, "src"))

from agent_si.runtime.devrun import protocol as _protocol  # noqa: E402
from agent_si.runtime.devrun import engine as _engine  # noqa: E402
from agent_si.runtime.devrun import audit as _audit  # noqa: E402

SET_PATH = os.path.join(HERE, "reasoning_eval_set.json")
# APP copy: default reports land next to this script; pass --out-json /
# --out-md to put them elsewhere.
DEFAULT_JSON = os.path.join(HERE, "REASONING_EVAL.json")
DEFAULT_MD = os.path.join(HERE, "REASONING_EVAL.md")

MODEL = "muse-spark-1.3-contributor"
BASE_URL = "https://api.meta.ai/v1"  # same base URL as the app's meta preset
CHAT_PATH = "/chat/completions"
PRICE_IN_1M = 0.10  # USD, app model catalog, contributor tier
PRICE_OUT_1M = 0.20  # USD, app model catalog, contributor tier
REPEATS = 3
CALL_TIMEOUT_S = 120
PROBE_TIMEOUT_S = 60
MAX_WORKERS = 4

CANDIDATE_LEVELS = ["low", "medium", "high", "max"]
# Two wire shapes for one level; the first shape the probe accepts wins.
SHAPES = ("reasoning_effort", "reasoning.effort")

#: Frozen decision text (see module docstring). decide_role() implements it.
DECISION_RULE_TEXT = (
    "cheapest level whose pass@1 per role is within 2 points "
    "(percentage points) of the best pass@1 for that role; "
    "ties go to lower latency (median latency for that role+level)"
)

ENV_KEY = "AGENT_SI_EVAL_KEY"


# ---------------------------------------------------------------- prompts
def director_messages(task):
    return [{"role": "user", "content": _engine._director_prompt(task["message"])}]


def worker_messages(task):
    spec = {"part_id": task["id"], "goal": task["goal"],
            "files": list(task["files"])}
    return [{"role": "user", "content": _engine._worker_prompt(
        spec, task["message"], 1, [], [])}]


def auditor_messages(task):
    return _audit.auditor_messages(
        task["goal"], task["files_diff"], list(task["checks"]), (), (),
        part_diff="", part_files=dict(task.get("part_files") or {}))


def solo_messages(task):
    return [{"role": "user", "content": task["question"]}]


# ---------------------------------------------------------------- graders
def grade_director(task, text):
    try:
        parsed = _protocol.parse_director_reply(text or "")
    except _protocol.PlanError as exc:
        return False, "director parse: %s" % (exc,)
    if task["kind"] == "question":
        return (True, "answer ok") if "answer" in parsed else (
            False, "no answer key")
    try:
        n = len(parsed["parts"])
    except (KeyError, TypeError):
        return False, "no parts list"
    lo, hi = task["expected_parts"]
    if lo <= n <= hi:
        return True, "parts=%d in [%d,%d]" % (n, lo, hi)
    return False, "parts=%d outside [%d,%d]" % (n, lo, hi)


def grade_worker(task, text):
    try:
        parsed = _protocol.parse_agent_reply(text or "")
    except _protocol.AgentError as exc:
        return False, "agent parse: %s" % (exc,)
    want_path = task["expected"]["path"].strip().replace("\\", "/")
    want_body = task["expected"]["content"].strip()
    for action in parsed.get("actions", []):
        if not isinstance(action, dict):
            continue
        if action.get("action") != "write_file":
            continue
        got_path = str(action.get("path", "")).strip().replace("\\", "/")
        got_body = str(action.get("content", "")).strip()
        if _protocol._clean_path(got_path) != want_path:
            continue
        if got_body == want_body:
            return True, "write %s exact" % (want_path,)
        return False, "path ok, content differs"
    return False, "no write_file for %s" % (want_path,)


def grade_auditor(task, text):
    try:
        parsed = _protocol.parse_auditor_reply(text or "")
    except _protocol.AuditError as exc:
        return False, "auditor parse: %s" % (exc,)
    if parsed.get("result") == task["expected"]:
        return True, "verdict %s matches" % (task["expected"],)
    return False, "verdict %s, expected %s" % (
        parsed.get("result"), task["expected"])


def grade_solo(task, text):
    want = task["expected_word"].strip().lower()
    if want and want in (text or "").lower():
        return True, "word %r present" % (want,)
    return False, "word %r absent" % (want,)


BUILDERS = {"director": director_messages, "worker": worker_messages,
            "auditor": auditor_messages, "solo": solo_messages}
GRADERS = {"director": grade_director, "worker": grade_worker,
           "auditor": grade_auditor, "solo": grade_solo}


# ---------------------------------------------------------------- http
def _post(base_url, key, payload, timeout_s):
    data = json.dumps(payload).encode("utf-8")
    req = _urlrequest.Request(
        base_url.rstrip("/") + CHAT_PATH, data=data, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key})
    try:
        with _urlrequest.urlopen(req, timeout=timeout_s) as resp:
            return resp.status, resp.read().decode("utf-8")
    except _urlerror.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        return exc.code, body
    except Exception as exc:
        return None, "%s: %s" % (type(exc).__name__, str(exc)[:160])


def _norm_usage(usage):
    out = {}
    if not isinstance(usage, dict):
        return out
    for key in ("input_tokens", "output_tokens", "reasoning_tokens"):
        val = usage.get(key)
        if isinstance(val, int) and not isinstance(val, bool):
            out[key] = val
    prompt = usage.get("prompt_tokens")
    if "input_tokens" not in out and isinstance(prompt, int):
        out["input_tokens"] = prompt
    comp = usage.get("completion_tokens")
    if "output_tokens" not in out and isinstance(comp, int):
        out["output_tokens"] = comp
    det = usage.get("completion_tokens_details")
    if "reasoning_tokens" not in out and isinstance(det, dict):
        val = det.get("reasoning_tokens")
        if isinstance(val, int):
            out["reasoning_tokens"] = val
    return out


def cost_usd(usage):
    """App-gate math: (in*0.10 + completion*0.20)/1e6; None when unknown."""
    inp = usage.get("input_tokens")
    outp = usage.get("output_tokens")
    if inp is None and outp is None:
        return None
    try:
        return ((PRICE_IN_1M * int(inp or 0)
                 + PRICE_OUT_1M * int(outp or 0)) / 1_000_000)
    except (TypeError, ValueError):
        return None


def one_call(base_url, key, messages, level, shape, timeout_s):
    payload = {"model": MODEL, "messages": messages, "stream": False}
    if level != "none":
        if shape == "reasoning_effort":
            payload["reasoning_effort"] = level
        else:
            payload["reasoning"] = {"effort": level}
    t0 = time.monotonic()
    status, raw = _post(base_url, key, payload, timeout_s)
    dt = time.monotonic() - t0
    if status != 200:
        return {"ok_text": "", "usage": {}, "error": "http-%s" % (status,),
                "latency_s": dt, "blank": True,
                "error_body": (raw or "")[:160]}
    try:
        body = json.loads(raw)
    except ValueError:
        return {"ok_text": "", "usage": {}, "error": "non-JSON",
                "latency_s": dt, "blank": True, "error_body": (raw or "")[:160]}
    choices = body.get("choices") if isinstance(body, dict) else None
    text = ""
    if isinstance(choices, list) and choices:
        msg = (choices[0] or {}).get("message", {})
        if isinstance(msg, dict):
            text = str(msg.get("content", "") or "")
    usage = _norm_usage((body or {}).get("usage", {}))
    return {"ok_text": text, "usage": usage, "error": None,
            "latency_s": dt, "blank": not text.strip(),
            "error_body": ""}


# ---------------------------------------------------------------- probe
def level_payload_shape(level, shape):
    if shape == "reasoning_effort":
        return {"reasoning_effort": level}
    return {"reasoning": {"effort": level}}


def classify_probe(status, raw):
    """accepted = HTTP 200. refused = anything else (record values)."""
    if status == 200:
        return True, ""
    low = (raw or "").lower()
    for marker in ("reasoning", "effort", "unsupported", "unknown",
                   "invalid", "unrecognized"):
        if marker in low:
            return False, "refused (%s)" % marker
    return False, "refused http-%s" % (status,)


def probe_levels(base_url, key):
    """Probe candidate levels x shapes once each. Returns (accepted, probe)."""
    probe_msgs = [{"role": "user",
                   "content": "Reply with exactly: probe ok"}]
    accepted = {}  # level -> winning shape (first accepted in SHAPES order)
    probe = []
    for level in CANDIDATE_LEVELS:
        for shape in SHAPES:
            payload = {"model": MODEL, "messages": probe_msgs,
                       "stream": False}
            payload.update(level_payload_shape(level, shape))
            status, raw = _post(base_url, key, payload, PROBE_TIMEOUT_S)
            ok, note = classify_probe(status, raw)
            entry = {"level": level, "shape": shape,
                     "accepted": bool(ok), "status": status, "note": note,
                     "body_tail": (raw or "")[:160]}
            probe.append(entry)
            if ok and level not in accepted:
                accepted[level] = shape
    return accepted, probe


# ---------------------------------------------------------------- stats
def _pct(vals, pct):
    if not vals:
        return None
    ordered = sorted(vals)
    idx = min(len(ordered) - 1, max(0, int(-(-pct * len(ordered) // 1)) - 1))
    return float(ordered[idx])


def cell_stats(rows):
    ok = [r for r in rows if r.get("ok")]
    lat = [r["latency_s"] for r in rows
           if isinstance(r.get("latency_s"), (int, float))]
    costs = [r["cost_usd"] for r in rows
             if isinstance(r.get("cost_usd"), (int, float))]
    def _mean(vals):
        return (sum(vals) / len(vals)) if vals else None
    return {
        "n": len(rows),
        "passes": len(ok),
        "pass_at_1": (len(ok) / len(rows)) if rows else 0.0,
        "latency_median_s": _stats.median(lat) if lat else None,
        "latency_p90_s": _pct(lat, 0.90) if lat else None,
        "mean_input_tokens": _mean([r["usage"].get("input_tokens", 0)
                                    for r in rows]),
        "mean_output_tokens": _mean([r["usage"].get("output_tokens", 0)
                                     for r in rows]),
        "mean_reasoning_tokens": _mean([r["usage"].get("reasoning_tokens", 0)
                                        for r in rows]),
        "mean_cost_usd": _mean(costs),
        "blanks": sum(1 for r in rows if r.get("blank")),
    }


def decide_role(level_order, stats_by_level):
    """Implement DECISION_RULE_TEXT for one role. Returns (winner, detail)."""
    scored = {lv: stats_by_level[lv]["pass_at_1"] for lv in level_order}
    best = max(scored.values())
    eligible = [lv for lv in level_order
                if scored[lv] >= best - 0.02]
    def _cost(lv):
        val = stats_by_level[lv]["mean_cost_usd"]
        return val if isinstance(val, (int, float)) else float("inf")
    cheapest = min(_cost(lv) for lv in eligible)
    cands = [lv for lv in eligible if _cost(lv) == cheapest]
    if len(cands) == 1:
        return cands[0], {"best": best, "eligible": eligible}
    def _lat(lv):
        val = stats_by_level[lv]["latency_median_s"]
        return val if isinstance(val, (int, float)) else float("inf")
    winner = min(cands, key=_lat)
    return winner, {"best": best, "eligible": eligible, "tie": list(cands)}


# ---------------------------------------------------------------- run
def load_set():
    with open(SET_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    tasks = []
    for role in ("director", "worker", "auditor", "solo"):
        for task in data[role]:
            item = dict(task)
            item["role"] = role
            tasks.append(item)
    return tasks


def run_cell(base_url, key, task, level, shape, rep, timeout_s):
    messages = BUILDERS[task["role"]](task)
    res = one_call(base_url, key, messages, level, shape, timeout_s)
    ok, note = GRADERS[task["role"]](task, res["ok_text"])
    if res["blank"]:
        ok, note = False, "blank reply"
    usage = res["usage"]
    return {
        "role": task["role"], "task_id": task["id"], "level": level,
        "shape": shape, "repeat": rep, "ok": bool(ok), "note": note,
        "latency_s": round(res["latency_s"], 2),
        "usage": usage, "cost_usd": cost_usd(usage),
        "blank": bool(res["blank"]), "error": res["error"],
    }


def main(argv):
    ap = argparse.ArgumentParser(
        description="reasoning-effort eval: probe levels, grid the set, "
                    "decide per role (key only via %s)" % ENV_KEY)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--probe-only", action="store_true")
    ap.add_argument("--sample", default="",
                      help="timing sample: comma-separated task ids (default S1)")
    ap.add_argument("--call-timeout", type=int, default=CALL_TIMEOUT_S)
    ap.add_argument("--out-json", default=DEFAULT_JSON)
    ap.add_argument("--out-md", default=DEFAULT_MD)
    args = ap.parse_args(argv)
    workers = max(1, min(int(args.workers or 1), MAX_WORKERS))

    key = os.environ.get(ENV_KEY, "")
    if not key:
        print("refused: no key in %s (run via the gateway mode)" % ENV_KEY)
        return 2
    t_start = time.monotonic()
    tasks = load_set()

    accepted, probe = probe_levels(BASE_URL, key)
    refused = ["%s/%s" % (p["shape"], p["level"])
               for p in probe if not p["accepted"]]
    levels = [("none", "no-parameter-sent")]
    for level in CANDIDATE_LEVELS:
        if level in accepted:
            levels.append((level, accepted[level]))
    if args.probe_only:
        print("probe accepted=%s refused=%s" % (
            sorted(accepted), sorted(set(refused))))
        return 0
    if args.sample:
        tids = [t.strip() for t in str(args.sample).split(",") if t.strip()] or ["S1"]
        for tid in tids:
            task = [t for t in tasks if t["id"] == tid][0]
            for level, shape in levels:
                res = one_call(BASE_URL, key, BUILDERS[task["role"]](task),
                               level, shape,
                               int(args.call_timeout or CALL_TIMEOUT_S))
                print("sample task=%s level=%s latency=%.1fs tokens=%s "
                      "blank=%s err=%s" % (
                          tid, level, res["latency_s"], res["usage"],
                          res["blank"], res["error"]))
        return 0

    jobs = [(task, level, shape, rep)
            for (level, shape) in levels
            for task in tasks
            for rep in range(1, REPEATS + 1)]
    rows = []
    timeout_s = int(args.call_timeout or CALL_TIMEOUT_S)
    if workers == 1:
        for task, level, shape, rep in jobs:
            rows.append(run_cell(BASE_URL, key, task, level, shape, rep,
                                 timeout_s))
    else:
        with _fut.ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(run_cell, BASE_URL, key, task, level,
                                shape, rep, timeout_s)
                    for task, level, shape, rep in jobs]
            for fut in _fut.as_completed(futs):
                rows.append(fut.result())
    rows.sort(key=lambda r: (r["level"], r["role"], r["task_id"],
                             r["repeat"]))

    level_order = [lv for lv, _ in levels]
    cells = {}
    for lv, shape in levels:
        cells[lv] = {"shape": shape}
        for role in ("director", "worker", "auditor", "solo"):
            cells[lv][role] = cell_stats(
                [r for r in rows if r["level"] == lv and r["role"] == role])
    decisions = {}
    for role in ("director", "worker", "auditor", "solo"):
        winner, detail = decide_role(
            level_order, {lv: cells[lv][role] for lv in level_order})
        decisions[role] = {"winner": winner, "detail": detail}

    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    wall_s = round(time.monotonic() - t_start, 1)
    doc = {"meta": {"model": MODEL, "base_url": BASE_URL,
                    "price_in_1m_usd": PRICE_IN_1M,
                    "price_out_1m_usd": PRICE_OUT_1M,
                    "repeats": REPEATS, "workers": workers,
                    "levels": [{"level": lv, "shape": sh}
                               for lv, sh in levels],
                    "decision_rule": DECISION_RULE_TEXT,
                    "probe": probe, "generated_at": stamp,
                    "wall_s": wall_s, "set_tasks": len(tasks)},
           "cells": cells, "decisions": decisions, "rows": rows}
    with open(args.out_json, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)

    def _f(val, fmt="%0.3f"):
        return fmt % val if isinstance(val, (int, float)) else "n/a"

    lines = ["# Reasoning-effort eval (%s)" % MODEL,
             "",
             "Set is small (%d tasks); no exact claim beyond the rows below." % (
                 len(tasks),),
             "",
             "| level | director pass@1 | worker pass@1 | auditor pass@1 | "
             "solo pass@1 | mean cost/attempt USD | median s | p90 s | blanks |",
             "|---|---|---|---|---|---|---|---|---|"]
    for lv, _ in levels:
        parts = [lv]
        for role in ("director", "worker", "auditor", "solo"):
            c = cells[lv][role]
            parts.append("%0.2f (%d/%d)" % (
                c["pass_at_1"], c["passes"], c["n"]))
        lat_all = [r["latency_s"] for r in rows if r["level"] == lv]
        costs = [r["cost_usd"] for r in rows
                 if r["level"] == lv
                 and isinstance(r.get("cost_usd"), (int, float))]
        blanks = sum(1 for r in rows if r["level"] == lv and r.get("blank"))
        parts.append(_f(sum(costs) / len(costs), "%0.6f") if costs else "n/a")
        parts.append(_f(_stats.median(lat_all)) if lat_all else "n/a")
        parts.append(_f(_pct(lat_all, 0.90)) if lat_all else "n/a")
        parts.append(str(blanks))
        lines.append("| " + " | ".join(parts) + " |")
    lines += ["",
              "Decision per role (%s):" % DECISION_RULE_TEXT]
    for role in ("director", "worker", "auditor", "solo"):
        d = decisions[role]
        lines.append("- %s: %s (eligible %s, best %0.2f)" % (
            role, d["winner"], ",".join(d["detail"]["eligible"]),
            d["detail"]["best"]))
    lines += ["",
              "Probe: accepted levels %s; refused %s." % (
                  sorted(accepted) or ["none"],
                  sorted(set(refused)) or ["none"]),
              "Baseline 'none' sends no reasoning parameter (today's app "
              "behaviour).",
              "Price: app model catalog, contributor tier: USD %.2f input / "
              "%.2f output per 1M tokens; cost bills completion tokens "
              "(reasoning included) exactly like the app budget gate." % (
                  PRICE_IN_1M, PRICE_OUT_1M),
              "Run wall time: %.1f s for %d attempts "
              "(one command, %d parallel)." % (
                  wall_s, len(rows), workers),
              "",
              "## Commands",
              "",
              "Run (key only in the gateway child environment):",
              "  set AGENT_SI_EVAL_KEY in the child env only, then",
              "  python scripts/reasoning_eval.py [--workers 1..4]",
              "Direct (needs %s in the environment):" % ENV_KEY,
              "  python scripts/reasoning_eval.py "
              "[--workers 1..4] [--probe-only]",
              "Offline checks (no key, no network):",
              "  python -m pytest tests/test_scripts_reasoning_eval.py",
              ""]
    with open(args.out_md, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("eval done: levels=%s rows=%d decisions=%s" % (
        level_order, len(rows),
        {r: decisions[r]["winner"] for r in decisions}))
    print("wrote %s and %s" % (args.out_json, args.out_md))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
