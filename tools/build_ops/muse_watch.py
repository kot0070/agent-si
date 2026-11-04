#!/usr/bin/env python3
# Development tool for this build, shown as written. Not part of the app.
# Machine paths, server addresses and session ids were replaced by <PLACEHOLDERS>; the logic is unchanged.
"""muse_watch.py - the Director's separate watcher over running Muse Code runs.

Commands
  loop  [--interval 30] [--idle-min 20] [--cost-step 0.5]   scan until killed; writes
        <state-dir>\\watch_heartbeat.txt (unix seconds) and <state-dir>\\watch.pid
  once  [same options]                                       one scan; prints the status table

Each scan reads <logs-root>\\*\\status.json (runs started by muse_run.py), the NEW tail of
every running run's events.jsonl and the run's Muse session store (root + child
session.jsonl files, also read incrementally from saved offsets), then writes
<state-dir>\\WATCH_STATUS.md and drops FEW inbox events (muse.started / finished / idle /
dead / model / cost / leftovers / child_failed). Every event is emitted at most once
(keys kept in <state-dir>\\watch_state.json).

Read-only on the run logs and the session store; never stops or changes any process.
Python 3.13 stdlib only (ctypes kernel32 only to test whether a pid is alive).
"""
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
import re
import sys
import time
import traceback
from pathlib import Path

try:
    import msvcrt
except ImportError:          # not Windows: no state lock (the tool targets Windows)
    msvcrt = None

# ---------------------------------------------------------------- constants
DIRECTOR = Path(__file__).resolve().parents[2]
DEF_LOGS = DIRECTOR / "LOGS" / "muse"
DEF_INBOX = DIRECTOR / "INBOX" / "new"
DEF_STATE = DIRECTOR / "MUSE_CODE"
EXPECTED_MODEL = "muse-spark-1.3-contributor"
# USD per 1M tokens (same table and formula as muse_run.py)
PRICES = {"muse-spark-1.3-contributor": {"input": 0.10, "cached": 0.002, "output": 0.20}}
STATE_VERSION = 1
FINISHED_ROWS = 10           # rows in WATCH_STATUS.md
FINISHED_KEEP = 50           # rows kept in the state file
HB_DEAD_S = 45               # status.json older than this + both pids gone -> dead
HB_STALE_S = 90              # shown as "hb!" in the table
SCHED_DEAD_RESEND_S = 3600   # DIRCCTRL1-F1: sched.dead inbox event at most once per hour
READ_CHUNK = 4 << 20
ERROR_LOG_MAX = 200_000
REMINDER_RE = re.compile(r"reminder|observer|recall", re.I)
FAIL_RE = re.compile(r"fail|cancel|abort|error|kill|timed?_?out|reject|crash|interrupt", re.I)
SID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{5,127}$")
ECHO_MODELS = {None, "", "None", "null", "echo"}
ROLE_ABBR = {"manager": "mgr", "auditor": "aud", "worker": "wrk", "probe": "prb"}


def cost_for(model, inp, cached, out, reasoning):
    """Copied from muse_run.py. Returns (cost, cost_if_reasoning_separate, priced, reasoning_added)."""
    p = PRICES.get(model or "")
    if not p:
        return 0.0, 0.0, False, False
    uncached = inp - cached if cached <= inp else inp
    reasoning_added = reasoning > out          # cannot be included -> must be separate
    out_billed = out + reasoning if reasoning_added else out
    base = uncached * p["input"] / 1e6 + cached * p["cached"] / 1e6
    return (base + out_billed * p["output"] / 1e6,
            base + (out + reasoning) * p["output"] / 1e6, True, reasoning_added)


# ---------------------------------------------------------------- small helpers
def local_now() -> str:
    return dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def local_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def write_text(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def replace_retry(tmp: Path, path: Path) -> None:
    for _ in range(30):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:      # a reader holds the target open
            time.sleep(0.1)
    os.replace(tmp, path)


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    write_text(tmp, text)
    replace_retry(tmp, path)


def read_json(path: Path, default=None):
    for _ in range(10):
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except (json.JSONDecodeError, PermissionError, UnicodeDecodeError):
            time.sleep(0.15)
        except OSError:
            return default
    return default


def iso_epoch(s):
    if not isinstance(s, str) or not s:
        return None
    try:
        return dt.datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


def mtime(path) -> float:
    try:
        return os.stat(path).st_mtime
    except OSError:
        return 0.0


def fmt_dur(s) -> str:
    if s is None:
        return "-"
    s = max(0, int(s))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def fmt_tok(n) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1e6:.2f}M"
    if n >= 1000:
        return f"{n / 1e3:.1f}k"
    return str(n)


def one_line(s, n: int) -> str:
    if not isinstance(s, str):
        return ""
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "\u2026"


def short_ws(p) -> str:
    if not p:
        return "-"
    return Path(str(p)).name or str(p)


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------- pid liveness (read-only)
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
ERROR_ACCESS_DENIED = 5
if os.name == "nt":
    import ctypes.wintypes as wt
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    _k32.OpenProcess.restype = ctypes.c_void_p
    _k32.CloseHandle.argtypes = [ctypes.c_void_p]
    _k32.CloseHandle.restype = wt.BOOL
    _k32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.DWORD)]
    _k32.GetExitCodeProcess.restype = wt.BOOL
    _k32.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(wt.FILETIME)] * 4
    _k32.GetProcessTimes.restype = wt.BOOL
    _k32.GetCurrentProcess.argtypes = []
    _k32.GetCurrentProcess.restype = ctypes.c_void_p

    def _create_time(h):
        c, e, k, u = wt.FILETIME(), wt.FILETIME(), wt.FILETIME(), wt.FILETIME()
        if not _k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)):
            return None
        return (c.dwHighDateTime << 32) | c.dwLowDateTime

    def pid_alive(pid, create_time=None) -> bool:
        """True if pid runs (and, when given, has the stored create time). Access denied = alive."""
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return False
        if pid <= 0:
            return False
        h = _k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return ctypes.get_last_error() == ERROR_ACCESS_DENIED
        try:
            code = wt.DWORD()
            if not _k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return True
            if code.value != STILL_ACTIVE:
                return False
            if create_time:
                ct = _create_time(h)
                if ct is not None and ct != int(create_time):
                    return False                 # pid reused by another process
            return True
        finally:
            _k32.CloseHandle(h)

    def own_create_time():
        return _create_time(_k32.GetCurrentProcess())
else:
    def pid_alive(pid, create_time=None) -> bool:
        try:
            os.kill(int(pid), 0)
            return True
        except (OSError, TypeError, ValueError):
            return False

    def own_create_time():
        return None


# ---------------------------------------------------------------- state lock
class StateLock:
    """OS lock so `once` and `loop` never scan at the same time (no duplicate events)."""

    def __init__(self, path: Path, timeout: float = 90.0):
        self.path, self.timeout, self.f = path, timeout, None

    def __enter__(self):
        if msvcrt is None:
            return self
        self.f = open(self.path, "a+b")
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
                return self
            except OSError:
                if time.monotonic() > deadline:
                    self.f.close()
                    raise TimeoutError(f"state lock busy: {self.path}")
                time.sleep(0.2)

    def __exit__(self, *exc):
        if self.f is not None:
            try:
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
            finally:
                self.f.close()
        return False


# ---------------------------------------------------------------- incremental JSONL reading
def consume(path: Path, off: int, handle) -> int:
    """Feed every complete JSON line after byte `off` to handle(obj); return the new offset."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return off
    if size < off:                    # rewritten / truncated: start over
        off = 0
    if size == off:
        return off
    pos = off
    carry = b""
    with open(path, "rb") as f:
        f.seek(off)
        while True:
            chunk = f.read(READ_CHUNK)
            if not chunk:
                break
            buf = carry + chunk
            nl = buf.rfind(b"\n")
            if nl < 0:
                carry = buf
                continue
            for raw in buf[:nl].split(b"\n"):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    o = json.loads(raw.decode("utf-8", "replace"))
                except ValueError:
                    continue
                if isinstance(o, dict):
                    try:
                        handle(o)
                    except Exception:        # unknown shapes never crash the watcher
                        pass
            pos += nl + 1
            carry = buf[nl + 1:]
    return pos


def note_model(lst: list, m) -> None:
    if isinstance(m, str) and m not in lst:
        lst.append(m)


def add_usage(d: dict, model, inp, cached, out, reasoning, calls=1) -> None:
    key = model if isinstance(model, str) and model else "null"
    u = d.setdefault(key, [0, 0, 0, 0, 0])
    u[0] += _int(inp)
    u[1] += _int(cached)
    u[2] += _int(out)
    u[3] += _int(reasoning)
    u[4] += _int(calls)


def merge_usage(dst: dict, src: dict) -> None:
    for m, v in src.items():
        u = dst.setdefault(m, [0, 0, 0, 0, 0])
        for i in range(5):
            u[i] += v[i]


# ---- events.jsonl (Muse `exec --json` stream of the root run)
def new_eacc():
    return {"off": 0, "models": [], "tools": 0, "tool_fail": 0, "main": None, "usage": {},
            "term": None, "spawns": 0, "sid": None}


def events_handler(a):
    def h(o):
        st = o.get("stream")
        if a["sid"] is None and isinstance(st, dict) and st.get("kind") == "session":
            a["sid"] = st.get("id")
        pt = o.get("payload_type")
        p = o.get("payload")
        if not isinstance(pt, str) or not isinstance(p, dict):
            return
        rs = p.get("run_stream")
        rsid = rs.get("id") if isinstance(rs, dict) else None
        if a["main"] is None and rsid:
            a["main"] = rsid
        if pt == "run.model.configured":
            note_model(a["models"], p.get("model_id"))
        elif pt == "run.usage":
            ms = []
            for m in p.get("models") or []:
                if isinstance(m, dict):
                    note_model(a["models"], m.get("model"))
                    ms.append([m.get("model"), _int(m.get("input_tokens")), _int(m.get("cached_tokens")),
                               _int(m.get("output_tokens")), _int(m.get("reasoning_tokens")), _int(m.get("calls"))])
            a["usage"][rsid or "?"] = {"ci": bool(p.get("children_included")), "m": ms}
        elif pt.startswith("run.terminal"):
            if rsid is None or rsid == a["main"]:
                a["term"] = str(p.get("terminal") or pt.rsplit(".", 1)[-1])
        elif pt == "tool.result":
            cf = p.get("correlation_facts") if isinstance(p.get("correlation_facts"), dict) else {}
            a["tools"] += 1
            oc = cf.get("outcome")
            if isinstance(oc, str) and oc != "success":
                a["tool_fail"] += 1
            if str(cf.get("tool_name") or "").endswith("subagent_spawn"):
                a["spawns"] += 1
    return h


# ---- session store: <session>\session.jsonl and subagent\<child>\session.jsonl (nested)
def new_sacc(sid, parent, depth):
    return {"sid": sid, "parent": parent, "depth": depth, "off": 0, "mt": 0.0, "last_ts": 0,
            "usage": {}, "rem": {}, "links": {}, "bound": {}, "spawn": {}, "result": {}, "cfail": {},
            "started": 0, "terms": 0, "last_term": None, "tools": 0, "tool_fail": 0,
            "models": [], "owners": [], "cfg_model": None}


def session_handler(a):
    sid = a["sid"]

    def h(o):
        ts = o.get("recorded_at")
        if isinstance(ts, int) and ts > a["last_ts"]:
            a["last_ts"] = ts
        pt = o.get("payload_type")
        p = o.get("payload")
        if not isinstance(pt, str) or not isinstance(p, dict):
            return
        if pt == "runtime.session":
            ev = p.get("event")
            if p.get("kind") != "run" or not isinstance(ev, dict):    # task/* events are not needed
                return
            k = ev.get("kind")
            if k == "model_completed":
                u = ev.get("usage") if isinstance(ev.get("usage"), dict) else {}
                add_usage(a["usage"], ev.get("model"), u.get("input_tokens"), u.get("cached_tokens"),
                          u.get("output_tokens"), u.get("reasoning_tokens"))
                note_model(a["models"], ev.get("model"))
            elif k == "started":
                a["started"] += 1
            elif k == "terminal":
                a["terms"] += 1
                a["last_term"] = str(ev.get("terminal"))
            elif k == "goal_usage_attribution":
                r = ev.get("record") if isinstance(ev.get("record"), dict) else {}
                ow = r.get("owner") if isinstance(r.get("owner"), dict) else {}
                ot = str(ow.get("owner_type") or "")
                if ot and ot not in a["owners"]:
                    a["owners"].append(ot)
                oid = str(ow.get("owner_id") or "?")
                # usage of Muse's reminder/observer child runs (most are never persisted as dirs)
                if REMINDER_RE.search(ot) and r.get("usage_family") in (None, "provider") and oid != sid:
                    q = r.get("quantity") if isinstance(r.get("quantity"), dict) else {}
                    u = a["rem"].setdefault(oid, [0, 0, 0, 0, 0])
                    u[0] += _int(q.get("input_tokens"))
                    u[1] += _int(q.get("cached_tokens"))
                    u[2] += _int(q.get("output_tokens"))
                    u[3] += _int(q.get("reasoning_tokens"))
                    u[4] += 1
            elif isinstance(ev.get("child_session_id"), str) and REMINDER_RE.search(str(k)):
                a["links"][ev["child_session_id"]] = str(ev.get("reminder_agent_id") or k)[:40]
        elif pt == "tool_batch.effect.terminal":
            r = p.get("record") if isinstance(p.get("record"), dict) else {}
            oc = r.get("outcome") if isinstance(r.get("outcome"), dict) else {}
            tc = oc.get("task_completion") if isinstance(oc.get("task_completion"), dict) else {}
            term = tc.get("terminal").get("kind") if isinstance(tc.get("terminal"), dict) else None
            a["tools"] += 1
            if (isinstance(term, str) and term != "completed") or FAIL_RE.search(str(oc.get("kind") or "")):
                a["tool_fail"] += 1
        elif pt.startswith("subagent.control."):
            r = p.get("record") if isinstance(p.get("record"), dict) else {}
            k = str(r.get("kind") or pt.rsplit(".", 1)[-1])
            sub = r.get("subagent_id")
            if not isinstance(sub, str):
                return
            if k == "spawn_accepted":
                da = r.get("definition_grant_audit") if isinstance(r.get("definition_grant_audit"), dict) else {}
                a["spawn"][sub] = {"path": str(r.get("agent_path") or "")[:80], "depth": r.get("depth"),
                                   "def": str(da.get("definition_name") or "")[:40]}
            elif k == "child_session_bound":
                if isinstance(r.get("child_session_id"), str):
                    a["bound"][r["child_session_id"]] = sub
            elif k == "start_attested":
                if isinstance(r.get("subagent_session_id"), str):
                    a["bound"].setdefault(r["subagent_session_id"], sub)
            elif k == "result_ready":
                ek = r.get("error_kind")
                a["result"][sub] = {"o": str(r.get("result_report_outcome")),
                                    "e": None if ek in (None, "", "none") else str(ek)[:60]}
            elif k == "status_updated":
                cs = str(r.get("control_status") or "")
                if FAIL_RE.search(cs):
                    a["cfail"][sub] = cs[:40]
            elif FAIL_RE.search(k):
                a["cfail"][sub] = k[:40]
        elif pt in ("run.model.configured", "runtime.session.metadata"):
            r = p.get("record") if isinstance(p.get("record"), dict) else {}
            m = r.get("model_id")
            note_model(a["models"], m)
            if a["cfg_model"] is None and isinstance(m, str):
                a["cfg_model"] = m
    return h


def enum_session_files(sdir: Path):
    """[(key, sid, parent_sid, depth, path)] for the root session and every nested child."""
    out = [(".", sdir.name, None, 0, sdir / "session.jsonl")]
    stack = [(sdir, sdir.name, 0, "")]
    while stack:
        d, sid, depth, rel = stack.pop()
        try:
            entries = sorted(os.scandir(d / "subagent"), key=lambda e: e.name)
        except OSError:
            continue
        for e in entries:
            if not e.is_dir():
                continue
            crel = f"{rel}subagent/{e.name}"
            out.append((crel, e.name, sid, depth + 1, Path(e.path) / "session.jsonl"))
            stack.append((Path(e.path), e.name, depth + 1, crel + "/"))
    return out


def update_session(rs: dict) -> float:
    """Read the new tail of every session file of the run; return the newest file mtime."""
    newest = 0.0
    sdir = rs.get("sdir")
    if not sdir:
        return newest
    files = rs.setdefault("files", {})
    for key, sid, parent, depth, path in enum_session_files(Path(sdir)):
        a = files.get(key)
        if a is None:
            a = files[key] = new_sacc(sid, parent, depth)
        mt = mtime(path)
        newest = max(newest, mt)
        if mt and mt != a["mt"]:
            a["off"] = consume(path, a["off"], session_handler(a))
            a["mt"] = mt
    return newest


# ---------------------------------------------------------------- tree view
def usage_cost(u: dict):
    total = 0.0
    unpriced = []
    for m, v in u.items():
        c, _alt, priced, _radd = cost_for(None if m == "null" else m, v[0], v[1], v[2], v[3])
        total += c
        if not priced and any(v[:4]):
            unpriced.append(m)
    return total, unpriced


def tree_view(rs: dict) -> dict:
    files = rs.get("files") or {}
    ea = rs.get("eacc") or new_eacc()
    links, bound, spawn, result, cfail = {}, {}, {}, {}, {}
    covered = set()
    for a in files.values():
        links.update(a["links"])
        bound.update(a["bound"])
        spawn.update(a["spawn"])
        result.update(a["result"])
        cfail.update(a["cfail"])
        covered.update(a["rem"].keys())
    u_root, u_work, u_rem = {}, {}, {}
    root = files.get(".")
    if root is not None:
        merge_usage(u_root, root["usage"])
    else:                                     # no session store: fall back to the exec stream usage
        main = ea["usage"].get(ea.get("main") or "")
        chosen = [main] if main else list(ea["usage"].values())
        if main and not main["ci"]:
            chosen += [v for k, v in ea["usage"].items() if k != ea.get("main")]
        for u in chosen:
            for m in u["m"]:
                add_usage(u_root, m[0], m[1], m[2], m[3], m[4], m[5])
    kids = {"run": 0, "done": 0, "fail": 0, "pend": 0, "rem": 0, "depth": 0}
    failed, children = [], []
    tool_fail = root["tool_fail"] if root else ea["tool_fail"]
    tools = root["tools"] if root else ea["tools"]
    models = list(ea["models"])
    run_model = rs.get("model") or EXPECTED_MODEL
    for key, a in files.items():
        for m in a["models"]:
            note_model(models, m)
        for oid, v in a["rem"].items():
            add_usage(u_rem, a["cfg_model"] or (next(iter(a["usage"]), None)) or run_model,
                      v[0], v[1], v[2], v[3], v[4])
        if key == ".":
            continue
        sid = a["sid"]
        if sid in links or any(REMINDER_RE.search(t) for t in a["owners"]):
            kids["rem"] += 1
            if sid not in covered:
                merge_usage(u_rem, a["usage"])
            continue
        merge_usage(u_work, a["usage"])
        tool_fail += a["tool_fail"]
        tools += a["tools"]
        sub = bound.get(sid)
        if sub is None and not any("native" in t for t in a["owners"]) and not a["started"]:
            kids["pend"] += 1                # not classified yet (no records so far)
            continue
        res = result.get(sub) if sub else None
        cf = cfail.get(sub) if sub else None
        why = None
        if res and (res.get("e") or FAIL_RE.search(res.get("o") or "")):
            state, why = "failed", res.get("e") or res.get("o")
        elif cf:
            state, why = "failed", cf
        elif a["started"] > a["terms"]:
            state = "running"
        elif a["last_term"] and a["last_term"] != "completed":
            state, why = "failed", a["last_term"]
        elif a["last_term"] == "completed" or res:
            state = "done"
        else:
            state = "running"
        label = (spawn.get(sub) or {}).get("path") or ("child-" + sid[-8:])
        kids["depth"] = max(kids["depth"], a["depth"])
        kids[{"running": "run", "done": "done", "failed": "fail"}[state]] += 1
        children.append({"sid": sid, "label": label, "state": state})
        if state == "failed":
            failed.append({"sid": sid, "label": label, "why": str(why)[:60]})
    u_tree = {}
    for u in (u_root, u_work, u_rem):
        merge_usage(u_tree, u)
    c_root, _ = usage_cost(u_root)
    c_work, _ = usage_cost(u_work)
    c_rem, _ = usage_cost(u_rem)
    c_tree, unpriced = usage_cost(u_tree)
    tok = [0, 0, 0, 0, 0]
    for v in u_tree.values():
        for i in range(5):
            tok[i] += v[i]
    return {"kids": kids, "children": children, "failed": failed,
            "cost": {"root": c_root, "workers": c_work, "reminders": c_rem, "tree": c_tree},
            "tokens": {"in": tok[0], "cached": tok[1], "out": tok[2], "reasoning": tok[3], "calls": tok[4]},
            "unpriced": unpriced, "tool_fail": tool_fail, "tools": tools, "models": models,
            "last_ts": max([a["last_ts"] for a in files.values()] or [0])}


def bad_models(models, provider) -> list:
    out = []
    for m in models:
        if m == EXPECTED_MODEL:
            continue
        if provider == "echo" and (m in ECHO_MODELS or "echo" in str(m).lower()):
            continue
        if m in (None, ""):
            continue
        out.append(m)
    return out


# ---------------------------------------------------------------- run discovery
def list_run_dirs(logs_root: Path):
    try:
        entries = sorted(os.scandir(logs_root), key=lambda e: e.name)
    except OSError:
        return []
    return [Path(e.path) for e in entries if e.is_dir() and os.path.isfile(os.path.join(e.path, "status.json"))]


def sessions_root_default() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "muse" / "sessions"


def resolve_sdir(rs: dict, s: dict, summary: dict | None, sessions_root: Path):
    if rs.get("sdir") and Path(rs["sdir"]).is_dir():
        return rs["sdir"]
    for v in ((summary or {}).get("session_dir"), s.get("session_dir")):
        if isinstance(v, str) and v and Path(v).is_dir():
            return v
    sid = (rs.get("eacc") or {}).get("sid") or (summary or {}).get("session_id")
    if isinstance(sid, str) and SID_RE.match(sid):
        hits = list(sessions_root.glob(f"*/*/*/{sid}"))
        if hits:
            return str(hits[0])
    return None


def ram_tail(path: Path):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 1024))
            data = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    lines = [x for x in data.strip().splitlines() if x.strip()]
    if not lines:
        return None
    parts = lines[-1].split(",")
    try:
        return {"t_s": float(parts[0]), "n_procs": int(parts[1]), "ws_mb": float(parts[2]),
                "priv_mb": float(parts[3])}
    except (ValueError, IndexError):
        return None


def new_run_state(rid: str, d: Path, s: dict, now: float) -> dict:
    return {"run_id": rid, "id": s.get("id") or rid, "role": s.get("role"), "ws": s.get("workspace"),
            "run_dir": str(d), "provider": s.get("provider"), "model": s.get("model"),
            "start": iso_epoch(s.get("start")) or mtime(d / "status.json") or now,
            "first_seen": now, "emitted": [], "eacc": new_eacc(), "files": {}, "sdir": None,
            "cost_idx": 0, "m": {}}


# SETUP-2A provider_error open
PROVIDER_ERROR_RE = re.compile(r"402|429|5\d\d|billing|insufficient|quota|rate limit", re.I)
# PE-01 (2026-10-25 21:2x): a bare 3-digit number matched sequence numbers, token counts and ids -> 790 false events,
# 0 real ones. A status code counts only next to status/http; lines that carry model or tool TEXT are never scanned.
PROVIDER_STATUS_RE = re.compile(r"(?i)(?:status(?:_code)?|http)\W{0,4}(402|429|5\d\d)\b")
PROVIDER_WORD_RE = re.compile(r"billing|insufficient|quota|rate limit", re.I)
CONTENT_KIND_RE = re.compile(r'"kind":\s*"(assistant_[a-z_]*|reasoning_[a-z_]*|tool_delta|output|tool_result[a-z_]*|'
                             r'model_input_trace_recorded|user_message[a-z_]*|turn_input[a-z_]*|run_started|task_stream_linked|tool_call[a-z_]*)"')


def provider_error_code(line: str):
    """Return the provider-error code for one events.jsonl line, or None (SETUP-2A rule helper)."""
    if CONTENT_KIND_RE.search(line):
        return None
    m = PROVIDER_STATUS_RE.search(line)
    if m:
        return m.group(1)
    m = PROVIDER_WORD_RE.search(line)
    if m:
        return " ".join(m.group(0).lower().split())
    return None


def check_provider_errors(self, rs: dict, d: Path) -> None:
    """Scan the new tail of a run's events.jsonl; emit one muse.provider_error per (run id, code)."""
    path = d / "events.jsonl"
    try:
        size = os.path.getsize(path)
    except OSError:
        return
    off = rs.get("provider_error_off", 0)
    if not isinstance(off, int) or off < 0:
        off = 0
    if size < off:                    # rewritten / truncated: start over
        off = 0
    if size == off:
        rs["provider_error_off"] = off
        return
    try:
        with open(path, "rb") as f:
            f.seek(off)
            data = f.read()
    except OSError:
        return
    nl = data.rfind(b"\n")
    if nl < 0:                        # no complete line yet: wait for the newline
        return
    rs["provider_error_off"] = off + nl + 1
    for raw in data[:nl].split(b"\n"):
        line = raw.decode("utf-8", "replace").strip()
        if not line:
            continue
        if not PROVIDER_ERROR_RE.search(line):
            continue
        code = provider_error_code(line)
        if code is None:
            continue
        self.emit(rs, "muse.provider_error", "provider_error:%s" % code,
                  "%s provider error %s: %s" % (rs.get("id") or rs.get("run_id"), code, one_line(line, 100)),
                  "provider billing/quota/rate-limit: check credits and quota, then re-run; see %s" % (path,),
                  {"code": code, "line": line[:200]})
# SETUP-2A provider_error close


def _canon_path(p) -> str:
    """L-001: canonical path key (realpath + normcase) for EVERY path comparison."""
    return os.path.normcase(os.path.realpath(os.fspath(p)))


def scan_hd_requests(workspace_root):
    """Pending HD_REQUEST*.md under <workspace>/_task and <workspace>/DIRECTOR/TASK_PACKAGES.

    L-068 numbered variants are real requests; L-120/L-103 cover both roots; a bounded
    recursive walk prunes tmp and node_modules at any depth; missing roots give [].
    Pending iff NO HD_VERDICT*.md in the same folder has mtime >= the request mtime.
    Returns sorted pending Paths."""
    req_mark = os.path.normcase("HD_REQUEST")
    ver_mark = os.path.normcase("HD_VERDICT")
    md_mark = os.path.normcase(".md")
    roots = [Path(str(workspace_root)) / "_task",
             Path(str(workspace_root)) / "DIRECTOR" / "TASK_PACKAGES"]
    found = {}
    for root in roots:
        try:
            if not root.is_dir():
                continue
        except OSError:
            continue
        stack = [(root, 0)]
        while stack:
            d, depth = stack.pop()
            if depth > 12:
                continue
            try:
                entries = sorted(os.scandir(d), key=lambda e: e.name)
            except OSError:
                continue
            for e in entries:
                try:
                    is_dir = e.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                if is_dir:
                    if os.path.basename(_canon_path(e.path)) in ("tmp", "node_modules"):
                        continue
                    stack.append((Path(e.path), depth + 1))
                else:
                    nm = os.path.normcase(e.name)
                    if not (nm.startswith(req_mark) and nm.endswith(md_mark)):
                        continue
                    try:
                        req_mt = e.stat(follow_symlinks=False).st_mtime
                    except OSError:
                        continue
                    pending = True
                    try:
                        for v in os.scandir(d):
                            vn = os.path.normcase(v.name)
                            if not (vn.startswith(ver_mark) and vn.endswith(md_mark)):
                                continue
                            try:
                                if not v.is_file(follow_symlinks=False):
                                    continue
                                if v.stat(follow_symlinks=False).st_mtime >= req_mt:
                                    pending = False
                                    break
                            except OSError:
                                pass
                    except OSError:
                        pass
                    if pending:
                        found.setdefault(_canon_path(e.path), Path(e.path))
    return [found[k] for k in sorted(found)]


_ROT_MOD = {"mod": None}


def load_rotation():
    """DIRROT1 M-ROT: sibling director_rotation.py, cached. Raises only when
    the helper file itself is missing or broken (the caller logs and skips)."""
    if _ROT_MOD["mod"] is None:
        spec = importlib.util.spec_from_file_location(
            "director_rotation",
            str(Path(__file__).resolve().parent / "director_rotation.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _ROT_MOD["mod"] = mod
    return _ROT_MOD["mod"]


# ---------------------------------------------------------------- watcher
OS32_RE = re.compile(r"(?i)(os error 32|winerror 32)")  # M-ROT32: check_chaos os32 anchor


class Watcher:
    def __init__(self, a):
        self.logs_root = Path(a.logs_root)
        self.inbox = Path(a.inbox)
        self.state_dir = Path(a.state_dir)
        self.sessions_root = Path(a.sessions_root) if a.sessions_root else sessions_root_default()
        self.interval = a.interval
        self.idle_s = a.idle_min * 60.0
        self.idle_min = a.idle_min
        self.cost_step = a.cost_step
        try:
            self.agent_silent_min = float(getattr(a, "agent_silent_min", 15.0))
        except (TypeError, ValueError):
            self.agent_silent_min = 15.0
        self.only = re.compile(a.only) if a.only else None
        self.mode = a.cmd
        self.state_path = self.state_dir / "watch_state.json"
        self.status_path = self.state_dir / "WATCH_STATUS.md"
        self.pending: list[dict] = []

    # ---- events
    def emit(self, rs: dict, kind: str, key: str, digest: str, next_hint: str, data: dict | None = None,
             rid: str | None = None) -> bool:
        em = rs.setdefault("emitted", [])
        if key in em:
            return False
        em.append(key)
        self.pending.append({"kind": kind, "id": rid or rs["run_id"], "digest": digest, "next_hint": next_hint,
                             "ts": local_iso(), "source": "muse_watch", "data": data or {}})
        return True

    def flush_events(self) -> list:
        out = []
        if not self.pending:
            return out
        self.inbox.mkdir(parents=True, exist_ok=True)
        for ev in self.pending:
            ms = int(time.time() * 1000)
            safe_id = re.sub(r"[^A-Za-z0-9._-]", "_", str(ev["id"]))[:90]
            name = f"{ms}_{ev['kind']}_{safe_id}.json"
            k = 2
            while (self.inbox / name).exists():
                name = f"{ms}_{ev['kind']}_{safe_id}_{k}.json"
                k += 1
            tmp = self.inbox / (name + ".tmp")          # the reader only picks *.json
            try:
                write_text(tmp, json.dumps(ev, ensure_ascii=False, indent=1) + "\n")
                replace_retry(tmp, self.inbox / name)
                out.append(ev)
            except OSError as ex:
                self.log_error(f"event write failed {name}: {ex!r}")
        self.pending = []
        return out

    # ---- scheduler liveness (DIRCCTRL1-F1: dead starter -> sched.dead inbox event)
    def _sched_run_dir(self):
        """DIRECTOR/RUN (AGENT_SI_ROOT-aware; explicit test paths win)."""
        env = os.environ.get("AGENT_SI_ROOT")
        if env and str(Path(self.state_dir)) == str(DEF_STATE):
            return Path(env) / "DIRECTOR" / "RUN"
        if Path(self.state_dir).name == "MUSE_CODE":
            return Path(self.state_dir).parent / "RUN"
        return Path(self.state_dir) / "RUN"

    def check_sched_alive(self, st: dict, now: float) -> list:
        """Scheduler pid file dead/missing -> one sched.dead inbox event (hourly)."""
        run_dir = self._sched_run_dir()
        try:
            pid = int((run_dir / "scheduler.pid").read_text(encoding="utf-8").strip().split()[0])
        except (OSError, ValueError, IndexError):
            pid = 0
        if pid > 0 and pid_alive(pid):
            return []
        try:
            ago = now - float(st.get("sched_dead_emitted") or 0)
        except (TypeError, ValueError):
            ago = SCHED_DEAD_RESEND_S
        if ago < SCHED_DEAD_RESEND_S:
            return []
        st["sched_dead_emitted"] = now
        self.pending.append({"kind": "sched.dead", "id": "scheduler",
                             "digest": "scheduler pid %s dead (no starter; cap unenforced)" % (pid or "?"),
                             "next_hint": "HD: dev.py start-all after live-start gap >=150s; queue untouched",
                             "ts": local_iso(), "source": "muse_watch", "data": {"pid": pid}})
        return [self.pending[-1]]

    # ---- silent agents (hook heartbeats without recent activity)
    def _silent_paths(self):
        """(heartbeats_dir, inbox_dir, notes_dir) honoring $AGENT_SI_ROOT."""
        hb_cli = Path(self.logs_root) / "heartbeats"
        inbox_cli = Path(self.inbox)
        notes_cli = inbox_cli.parent / "notes" if inbox_cli.name == "new" else inbox_cli / "notes"
        env = os.environ.get("AGENT_SI_ROOT")
        if not env:
            return hb_cli, inbox_cli, notes_cli
        if str(Path(self.logs_root)) != str(DEF_LOGS) or str(Path(self.inbox)) != str(DEF_INBOX):
            return hb_cli, inbox_cli, notes_cli     # explicit test paths win
        root = Path(env)
        return (root / "DIRECTOR" / "LOGS" / "muse" / "heartbeats",
                root / "DIRECTOR" / "INBOX" / "new",
                root / "DIRECTOR" / "INBOX" / "notes")

    def check_agent_silent(self, st: dict, now: float) -> list:
        """Emit muse.agent_silent for stale hook heartbeats (dedupe via watch_state.json)."""
        out = []
        try:
            thresh_min = float(self.agent_silent_min)
        except (TypeError, ValueError):
            thresh_min = 15.0
        if thresh_min <= 0:
            return out
        hb_dir, inbox_dir, notes_dir = self._silent_paths()
        try:
            entries = sorted(os.scandir(hb_dir), key=lambda e: e.name)
        except OSError:
            return out
        emitted = st.setdefault("agent_silent_emitted", [])
        # a root session never gets SubagentStop, and a stopped tree's children never do: skip every heartbeat that
        # belongs to a run that is no longer running (root session id = the run's session_dir name)
        ended_roots, any_live, live_start = set(), False, None
        for sp in Path(hb_dir).parent.glob("*/status.json"):
            try:
                with open(sp, "r", encoding="utf-8-sig") as f:
                    rs = json.load(f)
            except (OSError, ValueError):
                continue
            if rs.get("state") in ("running", "launching"):
                any_live = True
                st_ep = iso_epoch(rs.get("start"))
                if st_ep is not None:
                    live_start = st_ep if live_start is None else min(live_start, st_ep)
            elif rs.get("session_dir"):
                ended_roots.add(Path(str(rs["session_dir"])).name)
        if not any_live:
            return out
        # idle-tree rule: Muse keeps a tree flat (children's parent = root), so the newest heartbeat per root says whether
        # the tree still works; a waiting Manager is silent by design while its coders work
        all_hb, tree_last = {}, {}
        for e in entries:
            if e.is_file() and e.name.endswith(".json"):
                try:
                    with open(Path(e.path), "r", encoding="utf-8-sig") as f:
                        d = json.load(f)
                except (OSError, ValueError):
                    continue
                if isinstance(d, dict):
                    all_hb[e.name[:-5]] = d
        for s, d in all_hb.items():
            ep = iso_epoch(d.get("last_ts"))
            root = d.get("parent_session_id") or s
            if ep is not None:
                tree_last[root] = max(tree_last.get(root, 0.0), ep)
        for e in entries:
            if not e.is_file() or not e.name.endswith(".json") or e.name == "_errors.log":
                continue
            sid = e.name[:-5]
            try:
                with open(Path(e.path), "r", encoding="utf-8-sig") as f:
                    hb = json.load(f)
            except (OSError, ValueError):
                continue
            if not isinstance(hb, dict) or hb.get("status") == "done":
                continue
            if sid in ended_roots or hb.get("parent_session_id") in ended_roots:
                continue
            last_ts = hb.get("last_ts")
            ts_ep = iso_epoch(last_ts)
            if ts_ep is None:
                continue
            mins = (now - ts_ep) / 60.0
            if mins <= thresh_min:
                continue
            if live_start is not None and ts_ep < live_start:
                continue  # left over from a run that ended before every live run started
            root = hb.get("parent_session_id") or sid
            if (now - tree_last.get(root, ts_ep)) / 60.0 <= thresh_min:
                continue  # the tree is still working: this agent waits (e.g. a Manager on its coders)
            key = f"agent_silent:{sid}:{last_ts}"
            if key in emitted:
                continue
            name = hb.get("name") or sid
            parent = hb.get("parent_session_id")
            n = int(mins)
            stamp = dt.datetime.now().astimezone().strftime("%Y%m%d%H%M%S")
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(sid))[:90]
            ev = {"kind": "muse.agent_silent", "id": f"muse.agent_silent-{sid}-{stamp}",
                  "ts": local_iso(), "session": sid, "name": name, "parent": parent,
                  "minutes": n}
            try:
                inbox_dir.mkdir(parents=True, exist_ok=True)
                fname = f"muse-agent-silent-{safe}-{stamp}.json"
                k = 2
                while (inbox_dir / fname).exists():
                    fname = f"muse-agent-silent-{safe}-{stamp}_{k}.json"
                    k += 1
                write_text(inbox_dir / fname, json.dumps(ev, ensure_ascii=False, indent=1) + "\n")
            except OSError as ex:
                self.log_error(f"agent_silent event write failed {sid}: {ex!r}")
                continue
            if not parent:  # no known parent: the inbox event above reaches the Human Developer; never note the agent itself
                emitted.append(key)
                out.append(ev)
                continue
            try:
                notes_dir.mkdir(parents=True, exist_ok=True)
                with open(notes_dir / f"{parent}.txt", "a",
                          encoding="utf-8", newline="\n") as f:
                    f.write(f"agent {name} silent {n} min: check it; "
                            "cancel and restart it if hung\n")
            except OSError as ex:
                self.log_error(f"agent_silent note write failed {sid}: {ex!r}")
            emitted.append(key)
            out.append(ev)
        return out

    STEP_MIN = 20  # owner ladder (2026-10-25 20:2x): flags at 20 / 40 min, wake HD at 60, Director note at 80 if no HD ack
    NAG_MIN = 10  # L-084: unanswered HD request re-announced every 10 min
    WRITE_TOOLS = ("write_file","edit_file", "create_file", "apply_patch", "replace", "multi_edit")
    WAIT_TOOL_RE = re.compile(r"(?i)subagent_(wait|status|send_message|read_result)|work_(list|status)")
    POLL_CMD_RE = re.compile(r"(?i)test-path|start-sleep|timeout\s+/t")
    # absolute Windows paths (stop at blanks and shell syntax) and workspace-relative _task paths
    PATH_RE = re.compile(r"[A-Za-z]:\\[^\s;'\"|<>(){}]*|_task[\\/][^\s;'\"|<>(){}]*")

    @staticmethod
    def _tool(ev: dict) -> str:
        return str(ev.get("tool") or "").split(".")[-1]

    @staticmethod
    def _activity_rows(path: Path) -> list:
        rows = []
        if path.is_file():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if isinstance(ev, dict):
                    rows.append(ev)
        return rows

    def _newest_write(self, rows: list) -> float:
        return max([iso_epoch(ev.get("ts")) or 0.0 for ev in rows if self._tool(ev) in self.WRITE_TOOLS] or [0.0])

    def _as_dir(self, raw: str, cwd: str):
        raw = raw.rstrip("\\/.,:")
        p = Path(raw) if re.match(r"[A-Za-z]:", raw) else Path(cwd or ".") / raw
        try:
            if p.is_dir():
                return os.path.normcase(os.path.normpath(str(p)))
            if p.parent.is_dir():  # a polled file (it may not exist yet: HD_VERDICT2.md) -> its folder
                return os.path.normcase(os.path.normpath(str(p.parent)))
        except OSError:
            pass
        return None

    def _task_dir(self, rows: list):
        """Folder of the first *TASK*.md the agent read = the task it belongs to (tree_scan uses the same read)."""
        for ev in rows:
            target = str(ev.get("target") or "")
            if self._tool(ev) == "read_file" and re.search(r"(?i)task[^\\/]*\.md$", target):
                return self._as_dir(target, str(ev.get("cwd") or ""))
        return None

    def _polled_dirs(self, rows: list) -> set:
        dirs = set()
        for ev in rows:
            for m in self.PATH_RE.finditer(str(ev.get("target") or "")):
                d = self._as_dir(m.group(0), str(ev.get("cwd") or ""))
                if d:
                    dirs.add(d)
        return dirs

    @staticmethod
    def _is_descendant(sid, ancestor, pmap) -> bool:
        """True if following heartbeat parents from sid reaches ancestor."""
        cur, seen = pmap.get(sid), set()
        while cur and cur not in seen:
            if cur == ancestor:
                return True
            seen.add(cur)
            cur = pmap.get(cur)
        return False

    @staticmethod
    def _dir_newest(d: str) -> float:
        best = mtime(d)
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        best = max(best, e.stat().st_mtime)
                    except OSError:
                        pass
        except OSError:
            pass
        return best

    def check_stuck_ladder(self, st: dict, now: float) -> list:
        """Stuck ladder (STUCK2: stuck = NO tool call AND NO file change) -> flags 1, 2 silent
        (stuck_flags.log, dev.py status); 3 -> one inbox event stuck.ladder (wake the HD); 4 and no HD ack ->
        one Director note 'verify progress, never stop on this note alone'. Max one message per hour. Nothing acts."""
        out = []
        hb_dir, inbox_dir, notes_dir = self._silent_paths()
        logs = Path(hb_dir).parent
        roots = {}
        for sp in logs.glob("*/status.json"):
            try:
                with open(sp, "r", encoding="utf-8-sig") as f:
                    rs = json.load(f)
            except (OSError, ValueError):
                continue
            if rs.get("state") in ("running", "launching") and rs.get("session_dir"):
                roots[Path(str(rs["session_dir"])).name] = rs
        if not roots:
            return out
        lad = st.setdefault("stuck_ladder", {})
        msg = st.setdefault("stuck_msg", {})  # sid -> epoch of the HD wake, or "noted" after the Director note
        # STUCK2: child sids whose parent session account recorded a result (any outcome) count as ended
        ended = set()
        for rs in (st.get("runs") or {}).values():
            files = rs.get("files") if isinstance(rs, dict) else None
            if not isinstance(files, dict):
                continue
            res, bound = {}, {}
            for a in files.values():
                if isinstance(a, dict):
                    res.update(a.get("result") or {})
                    bound.update(a.get("bound") or {})
            for csid, sub in bound.items():
                if sub in res:
                    ended.add(csid)
        ack_dir = Path(inbox_dir).parent / "ack"
        flog = logs / "stuck_flags.log"
        agents = {}  # sid -> (heartbeat, root, activity rows) of the agents of live runs
        pmap = {}  # sid -> direct heartbeat parent (all heartbeats, any depth)
        for hb_p in Path(hb_dir).glob("*.json"):
            try:
                with open(hb_p, "r", encoding="utf-8-sig") as f:
                    hb0 = json.load(f)
            except (OSError, ValueError):
                continue
            sid0 = hb0.get("session_id") or hb_p.stem
            root0 = hb0.get("parent_session_id") or sid0
            pmap[sid0] = hb0.get("parent_session_id") or None
            if root0 in roots:
                agents[sid0] = (hb0, root0, self._activity_rows(logs / "activity" / (sid0 + ".jsonl")))
        # SL-01 (TH6): only RUNNING agents keep a waiter alive; a dead child's old writes never do
        live_writes = {}  # sid -> (root, task folder, newest write)
        for sid0, (hb0, root0, rows0) in agents.items():
            if hb0.get("status") != "done":
                live_writes[sid0] = (root0, self._task_dir(rows0), self._newest_write(rows0))
        for sid, (hb, root, rows) in agents.items():
            # STUCK2: ended agents are never stuck: drop the ladder entry and skip
            if hb.get("status") in ("done", "ended") or sid in ended or str(hb.get("last_event") or "").startswith("SubagentStop"):
                lad.pop(sid, None)
                continue
            # SL-01b: an agent without writes counts from its OWN first event, not from the run start
            base = iso_epoch(hb.get("first_ts") or "") or (iso_epoch(rows[0].get("ts")) if rows else 0.0) \
                or iso_epoch(roots[root].get("start")) or now
            # STUCK2: progress = writes + ANY tool call + task-folder change (reads/polls/waits count)
            td = self._task_dir(rows)
            any_ts = max([iso_epoch(ev.get("ts")) or 0.0 for ev in rows] or [0.0])
            progress = max(base, self._newest_write(rows), any_ts, self._dir_newest(td) if td else 0.0)
            last_tool = ("%s %s" % (self._tool(rows[-1]), str(rows[-1].get("target") or "")[-60:])) if rows else ""
            # a waiting parent (Director, Manager) is not stuck while what it WAITS FOR moves (owner: 'robota
            # vidpovidaie zavdanniu'). SL-01: TH6 M-NAV Manager polled 50 min for a coder dead since 20:16 while other
            # Managers wrote -> the whole-tree rule hid it. Now: the folders it polls + running agents tasked there.
            recent = rows[-5:]
            if any(self.WAIT_TOOL_RE.search(self._tool(ev)) or self.POLL_CMD_RE.search(str(ev.get("target") or ""))
                   for ev in recent):
                polled = self._polled_dirs(recent)
                others = [(td, w) for s2, (r2, td, w) in live_writes.items() if s2 != sid and r2 == root]
                if polled:
                    progress = max([progress] + [self._dir_newest(d) for d in polled]
                                   + [w for td, w in others if td in polled])
                else:  # waits without a visible target (bare subagent_wait): running agents of its tree
                    progress = max([progress] + [w for td, w in others])
                # M-SIG: a root/Manager sitting in subagent_wait whose TREE
                # (genealogical descendants, live or just ended) wrote within
                # STEP_MIN is progressing even outside the polled folders (or
                # polled by a tool the poll patterns miss): no level-up, no
                # flag, no event. Only the window counts, never old writes;
                # same-tree peers never keep a waiter alive (TH6/SL-01).
                if any("subagent_wait" in self._tool(r) for r in recent):
                    tw = 0.0
                    for s2 in pmap:
                        if s2 == sid or not self._is_descendant(s2, sid, pmap):
                            continue
                        if s2 in agents:
                            tw = max(tw, self._newest_write(agents[s2][2]))
                        else:
                            tw = max(tw, self._newest_write(self._activity_rows(
                                logs / "activity" / (s2 + ".jsonl"))))
                    if tw and now - tw <= self.STEP_MIN * 60:
                        progress = max(progress, now)
            ack = ack_dir / (sid + ".txt")
            if ack.is_file():
                progress = max(progress, ack.stat().st_mtime)
            level = min(4, int((now - progress) / 60 / self.STEP_MIN))
            prev = int(lad.get(sid, 0))
            if level == 0:
                lad.pop(sid, None)  # progress (or ack) resets the ladder
                msg.pop(sid, None)
                continue
            # SL-02: the HD is always woken first; the Director note only STEP_MIN after an unanswered wake (an agent
            # first seen at 80+ min used to jump to level 4 and skip the wake)
            woke = msg.get(sid)
            if level == 4 and not (isinstance(woke, (int, float)) and now - woke >= self.STEP_MIN * 60):
                level = 3
            name = hb.get("name") or sid
            line = "%s level=%d agent=%s run=%s no-progress=%d min last=%s" % (
                local_iso(), level, name, roots[root].get("run_id"), int((now - progress) / 60), last_tool)
            if level > prev:
                lad[sid] = level
                with open(flog, "a", encoding="utf-8", newline="\n") as f:
                    f.write(line + "\n")
            if level < 3 or (level == 3 and sid in msg) or (level == 4 and msg.get(sid) == "noted"):
                continue
            # max one message per hour (owner), counted per recipient: HD wakes and Director notes have their own clock.
            # SL-02: a message held back by the hour limit is NOT consumed - it goes out on a later scan
            channel = "stuck_last_msg" if level == 3 else "stuck_last_note"
            if now - float(st.get(channel, 0)) < 3600:
                continue
            if level == 3:
                ev = {"kind": "stuck.ladder", "id": "stuck-%s-%d" % (sid[:8], int(now)), "ts": local_iso(), "agent": name,
                      "run": roots[root].get("run_id"), "session": sid, "minutes": int((now - progress) / 60),
                      "last": last_tool,
                      "digest": "%s: no task progress for %d min - look: stuck (fresh agent) or still working; "
                                "ack with dev.py ack %s" % (name, int((now - progress) / 60), sid)}
                inbox_dir.mkdir(parents=True, exist_ok=True)
                write_text(inbox_dir / ("stuck-ladder-%s-%d.json" % (sid[:8], int(now))), json.dumps(ev, indent=1) + "\n")
                msg[sid] = now
            else:  # level 4: the HD did not react for 20 min -> one note to the Director (the run root)
                notes_dir.mkdir(parents=True, exist_ok=True)
                with open(notes_dir / ("%s.txt" % root), "a", encoding="utf-8", newline="\n") as f:
                    f.write("agent %s may be stuck (%d min without task progress). Verify its progress first; "
                            "never stop it on this note alone.\n" % (name, int((now - progress) / 60)))
                # PIPEFIX1 R1: escalate beyond the note - a stop-request event
                # the HD/scheduler can act on (the note alone never stopped a run).
                ev4 = {"kind": "stuck.stop_request", "id": "stuck-stop-%s-%d" % (sid[:8], int(now)),
                       "ts": local_iso(), "agent": name, "run": roots[root].get("run_id"),
                       "session": sid, "minutes": int((now - progress) / 60),
                       "last": last_tool,
                       "digest": "%s: no task progress for %d min - stop requested; "
                                 "verify with dev.py ack %s, then stop the run" % (
                                     name, int((now - progress) / 60), sid)}
                inbox_dir.mkdir(parents=True, exist_ok=True)
                write_text(inbox_dir / ("stuck-stop-%s-%d.json" % (sid[:8], int(now))),
                           json.dumps(ev4, indent=1) + "\n")
                msg[sid] = "noted"
                out.append(line)
            st[channel] = now
            out.append(line)
        # STUCK2: agents whose run ended vanish from heartbeats: drop their ladder entries
        for sid in list(lad):
            if sid not in agents:
                lad.pop(sid, None)
        return out

    ENDED_WAIT_RE = re.compile(r"(?i)\b(wait(s|ing)?|poll(s|ing)?|will report|on delivery|pending)\b")

    def check_ended_waiting(self, st: dict) -> list:
        """MW-01 (TH6): a child that ENDS while its parent waits for it deadlocks the tree (M-NAV: 50 min). On the
        child's SubagentStop (heartbeat status done + its last words, native payload) every running agent that polls
        the child's task folder gets a note at once; if the last words say it was still waiting, the HD gets an event."""
        out = []
        hb_dir, inbox_dir, notes_dir = self._silent_paths()
        logs = Path(hb_dir).parent
        roots = set()
        for sp in logs.glob("*/status.json"):
            rs = read_json(sp, None)
            if isinstance(rs, dict) and rs.get("state") in ("running", "launching") and rs.get("session_dir"):
                roots.add(Path(str(rs["session_dir"])).name)
        if not roots:
            return out
        now = time.time()
        handled = st.setdefault("ended_seen", [])
        agents = {}
        for hb_p in Path(hb_dir).glob("*.json"):
            hb = read_json(hb_p, None)
            if not isinstance(hb, dict):
                continue
            sid = hb.get("session_id") or hb_p.stem
            if (hb.get("parent_session_id") or sid) in roots:
                agents[sid] = (hb, self._activity_rows(logs / "activity" / (sid + ".jsonl")))
        for sid, (hb, rows) in agents.items():
            if hb.get("status") != "done" or sid in handled:
                continue
            # ENDW2 activity gate: done-status alone never ends an agent; only real
            # silence ends it. Reads/polls never gate (heartbeat last_ts stays
            # informational only); file-change signal is row-derived only, never fs mtime.
            live = False
            for ev in rows:
                if self._tool(ev) == "read_file":
                    continue
                ts = iso_epoch(ev.get("ts"))
                if ts is not None and now - ts <= 300:
                    live = True
                    break
            if live:
                continue
            handled.append(sid)
            task_dir = self._task_dir(rows)
            if not task_dir:
                continue
            name = hb.get("name") or sid
            last = str(hb.get("last_message") or "")
            waiters = [s2 for s2, (h2, rows2) in agents.items()
                       if s2 != sid and h2.get("status") != "done" and task_dir in self._polled_dirs(rows2[-5:])]
            text = ("agent %s has ENDED its session (last words: '%s'). It will not answer any more: do not wait for "
                    "it; read its RETURN in %s and act (a fresh agent gets that RETURN if work remains)."
                    % (name, last[:160], task_dir))
            for w in waiters:
                notes_dir.mkdir(parents=True, exist_ok=True)
                with open(notes_dir / ("%s.txt" % w), "a", encoding="utf-8", newline="\n") as f:
                    f.write(text + "\n")
            if last and self.ENDED_WAIT_RE.search(last):
                # ENDW1 parent note: the ended agent's parent waits on it too, so the parent
                # gets one line at once (matched by session ids only); the HD event below is unchanged.
                parent = hb.get("parent_session_id")
                running_kids = []
                for hb_p2 in Path(hb_dir).glob("*.json"):
                    hb2 = read_json(hb_p2, None)
                    if not isinstance(hb2, dict):
                        continue
                    if hb2.get("parent_session_id") == sid and hb2.get("status") != "done":
                        running_kids.append(hb2.get("name") or (hb2.get("session_id") or hb_p2.stem))
                running_kids = sorted(set(running_kids))
                phb = agents[parent][0] if parent in agents else read_json(Path(hb_dir) / ("%s.json" % parent), None)
                parent_alive = isinstance(phb, dict) and phb.get("status") != "done"
                parent_noted = None
                parent_missing = False
                if parent and parent_alive:
                    hhmm = dt.datetime.now().astimezone().strftime("%H:%M")
                    pnote = ("[watch %s] your child %s (%s) ENDED while waiting (last words: %s). "
                             "Its running children %d (%s) lost their tools. Do not wait for it: read %s, then spawn a "
                             "FRESH agent with the same task file and one state-so-far line for the remaining work; "
                             "never resume the ended one. Before a replacement: cancel it, then wait until it has made no tool call for 5 min; never two writers on one file."
                             % (hhmm, name, sid[:8], last[:160], len(running_kids), ", ".join(running_kids), task_dir))
                    notes_dir.mkdir(parents=True, exist_ok=True)
                    with open(notes_dir / ("%s.txt" % parent), "a", encoding="utf-8", newline="\n") as f:
                        f.write(pnote + "\n")
                    parent_noted = parent
                else:
                    parent_missing = True
                ev = {"kind": "agent.ended_waiting", "id": "ended-%s-%d" % (sid[:8], int(time.time())), "ts": local_iso(),
                      "agent": name, "waiters_noted": waiters, "digest": text,
                      "parent_noted": parent_noted}
                if parent_missing:
                    ev["parent_missing"] = True
                inbox_dir.mkdir(parents=True, exist_ok=True)
                write_text(inbox_dir / ("agent-ended-waiting-%s-%d.json" % (sid[:8], int(time.time()))),
                           json.dumps(ev, ensure_ascii=False, indent=1) + "\n")
                out.append(ev)
        del handled[:-500]
        return out

    def check_chaos(self, st: dict) -> list:
        """Loop guard: a LIVE agent (running run, running heartbeat) repeating one test (>3x), reading >40
        files, or past 2x its estimate (status.json estimate_min; absent: skip) -> one chaos.loop per agent+reason."""
        out = []
        now = time.time()
        hb_dir, inbox_dir, notes_dir = self._silent_paths()
        logs = Path(hb_dir).parent
        roots = {}
        for sp in logs.glob("*/status.json"):
            try:
                with open(sp, "r", encoding="utf-8-sig") as f:
                    rs = json.load(f)
            except (OSError, ValueError):
                continue
            if rs.get("state") in ("running", "launching") and rs.get("session_dir"):
                roots[Path(str(rs["session_dir"])).name] = rs
        if not roots:
            return out
        seen = st.setdefault("chaos_seen", [])
        test_re = re.compile(r"(?i)unittest|pytest|vitest|--test")
        agents = {}
        for hb_p in Path(hb_dir).glob("*.json"):
            try:
                with open(hb_p, "r", encoding="utf-8-sig") as f:
                    hb = json.load(f)
            except (OSError, ValueError):
                continue
            sid = hb.get("session_id") or hb_p.stem
            if hb.get("status") != "running" or (hb.get("parent_session_id") or sid) not in roots:
                continue
            agents[sid] = (hb, self._activity_rows(logs / "activity" / (sid + ".jsonl")))
        pending = []  # ENDW2 chaos note: (key, sid, hb, name, run_id, reason, digest, top, nreads)
        for sid, (hb, rows) in agents.items():
            rs = roots.get(hb.get("parent_session_id") or sid, {})
            name = hb.get("name") or sid
            cmds = {}
            changed = set()
            code_exts = (".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".html",
                         ".json", ".toml", ".sql", ".ps1", ".sh", ".rs")
            anchors = [(ai, " ".join(str(aev.get("target") or "").lower().split()))
                       for ai, aev in enumerate(rows)
                       if aev.get("failed") and OS32_RE.search(str(aev.get("error") or ""))]
            for i, ev in enumerate(rows):
                t = str(ev.get("target") or "")
                tl = t.replace("\\", "/").strip().lower()
                if (self._tool(ev) in self.WRITE_TOOLS and tl.endswith(code_exts)
                        and "_task" not in tl.split("/") and "director" not in tl.split("/")):
                    changed.update(cmds)
                    continue
                if test_re.search(t):
                    k = " ".join(t.lower().split())
                    if ev.get("failed"):  # L-134: only FAILING runs count
                        if any(k == ak and 1 <= i - ai <= 3 for ai, ak in anchors):
                            continue  # os32 window: transient retry, cmds untouched
                        if k not in cmds or k in changed:
                            cmds[k] = 1
                            changed.discard(k)
                        else:
                            cmds[k] = cmds.get(k, 0) + 1
                    else:  # a passing re-run resets this command's count
                        cmds[k] = 0
                        changed.discard(k)
            top = max(cmds.values(), default=0)
            reads = {str(ev.get("target") or "").strip() for ev in rows
                     if self._tool(ev) == "read_file" and str(ev.get("target") or "").strip()}
            try:
                est = float(rs.get("estimate_min")) * 60.0 if rs.get("estimate_min") is not None else 0.0
            except (TypeError, ValueError):
                est = 0.0
            start = iso_epoch(rs.get("start")) or 0.0
            wall = now - start if start else 0.0
            reasons = {}
            if top > 3:
                reasons["repeat-test"] = ("%s: chaos repeat-test: same test %d times - check the loop, fix or stop it"
                                          % (name, top))
            if len(reads) > 40:
                reasons["many-reads"] = ("%s: chaos many-reads: %d distinct files read - check the loop, fix or stop it"
                                         % (name, len(reads)))
            if est > 0 and wall > 2 * est:
                reasons["over-estimate"] = ("%s: chaos over-estimate: wall %s past 2x estimate %d min - check it"
                                            % (name, fmt_dur(wall), int(est / 60)))
            # ENDW2 chaos note: collect new events first; notes + digest counter need scan totals.
            for reason, digest in reasons.items():
                key = "%s|%s" % (sid, reason)
                if key in seen:
                    continue
                pending.append((key, sid, hb, name, rs.get("run_id"), reason, digest, top, len(reads)))
        hhmm = dt.datetime.now().astimezone().strftime("%H:%M")
        noted = {}
        for (key, sid, hb, name, run_id, reason, digest, top, nreads) in pending:
            parent = hb.get("parent_session_id")
            note = None
            if parent and reason == "repeat-test":
                note = ("[watch %s] chaos repeat-test: %s ran the same test %d times with NO code change. "
                        "Stop the reruns; read the failure once, fix the cause or report BLOCKED with the exact output."
                        % (hhmm, name, top))
            elif parent and reason == "many-reads":
                note = ("[watch %s] chaos many-reads: %s read %d distinct files. "
                        "Point reads only (changed files, their tests, the touched call path), in parts, no re-reads."
                        % (hhmm, name, nreads))
            if note is None:
                continue
            try:
                notes_dir.mkdir(parents=True, exist_ok=True)
                with open(notes_dir / ("%s.txt" % parent), "a", encoding="utf-8", newline="\n") as f:
                    f.write(note + "\n")
                noted[key] = parent
            except OSError as ex:
                self.log_error("chaos note write failed %s: %r" % (sid, ex))
        n_new, n_noted = len(pending), len(noted)
        for (key, sid, hb, name, run_id, reason, digest, top, nreads) in pending:
            stamp = dt.datetime.now().astimezone().strftime("%Y%m%d%H%M%S")
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", sid)[:90]
            ev = {"kind": "chaos.loop", "id": "chaos.loop-%s-%s" % (safe[:8], stamp), "ts": local_iso(),
                  "agent": name, "session": sid, "run": run_id, "reason": reason,
                  "digest": "%s | chaos: %d new, Managers noted %d" % (digest, n_new, n_noted)}
            if reason == "repeat-test":
                ev["data"] = {"failing": top, "unchanged_runs": top}
            ev["manager_noted"] = noted.get(key)
            try:
                inbox_dir.mkdir(parents=True, exist_ok=True)
                fname = "chaos-loop-%s-%s-%s.json" % (safe, reason, stamp)
                k = 2
                while (inbox_dir / fname).exists():
                    fname = "chaos-loop-%s-%s-%s_%d.json" % (safe, reason, stamp, k)
                    k += 1
                write_text(inbox_dir / fname, json.dumps(ev, ensure_ascii=False, indent=1) + "\n")
            except OSError as ex:
                self.log_error("chaos event write failed %s: %r" % (sid, ex))
                continue
            seen.append(key)
            out.append(ev)
        del seen[:-500]
        return out

    def check_poll_fast(self, st: dict) -> list:
        """Poll-fast guard: a LIVE agent polling a child more often than once per 120 s -> one watch.poll_fast."""
        out = []
        hb_dir, inbox_dir, notes_dir = self._silent_paths()
        logs = Path(hb_dir).parent
        roots = {}
        for sp in logs.glob("*/status.json"):
            try:
                with open(sp, "r", encoding="utf-8-sig") as f:
                    rs = json.load(f)
            except (OSError, ValueError):
                continue
            if rs.get("state") in ("running", "launching") and rs.get("session_dir"):
                roots[Path(str(rs["session_dir"])).name] = rs
        if not roots:
            return out
        seen = st.setdefault("pollfast_seen", [])
        agents = {}
        for hb_p in Path(hb_dir).glob("*.json"):
            try:
                with open(hb_p, "r", encoding="utf-8-sig") as f:
                    hb = json.load(f)
            except (OSError, ValueError):
                continue
            sid = hb.get("session_id") or hb_p.stem
            if hb.get("status") != "running" or (hb.get("parent_session_id") or sid) not in roots:
                continue
            agents[sid] = (hb, self._activity_rows(logs / "activity" / (sid + ".jsonl")))
        for sid, (hb, rows) in agents.items():
            key = "pollfast|%s" % sid
            if key in seen:
                continue
            polls = [ev for ev in rows
                     if self.WAIT_TOOL_RE.search(self._tool(ev))
                     or self.POLL_CMD_RE.search(str(ev.get("target") or ""))]
            gap = None
            for prev, cur in zip(polls, polls[1:]):
                t0, t1 = iso_epoch(prev.get("ts")), iso_epoch(cur.get("ts"))
                if t0 is None or t1 is None:
                    continue
                g = t1 - t0
                if g < 0:
                    continue
                if g < 120:
                    gap = g
                    break
            if gap is None:
                continue
            rs = roots.get(hb.get("parent_session_id") or sid, {})
            name = hb.get("name") or sid
            stamp = dt.datetime.now().astimezone().strftime("%Y%m%d%H%M%S")
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", sid)[:90]
            ev = {"kind": "watch.poll_fast", "id": "poll_fast-%s-%s" % (safe[:8], stamp), "ts": local_iso(),
                  "agent": name, "session": sid, "run": rs.get("run_id"),
                  "digest": "%s: polled again after %d s - slow polls to >=120 s apart" % (name, int(gap))}
            try:
                inbox_dir.mkdir(parents=True, exist_ok=True)
                fname = "pollfast-%s-%s.json" % (safe, stamp)
                k = 2
                while (inbox_dir / fname).exists():
                    fname = "pollfast-%s-%s-%s_%d.json" % (safe, stamp, k)
                    k += 1
                write_text(inbox_dir / fname, json.dumps(ev, ensure_ascii=False, indent=1) + "\n")
            except OSError as ex:
                self.log_error("poll_fast event write failed %s: %r" % (sid, ex))
                continue
            seen.append(key)
            out.append(ev)
        del seen[:-500]
        return out

    # ---- OUT-WS path base (OUTW1/ENDW2 M-OUTWS): an agent's own WT package dir, never the workspace root
    def _outws_base(self, rows: list, run_ws: str | None):
        """Path base for OUT-WS: the agent's own WT package dir first (WT/<PKG> holding its task dir).

        Every compare via _canon_path (L-001). Root-base (the run workspace) only for agents with no
        package dir; None when neither exists, and then the agent stays quiet (old fixtures)."""
        td = self._task_dir(rows)
        if td:
            try:
                parts = Path(td).parts
            except (TypeError, ValueError):
                parts = ()
            for i, part in enumerate(parts):
                if os.path.normcase(part) == os.path.normcase("WT") and i + 1 < len(parts):
                    return str(Path(*parts[: i + 2]))
        return run_ws or None

    def check_out_ws(self, st: dict) -> list:
        """OUT-WS (OUTW1): a LIVE agent's write-tool target outside its own _outws_base -> one agent.out_ws event.

        Own WT package writes count as in-workspace and never flag; the root base applies only with no
        package dir; with no base at all (old fixtures) the agent stays quiet. Dedupe per agent in st;
        additive only: every existing event kind/shape untouched."""
        out = []
        hb_dir, inbox_dir, _ = self._silent_paths()
        logs = Path(hb_dir).parent
        roots = {}
        for sp in logs.glob("*/status.json"):
            try:
                with open(sp, "r", encoding="utf-8-sig") as f:
                    rs = json.load(f)
            except (OSError, ValueError):
                continue
            if rs.get("state") in ("running", "launching") and rs.get("session_dir"):
                roots[Path(str(rs["session_dir"])).name] = rs
        if not roots:
            return out
        seen = st.setdefault("out_ws_seen", [])
        agents = {}
        for hb_p in Path(hb_dir).glob("*.json"):
            try:
                with open(hb_p, "r", encoding="utf-8-sig") as f:
                    hb = json.load(f)
            except (OSError, ValueError):
                continue
            sid = hb.get("session_id") or hb_p.stem
            if hb.get("status") != "running" or (hb.get("parent_session_id") or sid) not in roots:
                continue
            agents[sid] = (hb, self._activity_rows(logs / "activity" / (sid + ".jsonl")))
        for sid, (hb, rows) in agents.items():
            if sid in seen:
                continue
            rs = roots.get(hb.get("parent_session_id") or sid, {})
            base = self._outws_base(rows, rs.get("workspace"))
            if not base:
                continue
            canon_base = _canon_path(base)
            outside = []
            for ev in rows:
                if self._tool(ev) not in self.WRITE_TOOLS:
                    continue
                target = str(ev.get("target") or "")
                if not target:
                    continue
                full = target if os.path.isabs(target) else os.path.join(str(ev.get("cwd") or base), target)
                canon_full = _canon_path(os.path.normpath(full))
                if canon_full != canon_base and not canon_full.startswith(canon_base + os.sep):
                    outside.append(target)
            if not outside:
                continue
            name = hb.get("name") or sid
            stamp = dt.datetime.now().astimezone().strftime("%Y%m%d%H%M%S")
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", sid)[:90]
            ev = {"kind": "agent.out_ws", "id": "out-ws-%s-%s" % (safe[:8], stamp), "ts": local_iso(),
                  "agent": name, "session": sid, "run": rs.get("run_id"),
                  "digest": "%s: wrote %d path(s) outside its own package dir - check the targets"
                            % (name, len(outside)),
                  "writes": outside[:10]}
            try:
                inbox_dir.mkdir(parents=True, exist_ok=True)
                fname = "agent-out-ws-%s-%s.json" % (safe, stamp)
                k = 2
                while (inbox_dir / fname).exists():
                    fname = "agent-out-ws-%s-%s_%d.json" % (safe, stamp, k)
                    k += 1
                write_text(inbox_dir / fname, json.dumps(ev, ensure_ascii=False, indent=1) + "\n")
            except OSError as ex:
                self.log_error("out_ws event write failed %s: %r" % (sid, ex))
                continue
            seen.append(sid)
            out.append(ev)
        del seen[:-500]
        return out

    def check_hd_request(self, st: dict) -> list:
        """L-045: HD_REQUEST.md of a LIVE run -> inbox event hd.request (once per file version; malformed -> its own kind).
        <workspace>\\_task\\HD_REQUEST*.md and <workspace>\\DIRECTOR\\TASK_PACKAGES\\**\\HD_REQUEST*.md of running runs."""
        out = []
        hb_dir, inbox_dir, _ = self._silent_paths()
        seen = st.setdefault("hd_request_seen", [])
        opened = st.setdefault("hd_request_open", {})  # request file -> announce times (L-084 nag)
        live = set()
        for sp in Path(hb_dir).parent.glob("*/status.json"):
            try:
                with open(sp, "r", encoding="utf-8-sig") as f:
                    rs = json.load(f)
            except (OSError, ValueError):
                continue
            if rs.get("state") not in ("running", "launching") or not rs.get("workspace"):
                continue
            live.add(rs.get("run_id"))
            run_start = iso_epoch(rs.get("start")) or 0.0
            # HD_REQUEST*.md at any depth (D-HDW-1): one shared scan rule, _task + TASK_PACKAGES
            reqs = scan_hd_requests(rs["workspace"])
            for req in reqs:
                try:
                    if not req.is_file():
                        continue
                    if req.stat().st_mtime < run_start - 2:  # left by an earlier run in the same workspace (2 s clock slack)
                        continue
                    text = req.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                # analyst verdict on L-045: dedupe by CONTENT hash (a touched file is not a new request)
                key = "%s|%s" % (req, hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16])
                if key in seen:
                    continue
                # TH6: the 'required fields' gate swallowed REAL requests written in another format (Ask:, change:).
                # A request of a LIVE run, newer than its start, is never dropped: missing fields are only noted.
                low = text.lower()
                ok = ("files-changed:" in low or "files:" in low or "change:" in low) and ("ask:" in low or "native" in low)
                if not ok:
                    self.log_error("hd.request with missing fields (still announced) %s" % req)
                kind = "hd.request"
                stamp = dt.datetime.now().astimezone().strftime("%Y%m%d%H%M%S")
                ev = {"kind": kind, "id": "%s-%s" % (kind, stamp), "ts": local_iso(), "run": rs.get("run_id"),
                      "file": str(req), "digest": text.strip().splitlines()[0][:200] if text.strip() else "(empty)"}
                inbox_dir.mkdir(parents=True, exist_ok=True)
                write_text(inbox_dir / ("%s-%s-%s.json" % (kind.replace(".", "-"), stamp, key.rsplit("|", 1)[-1][:6])),
                           json.dumps(ev, ensure_ascii=False, indent=1) + "\n")
                seen.append(key)
                out.append(ev)
                opened[str(req)] = {"run": rs.get("run_id"), "announced": time.time(), "first": time.time()}
        # L-084: re-announce an unanswered request every NAG_MIN until any HD_VERDICT*.md newer than it exists
        now = time.time()
        for path, o in list(opened.items()):
            req = Path(path)
            req_t = mtime(req)
            answered = any(mtime(v) >= req_t for v in req.parent.glob("HD_VERDICT*.md"))
            if o.get("run") not in live or not req_t or answered:
                opened.pop(path, None)
                continue
            if now - float(o.get("announced", now)) < self.NAG_MIN * 60:
                continue
            o["announced"] = now
            mins = int((now - float(o.get("first", now))) / 60)
            stamp = dt.datetime.now().astimezone().strftime("%Y%m%d%H%M%S")
            ev = {"kind": "hd.request.nag", "id": "hd.request.nag-%s" % stamp, "ts": local_iso(), "run": o.get("run"),
                  "file": path, "digest": "UNANSWERED %d min: %s (write the matching HD_VERDICT*.md)" % (mins, req.name)}
            inbox_dir.mkdir(parents=True, exist_ok=True)
            write_text(inbox_dir / ("hd-request-nag-%s-%s.json" % (stamp, hashlib.sha256(path.encode()).hexdigest()[:6])),
                       json.dumps(ev, ensure_ascii=False, indent=1) + "\n")
            out.append(ev)
        del seen[:-200]
        return out

    def check_rotation(self, st: dict, now: float) -> list:
        """DIRROT1 M-ROT: an over-limit Director run rotates (note + replace
        marker); a director_reads flag notes (hits>=1) or replaces (hits>=2)
        that Director. Marker-file idempotent; never raises."""
        out = []
        try:
            rot = load_rotation()
        except Exception as ex:
            self.log_error(f"rotation helper unloadable: {ex!r}")
            return out
        hb_dir, inbox_dir, notes_dir = self._silent_paths()
        logs = Path(hb_dir).parent
        try:
            sps = sorted(logs.glob("*/status.json"), key=lambda p: p.parent.name)
        except OSError:
            return out
        noted = st.setdefault("rotation_noted", [])
        for sp in sps:
            try:
                with open(sp, "r", encoding="utf-8-sig") as f:
                    rs = json.load(f)
            except (OSError, ValueError):
                continue
            if not isinstance(rs, dict) or rs.get("state") not in ("running", "launching"):
                continue
            rid = str(rs.get("run_id") or sp.parent.name)
            try:
                self._rotation_one(rot, noted, logs, inbox_dir, notes_dir, rs, rid, out)
            except Exception:
                self.log_error(f"rotation {rid}: {traceback.format_exc(limit=6)}")
        del noted[:-200]
        return out

    def _rotation_event(self, inbox_dir: Path, rid: str, reason: str, handoff) -> None:
        stamp = dt.datetime.now().astimezone().strftime("%Y%m%d%H%M%S")
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", rid)[:90]
        ev = {"kind": "muse.director_rotate", "id": f"muse.director_rotate-{safe}-{stamp}",
              "ts": local_iso(), "run": rid, "reason": reason,
              "handoff": str(handoff) if handoff else None}
        try:
            inbox_dir.mkdir(parents=True, exist_ok=True)
            fname = f"muse-director-rotate-{safe}-{stamp}.json"
            k = 2
            while (inbox_dir / fname).exists():
                fname = f"muse-director-rotate-{safe}-{stamp}_{k}.json"
                k += 1
            tmp = inbox_dir / (fname + ".tmp")
            write_text(tmp, json.dumps(ev, ensure_ascii=False, indent=1) + "\n")
            replace_retry(tmp, inbox_dir / fname)
        except OSError as ex:
            self.log_error(f"rotation event write failed {rid}: {ex!r}")

    def _rotation_one(self, rot, noted: list, logs: Path, inbox_dir: Path, notes_dir: Path,
                      rs: dict, rid: str, out: list) -> None:
        marker = logs / rid / "DIRECTOR_REPLACE.json"
        try:
            marked = marker.is_file()
        except OSError:
            marked = False
        # read-flag path (M-READHOOK writes the flag; any live run may carry one)
        try:
            hits = rot.read_hits(rid, logs_root=logs)
        except Exception:
            hits = None
        if hits is not None and hits >= 2 and not marked:
            mp = rot.mark_for_replacement(rid, "director-reads", logs_root=logs, notes_dir=notes_dir)
            if mp is None:
                self.log_error(f"rotation mark failed {rid} (director-reads)")
                return
            self._rotation_event(inbox_dir, rid, "director-reads", rot.handoff_path_for_run(rid, logs_root=logs))
            out.append(rid + ":director-reads")
            return
        if hits == 1:
            key = f"rot:reads1:{rid}"
            if key not in noted:
                np = rot.write_director_note(
                    rid, f"DIRECTOR reads: 1 read/testrun event recorded against run {rid}. "
                         "No action needed; a second one rotates you (write DIRECTOR_HANDOFF.md and end).\n",
                    logs_root=logs, notes_dir=notes_dir)
                if np is None:
                    self.log_error(f"rotation note failed {rid} (reads1)")
                else:
                    noted.append(key)
                    self._rotation_event(inbox_dir, rid, "reads-note",
                                         rot.handoff_path_for_run(rid, logs_root=logs))
                    out.append(rid + ":reads-note")
        # threshold path: Director runs only, measured from the run's own logs
        if marked or not rot.is_director_run(rs):
            return
        try:
            over, reason = rot.should_rotate(rid, logs_root=logs, sessions_root=self.sessions_root)
        except Exception:
            return
        if not over:
            return
        try:
            if marker.is_file():
                return
        except OSError:
            pass
        mp = rot.mark_for_replacement(rid, reason, logs_root=logs, notes_dir=notes_dir)
        if mp is None:
            self.log_error(f"rotation mark failed {rid} ({reason})")
            return
        self._rotation_event(inbox_dir, rid, reason, rot.handoff_path_for_run(rid, logs_root=logs))
        out.append(rid + ":" + reason)

    def log_error(self, text: str) -> None:
        try:
            p = self.state_dir / "watch_errors.log"
            if p.exists() and p.stat().st_size > ERROR_LOG_MAX:
                os.replace(p, p.with_name("watch_errors.old.log"))
            with open(p, "a", encoding="utf-8", newline="\n") as f:
                f.write(f"{local_now()} {text}\n")
        except OSError:
            pass

    # ---- state
    def load_state(self) -> dict:
        st = read_json(self.state_path, None)
        if st is None and self.state_path.exists():
            try:
                os.replace(self.state_path, self.state_path.with_name("watch_state.bad.json"))
            except OSError:
                pass
        if not isinstance(st, dict) or st.get("version") != STATE_VERSION:
            st = {"version": STATE_VERSION, "initialized": False, "known": [], "runs": {}, "finished": []}
        return st

    def save_state(self, st: dict) -> None:
        write_atomic(self.state_path, json.dumps(st, ensure_ascii=False, separators=(",", ":")) + "\n")

    # ---- one running run
    def watch_running(self, rs: dict, d: Path, s: dict, now: float) -> None:
        ea = rs.setdefault("eacc", new_eacc())
        ea["off"] = consume(d / "events.jsonl", ea["off"], events_handler(ea))
        ev_mt = mtime(d / "events.jsonl")
        check_provider_errors(self, rs, d)
        rs["sdir"] = resolve_sdir(rs, s, None, self.sessions_root)
        sess_mt = update_session(rs)
        tv = tree_view(rs)
        hb_age = now - (mtime(d / "status.json") or now)
        runner_ok = pid_alive(s.get("runner_pid"), s.get("runner_create_time"))
        muse_ok = pid_alive(s.get("pid"), s.get("pid_create_time"))
        last_act = max(ev_mt, sess_mt, rs.get("start") or 0)
        quiet = now - last_act
        ram = ram_tail(d / "ram.csv")
        state = "running"
        if not runner_ok and not muse_ok:
            state = "DEAD?"
        elif not runner_ok:
            state = "orphan (runner gone)"
        elif not muse_ok:
            state = "muse exited"
        if quiet >= self.idle_s:
            state += f" IDLE {fmt_dur(quiet)}"
        if hb_age > HB_STALE_S:
            state += f" hb!{fmt_dur(hb_age)}"
        rs["m"] = {"wall": now - (rs.get("start") or now), "hb_age": hb_age, "runner": runner_ok, "muse": muse_ok,
                   "quiet": quiet, "ev_age": now - ev_mt if ev_mt else None, "kids": tv["kids"],
                   "tok_in": tv["tokens"]["in"], "tok_out": tv["tokens"]["out"], "cost": tv["cost"],
                   "tool_fail": tv["tool_fail"], "ram": ram, "state": state, "sdir": rs.get("sdir")}
        cost = tv["cost"]["tree"]
        # model alert (events stream or any session in the tree)
        bad = [m for m in bad_models(tv["models"], rs.get("provider")) if f"model:{m}" not in rs["emitted"]]
        if bad:
            for m in bad[1:]:
                rs["emitted"].append(f"model:{m}")
            self.emit(rs, "muse.model", f"model:{bad[0]}",
                      f"ALERT {rs['id']} uses model(s) {', '.join(map(str, bad))} (expected {EXPECTED_MODEL}); "
                      f"tree cost so far ${cost:.4f}",
                      "check the Manager/agents definitions; wrong model = wrong price/quality; stop it if not intended",
                      {"models": bad, "expected": EXPECTED_MODEL})
        # cost step
        if self.cost_step > 0:
            idx = int(math.floor(cost / self.cost_step + 1e-9))
            if idx > rs.get("cost_idx", 0):
                rs["cost_idx"] = idx
                k = tv["kids"]
                self.emit(rs, "muse.cost", f"cost:{idx}",
                          f"{rs['id']} whole-tree cost passed ${idx * self.cost_step:.2f}: now ${cost:.4f} "
                          f"(root ${tv['cost']['root']:.4f}, children ${tv['cost']['workers']:.4f}, "
                          f"reminders ${tv['cost']['reminders']:.4f}); wall {fmt_dur(rs['m']['wall'])}, "
                          f"children {k['run']} run/{k['done']} done/{k['fail']} failed",
                          "compare progress with the budget; see WATCH_STATUS.md",
                          {"cost_usd_tree": round(cost, 6), "step": self.cost_step})
        # failed children (one batched event per scan)
        new_failed = [f for f in tv["failed"] if f"cf:{f['sid']}" not in rs["emitted"]]
        if new_failed:
            for f in new_failed[1:]:
                rs["emitted"].append(f"cf:{f['sid']}")
            self.emit(rs, "muse.child_failed", f"cf:{new_failed[0]['sid']}",
                      f"{rs['id']}: {len(new_failed)} child agent(s) ended failed: "
                      + "; ".join(f"{f['label']} ({f['why']})" for f in new_failed[:6])
                      + (" ..." if len(new_failed) > 6 else ""),
                      "check that the Manager retries or reports it",
                      {"children": new_failed})
        # idle
        if quiet >= self.idle_s:
            k = tv["kids"]
            self.emit(rs, "muse.idle", f"idle:{int(last_act)}",
                      f"{rs['id']} idle {fmt_dur(quiet)}: no new event and no child session activity "
                      f"(children {k['run']} running; cost ${cost:.4f}; RAM {ram['ws_mb'] if ram else '-'} MB; "
                      f"runner {'alive' if runner_ok else 'GONE'}, muse {'alive' if muse_ok else 'GONE'})",
                      "look at the Manager (muse_run.py status --id " + str(rs["id"]) +
                      "); the runner's own idle watchdog stops the tree after its --idle-min",
                      {"quiet_s": round(quiet), "last_activity": dt.datetime.fromtimestamp(last_act).astimezone()
                       .isoformat(timespec="seconds")})
        # dead: status still says running but both processes are gone
        if not runner_ok and not muse_ok and hb_age >= HB_DEAD_S:
            s2 = read_json(d / "status.json", {}) or {}
            if s2.get("state") == "running":
                k = tv["kids"]
                self.emit(rs, "muse.dead", "dead",
                          f"{rs['id']} DEAD: status.json still says running but runner pid {s.get('runner_pid')} "
                          f"and muse pid {s.get('pid')} are gone (heartbeat {fmt_dur(hb_age)} old); "
                          f"tree cost ${cost:.4f}, children {k['done']} done/{k['fail']} failed/{k['run']} unfinished",
                          "run muse_run.py summarize <run_dir> --write, check the workspace, decide a re-run",
                          {"run_dir": str(d), "cost_usd_tree": round(cost, 6)})
                rs["dead"] = True

    # ---- finished run -> table row (+ events unless quiet)
    def finalize(self, rs: dict, d: Path, s: dict, now: float, quiet: bool, dead: bool = False) -> dict:
        summary = read_json(d / "summary.json", None)
        summary = summary if isinstance(summary, dict) else {}
        ea = rs.setdefault("eacc", new_eacc())
        ea["off"] = consume(d / "events.jsonl", ea["off"], events_handler(ea))
        rs["sdir"] = resolve_sdir(rs, s, summary, self.sessions_root)
        check_provider_errors(self, rs, d)
        update_session(rs)
        tv = tree_view(rs)
        leftovers = summary.get("leftovers")
        n_left = len(leftovers) if isinstance(leftovers, list) else _int(s.get("leftovers"))
        end = s.get("end") or summary.get("end")
        if dead and not end:                  # last sign of life = end
            last = now - ((rs.get("m") or {}).get("quiet") or 0)
            end = dt.datetime.fromtimestamp(last).astimezone().isoformat(timespec="seconds")
        end_epoch = iso_epoch(end) or mtime(d / "status.json")
        wall = summary.get("wall_s") or s.get("wall_s")
        if wall is None and rs.get("start"):
            wall = round(end_epoch - rs["start"], 1)
        exit_code = summary.get("exit_code", s.get("exit_code"))
        terminal = "dead" if dead else (summary.get("terminal") or s.get("terminal") or ea.get("term")
                                        or s.get("state"))
        k = tv["kids"]
        spawns = summary.get("subagent_spawn_count")
        if spawns is None:
            spawns = ea.get("spawns", 0)
        row = {"run_id": rs["run_id"], "id": rs.get("id"), "role": rs.get("role"), "ws": rs.get("ws"),
               "state": "dead" if dead else s.get("state"), "exit": exit_code, "terminal": terminal,
               "end": end, "end_epoch": end_epoch, "wall_s": wall,
               "cost_tree": round(tv["cost"]["tree"], 6), "cost_root": round(tv["cost"]["root"], 6),
               "cost_workers": round(tv["cost"]["workers"], 6), "cost_reminders": round(tv["cost"]["reminders"], 6),
               "cost_root_runner": summary.get("cost_usd_est"),
               "tok_in": tv["tokens"]["in"], "tok_out": tv["tokens"]["out"],
               "kids_done": k["done"], "kids_fail": k["fail"], "kids_unfinished": k["run"] + k["pend"],
               "reminders": k["rem"], "spawns": spawns, "leftovers": n_left, "tool_fail": tv["tool_fail"],
               "unpriced": tv["unpriced"], "emitted": list(rs.get("emitted") or [])}
        if quiet:
            return row
        bad =[m for m in bad_models(tv["models"], rs.get("provider")) if f"model:{m}" not in rs["emitted"]]
        if bad:
            for m in bad[1:]:
                rs["emitted"].append(f"model:{m}")
            self.emit(rs, "muse.model", f"model:{bad[0]}",
                      f"ALERT {rs['id']} used model(s) {', '.join(map(str, bad))} (expected {EXPECTED_MODEL})",
                      "check the agents definitions before the next run", {"models": bad})
        new_failed = [f for f in tv["failed"] if f"cf:{f['sid']}" not in rs["emitted"]]
        if new_failed:
            for f in new_failed[1:]:
                rs["emitted"].append(f"cf:{f['sid']}")
            self.emit(rs, "muse.child_failed", f"cf:{new_failed[0]['sid']}",
                      f"{rs['id']}: {len(new_failed)} child agent(s) ended failed: "
                      + "; ".join(f"{f['label']} ({f['why']})" for f in new_failed[:6]),
                      "check the Manager's final report covers them", {"children": new_failed})
        if not dead:
            extra = ""
            if s.get("state") == "runner_interrupted":
                extra = f" runner interrupted, muse {'STILL RUNNING' if pid_alive(s.get('pid'), s.get('pid_create_time')) else 'gone'};"
            ft = one_line(summary.get("final_text"), 120)
            self.emit(rs, "muse.finished", "finished",
                      f"{rs['id']} {s.get('state')}: exit {exit_code}, terminal {terminal}, wall {fmt_dur(wall)},"
                      f"{extra} tree cost ${tv['cost']['tree']:.4f} (root ${tv['cost']['root']:.4f}), children "
                      f"{k['done']} ok/{k['fail']} failed" + (f"/{k['run'] + k['pend']} unfinished"
                                                               if k['run'] + k['pend'] else "")
                      + f", leftovers {n_left}" + (f', final: "{ft}"' if ft else ""),
                      f"read {d}\\summary.json and check the workspace result",
                      {"run_dir": str(d), "exit_code": exit_code, "terminal": terminal, "wall_s": wall,
                       "cost_usd_tree": row["cost_tree"], "cost_usd_root": row["cost_root"],
                       "children_ok": k["done"], "children_failed": k["fail"], "leftovers": n_left})
        if isinstance(leftovers, list) and leftovers:
            stopped = summary.get("leftovers_stopped") or []
            st_ok = sum(1 for x in stopped if isinstance(x, dict) and x.get("stopped"))
            names = ", ".join(f"{x.get('exe')}:{x.get('pid')}" for x in leftovers[:5] if isinstance(x, dict))
            self.emit(rs, "muse.leftovers", "leftovers",
                      f"{rs['id']} left {len(leftovers)} process(es) alive after Muse exited ({names}); "
                      f"runner stopped {st_ok}/{len(leftovers)}",
                      "verify they are gone (tasklist); they belong to this run's tree only",
                      {"leftovers": leftovers[:20], "stopped": st_ok})
        row["emitted"] = list(rs.get("emitted") or [])
        return row

    # ---- full scan
    def scan(self):
        t0 = time.time()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with StateLock(self.state_dir / "watch_state.lock"):
            st = self.load_state()
            first = not st.get("initialized")
            now = time.time()
            known = set(st.get("known") or [])
            runs = st.setdefault("runs", {})
            finished = st.setdefault("finished", [])
            baseline = []
            seen = set()
            for d in list_run_dirs(self.logs_root):
                s = read_json(d / "status.json", None)
                if not isinstance(s, dict):
                    continue
                rid = str(s.get("run_id") or d.name)
                if self.only and not self.only.search(rid):
                    continue
                seen.add(rid)
                state = s.get("state")
                rs = runs.get(rid)
                try:
                    if state == "running":
                        if rid in known:
                            continue                       # reported dead earlier
                        if rs is None:
                            rs = runs[rid] = new_run_state(rid, d, s, now)
                            late = now - rs["start"]
                            self.emit(rs, "muse.started", "started",
                                      f"{rs['id']} started ({s.get('role')}, ws {short_ws(s.get('workspace'))}, "
                                      f"model {s.get('model')}, effort {s.get('effort')}, max_steps "
                                      f"{s.get('max_steps')}, capacity {s.get('capacity')}, pid {s.get('pid')})"
                                      + (f"; watcher saw it {fmt_dur(late)} after start" if late > 2 * max(
                                          self.interval, 30) else ""),
                                      "WATCH_STATUS.md shows its progress; events follow only if needed",
                                      {"run_dir": str(d), "workspace": s.get("workspace")})
                        self.watch_running(rs, d, s, now)
                        if rs.get("dead"):
                            finished.append(self.finalize(rs, d, s, now, quiet=True, dead=True))
                            known.add(rid)
                            runs.pop(rid, None)
                        continue
                    if rid in known:
                        prev = next((r for r in finished if r.get("run_id") == rid), None)
                        if not (prev and prev.get("state") == "dead"):
                            continue
                        # reported dead earlier but the runner did finish after all: report the real end
                        finished.remove(prev)
                        rs = new_run_state(rid, d, s, now)
                        rs["emitted"] = [e for e in prev.get("emitted", []) if e != "finished"]
                        finished.append(self.finalize(rs, d, s, now, quiet=False))
                        continue
                    if rs is None:
                        if first:
                            baseline.append((d, s, rid))
                            known.add(rid)
                            continue
                        rs = new_run_state(rid, d, s, now)    # started and finished between two scans
                    finished.append(self.finalize(rs, d, s, now, quiet=False))
                    known.add(rid)
                    runs.pop(rid, None)
                except Exception:
                    self.log_error(f"run {rid}: {traceback.format_exc(limit=6)}")
            for rid in list(runs):
                if rid not in seen and not (self.only and not self.only.search(rid)):
                    runs.pop(rid, None)                    # run dir removed
            if baseline:
                baseline.sort(key=lambda x: iso_epoch(x[1].get("end")) or mtime(x[0] / "status.json"))
                for d, s, rid in baseline[-FINISHED_ROWS:]:
                    try:
                        finished.append(self.finalize(new_run_state(rid, d, s, now), d, s, now, quiet=True))
                    except Exception:
                        self.log_error(f"baseline {rid}: {traceback.format_exc(limit=6)}")
            try:
                self.check_agent_silent(st, now)
            except Exception:
                self.log_error("agent_silent: " + traceback.format_exc(limit=6))
            try:
                wake_hd(self.check_hd_request(st))
            except Exception:
                self.log_error("hd_request: " + traceback.format_exc(limit=6))
            try:
                self.check_stuck_ladder(st, now)
            except Exception:
                self.log_error("stuck_ladder: " + traceback.format_exc(limit=6))
            try:
                self.check_ended_waiting(st)
            except Exception:
                self.log_error("ended_waiting: " + traceback.format_exc(limit=6))
            try:
                self.check_chaos(st)
            except Exception:
                self.log_error("chaos: " + traceback.format_exc(limit=6))
            try:
                self.check_poll_fast(st)
            except Exception:
                self.log_error("poll_fast: " + traceback.format_exc(limit=6))

            try:
                self.check_out_ws(st)
            except Exception:
                self.log_error("out_ws: " + traceback.format_exc(limit=6))
            try:
                wake_hd(self.check_rotation(st, now))
            except Exception:
                self.log_error("rotation: " + traceback.format_exc(limit=6))
            try:
                self.check_sched_alive(st, now)
            except Exception:
                self.log_error("sched_alive: " + traceback.format_exc(limit=6))
            finished.sort(key=lambda r: r.get("end_epoch") or 0)
            del finished[:-FINISHED_KEEP]
            st["known"] = sorted(known)
            st["initialized"] = True
            st["last_scan"] = now
            st["last_scan_local"] = local_now()
            self.save_state(st)                 # state first: an event is never written twice
            emitted = self.flush_events()
            wake_hd(emitted)
        text = self.render(st, time.time() - t0, emitted)
        write_atomic(self.status_path, text)
        return text, emitted

    # ---- WATCH_STATUS.md
    def render(self, st: dict, scan_s: float, emitted: list) -> str:
        who = f"loop pid {os.getpid()}, every {self.interval:g} s" if self.mode == "loop" else "once"
        L = ["# Muse watch status", "",
             f"Updated {local_now()} (PC clock) | scan {scan_s:.1f} s | {who} | idle alert {self.idle_min:g} min | "
             f"cost step ${self.cost_step:g}", ""]
        runs = st.get("runs") or {}
        L.append(f"## Running ({len(runs)})")
        L.append("")
        if runs:
            L.append("| run | role | ws | wall | children run/done/fail (+rem) | tok in/out | cost $ | tool fails "
                     "| last act | RAM MB | state |")
            L.append("|---|---|---|---|---|---|---|---|---|---|---|")
            for rid, rs in sorted(runs.items(), key=lambda kv: kv[1].get("start") or 0):
                m = rs.get("m") or {}
                k = m.get("kids") or {}
                kid = f"{k.get('run', 0)}/{k.get('done', 0)}/{k.get('fail', 0)} (+{k.get('rem', 0)})"
                if k.get("pend"):
                    kid += f" ?{k['pend']}"
                ram = m.get("ram") or {}
                c = (m.get("cost") or {}).get("tree", 0.0)
                L.append(f"| {rid} | {ROLE_ABBR.get(rs.get('role'), rs.get('role'))} | {short_ws(rs.get('ws'))} | "
                         f"{fmt_dur(m.get('wall'))} | {kid} | {fmt_tok(m.get('tok_in'))}/{fmt_tok(m.get('tok_out'))} | "
                         f"{c:.4f} | {m.get('tool_fail', 0)} | {fmt_dur(m.get('quiet'))} | "
                         f"{ram.get('ws_mb', '-')} | {m.get('state', '?')} |")
        else:
            L.append("none")
        fin = (st.get("finished") or [])[-FINISHED_ROWS:]
        L += ["", f"## Finished (last {len(fin)})", ""]
        if fin:
            L.append("| run | role | exit | terminal | wall | cost $ tree (root) | children ok/fail | spawns "
                     "| leftovers | end |")
            L.append("|---|---|---|---|---|---|---|---|---|---|")
            for r in reversed(fin):
                end = r.get("end") or ""
                L.append(f"| {r.get('run_id')} | {ROLE_ABBR.get(r.get('role'), r.get('role'))} | {r.get('exit')} | "
                         f"{r.get('terminal')} | {fmt_dur(r.get('wall_s'))} | {r.get('cost_tree', 0):.4f} "
                         f"({r.get('cost_root', 0):.4f}) | {r.get('kids_done', 0)}/{r.get('kids_fail', 0)} | "
                         f"{r.get('spawns')} | {r.get('leftovers')} | {end[11:19] if len(end) >= 19 else end} |")
        else:
            L.append("none")
        L += ["", "Events this scan: " + (", ".join(f"{e['kind']} {e['id']}" for e in emitted) if emitted else "none"),
              "",
              "Cost = whole tree: root + child agents (model_completed in every session.jsonl) + Muse reminder/"
              "observer runs (goal_usage_attribution); USD/1M in 0.10, cached 0.002, out 0.20 "
              "(reasoning inside output unless larger). `(+rem)` = reminder/observer sessions, not workers."]
        return "\n".join(L) + "\n"


# ---------------------------------------------------------------- commands
def cmd_once(w: Watcher) -> int:
    try:
        text, emitted = w.scan()
    except TimeoutError as ex:
        print(json.dumps({"error": str(ex)}))
        return 1
    print(text, end="")
    for e in emitted:
        print(f"EVENT {e['kind']} {e['id']} \u2014 {e['digest']} | next: {e['next_hint']}")
    return 0


def cmd_loop(w: Watcher) -> int:
    w.state_dir.mkdir(parents=True, exist_ok=True)
    pidf = w.state_dir / "watch.pid"
    try:
        old = pidf.read_text(encoding="utf-8").split()
        if old and int(old[0]) != os.getpid() and pid_alive(int(old[0]), int(old[1]) if len(old) > 1 else None):
            print(json.dumps({"error": f"another muse_watch loop runs (pid {old[0]}); not starting"}))
            return 2
    except (OSError, ValueError):
        pass
    ct = own_create_time()
    write_atomic(pidf, f"{os.getpid()} {ct if ct else ''}".strip() + "\n")
    hb = w.state_dir / "watch_heartbeat.txt"
    try:
        while True:
            t = time.monotonic()
            try:
                w.scan()
            except Exception:
                w.log_error("scan: " + traceback.format_exc(limit=8))
            try:
                write_atomic(hb, f"{int(time.time())}\n")
            except OSError:
                pass
            delay = w.interval - (time.monotonic() - t)
            if delay > 0:
                time.sleep(delay)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if pidf.read_text(encoding="utf-8").split()[0] == str(os.getpid()):
                pidf.unlink()
        except (OSError, IndexError):
            pass
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(prog="muse_watch.py", description="Director watcher over running Muse Code runs")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("loop", "once"):
        p = sub.add_parser(name, help="scan until killed" if name == "loop" else "one scan, print the table")
        p.add_argument("--interval", type=float, default=30.0, help="seconds between scans (loop)")
        p.add_argument("--idle-min", type=float, default=20.0, help="muse.idle after N quiet minutes")
        p.add_argument("--cost-step", type=float, default=0.5, help="muse.cost at every N USD of tree cost")
        p.add_argument("--agent-silent-min", type=float, default=15.0, help="muse.agent_silent after N silent minutes (hook heartbeats)")
        p.add_argument("--logs-root", default=str(DEF_LOGS))
        p.add_argument("--inbox", default=str(DEF_INBOX), help="folder the event JSON files are dropped into")
        p.add_argument("--state-dir", default=str(DEF_STATE), help="watch_state.json, WATCH_STATUS.md, heartbeat, pid")
        p.add_argument("--sessions-root", default=None, help="Muse session store (default ~/.local/share/muse/sessions)")
        p.add_argument("--only", default=None, help="regex on run_id: watch only matching runs")
    a = ap.parse_args(argv)
    if a.interval < 1:
        ap.error("--interval must be >= 1")
    if a.idle_min <= 0:
        ap.error("--idle-min must be > 0")
    w = Watcher(a)
    return cmd_loop(w) if a.cmd == "loop" else cmd_once(w)


if __name__ == "__main__":
    sys.exit(main())


# S5 event wake (append-only hook): RUN END / HD_REQUEST / HANDOFF -> one line into the pinned HD chat via hd_msg.ps1
_HD_WAKE_SEEN, _HD_WAKE_KINDS = set(), ("muse.finished", "hd.request", "hd.request.nag", "muse.director_rotate")
def wake_hd(evs):
    try:
        new = [e for e in (evs or []) if str(e.get("id") if isinstance(e, dict) else e) not in _HD_WAKE_SEEN and (not isinstance(e, dict) or e.get("kind") in _HD_WAKE_KINDS or "FINISH" in str(e.get("kind", "")).upper() or "HANDOFF" in (str(e.get("kind", "")) + str(e.get("file", "")) + str(e.get("handoff", ""))).upper())]
        for e in new: _HD_WAKE_SEEN.add(str(e.get("id") if isinstance(e, dict) else e))
        if new: t = __import__("tempfile").NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8"); t.write(("\n".join([str(e) if not isinstance(e, dict) else "%s %s -- %s" % (e.get("kind"), e.get("id"), (e.get("digest") or e.get("file") or e.get("handoff") or "")) for e in new]) + " " * 10)[:2000]); t.close(); __import__("subprocess").run(["powershell", "-NoProfile", "-File", str(Path(__file__).resolve().parents[1] / "hd_msg.ps1"), "-File", t.name], capture_output=True, timeout=30, creationflags=getattr(__import__("subprocess"), "CREATE_NO_WINDOW", 0))  # WINFIX: no Terminal window per wake
    except Exception: pass
