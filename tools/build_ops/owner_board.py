# Development tool for this build, shown as written. Not part of the app.
# Machine paths, server addresses and session ids were replaced by <PLACEHOLDERS>; the logic is unchanged.
"""owner_board.py - owner phone console, one screen, read-only, stdlib only. Never writes/deletes/spawns product work.
Collect: progress --line (import, fallback dev.py), dev.py status live runs + newest artifact mtime under WT _task + SILENT>10min,
queue.txt + RESERVE.txt, fresh (<6h) HD_REQUEST*.md without verdict (WT/*/_task + ROOT/_task), daemon pids + alive, sched.sh bash
roots, wake.log last line, NIGHT_LOG.md last 3 lines. Flags: --once (default), --loop N. Exit 0 on --once, never crash (ABSENT)."""
import datetime
import glob
import importlib.util
import json
import os
import subprocess
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
D = os.path.join(ROOT, "DIRECTOR")
RUN = os.path.join(D, "RUN")
TOOLS = os.path.join(D, "TOOLS")
SILENT_MIN = 10
FRESH_H = 6
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def closed_by_verdict(req):
    """True when a same-dir HD_VERDICT*.md, not older than the request, says CLOSED/merged
    (lanes merged under another lane name, e.g. K10D via K10MERGE). BOARDFIX F11:
    also accepts a cross-dir HD_VERDICT*.md under the same _task tree that names the
    request id and says CLOSED/merged (same proof, other folder); never matches on age
    alone, never matches a non-closing verdict."""
    try:
        rm = os.path.getmtime(req)
        for v in glob.glob(os.path.join(os.path.dirname(req), "HD_VERDICT*.md")):
            if os.path.getmtime(v) >= rm and re.search(r"CLOSED|merged", open(v, encoding="utf-8", errors="replace").read(2000), re.I):
                return True
        base = os.path.basename(req)
        lid = base[len("HD_REQUEST_"):-len(".md")] if base.upper().startswith("HD_REQUEST_") and base.lower().endswith(".md") else ""
        lid = lid.strip("_")
        if lid:
            stem = re.sub(r"(MGR|AUD|R|FIX)$", "", lid)
            ids = {i for i in (lid, stem) if i}
            head = os.path.dirname(req)
            taskroot = None
            while head and len(head) > 3:
                if os.path.basename(head).lower() == "_task":
                    taskroot = head
                    break
                head = os.path.dirname(head)
            if taskroot and os.path.isdir(taskroot):
                for dp2, dn2, fn2 in os.walk(taskroot):
                    dn2[:] = [x for x in dn2 if x.lower() not in ("tmp", "node_modules", "_archive", "__pycache__")]
                    for f2 in fn2:
                        fl2 = f2.lower()
                        if not (fl2.startswith("hd_verdict") and fl2.endswith(".md")):
                            continue
                        vp = os.path.join(dp2, f2)
                        if os.path.abspath(vp) == os.path.abspath(req):
                            continue
                        try:
                            if os.path.getmtime(vp) < rm:
                                continue
                            txt = open(vp, encoding="utf-8", errors="replace").read(2000)
                        except OSError:
                            continue
                        if re.search(r"CLOSED|merged", txt, re.I) and any(i in txt for i in ids):
                            return True
    except OSError:
        pass
    return False


def read_lines(path, tail=None):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        return lines[-tail:] if tail else lines
    except OSError:
        return None


def age_min(path):
    try:
        return (time.time() - os.path.getmtime(path)) / 60
    except OSError:
        return None


def readiness():
    try:
        spec = importlib.util.spec_from_file_location("ob_progress", os.path.join(TOOLS, "progress.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.line_text(mod.load_rows(os.path.join(ROOT, "kit", "BUILD_PLAN.md")))
    except Exception:
        pass
    try:
        p = subprocess.run([sys.executable, os.path.join(TOOLS, "dev.py"), "progress", "--line"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, cwd=ROOT,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for ln in (p.stdout or "").splitlines():
            if "Готовність" in ln:
                return ln.strip()
    except Exception:
        pass
    return "ABSENT"


def headline_for(live_pct, live_n, total, pre_pct, code_pct, demo_live, demo_total):
    """Phone headline (G01+G03): readiness is UI-live first with the demo x/14
    count embedded, pre-check never LIVE. Pure (tests cover this, not the screen)."""
    dl = str(demo_live) if demo_live is not None else "?"
    return "Готово UI-live %s%% (%d/%d; демо %s/%d) (+%s%% pre-check, не LIVE; +%s%% код чекає живого)" % (
        live_pct, live_n, total, dl, demo_total, pre_pct, code_pct)


def parse_readiness(rd):
    """(live_pct, live_n, total, pre_pct, code_pct, demo_live|None, demo_total)
    from a progress --line; None when the line is foreign/old (caller falls back)."""
    m = re.search(r"Готовність:\s*([\d.]+)% UI-live \((\d+)/(\d+); демо (\?|\d+)/(\d+)\)\s*/\s*"
                  r"([\d.]+)% \(pre-check[^)]*\)\s*/\s*([\d.]+)%", rd or "")
    if not m:
        return None
    dl = None if m.group(4) == "?" else int(m.group(4))
    return (m.group(1), int(m.group(2)), int(m.group(3)), m.group(6), m.group(7), dl, int(m.group(5)))


def live_runs():
    try:
        p = subprocess.run([sys.executable, os.path.join(TOOLS, "dev.py"), "status"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, cwd=ROOT,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        lines = (p.stdout or "").splitlines()
    except Exception:
        return None
    import re
    out = []
    for ln in lines:
        m = re.match(r"\s*(\S+)\s+([\d.]+)\s+min\s+ws=(\S+)", ln)
        if m:
            out.append((m.group(1), m.group(3), float(m.group(2))))
    return out


def live_agents():
    try:  # same source as dev.py status agents (dev.py active_agents)
        spec = importlib.util.spec_from_file_location("ob_dev", os.path.join(TOOLS, "dev.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.active_agents()
    except Exception:
        pass
    try:  # fallback: live muse-bin processes
        p = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=15,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return sum(1 for ln in (p.stdout or "").splitlines() if ln.strip().lower().startswith("muse-bin"))
    except Exception:
        return None


def newest_artifact(ws, rid=""):
    base = os.path.join(ROOT, "WT", ws, "_task")
    if not os.path.isdir(base) and ws == os.path.basename(ROOT):
        base = os.path.join(ROOT, "_task")
    if not os.path.isdir(base):
        return None
    roots = [base]
    if ws == os.path.basename(ROOT) and rid:
        pkgdir = os.path.join(D, "TASK_PACKAGES")
        stem = rid.split("-D")[0].split("_")[0]
        try:
            for d in os.listdir(pkgdir):
                if d == stem or d.startswith(stem + "-") or stem.startswith(d + "-"):
                    p = os.path.join(pkgdir, d)
                    if os.path.isdir(p):
                        roots.append(p)
        except OSError:
            pass
    best = None
    for root in roots:
        for dp, dn, fn in os.walk(root):
            dn[:] = [x for x in dn if x.lower() not in ("tmp", "_archive", "__pycache__", "node_modules")]
            for f in fn:
                p = os.path.join(dp, f)
                try:
                    t = os.path.getmtime(p)
                except OSError:
                    continue
                if best is None or t > best[0]:
                    best = (t, os.path.relpath(p, root))
    if not best:
        return ("-", None)
    # BOARDFIX F8: full relpath (was best[1][-38:] which cut front keywords of
    # long names, hiding VERDICT/MANAGER/RETURN from lane_state).
    return (best[1], (time.time() - best[0]) / 60)


def file_list(name):
    lines = read_lines(os.path.join(D, name))
    if lines is None:
        return None
    return [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]


def hd_requests(hours=FRESH_H):
    roots = []
    rt = os.path.join(ROOT, "_task")
    if os.path.isdir(rt):
        roots.append(rt)
    try:
        subs = sorted(os.listdir(os.path.join(ROOT, "WT")))
    except OSError:
        subs = []
    for s in subs:
        d = os.path.join(ROOT, "WT", s, "_task")
        if os.path.isdir(d):
            roots.append(d)
    now = time.time()
    out = []
    for root in roots:
        for dp, dn, fn in os.walk(root):
            dn[:] = [x for x in dn if x.lower() not in ("tmp", "node_modules", "_archive", "__pycache__")]
            for f in fn:
                ln = f.lower()
                if not (ln.startswith("hd_request") and ln.endswith(".md")):
                    continue
                p = os.path.join(dp, f)
                try:
                    mt = os.path.getmtime(p)
                except OSError:
                    continue
                # BOARDFIX F11: no expiry drop (an old open request must stay
                # visible; expiry looked like an answer). Age is reported, not filtered.
                if closed_by_verdict(p):
                    continue
                out.append(((now - mt) / 60, os.path.relpath(p, ROOT)))
    return sorted(out)


def pid_alive(pid):
    try:
        pid = int(str(pid).strip())
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
        except Exception:
            return False
    try:
        import ctypes
        import ctypes.wintypes as wt
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        h = k.OpenProcess(0x1000, False, pid)
        if not h:
            return ctypes.get_last_error() == 5
        try:
            code = wt.DWORD()
            if not k.GetExitCodeProcess(h, ctypes.byref(code)):
                return False
            return code.value == 259
        finally:
            k.CloseHandle(h)
    except Exception:
        pass
    try:
        p = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid],
                           capture_output=True, text=True, timeout=15,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return str(pid) in (p.stdout or "")
    except Exception:
        return False


def _pid_cmdline(pid):
    """CommandLine of one Windows pid ("" when unknown/gone). Read-only."""
    try:
        pid = int(str(pid).strip())
    except (TypeError, ValueError):
        return ""
    if pid <= 0 or os.name != "nt":
        return ""
    try:
        ps = ("(Get-CimInstance Win32_Process -Filter \"ProcessId=%d\").CommandLine" % pid)
        p = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=15,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return (p.stdout or "").strip()
    except Exception:
        return ""


def _find_live_pids(*needles):
    """Pids whose process CommandLine contains every needle (case-insensitive).

    Read-only; never starts anything. Python-only match for python daemons so
    the probing powershell itself (whose own command line holds the needles)
    can never match."""
    if os.name != "nt":
        return []
    clean = [n.replace("'", "") for n in needles if n]
    if not clean:
        return []
    try:
        cond = " -and ".join("$_.CommandLine -like '*%s*'" % n for n in clean)
        ps = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*'"
              " -and %s } | ForEach-Object { $_.ProcessId }" % cond)
        p = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=20,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out = []
        for tok in (p.stdout or "").replace(",", " ").split():
            try:
                out.append(int(tok))
            except ValueError:
                continue
        return [i for i in out if i > 0]
    except Exception:
        return []


def _find_live_gateway():
    """Any live process whose command line names a gateway daemon.

    The probe itself is excluded by process name (powershell/pwsh/conhost
    never match); never starts anything."""
    if os.name != "nt":
        return []
    try:
        ps = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -notlike 'powershell*'"
              " -and $_.Name -notlike 'pwsh*' -and $_.CommandLine -like '*gateway*' }"
              " | ForEach-Object { $_.ProcessId }")
        p = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=20,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out = []
        for tok in (p.stdout or "").replace(",", " ").split():
            try:
                out.append(int(tok))
            except ValueError:
                continue
        return [i for i in out if i > 0 and i != os.getpid()]
    except Exception:
        return []


def daemon_state(name):
    """Pid-file liveness, fail-closed. Two self-heal rules (read-only except
    rewriting our own stale .pid, never starting a loop):

    owner_board: a dead pid file + a live `owner_board.py --loop` process is
    OK; the pid file is healed to the live pid (no second loop is started).
    A live pid whose command line is NOT the board is stale (pid reuse) and
    falls through to the same heal path.
    gateway: a dead pid + no live gateway process is ABSENT (нема) when both
    logs are empty (nothing ever ran); DEAD only when a stale pid or a
    non-empty log proves it ran and died. Never claims a running шлюз."""
    lines = read_lines(os.path.join(RUN, name + ".pid"))
    first = lines[0].strip() if lines and lines[0].strip() else ""
    if first and pid_alive(first):
        if name == "owner_board":
            try:
                cl = _pid_cmdline(first)
            except Exception:
                cl = ""
            if cl and "owner_board.py" not in cl.lower():
                pass  # pid reuse: stale, fall through to heal
            else:
                return "OK"
        elif name == "gateway":
            try:
                cl = _pid_cmdline(first)
            except Exception:
                cl = ""
            if cl and "gateway" not in cl.lower():
                pass  # pid reuse: stale, fall through
            else:
                return "OK"
        else:
            return "OK"
    if name == "owner_board":
        try:
            live = _find_live_pids("owner_board.py", "--loop")
        except Exception:
            live = []
        if live:
            try:
                with open(os.path.join(RUN, name + ".pid"), "w", encoding="utf-8") as f:
                    f.write(str(live[0]))
            except OSError:
                pass
            return "OK"
    if name == "gateway":
        try:
            live = _find_live_gateway()
        except Exception:
            live = []
        if live:
            try:
                with open(os.path.join(RUN, name + ".pid"), "w", encoding="utf-8") as f:
                    f.write(str(live[0]))
            except OSError:
                pass
            return "OK"
        if not first:
            return "ABSENT"
        try:
            size = 0
            for lg in ("gateway.out.log", "gateway.err.log"):
                try:
                    size += os.path.getsize(os.path.join(RUN, lg))
                except OSError:
                    pass
            if size <= 0:
                return "ABSENT"
        except Exception:
            pass
        return "DEAD"
    if not first:
        return "ABSENT"
    return "DEAD"


def sched_roots():
    try:
        ps = ("$a=Get-CimInstance Win32_Process -Filter \"Name='bash.exe'\" | Where-Object { $_.CommandLine -match 'sched.sh' }; "
              "$ids=@($a | ForEach-Object { $_.ProcessId }); @($a | Where-Object { $ids -notcontains $_.ParentProcessId }).Count")
        p = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=20,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))  # WINFIX: no Terminal window per poll
        return int((p.stdout or "0").strip() or 0)
    except Exception:
        return -1


def auto_line():
    try:  # state file only, never spawns, never crashes
        import json as _j
        with open(os.path.join(RUN, "auto_merge_state.json"), encoding="utf-8") as _f:
            _st = _j.load(_f)
        if not isinstance(_st, dict):
            _st = {}
        _last = _st.get("last") or {}
        return "[AUTO] merged=%d failed=%d freed=%d last=%s %s %s" % (
            int(_st.get("merged") or 0), int(_st.get("failed_n") or 0),
            int(_st.get("freed") or 0), _last.get("id") or "-",
            _last.get("sha") or "-", _last.get("time") or "-")
    except Exception:
        return "[AUTO] merged=0 failed=0 freed=0 last=- - -"


def tasks_block():
    """Board ЗАВДАННЯ block from TASKS_NOW.tsv via task_ledger.evaluate():
    LATE rows first (who + due), then open/done counts. Read-only, stdlib
    only, never crashes (fail-closed single line)."""
    try:
        spec = importlib.util.spec_from_file_location(
            "ob_task_ledger", os.path.join(TOOLS, "advisor_probes", "task_ledger.py"))
        tl = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tl)
        rows = list(tl.evaluate())
    except Exception:
        return ["ЗАВДАННЯ: нема даних"]
    if not rows:
        return ["ЗАВДАННЯ: порожньо"]
    late = sorted([r for r in rows if r.get("late")], key=lambda r: r.get("due") or "")
    opn = sum(1 for r in rows if not r.get("done"))
    done = sum(1 for r in rows if r.get("done"))
    out = ["ЗАВДАННЯ відкрито %d, прострочено %d, готово %d:" % (opn, len(late), done)]
    for r in late[:8]:
        out.append("  ! %s %s до %s %s" % (
            r.get("id"), r.get("who"), r.get("due"), (r.get("what") or "")[:60]))
    return out


def screen():
    now = datetime.datetime.now()
    out = ["=" * 78, "OWNER BOARD %s (PC clock; read-only)" % now.strftime("%d.%m %H:%M:%S")]
    out.append("[READINESS] " + readiness())
    runs = live_runs()
    if runs is None:
        out.append("[LIVE] ABSENT (dev.py status failed)")
    else:
        ag = live_agents(); out.append("[LIVE] runs=%d agents=%s" % (len(runs), ag if ag is not None else "?"))
        for rid, ws, mins in runs:
            art = newest_artifact(ws, rid)
            if art is None:
                out.append("  %s ws=%s run=%.0fmin newest=ABSENT" % (rid[:32], ws, mins))
            else:
                ap, aa = art
                flag = " SILENT" if (aa is not None and aa > SILENT_MIN) else ""
                out.append("  %s ws=%s run=%.0fmin newest=%s %s%s" % (
                    rid[:32], ws, mins, ap, ("%.0fmin ago" % aa) if aa is not None else "-", flag))
    q = file_list("queue.txt")
    r = file_list("RESERVE.txt")
    out.append("[QUEUE/RESERVE] queue=%s reserve=%s" % (
        ("ABSENT" if q is None else "%d: %s" % (len(q), ", ".join(q) or "EMPTY")),
        ("ABSENT" if r is None else "%d: %s" % (len(r), ", ".join(r) or "EMPTY"))))
    try:
        out += tasks_block()
    except Exception:
        out.append("ЗАВДАННЯ: нема даних")
    try:  # copy sync (owner 31.10 19:3x): idle copies must sit on APP int after every merge
        spec = importlib.util.spec_from_file_location("sync_status", os.path.join(TOOLS, "sync_status.py"))
        ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)
        isha2, srows2 = ss.status({ws: rid for rid, ws, _m in (runs or [])})
        out.append(ss.line(isha2, srows2))
        out += ss.block({ws: rid for rid, ws, _m in (runs or [])}, rows=srows2, int_sha=isha2)
    except Exception as ex:
        out.append("[SYNC] ABSENT (%s)" % type(ex).__name__)
    try:
        out.append(auto_line())
    except Exception:
        out.append("[AUTO] ABSENT")
    try:
        fr = hd_requests()
    except Exception:
        fr = None
    if fr is None:
        out.append("[HD-REQUESTS] ABSENT")
    else:
        # BOARDFIX F11: no fresh<6h filter (hd_requests shows every age now).
        out.append("[HD-REQUESTS] no-verdict=%d%s" % (
            len(fr), (" oldest %dmin %s" % (fr[-1][0], fr[-1][1][-50:]) if fr else "")))
    states = {n: daemon_state(n) for n in ("watcher", "lai_daemon", "analyst", "watchdog2", "scheduler")}
    sa = sched_roots()
    wake = read_lines(os.path.join(RUN, "wake.log"), 1)
    out.append("[DAEMONS+SCHED+WAKE] %s | sched.sh roots=%s | wake=%s" % (
        " ".join("%s=%s" % (k, states[k]) for k in ("watcher", "lai_daemon", "analyst", "watchdog2", "scheduler")),
        sa if sa >= 0 else "?", wake[0].strip()[:100] if wake else "ABSENT"))
    nl = read_lines(os.path.join(D, "NIGHT_LOG.md"), 12)
    out.append("[NIGHT-LOG-TAIL]")
    if not nl:
        out.append("  ABSENT")
    else:
        for l in [x for x in nl if x.strip()][-3:]:
            out.append("  " + l.strip()[:150])
    return "\n".join(out)


def lane_state(name, age):
    """Plain-Ukrainian lane stage from the newest artifact name (phone view).
    BOARDFIX F8: the stage word is never hidden by stale-TISHA (a stale verdict
    read as silence, misdirecting the board). A stale specific stage keeps its
    ТИША prefix (WATCHFIX silence compat: startswith ТИША, same minute bucket)
    with the stage in parens; pure working stays bare ТИША."""
    n = (name or "").upper()
    if "VERDICT" in n or "ВЕРДИКТ" in n:
        stage = "є вердикт"
    elif "AUDIT" in n or "АУДИТ" in n:
        stage = "аудит"
    elif "STATUS" in n or "СТАТУС" in n:
        stage = "статус"
    elif "MANAGER" in n and "RETURN" in n:
        stage = "звіт менеджера"
    elif "CODER" in n and ("RETURN" in n or "SUBMIT" in n):
        stage = "код здано"
    elif "RETURN_DRAFT" in n or "ROWS_TRACK" in n:
        stage = "пише звіт"
    elif "TASK" in n:
        stage = "старт/код"
    else:
        stage = "працює"
    if age is not None and age > 15:
        if stage == "працює":
            return "ТИША %dхв" % age
        return "ТИША %dхв (%s)" % (age, stage)
    return stage


def lane_agents(runs, window_min=30):
    """{run_id: [(start, last, last_event, status, depth)]} from heartbeats, mapped to the run's root session (events.jsonl line 1)."""
    import json as _j
    logs = os.path.join(D, "LOGS", "muse")
    roots = {}
    for rid, _ws, _m in runs:
        try:
            with open(os.path.join(logs, rid, "events.jsonl"), encoding="utf-8", errors="replace") as f:
                roots[_j.loads(f.readline())["stream"]["id"]] = rid
        except Exception:
            continue
    hbs = {}
    now = time.time()
    for p in glob.glob(os.path.join(logs, "heartbeats", "*.json")):
        try:
            if now - os.path.getmtime(p) > 6 * 3600:
                continue
            hb = _j.load(open(p, encoding="utf-8"))
            hbs[hb.get("session_id")] = hb
        except Exception:
            continue
    out = {}
    for sid, hb in hbs.items():
        cur, depth = hb, 0
        while cur and cur.get("parent_session_id") and depth < 8:
            depth += 1
            par = cur.get("parent_session_id")
            if par in roots:
                break
            cur = hbs.get(par)
        par = (cur or {}).get("parent_session_id")
        rid = roots.get(sid) or roots.get(par)
        if not rid:
            continue
        try:
            last = datetime.datetime.fromisoformat(hb.get("last_ts"))
            first = datetime.datetime.fromisoformat(hb.get("first_ts"))
        except Exception:
            continue
        age = (now - last.timestamp()) / 60
        if hb.get("status") == "done" and age > window_min:
            continue
        st = "готово" if hb.get("status") == "done" else ("працює" if age <= 10 else "тиша %dхв" % age)
        out.setdefault(rid, []).append((first.strftime("%H:%M"), last.strftime("%H:%M"), (hb.get("last_event") or "")[:12], st, 0 if sid in roots else depth))
    for rid in out:
        out[rid].sort(key=lambda x: x[0])
    return out


def scripts_line():
    names = (("scheduler", "черга"), ("auto_merge", "автозлиття"), ("watchdog2", "наглядач"), ("watcher", "watcher"),
             ("analyst", "аналітик"), ("gateway", "шлюз"), ("owner_board", "дошка"))
    return "СКРИПТИ: " + " ".join("%s=%s" % (ua, {"OK": "ок", "DEAD": "ВПАВ", "ABSENT": "нема"}.get(daemon_state(n), "?")) for n, ua in names)


_GITPASS = {"head": None, "merges": None, "subjects": None}


def _int_head_sha(app):
    """40-hex int sha or ''; one cheap rev-parse per board pass."""
    try:
        p = subprocess.run(["git", "-C", app, "rev-parse", "int"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=20,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        sha = (p.stdout or "").strip()
        return sha if len(sha) == 40 and all(c in "0123456789abcdefABCDEF" for c in sha) else ""
    except Exception:
        return ""


def _gitpass(app):
    """(merges, subjects) for this pass; heavy git log calls run only when
    the int head moved since the last pass (pace fix: no git per pass
    when int is quiet). First pass, or an unreadable head, runs them."""
    head = _int_head_sha(app)
    if head and head == _GITPASS.get("head") and _GITPASS.get("merges") is not None:
        return _GITPASS["merges"], _GITPASS["subjects"]
    merges, subjects = [], ""
    try:
        p = subprocess.run(["git", "-C", app, "log", "int", "--since=midnight", "--merges", "--format=%ct %h %s"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        merges = [l.split(" ", 2) for l in p.stdout.splitlines() if l.strip()]
        subjects = subprocess.run(["git", "-C", app, "log", "int", "-400", "--format=%s"], capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=20,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except Exception:
        pass
    if head:
        _GITPASS.update(head=head, merges=merges, subjects=subjects)
    return merges, subjects


def project_lines():
    """Compact project-state lines for owner + advisor (owner 20:4x: cheap, compact, informative)."""
    import re
    app = os.path.join(ROOT, "APP")
    out, warn = [], []
    try:
        mg, subj = _gitpass(app)
        if mg:
            age = (time.time() - int(mg[0][0])) / 60
            out.append("ЗЛИТТЯ сьогодні %d | ост. %s %s, %dхв тому" % (len(mg), mg[0][1], re.sub(r"Merge branch 'pkg/([^']+)'.*", r"\1", mg[0][2])[:16], age))
        else:
            subj, age = subj if 'subj' in dir() else "", 9999
            out.append("ЗЛИТТЯ сьогодні 0")
    except Exception:
        subj, age = "", 9999
    pend, blk = [], 0
    now = time.time()
    for f in glob.glob(os.path.join(ROOT, "WT", "*", "_task", "HD_REQUEST_*.md")):
        try:
            # BOARDFIX F11: no 6h expiry skip (an old PASS without merge must stay
            # pending; expiry looked like an answer). closed_by_verdict (now also
            # cross-dir) is the only way a request clears.
            txt = open(f, encoding="utf-8", errors="replace").read(3000)
        except OSError:
            continue
        lid = os.path.basename(f)[11:-3]
        first = txt.splitlines()[0] if txt else ""
        if re.search(r"BLOCKED|STUCK", first):
            if now - os.path.getmtime(f) < 3600:
                blk += 1
            continue
        base = re.sub(r"(MGR|AUD|R|FIX)$", "", lid)
        evidence_only = re.match(r"(COPY|ROWS_|STUCK|IFACE|PAGE_)", lid) or re.search(r"AUD$|LIVE|PROBE|ACCEPT", lid)
        merged = any(("%s:" % x) in subj or ("pkg/%s'" % x) in subj for x in (lid, base)) or closed_by_verdict(f)
        if re.search(r"DONE|PASS|ACCEPT", first) and "HOLD" not in txt and not merged and not evidence_only:
            pend.append(lid)
    out.append("PASS БЕЗ ЗЛИТТЯ %d: %s" % (len(pend), " ".join(sorted(pend)[:6]) or "-"))
    if pend and age > 30:
        warn.append("є %d PASS без злиття, ост. злиття %dхв тому" % (len(pend), age))
    try:
        rv_lines = open(os.path.join(D, "REVIEW.txt"), encoding="utf-8").read().splitlines()
        rulings = "\n".join(l for l in rv_lines if l.startswith("#"))  # a ruled lane is no longer waiting (01.11: count only grew)
        rv = [l for l in rv_lines if l.strip() and not l.startswith("#") and l.strip() not in rulings and l.split(":")[0].strip() not in rulings]
    except OSError:
        rv = []
    if rv:
        warn.append("на перевірці у радника %d" % len(rv))
    try:
        ck = open(os.path.join(D, "FUNCTIONS_CHECKLIST.md"), encoding="utf-8").read().split("## Part 2")[0]
        rows = re.findall(r"^\| (\d+) \|[^|]*\| ([^|]*) \|", ck, re.M)
        live = sum(1 for _n, st in rows if "LIVE" in st or "DONE" in st)
        out.append("ДЕМО-ФУНКЦІЇ живі %d/%d | блоків за год %d | на перевірці %d" % (live, len(rows) or 14, blk, len(rv)))
    except OSError:
        pass
    return out, warn


def wire_line():
    """wire_gate advisory counts (owner LIVEFAST): one line, never crashes.
    BOARDFIX D-wire: scan every line for the WIRE_GATE counts (was read_lines
    tail=1 = LAST line while counts print on line 1 of the 53-line file)."""
    try:
        for ln in (read_lines(os.path.join(RUN, "wire_gate_last.txt")) or []):
            m = re.search(r"unrouted=(\d+)\s+unmounted=(\d+)", ln)
            if m:
                return "ЗВ'ЯЗКИ: без маршруту %s, без екрана %s" % m.groups()
    except Exception:
        pass
    return "ЗВ'ЯЗКИ: нема даних"


def _exe_manifest():
    """Portable HASH.json: prefer the APP copy, fall back to the WT/INSTALLB
    copy (BOARDBUILD: board said ABSENT while INSTALLB had a fresh HASH)."""
    app = os.path.join(ROOT, "APP", "dist", "portable", "HASH.json")
    try:
        if os.path.isfile(app):
            return app
    except Exception:
        return app
    inst = os.path.join(ROOT, "WT", "INSTALLB", "dist", "portable", "HASH.json")
    try:
        if os.path.isfile(inst):
            return inst
    except Exception:
        pass
    return app


def _exe_source(man=None):
    """Which copy the manifest came from (APP default, INSTALLB fallback)."""
    try:
        if "INSTALLB" in (man or _exe_manifest()).upper():
            return "INSTALLB"
    except Exception:
        pass
    return "APP"


def build_provenance(manifest=None, app_repo=None):
    """(exe_sha7, built_hhmm, int_sha7, behind) or None when unprovable.

    PROV: the exe the passes test (portable HASH.json built_from_commit)
    against int. Never raises (the board is read-only, fail-closed)."""
    import json as _j
    try:
        man = manifest or _exe_manifest()
        repo = app_repo or os.path.join(ROOT, "APP")
        with open(man, encoding="utf-8") as f:
            doc = _j.load(f)
        exe = str(doc.get("built_from_commit") or "").strip()
        if len(exe) != 40 or any(c not in "0123456789abcdefABCDEF" for c in exe):
            return None
        try:
            raw = str(doc.get("built_at"))
            iso = raw.replace("Z", "+00:00")
            m2 = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6})\d*(.*)$", iso)
            if m2:
                iso = m2.group(1) + m2.group(2)
            hhmm = datetime.datetime.fromisoformat(iso).strftime("%H:%M")
        except Exception:
            try:
                hhmm = datetime.datetime.fromtimestamp(os.path.getmtime(man)).strftime("%H:%M")
            except OSError:
                hhmm = "?"
        try:
            p = subprocess.run(["git", "-c", "safe.directory=*", "-C", repo, "rev-parse", "int"],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=20,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            intsha = (p.stdout or "").strip()
            if p.returncode != 0 or len(intsha) != 40:
                intsha = ""
        except Exception:
            intsha = ""
        behind = None
        if intsha:
            try:
                q = subprocess.run(["git", "-c", "safe.directory=*", "-C", repo, "rev-list", "--count",
                                    "%s..int" % exe],
                                   capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=20,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                behind = int((q.stdout or "").strip()) if q.returncode == 0 else None
            except Exception:
                behind = None
        return (exe[:7], hhmm, intsha[:7] if intsha else "?", behind)
    except Exception:
        return None


def exe_line(live=()):
    """One board line: EXE <sha> built hh:mm | int <sha> | behind N.

    PROV: RED when the tested build is behind int while a pass is running."""
    prov = build_provenance()
    if prov is None:
        return "ЗБІРКА: ABSENT (no portable HASH.json)"
    sha, hhmm, intsha, behind = prov
    src = _exe_source()
    if behind is None:
        return "ЗБІРКА: EXE %s built %s | int %s | behind ? (%s)" % (sha, hhmm, intsha, src)
    if behind > 0 and bool(live):
        return "ЗБІРКА: EXE %s built %s | int %s | behind %d RED (pass running on stale exe, STALE BY %d) (%s)" % (
            sha, hhmm, intsha, behind, behind, src)
    return "ЗБІРКА: EXE %s built %s | int %s | behind %d (%s)" % (sha, hhmm, intsha, behind, src)


# ================= BOARD TRUTH (advisor 2026-11-02) =================
# One screen from the train files, in order:
# head / ЗЛИТТЯ / ЛЕЙНИ / ГЕЙТ / ЛЮДИ / СКРИПТИ / ЗБІРКА / ЖУРНАЛ.
HD2_SID = "<SESSION_ID>"
STALE_MIN = 8
_SCRIPTS = (("merge_train", ("merge_train.py",)), ("int_gate", ("int_gate.py", "--watch")),
            ("backup_15min", ("backup_15min.py",)), ("дошка", ("owner_board.py", "--loop")))


def _load_lane_status():
    spec = importlib.util.spec_from_file_location("board_lane_status", os.path.join(TOOLS, "lane_status.py"))
    ls = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ls)
    return ls


def _train_state(root=ROOT):
    try:
        with open(os.path.join(root, "DIRECTOR", "RUN", "TRAIN_STATE.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _train_lanes(root=ROOT):
    rows = []
    try:
        with open(os.path.join(root, "DIRECTOR", "RUN", "TRAIN_LANES.txt"), encoding="utf-8") as f:
            for ln in f:
                p = [x.strip() for x in ln.split("|")]
                if len(p) >= 4 and p[3].startswith("ses_"):
                    rows.append((p[0], p[1], p[2], p[3]))
    except OSError:
        pass
    return rows


def _int_head_full(app):
    try:
        return _int_head_sha(app)
    except Exception:
        return ""


def _head_lines(now):
    try:
        lanes = _train_lanes()
    except Exception:
        lanes = []
    try:
        n = len((_train_state().get("landed") or []))
    except Exception:
        n = None
    head = _int_head_full(os.path.join(ROOT, "APP"))[:7] or "нема даних"
    return ["AGENT SI %s | int %s | ЗЛИТО %s/%d" % (now.strftime("%H:%M"), head, n if n is not None else "?", len(lanes))]


def _train_log_last_landed(root=ROOT):
    """(lane, minutes_ago) of the last TRAIN <LANE> LANDED line, or (None, None)."""
    try:
        f = open(os.path.join(root, "DIRECTOR", "RUN", "TRAIN_LOG.txt"), encoding="utf-8", errors="replace")
    except OSError:
        return None, None
    lane, age = None, None
    now = datetime.datetime.now(datetime.timezone.utc)
    with f:
        for ln in f:
            m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z?\s+TRAIN (\S+) LANDED\b", ln)
            if not m:
                continue
            try:
                ts = datetime.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
            except ValueError:
                continue
            lane, age = m.group(2), int((now - ts).total_seconds() // 60)
    return lane, age


def _zlitya_lines():
    lane, age = _train_log_last_landed()
    if lane is None:
        return ["ЗЛИТТЯ: нема даних"]
    return ["ЗЛИТТЯ: %s %dхв тому" % (lane, max(0, age))]


def lane_stage(lane, verdict_last, audits, conflicts):
    """Board lane stage from shared data (tests pin this, not the old artifact labels)."""
    up = (verdict_last or "").upper()
    if lane in conflicts:
        return "конфлікт"
    if "FAIL" in up:
        return "FAIL у кодера"
    if "PASS" in up or "DONE" in up:
        return "PASS чекає злиття"
    if lane in audits:
        return "аудит"
    return "працює"


def board_lane_data(root=ROOT):
    """(rows, audits, conflicts, landed): shared lane_status reading + verdict tails for the board stage."""
    ls = _load_lane_status()
    rows = ls.lane_rows(root=root)
    st = _train_state(root)
    audits = st.get("audits", {}) or {}
    conflicts = st.get("conflicts", {}) or {}
    landed = set(st.get("landed", []) or [])
    for r in rows:
        vp = os.path.join(root, r["cl"], "_task", r["lane"], "VERDICT.md")
        try:
            lines = open(vp, encoding="utf-8", errors="replace").read().rstrip().splitlines()
            r["verdict_last"] = lines[-1] if lines else ""
        except OSError:
            r["verdict_last"] = ""
    return rows, audits, conflicts, landed


def _lanes_lines():
    rows, audits, conflicts, landed = board_lane_data()
    todo = [r for r in rows if r["lane"] not in landed]
    out = ["ЛЕЙНИ %d:" % len(todo)]
    if not todo:
        out.append("  немає")
        return out
    for r in rows:
        if r["lane"] in landed:
            continue
        stage = lane_stage(r["lane"], r.get("verdict_last", ""), audits, conflicts)
        try:
            recent_audit = (time.time() - float((audits.get(r["lane"]) or {}).get("start") or 0)) < STALE_MIN * 60
        except (TypeError, ValueError):
            recent_audit = False
        stale = " СТОЇТЬ" if (r.get("idle", 10 ** 9) >= STALE_MIN and not recent_audit) else ""
        out.append("  %-9s %-16s %3dхв%s" % (r["lane"], stage, r.get("idle", 0), stale))
    return out


def _newest_gate(root=ROOT):
    """(rev, verdict, age_min, int_full) of the newest GATE_*.md; Nones when unreadable."""
    try:
        files = sorted(glob.glob(os.path.join(root, "DIRECTOR", "RUN", "GATE_*.md")), key=os.path.getmtime)
    except Exception:
        return None, None, None, None
    if not files:
        return None, None, None, None
    p = files[-1]
    try:
        age = int((time.time() - os.path.getmtime(p)) // 60)
    except OSError:
        age = None
    rev = os.path.basename(p)[5:-3] or None
    verdict, full = None, None
    try:
        for ln in open(p, encoding="utf-8", errors="replace"):
            s = ln.strip()
            m = re.match(r"# GATE (?:FAST|FULL) (\S+) int (\S+)", s)
            if m:
                full = m.group(2)
            m2 = re.match(r"## \S+ (PASS|FAIL)\b", s)
            if m2:
                if m2.group(1) == "FAIL":
                    verdict = "FAIL"
                elif verdict is None:
                    verdict = "PASS"
    except OSError:
        pass
    return rev, verdict, age, full


def _gate_lines():
    rev, verdict, age, full = _newest_gate()
    if not rev or not verdict:
        return ["ГЕЙТ: нема даних"]
    head = _int_head_full(os.path.join(ROOT, "APP"))
    if head and full and head == full:
        same = " (=int)"
    elif head:
        same = " (int %s)" % head[:7]
    else:
        same = ""
    agestr = " %dхв тому" % max(0, age) if age is not None else ""
    return ["ГЕЙТ: %s %s%s%s" % (verdict, rev, agestr, same)]


def _people_lines():
    try:
        ls = _load_lane_status()
        pr = ls.people_rows([("HD2", HD2_SID)])
    except Exception:
        return ["ЛЮДИ: нема даних"]
    if not pr:
        return ["ЛЮДИ: нема даних"]
    _tag, idle, _lt, _k = pr[0]
    try:
        subs = ls.sub_count(HD2_SID)
    except Exception:
        subs = -1
    if idle >= 10 ** 9 or subs < 0:
        return ["ЛЮДИ: нема даних"]
    return ["ЛЮДИ: HD2 %dхв сабів %d" % (idle, subs)]


def _script_states():
    out = []
    for label, needles in _SCRIPTS:
        try:
            live = _find_live_pids(*needles)
        except Exception:
            live = []
        out.append((label, live[0] if live else None))
    return out


def _scripts_lines(scripts):
    parts = []
    for label, pid in scripts:
        parts.append("%s=%s" % (label, "ок(%d)" % pid if pid else "ВПАВ"))
    return ["СКРИПТИ: " + (" ".join(parts) if parts else "нема даних")]


_JOURNAL_RES = ("LANDED", "CONFLICT", "GATE", "NEW-RED", "QUIET")


def _to_advisor_hd2(root=ROOT):
    """Non-AUTO lines under the ## HD2 heading of TO_ADVISOR.md."""
    try:
        text = open(os.path.join(root, "DIRECTOR", "INBOX", "TO_ADVISOR.md"), encoding="utf-8", errors="replace").read()
    except OSError:
        return []
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip() == "## HD2"), None)
    if start is None:
        return []
    chunk = []
    for l in lines[start + 1:]:
        if l.startswith("## "):
            break
        chunk.append(l)
    return [l.strip()[2:].strip() if l.strip().startswith("- ") else l.strip()
            for l in chunk if l.strip() and "AUTO" not in l]


def _journal_lines():
    out = ["ЖУРНАЛ:"]
    try:
        with open(os.path.join(ROOT, "DIRECTOR", "RUN", "TRAIN_LOG.txt"), encoding="utf-8", errors="replace") as f:
            lines = [l.rstrip() for l in f]
    except OSError:
        lines = []
    for h in [l for l in lines if any(k in l for k in _JOURNAL_RES)][-6:]:
        out.append("  - " + h[:160])
    try:
        adv = _to_advisor_hd2()
    except Exception:
        adv = []
    for h in adv[-6:]:
        out.append("  - " + h[:160])
    if len(out) == 1:
        out.append("  нема даних")
    return out


def _logs_lines():
    """ЛОГИ section (owner 2026-11-02: board has no logs): raw TRAIN_LOG tail
    + newest GATE verdicts + newest sub ends (RETURN/VERDICT HH:MM).
    Read-only, short, fail-closed ('нема даних', never a crash)."""
    out = ["ЛОГИ:"]
    try:
        tail = read_lines(os.path.join(ROOT, "DIRECTOR", "RUN", "TRAIN_LOG.txt"), 3)
    except Exception:
        tail = None
    if not tail:
        out.append("  train: нема даних")
    else:
        for ln in tail:
            out.append("  train: " + ln.strip()[:150])
    try:
        gates = sorted(glob.glob(os.path.join(ROOT, "DIRECTOR", "RUN", "GATE_*.md")),
                       key=os.path.getmtime)[-3:]
    except Exception:
        gates = []
    if not gates:
        out.append("  gate: нема даних")
    else:
        for gp in gates:
            rev = os.path.basename(gp)[5:-3]
            ver = "?"
            try:
                for ln in open(gp, encoding="utf-8", errors="replace"):
                    s = ln.strip()
                    if re.match(r"## \S+ FAIL\b", s):
                        ver = "FAIL"
                        break
                    if ver == "?" and re.match(r"## \S+ PASS\b", s):
                        ver = "PASS"
            except OSError:
                ver = "?"
            try:
                hhmm = time.strftime("%H:%M", time.localtime(os.path.getmtime(gp)))
            except OSError:
                hhmm = "?"
            out.append("  gate: %s %s %s" % (rev[:12], ver, hhmm))
    try:
        cands = []
        for pat in ("WT/*/_task/*/PAIR-RETURN.md", "WT/*/_task/*/RETURN.md",
                    "WT/*/_task/*/VERDICT.md"):
            cands += glob.glob(os.path.join(ROOT, pat))
        cands = sorted(set(cands), key=os.path.getmtime)[-3:]
    except Exception:
        cands = []
    if not cands:
        out.append("  sub: нема даних")
    else:
        for cp in cands:
            try:
                hhmm = time.strftime("%H:%M", time.localtime(os.path.getmtime(cp)))
            except OSError:
                hhmm = "?"
            out.append("  sub: %s %s" % (os.path.basename(os.path.dirname(cp))[:24], hhmm))
    return out


def phone_screen():
    """BOARD TRUTH (advisor 2026-11-02): one screen from the train files, in order:
    head / ЗЛИТТЯ / ЛЕЙНИ / ГЕЙТ / ЛЮДИ / СКРИПТИ / ЗБІРКА / ЖУРНАЛ / ЛОГИ.
    A value that cannot be read prints 'нема даних', never a guess, never a crash."""
    now = datetime.datetime.now()
    out = ["=" * 44]
    try:
        out += _head_lines(now)
    except Exception:
        out.append("AGENT SI %s | int нема даних | ЗЛИТО ?/0" % now.strftime("%H:%M"))
    warn = []
    try:
        scripts = _script_states()
    except Exception:
        scripts = []
    if scripts and scripts[0][1] is None:
        warn.append("merge_train ВПАВ (злиття стоїть)")
    try:
        out += _zlitya_lines()
    except Exception:
        out.append("ЗЛИТТЯ: нема даних")
    try:
        out += _lanes_lines()
    except Exception:
        out += ["ЛЕЙНИ:", "  нема даних"]
    try:
        out += _gate_lines()
    except Exception:
        out.append("ГЕЙТ: нема даних")
    try:
        out += _people_lines()
    except Exception:
        out.append("ЛЮДИ: нема даних")
    try:
        out += _scripts_lines(scripts)
    except Exception:
        out.append("СКРИПТИ: нема даних")
    try:
        out.append(exe_line([]))
    except Exception:
        out.append("ЗБІРКА: нема даних")
    try:
        out += _journal_lines()
    except Exception:
        out += ["ЖУРНАЛ:", "  нема даних"]
    try:
        out += _logs_lines()
    except Exception:
        out += ["ЛОГИ:", "  нема даних"]
    if warn:
        out[1:1] = ["! УВАГА:"] + ["  - " + w for w in warn[:6]]
    return "\n".join(out)


def _watch_files():
    """Tool files whose change must never show stale on a --loop board."""
    here = os.path.dirname(os.path.abspath(__file__))
    return [os.path.join(here, n) for n in ("owner_board.py", "progress.py", "dev.py", "sync_status.py")]


def _snapshot_mtimes(paths=None):
    if paths is None:
        paths = _watch_files()
    snap = {}
    for p in paths:
        try:
            snap[p] = os.path.getmtime(p)
        except OSError:
            snap[p] = None
    return snap


def _newer_path(snapshot, paths=None):
    """First watched path whose mtime grew since snapshot; None when unchanged.

    Only strictly newer mtime counts (no flapping on equal/older/touch-back).
    Missing-then-or-still-missing paths never count."""
    if paths is None:
        paths = list(snapshot.keys())
    for p in paths:
        try:
            cur = os.path.getmtime(p)
        except OSError:
            continue
        old = snapshot.get(p)
        if old is None:
            return p
        if cur > old:
            return p
    return None


def _maybe_reexec(snapshot, paths=None):
    """Re-exec self when any watched file got newer; return the live snapshot.

    os.execv replaces the process on success (no return); on failure (or under
    test with execv mocked) the refreshed snapshot is returned so the next tick
    is quiet -- exactly one exec attempt per change, never a flap loop."""
    if paths is None:
        paths = list(snapshot.keys())
    if _newer_path(snapshot, paths) is None:
        return snapshot
    try:
        script = os.path.abspath(__file__)
        rest = list(sys.argv[1:])
        os.execv(sys.executable, [sys.executable, script] + rest)
    except Exception:
        pass
    return _snapshot_mtimes(paths)


def main(argv):
    global screen
    screen = phone_screen  # the only screen (BOARD TRUTH 2026-11-02); --full is accepted and ignored
    loop = 0
    if "--loop" in argv:
        i = argv.index("--loop")
        try:
            loop = int(argv[i + 1]) if len(argv) > i + 1 else 30
        except ValueError:
            loop = 30
    out_path = os.path.join(RUN, "owner_board.out")
    if loop:
        try:
            with open(os.path.join(RUN, "owner_board.pid"), "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
        except OSError:
            pass
    snap = _snapshot_mtimes() if loop else {}
    while True:
        if loop:
            snap = _maybe_reexec(snap)
        try:
            txt = screen()
        except Exception as ex:
            txt = "OWNER BOARD error: %r" % ex
        if loop:
            try:  # bounded: rewrite in place, atomic (tmp + replace), never append
                tmp = out_path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(txt + "\n")
                os.replace(tmp, out_path)
            except OSError:
                pass
        else:
            try:
                print(txt, flush=True)
            except Exception:
                pass
            break
        time.sleep(loop)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
