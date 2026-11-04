# Development tool for this build, shown as written. Not part of the app.
# Machine paths, server addresses and session ids were replaced by <PLACEHOLDERS>; the logic is unchanged.
"""Merge train + closed audit loop. Train is the ONLY writer of int.
No model calls. Atomic writes. Absolute paths only, always pass workdir.
No delete, no reset --hard, no clean, no chr() paths, no rmtree.
"""
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time

ROOT = r'<BUILD_ROOT>'
APP = os.path.join(ROOT, 'APP')
TRAIN = os.path.join(ROOT, 'WT', 'TRAIN')
RUN = os.path.join(ROOT, 'DIRECTOR', 'RUN')
TOOLS = os.path.join(ROOT, 'DIRECTOR', 'TOOLS')
LANES_FILE = os.path.join(RUN, 'TRAIN_LANES.txt')
STATE_FILE = os.path.join(RUN, 'TRAIN_STATE.json')
LOG_FILE = os.path.join(RUN, 'TRAIN_LOG.txt')
ALLOWED_FILE = os.path.join(RUN, 'GOLDEN_ALLOWED.txt')
TEMPLATE_FILE = os.path.join(RUN, 'audit_FXWATCH.txt')
RECORDS_JSONL = os.path.join(APP, 'RECORDS', 'accepted_packages.jsonl')
WORKER_START = os.path.join(TOOLS, 'advisor_probes', 'worker_start.ps1')
HD_MSG = os.path.join(TOOLS, 'hd_msg.ps1')
VENV_PYTHON = r'<VENV_PYTHON_EXE>'

#: No-op browser for train test runs: windowless pythonw runs `pass` on the
#: URL arg (argv ignored, exits 0, no shell parsing, no window). The %s
#: template survives webbrowser's shlex.split (forward slashes: backslashes
#: would corrupt); rc 0 stops webbrowser.open at this sink so it never
#: falls through to the owner's Chrome (old chcp.com sink exited 1).
#: Proven 2026-11-02: GenericBrowser.open -> True, no window.
TEST_BROWSER_NOOP = r"<VENV_PYTHONW_EXE> -c pass %s"


def _hidden_kwargs():
    """Kwargs hiding console windows for every child process on Windows.

    The train loop runs detached with no console; without CREATE_NO_WINDOW
    each git/pwsh/pytest child opens its own terminal window. Pass the
    result to every subprocess.run AND subprocess.Popen call.
    """
    try:
        if os.name == 'nt':
            return {'creationflags': subprocess.CREATE_NO_WINDOW}
    except Exception:
        pass
    return {}


def free_ram_gb():
    """Available RAM in GiB from the `\\Memory\\Available MBytes` counter.

    Read fresh on every call (low-RAM guard). Falls back to
    GlobalMemoryStatusEx only if the counter cannot be read.
    """
    if os.name == 'nt':
        try:
            r = subprocess.run(
                ['typeperf', r'\Memory\Available MBytes', '-sc', '1'],
                capture_output=True, text=True, timeout=60, **_hidden_kwargs())
            for line in reversed((r.stdout or '').splitlines()):
                m = re.search(r'([\d.]+)\s*"?$', line.strip())
                if m and 'Available' not in line:
                    return float(m.group(1)) / 1024.0
        except Exception:
            pass
        try:
            import ctypes

            class _MS(ctypes.Structure):
                _fields_ = [('dwLength', ctypes.c_ulong),
                            ('dwMemoryLoad', ctypes.c_ulong),
                            ('ullTotalPhys', ctypes.c_ulonglong),
                            ('ullAvailPhys', ctypes.c_ulonglong),
                            ('ullTotalPageFile', ctypes.c_ulonglong),
                            ('ullAvailPageFile', ctypes.c_ulonglong),
                            ('ullTotalVirtual', ctypes.c_ulonglong),
                            ('ullAvailVirtual', ctypes.c_ulonglong),
                            ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
            st = _MS()
            st.dwLength = ctypes.sizeof(_MS)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return st.ullAvailPhys / (1024.0 ** 3)
        except Exception:
            pass
        return 99.0
    try:
        with open('/proc/meminfo', encoding='utf-8') as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1]) / 1048576.0
    except Exception:
        pass
    return 99.0


def audit_cap(free_gb=None):
    """Max parallel audits: 3 while Available MBytes is below 3 GB,
    6 while below 8 GB, 10 at 8 GB or more."""
    try:
        g = float(free_gb if free_gb is not None else free_ram_gb())
    except Exception:
        return 6
    if g < 3.0:
        return 3
    if g < 8.0:
        return 6
    return 10


def wait_for_ram(min_gb=1.5, poll_s=30.0, limit_s=1800.0, log_file=None, lane='?'):
    """Block the recipe's own test run while Available MBytes is below min_gb."""
    waited = 0.0
    while True:
        try:
            g = free_ram_gb()
        except Exception:
            return True
        if g >= min_gb:
            return True
        if waited >= limit_s:
            try:
                log_event('WAIT-TIMEOUT %s free=%.1fGB' % (lane, g), log_file or LOG_FILE)
            except Exception:
                pass
            return False
        time.sleep(poll_s)
        waited += poll_s


def _pytest_env():
    """Env for train pytest runs: clean, hermetic, windowless.

    The loop process itself may run from an interpreter whose directory is
    not on PATH (so shutil.which("python") finds nothing or a stub and every
    served test that launches a python part fails). Put the loop's own
    interpreter dir + Scripts first so `python` always resolves.
    AGENT_SI_ALLOW_MULTI is deliberately NOT set here: it stays opt-in per
    test copy, never global for train runs.
    """
    import sys as _sys
    env = dict(os.environ)
    env['AGENT_SI_SECRET_STORE'] = 'memory'
    env['BROWSER'] = TEST_BROWSER_NOOP
    env.pop('AGENT_SI_ALLOW_MULTI', None)
    try:
        pydir = os.path.dirname(os.path.abspath(_sys.executable))
        scripts = os.path.join(pydir, 'Scripts')
        old = env.get('PATH', '')
        parts = [p for p in (pydir, scripts) if p and os.path.isdir(p)]
        if old:
            parts.append(old)
        env['PATH'] = os.pathsep.join(parts)
    except Exception:
        pass
    return env
WATCH_FILE = os.path.join(RUN, 'TRAIN_WATCH.txt')
HD_SESSION = '<SESSION_ID>'
HD_TICK_MSG = (r'Tick: run DIRECTOR\TOOLS\lane_status.py, keep 6 subs busy per '
               r'RUN\advisor_msg_1250.txt, start the next item, no foreground wait.')
STALL_MSG = ('NEVER call the question tool. You stopped. Go on with your order list now, '
             'commit per item, no stopping between items. If all is done write the PAIR-RETURN, last line exactly DONE.')
STALL_IDLE_SEC = 4 * 60
HD_IDLE_SEC = 8 * 60
NUDGE_MIN_SEC = 8 * 60
CHILD_ACTIVE_SEC = 8 * 60


def utc_now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def atomic_write_text(path, text):
    tmp = path + '.tmp.' + str(os.getpid())
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp, path)


def log_event(msg, log_file=LOG_FILE):
    line = '%s TRAIN %s' % (utc_now(), msg)
    for _ in range(20):
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
            return line
        except Exception:
            time.sleep(0.5)
    return line


def parse_lanes_file(path=LANES_FILE):
    lanes = []
    with open(path, encoding='utf-8') as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith('#') or line.startswith('Note:'):
                continue
            parts = [p.strip() for p in line.split('|')]
            if len(parts) != 5:
                continue
            lane, clone, branch, session, after = parts
            lanes.append({'lane': lane, 'clone': clone, 'branch': branch,
                          'session': session, 'after': after})
    return lanes


def lane_paths(lane, clone_rel, root=ROOT):
    clone_abs = os.path.join(root, clone_rel) if not os.path.isabs(clone_rel) else clone_rel
    return {
        'clone': clone_abs,
        'return': os.path.join(clone_abs, '_task', lane, 'PAIR-RETURN.md'),
        'verdict': os.path.join(clone_abs, '_task', lane, 'VERDICT.md'),
    }


def load_state(path=STATE_FILE):
    try:
        with open(path, encoding='utf-8') as f:
            st = json.load(f)
        if not isinstance(st, dict):
            return {}
        return st
    except Exception:
        return {}


def save_state_atomic(path, state):
    atomic_write_text(path, json.dumps(state, indent=1, sort_keys=True) + '\n')


def _done_line_ok(line):
    t = line.strip()
    for _ in range(3):
        t = t.strip()
        # strip trailing dots (DONE. / DONE..)
        t = t.rstrip('.').strip()
        # strip markdown / quote marks from both ends
        t = t.strip('#>*`_- ').strip()
        t = t.strip('"\'').strip()
    return t.upper() == 'DONE'


def return_is_done(return_path):
    try:
        with open(return_path, encoding='utf-8') as f:
            text = f.read()
    except Exception:
        return False
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return False
    return _done_line_ok(lines[-1])


def verdict_status(verdict_path, lane=None):
    try:
        with open(verdict_path, encoding='utf-8') as f:
            text = f.read()
    except Exception:
        return None
    lines = text.splitlines()
    last = None
    for line in lines:
        m = re.search(r'verdict\s*:\s*(PASS|FAIL)\b', line, re.IGNORECASE)
        if m:
            last = m.group(1).upper()
            continue
        m2 = re.search(r'VERDICT\s*[:\s]+\S+\s*[-=\u2014\u2013:.\s]*\b(PASS|FAIL)\b', line, re.IGNORECASE)
        if m2:
            last = m2.group(1).upper()
    if last:
        return last
    for line in lines:
        s = line.strip()
        if s.startswith('#'):
            m3 = re.search(r'\b(PASS|FAIL)\b', s, re.IGNORECASE)
            if m3:
                return m3.group(1).upper()
    return None


# 2026-11-02 13:55 local (UTC-6) = 19:55 UTC: shell-denying guard rule lifted.
# Verdicts before this that blame shell-denied/no-runs are hollow, not real.
GUARD_CUT_EPOCH = 1793649300
HOLLOW_PAT = re.compile(r'shell[ -](denied|blocked)|no[- ]auditor[- ]runs?|no re-runs|'
                        r'PASS ONLY WITH A RUN|no auditor test run|golden not run',
                        re.IGNORECASE)


def is_hollow_fail(verdict_path):
    """True if the verdict is an explicit no-run FAIL from the guard era."""
    try:
        with open(verdict_path, encoding='utf-8') as f:
            text = f.read()
    except Exception:
        return False
    if verdict_status(verdict_path) == 'PASS':
        return False
    if not HOLLOW_PAT.search(text):
        return False
    try:
        if os.path.getmtime(verdict_path) >= GUARD_CUT_EPOCH:
            return False
    except Exception:
        return False
    return True


def run_git(args, cwd):
    return subprocess.run(['git'] + args, cwd=cwd, capture_output=True, text=True, timeout=120,
                          **_hidden_kwargs())


def is_tree_clean(clone_abs):
    r = run_git(['status', '--porcelain=v1', '--untracked-files=no'], cwd=clone_abs)
    if r.returncode != 0:
        return False
    return r.stdout.strip() == ''


def current_branch(clone_abs):
    r = run_git(['branch', '--show-current'], cwd=clone_abs)
    if r.returncode != 0:
        return ''
    return r.stdout.strip()


def get_tip_time(clone_abs, branch):
    r = run_git(['log', '-1', '--format=%ct', branch, '--'], cwd=clone_abs)
    if r.returncode != 0:
        return 0
    try:
        return int(r.stdout.strip())
    except Exception:
        return 0


def is_worktree_of_app(clone_abs, app=APP):
    r = run_git(['worktree', 'list', '--porcelain'], cwd=app)
    if r.returncode != 0:
        return False
    for line in r.stdout.splitlines():
        if line.startswith('worktree '):
            p = line[len('worktree '):].strip()
            if os.path.normcase(os.path.normpath(p)) == os.path.normcase(os.path.normpath(clone_abs)):
                return True
    return False


LANE_ORDER_EXTRA = {
    'FXGAPT': ('Note: this lane adds tests only; zero product diff is fine. '
               'A RED test that names a product defect is REPORTED with file+line+expected behavior, '
               'not counted as a FAIL of this lane.'),
}


def build_order(template_text, lane, clone_abs, branch):
    text = template_text.replace('FXWATCH', lane)
    text = text.replace(r'<BUILD_ROOT>\WT\R07', clone_abs)
    text = text.replace('pkg/FXWATCH', branch)
    if 'LANE ' + lane not in text:
        text = text + '\nLANE %s clone %s branch %s.\n' % (lane, clone_abs, branch)
    extra = LANE_ORDER_EXTRA.get(lane)
    if extra and extra not in text:
        text = text + '\n' + extra + '\n'
    return text


def count_session_rows(session_id, db_path=None):
    if db_path is None:
        home = os.path.expanduser('~')
        db_path = os.path.join(home, '.local', 'share', 'opencode', 'opencode.db')
    try:
        con = sqlite3.connect('file:' + db_path + '?mode=ro', uri=True, timeout=5)
        try:
            cur = con.cursor()
            cur.execute('SELECT count(*) FROM session_message WHERE session_id=?', (session_id,))
            row = cur.fetchone()
            return int(row[0]) if row else 0
        finally:
            con.close()
    except Exception:
        return -1


def session_idle_info(session_id, db_path=None, now_sec=None):
    """Return (has_running, last_msg_sec). Read-only. Never raises."""
    if db_path is None:
        home = os.path.expanduser('~')
        db_path = os.path.join(home, '.local', 'share', 'opencode', 'opencode.db')
    has_running = False
    last_ms = 0
    try:
        con = sqlite3.connect('file:' + db_path + '?mode=ro', uri=True, timeout=5)
        try:
            cur = con.cursor()
            try:
                cur.execute("SELECT count(*) FROM job WHERE session_id=? AND status='running'", (session_id,))
                row = cur.fetchone()
                has_running = bool(row and row[0])
            except Exception:
                has_running = False
            try:
                cur.execute('SELECT max(time_updated) FROM session_message WHERE session_id=?', (session_id,))
                row = cur.fetchone()
                last_ms = int(row[0]) if row and row[0] else 0
            except Exception:
                last_ms = 0
        finally:
            con.close()
    except Exception:
        return (False, 0)
    return (has_running, last_ms / 1000.0)


def child_session_ids(session_id, db_path=None):
    if db_path is None:
        home = os.path.expanduser('~')
        db_path = os.path.join(home, '.local', 'share', 'opencode', 'opencode.db')
    try:
        con = sqlite3.connect('file:' + db_path + '?mode=ro', uri=True, timeout=5)
        try:
            cur = con.cursor()
            cur.execute('SELECT id FROM session_v2 WHERE parent_id=?', (session_id,))
            return [r[0] for r in cur.fetchall()]
        finally:
            con.close()
    except Exception:
        return []


def session_last_type(session_id, db_path=None):
    if db_path is None:
        home = os.path.expanduser('~')
        db_path = os.path.join(home, '.local', 'share', 'opencode', 'opencode.db')
    try:
        con = sqlite3.connect('file:' + db_path + '?mode=ro', uri=True, timeout=5)
        try:
            cur = con.cursor()
            cur.execute('SELECT type FROM session_message WHERE session_id=? ORDER BY seq DESC LIMIT 1', (session_id,))
            row = cur.fetchone()
            return str(row[0]) if row and row[0] else ''
        finally:
            con.close()
    except Exception:
        return ''


def session_is_live(session_id, now_sec, db_path=None, _depth=0):
    """True when the session itself runs (tool or streaming reply) or a child does.
    Read-only. A live session is never stalled: no nudge, no STALL line."""
    try:
        has_run, last_sec = session_idle_info(session_id, db_path)
    except Exception:
        has_run, last_sec = (False, 0.0)
    if has_run:
        return True
    if _depth > 2:
        return False
    try:
        ltype = session_last_type(session_id, db_path)
    except Exception:
        ltype = ''
    if ltype and ltype != 'idle' and last_sec and (now_sec - last_sec) < CHILD_ACTIVE_SEC:
        return True
    try:
        kids = child_session_ids(session_id, db_path)
    except Exception:
        kids = []
    for k in kids or []:
        try:
            if session_is_live(k, now_sec, db_path, _depth + 1):
                return True
        except Exception:
            pass
    return False


def parse_watch_file(path=WATCH_FILE):
    rows = []
    try:
        with open(path, encoding='utf-8') as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith('#'):
                    continue
                parts = [p.strip() for p in line.split('|')]
                if len(parts) != 3:
                    continue
                rows.append({'title': parts[0], 'session': parts[1], 'done_file': parts[2]})
    except Exception:
        pass
    return rows


def lane_tip_hash(clone_abs, branch):
    try:
        r = run_git(['rev-parse', branch], cwd=clone_abs)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return ''


def golden_new_reds(reds, allowed):
    """Sorted golden test names outside the allowed list (empty allowed blocks all)."""
    norm_allowed = set([str(a).lstrip('0') or '0' for a in (allowed or [])])
    out = []
    for x in (reds or []):
        n = str(x).lstrip('0') or '0'
        if n not in norm_allowed:
            out.append('test_golden_%s' % n)
    return sorted(out)


def int_head_for_gate(app=APP):
    try:
        r = run_git(['rev-parse', 'int'], cwd=app)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()[:12]
    except Exception:
        pass
    return ''


def gate_hold_enabled(run_dir=RUN):
    """False while RUN/GATE_HOLD.off exists: landings proceed by the normal
    recipe (fix lanes must land despite a red gate); the hold logic stays
    for later, re-armed by deleting the file."""
    try:
        return not os.path.exists(os.path.join(run_dir, 'GATE_HOLD.off'))
    except Exception:
        return True


def read_gate_report(run_dir=RUN, rev12=''):
    """(status, sections, test_ids) for RUN/GATE_<rev12>.md.

    absent: file missing or still running (no walls: summary) -> land as now.
    """
    if not rev12:
        return ('absent', [], [])
    p = os.path.join(run_dir, 'GATE_%s.md' % rev12)
    try:
        with open(p, encoding='utf-8') as f:
            text = f.read()
    except Exception:
        return ('absent', [], [])
    if 'walls:' not in text:
        return ('absent', [], [])
    sections = []
    for m in re.finditer(r'^##\s+(\S+)\s+FAIL\b', text, re.MULTILINE):
        if m.group(1) not in sections:
            sections.append(m.group(1))
    ids = []
    for m in re.finditer(r'FAILED\s+(\S+)', text):
        if m.group(1) not in ids:
            ids.append(m.group(1))
    if sections:
        return ('FAIL', sections, ids)
    return ('PASS', [], [])


def append_train_line(line, path=None):
    """Append one line under ## Train in TO_ADVISOR.md (append-only)."""
    p = path or os.path.join(ROOT, 'DIRECTOR', 'INBOX', 'TO_ADVISOR.md')
    try:
        with open(p, encoding='utf-8') as f:
            cur = f.read()
    except Exception:
        cur = ''
    with open(p, 'a', encoding='utf-8') as f:
        if '\n## Train' not in cur and not cur.startswith('## Train'):
            f.write('\n## Train\n')
        f.write(line if line.endswith('\n') else line + '\n')


def int_head_hash(app=APP, train=TRAIN):
    for cwd, ref in ((app, 'int'), (train, 'origin/int')):
        try:
            r = run_git(['rev-parse', ref], cwd=cwd)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass
    return ''


def noaudit_merge_ok(clone_abs, branch, ver_mtime, conflict_files=None):
    """True iff the lane tip is exactly one merge of int newer than the verdict,
    touching only conflict (or int-side) files. Read-only. Returns (ok, reason)."""
    try:
        r = run_git(['rev-parse', branch], cwd=clone_abs)
        if r.returncode != 0 or not r.stdout.strip():
            return (False, 'no-branch')
        tip = r.stdout.strip()
        r = run_git(['log', '--first-parent', '--format=%H_%P_%ct', branch, '--'], cwd=clone_abs)
        if r.returncode != 0:
            return (False, 'no-log')
        newc = []
        for line in r.stdout.splitlines():
            p = line.strip().split('_')
            if len(p) != 3:
                continue
            h, ps, ct = p
            try:
                ctt = int(ct)
            except Exception:
                continue
            if ctt > ver_mtime:
                newc.append((h, ps.split(), ctt))
        if len(newc) != 1:
            return (False, 'new=%d' % len(newc))
        h, parents, _ = newc[0]
        if h != tip:
            return (False, 'tip-not-newest')
        if len(parents) != 2:
            return (False, 'not-merge')
        p1, p2 = parents
        intref = None
        for cand in ('origin/int', 'int'):
            rr = run_git(['rev-parse', '--verify', cand], cwd=clone_abs)
            if rr.returncode == 0:
                intref = cand
                break
        if intref:
            rr = run_git(['merge-base', '--is-ancestor', p2, intref], cwd=clone_abs)
            if rr.returncode != 0:
                return (False, 'p2-not-int')
        else:
            rr = run_git(['log', '-1', '--format=%s', p2, '--'], cwd=clone_abs)
            if rr.returncode != 0 or 'int' not in (rr.stdout or '').lower():
                return (False, 'no-intref')
        r = run_git(['diff', '--name-only', p1, h], cwd=clone_abs)
        if r.returncode != 0:
            return (False, 'no-diff')
        touched = set([x.strip() for x in r.stdout.splitlines() if x.strip()])
        if conflict_files:
            cf = set([x.strip() for x in conflict_files if x.strip()])
            extra = touched - cf
            if extra:
                return (False, 'extra=%d' % len(extra))
            return (True, 'files=%d' % len(touched))
        r = run_git(['merge-base', p1, p2], cwd=clone_abs)
        mb = r.stdout.strip() if r.returncode == 0 else ''
        if not mb:
            return (False, 'no-base')
        r = run_git(['diff', '--name-only', mb, p2], cwd=clone_abs)
        if r.returncode != 0:
            return (False, 'no-intdiff')
        intside = set([x.strip() for x in r.stdout.splitlines() if x.strip()])
        extra = touched - intside
        if extra:
            return (False, 'extra=%d' % len(extra))
        return (True, 'files=%d' % len(touched))
    except Exception as e:
        return (False, 'err=%s' % str(e)[:60])


def start_auditor(title, order_file):
    r = subprocess.run(['pwsh', '-NoProfile', '-File', WORKER_START,
                        '-Title', title, '-File', order_file],
                       capture_output=True, text=True, timeout=120, cwd=ROOT,
                       **_hidden_kwargs())
    out = (r.stdout or '') + (r.stderr or '')
    m = re.search(r'started\s+(ses_[A-Za-z0-9]+)', out)
    if m:
        return m.group(1)
    return None


def post_hd_msg(msg_file, sid):
    args = ['pwsh', '-NoProfile', '-File', HD_MSG, '-File', msg_file]
    if sid:
        args += ['-Sid', sid]
    r = subprocess.run(args, capture_output=True, text=True, timeout=60, cwd=ROOT,
                       **_hidden_kwargs())
    return r.returncode == 0


def read_allowed(path=ALLOWED_FILE):
    try:
        with open(path, encoding='utf-8') as f:
            return set([l.strip() for l in f if l.strip()])
    except Exception:
        return set()


def parse_golden_reds(pytest_text):
    reds = set()
    for line in pytest_text.splitlines():
        if 'test_golden_user_path.py' in line and ('FAILED' in line.upper() or 'ERROR' in line.upper()):
            m = re.search(r'test_golden_(\d+)_', line)
            if m:
                reds.add(m.group(1).lstrip('0') or '0')
    if not reds:
        for m in re.finditer(r'(?:FAILED|ERROR)\s+\S*test_golden_(\d+)', pytest_text):
            reds.add(m.group(1).lstrip('0') or '0')
    return reds


def first_e_lines(pytest_text):
    """Map test function name -> first E line of its failure section."""
    res = {}
    cur = None
    for line in (pytest_text or '').splitlines():
        m = re.match(r'_{2,}\s*(.+?)\s*_{2,}\s*$', line)
        if m:
            cur = m.group(1).strip()
            continue
        me = re.match(r'ERROR at (?:setup|teardown) of (\S+)\s*$', line)
        if me:
            cur = me.group(1).strip()
            continue
        if cur is not None and cur not in res:
            me = re.match(r'\s*E\s+(.*\S)\s*$', line)
            if me:
                res[cur] = 'E ' + me.group(1)
    return res


def parse_all_failures(pytest_text):
    """All FAILED/ERROR test node ids in order, deduped (golden + lane files)."""
    out = []
    for line in (pytest_text or '').splitlines():
        m = re.match(r'(?:FAILED|ERROR)\s+(\S+)', line)
        if m:
            out.append(m.group(1))
    seen = set()
    res = []
    for x in out:
        if x not in seen:
            seen.add(x)
            res.append(x)
    return res


_BASELINE_GATE = os.path.join(RUN, 'GATE_8b180bc6b054.md')


def read_baseline_ids(path=None):
    """Test ids/names from the int-gate baseline RED/FAIL list (FXRED-owned)."""
    p = path or _BASELINE_GATE
    ids = set()
    try:
        with open(p, encoding='utf-8') as f:
            for line in f:
                s = line.strip()
                if s.startswith('- RED ') or s.startswith('- FAIL '):
                    parts = s.split()
                    if len(parts) >= 3:
                        tok = parts[2]
                        ids.add(tok)
                        ids.add(os.path.basename(tok))
    except Exception:
        pass
    return ids


def parse_golden_tail(pytest_text):
    m = None
    for line in pytest_text.splitlines():
        if 'passed' in line or 'failed' in line:
            m = line.strip()
    if m:
        return m[:200]
    return ''


def changed_test_files(train=TRAIN):
    r = run_git(['diff', '--name-only', 'origin/int..HEAD'], cwd=train)
    if r.returncode != 0:
        return []
    files = []
    for line in r.stdout.splitlines():
        s = line.strip().replace('/', os.sep)
        if s.startswith('tests' + os.sep) and s.endswith('.py'):
            files.append(s.replace(os.sep, '/'))
    return files


def attempt_merge(train, branch, msg):
    """Merge FETCH_HEAD with --no-ff --no-commit. Returns (state, files, err):
    clean: merged, uncommitted, ready for the stray-file gate + commit.
    up-to-date: lane already contained, nothing to commit.
    conflict: real conflicts; U-list read BEFORE abort so it is never empty.
    failed: merge failed otherwise (err carries the git stderr tail)."""
    r = run_git(['merge', '--no-ff', '--no-commit', 'FETCH_HEAD', '-m', msg], cwd=train)
    if r.returncode == 0:
        if 'already up to date' in ((r.stdout or '') + (r.stderr or '')).lower():
            return ('up-to-date', [], '')
        return ('clean', [], '')
    rf = run_git(['diff', '--name-only', '--diff-filter=U'], cwd=train)
    files = sorted(set([x.strip() for x in (rf.stdout or '').splitlines() if x.strip()]))
    run_git(['merge', '--abort'], cwd=train)
    if files:
        return ('conflict', files, '')
    tail = ((r.stderr or '').strip().splitlines() or ['']) [-1][:300]
    return ('failed', [], tail)


def is_stray_added(path):
    """Lane-added files that must never land: repo-root files, _task/ content,
    merge leftovers."""
    b = os.path.basename(path)
    return ('/' not in path or path.startswith('_task/')
            or os.path.splitext(b)[1].lower() in ('.orig', '.rej', '.bak'))


def run_merge_recipe(lane, clone_rel, branch, verdict_path='', root=ROOT, train=TRAIN,
                     app=APP, log_file=LOG_FILE, records_jsonl=RECORDS_JSONL,
                     allowed_file=ALLOWED_FILE, pytest_timeout='120'):
    clone_abs = os.path.join(root, clone_rel) if not os.path.isabs(clone_rel) else clone_rel
    # fetch origin, detach int
    r = run_git(['fetch', 'origin'], cwd=train)
    if r.returncode != 0:
        log_event('MERGE %s FETCH-ORIGIN-FAIL %s' % (lane, (r.stderr or '')[:200]), log_file)
        return None
    r = run_git(['switch', '--detach', 'origin/int'], cwd=train)
    if r.returncode != 0:
        log_event('MERGE %s DETACH-FAIL %s' % (lane, (r.stderr or '')[:200]), log_file)
        return None
    # fetch lane: try clone path, fallback to origin (worktrees share APP)
    r = run_git(['fetch', clone_abs, branch], cwd=train)
    if r.returncode != 0:
        r2 = run_git(['fetch', 'origin', branch], cwd=train)
        if r2.returncode != 0:
            log_event('MERGE %s FETCH-LANE-FAIL %s' % (lane, (r.stderr or '')[:200]), log_file)
            return None
    if not wait_for_ram(1.5, 30.0, 1800.0, log_file, lane):
        return {'wait_timeout': True}
    mstate, mfiles, merr = attempt_merge(train, branch, "Merge branch '%s' into int" % branch)
    if mstate == 'conflict':
        log_event('MERGE %s CONFLICT %s' % (lane, ' '.join(mfiles)[:500]), log_file)
        return {'conflict': mfiles}
    if mstate == 'failed':
        log_event('MERGE %s MERGE-FAILED %s' % (lane, merr), log_file)
        return None
    if mstate == 'clean':
        r = run_git(['diff', '--name-only', '--diff-filter=A', 'HEAD'], cwd=train)
        added = [x.strip() for x in (r.stdout or '').splitlines() if x.strip()]
        strays = [p for p in added if is_stray_added(p)]
        if strays:
            run_git(['merge', '--abort'], cwd=train)
            log_event('STRAY %s %s' % (lane, strays[:12]), log_file)
            return {'stray': strays}
        r = run_git(['commit', '--no-edit'], cwd=train)
        if r.returncode != 0:
            run_git(['merge', '--abort'], cwd=train)
            log_event('MERGE %s COMMIT-FAIL %s' % (lane, (r.stderr or '')[:200]), log_file)
            return None
    test_files = changed_test_files(train)
    targets = ['tests/test_golden_user_path.py'] + test_files
    tmpbase = os.path.join(train, '_task', 'tmp')
    try:
        os.makedirs(tmpbase, exist_ok=True)
    except Exception:
        pass
    if not wait_for_ram(1.5, 30.0, 1800.0, log_file, lane):
        return {'wait_timeout': True}
    basetemp = os.path.join(tmpbase, 'pt-TRAIN-%s-%d' % (lane, int(time.time())))
    env = _pytest_env()
    cmd = [VENV_PYTHON, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
           '--basetemp', basetemp, '--timeout', str(pytest_timeout)] + targets
    try:
        pr = subprocess.run(cmd, cwd=train, capture_output=True, text=True,
                            timeout=900, env=env, **_hidden_kwargs())
    except Exception as e:
        log_event('MERGE %s PYTEST-ERROR %s' % (lane, str(e)[:200]), log_file)
        return None
    out = (pr.stdout or '') + (pr.stderr or '')
    reds = parse_golden_reds(out)
    tail = parse_golden_tail(out)
    allowed = read_allowed(allowed_file)
    new_reds = golden_new_reds(reds, allowed)
    failed = parse_all_failures(out)
    golden_nodes = [f for f in failed
                    if os.path.basename(f.split('::')[0]) == 'test_golden_user_path.py']
    lane_reds = [f for f in failed
                 if os.path.basename(f.split('::')[0]) != 'test_golden_user_path.py']
    flaky_all, excused_all, first_e = [], [], {}
    if new_reds or lane_reds:
        by_file = {}
        if new_reds:
            by_file.setdefault('tests/test_golden_user_path.py', []).extend(
                golden_nodes or ['tests/test_golden_user_path.py'])
        for _node in lane_reds:
            by_file.setdefault(_node.split('::')[0], []).append(_node)
        baseline = read_baseline_ids()
        still = []
        for _i, (_tfile, _nodes) in enumerate(sorted(by_file.items())):
            _rdir = os.path.join(tmpbase, 'pt-TRAIN-%s-re%d' % (lane, _i))
            _rcmd = [VENV_PYTHON, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                     '--basetemp', _rdir, '--timeout', str(pytest_timeout), _tfile]
            try:
                _rr = subprocess.run(_rcmd, cwd=train, capture_output=True, text=True,
                                     timeout=900, env=env, **_hidden_kwargs())
                _rout = (_rr.stdout or '') + (_rr.stderr or '')
                _emap = first_e_lines(_rout)
                for _n in parse_all_failures(_rout):
                    if _n.split('::')[0] == _tfile or _tfile in _n:
                        still.append(_n)
                        _fn = _n.split('::')[-1].split('[')[0]
                        for _hk, _hv in _emap.items():
                            if _fn and _fn in _hk:
                                first_e[_n] = _hv
                                break
            except Exception:
                still.extend(_nodes)
        excused = [n for n in still
                   if n in baseline or n.split('::')[0] in baseline
                   or os.path.basename(n.split('::')[0]) in baseline]
        flaky_all = [n for n in lane_reds if n not in still] + \
                    [n for n in golden_nodes if n not in still]
        excused_all = list(excused)
        blocking = [n for n in still if n not in excused]
        if blocking:
            log_event('NEW-RED %s %s tail=%s' % (lane, blocking[:12], tail), log_file)
            for _bn in blocking[:12]:
                log_event('NEW-RED-E %s %s | %s' % (lane, _bn, first_e.get(_bn, 'no E line')[:200]), log_file)
            if excused:
                log_event('NEW-RED-EXCUSED %s %s' % (lane, excused[:12]), log_file)
            return {'new_red': blocking,
                    'first_e': {n: first_e.get(n, '') for n in blocking}}
        if excused:
            log_event('NEW-RED-EXCUSED %s %s tail=%s' % (lane, excused[:12], tail), log_file)
    head = run_git(['rev-parse', 'HEAD'], cwd=train)
    merge_hash = head.stdout.strip()
    # land on APP
    br = current_branch(app)
    clean = is_tree_clean(app)
    landed = False
    if br == 'int' and clean:
        f1 = run_git(['fetch', train, 'HEAD'], cwd=app)
        if f1.returncode == 0:
            m1 = run_git(['merge', '--ff-only', 'FETCH_HEAD'], cwd=app)
            landed = m1.returncode == 0
    else:
        p1 = run_git(['push', 'origin', 'HEAD:int'], cwd=train)
        landed = p1.returncode == 0
    if not landed:
        log_event('MERGE %s LAND-FAIL branch=%s clean=%s' % (lane, br, clean), log_file)
        return None
    if not is_worktree_of_app(clone_abs, app):
        run_git(['fetch', clone_abs, '%s:refs/heads/%s' % (branch, branch)], cwd=app)
    log_event('%s LANDED %s %s golden_reds=%s flaky=%s excused=%s' % (
        lane, merge_hash, tail,
        sorted(['test_golden_%s' % x for x in reds]),
        flaky_all[:12], excused_all[:12]), log_file)
    for _ in range(20):
        try:
            with open(records_jsonl, 'a', encoding='utf-8') as f:
                f.write(json.dumps({'id': lane, 'merge_hash': merge_hash,
                                    'verdict': verdict_path, 'golden_tail': tail,
                                    'time': utc_now()}) + '\n')
            break
        except Exception:
            time.sleep(0.5)
    return (merge_hash, tail)


def pending_audits(state, lanes=None, root=ROOT, now=None, db_path=None, fn_live=None):
    """An audit holds a slot only while its VERDICT.md is older than its start
    AND its session is live (running tool or running child). A finished audit
    (verdict newer than start) never holds a slot."""
    n = 0
    now = now if now is not None else time.time()
    by_lane = {}
    try:
        for it in lanes or []:
            by_lane[it.get('lane')] = it
    except Exception:
        pass
    for lane, v in (state.get('audits') or {}).items():
        if not isinstance(v, dict) or not v.get('sid') or v.get('verdict_seen'):
            continue
        if lane in (state.get('landed') or []):
            continue
        ver = None
        it = by_lane.get(lane)
        if it is not None:
            try:
                ver = lane_paths(lane, it.get('clone', ''), root)['verdict']
            except Exception:
                ver = None
        try:
            ver_mtime = os.path.getmtime(ver) if ver else 0
        except Exception:
            ver_mtime = 0
        if ver_mtime and ver_mtime > (v.get('start') or 0):
            continue
        sid = v.get('sid')
        try:
            live = fn_live(sid) if fn_live else session_is_live(sid, now, db_path)
        except Exception:
            live = False
        if live:
            n += 1
    return n


def process_once(config=None):
    cfg = dict(config or {})
    root = cfg.get('root', ROOT)
    run_dir = cfg.get('run_dir', RUN)
    train = cfg.get('train', TRAIN)
    app = cfg.get('app', APP)
    lanes_file = cfg.get('lanes_file', LANES_FILE)
    state_file = cfg.get('state_file', STATE_FILE)
    log_file = cfg.get('log_file', LOG_FILE)
    template_file = cfg.get('template_file', TEMPLATE_FILE)
    records_jsonl = cfg.get('records_jsonl', RECORDS_JSONL)
    allowed_file = cfg.get('allowed_file', ALLOWED_FILE)
    fn_start = cfg.get('fn_start', start_auditor)
    fn_post = cfg.get('fn_post', post_hd_msg)
    fn_merge = cfg.get('fn_merge', None)
    fn_rows = cfg.get('fn_rows', count_session_rows)
    now = time.time()
    lanes = parse_lanes_file(lanes_file)
    state = load_state(state_file)
    state.setdefault('landed', [])
    state.setdefault('audits', {})
    state.setdefault('notified_fail', {})
    state.setdefault('conflicts', {})
    state.setdefault('conflict_notified', {})
    state.setdefault('hollow_reaudit', {})
    state.setdefault('gate_hold', {})

    def _noaudit(lane, clone_abs, branch, status, ver_mtime, ret, ret_mtime, after_ok):
        if not (status == 'PASS' and ver_mtime and after_ok):
            return (False, '')
        try:
            _t = get_tip_time(clone_abs, branch)
        except Exception:
            return (False, '')
        if _t <= ver_mtime:
            return (False, '')
        try:
            _rd = return_is_done(ret)
        except Exception:
            return (False, '')
        if not (_rd and ret_mtime):
            return (False, '')
        _cf = ((state.get('conflicts') or {}).get(lane) or {}).get('files')
        try:
            return noaudit_merge_ok(clone_abs, branch, ver_mtime, _cf)
        except Exception:
            return (False, '')
    try:
        with open(template_file, encoding='utf-8') as f:
            template = f.read()
    except Exception:
        template = 'NEVER call the question tool. LANE FXWATCH clone X branch Y.'
    events = []
    try:
        cap_now = audit_cap()
    except Exception:
        cap_now = 6
    # 60s repost check first (rebuild order from template each time)
    for lane, info in list((state.get('audits') or {}).items()):
        if not isinstance(info, dict):
            continue
        if info.get('repost_checked'):
            continue
        sid = info.get('sid')
        start = info.get('start', 0)
        if sid and now - start > 60:
            n = fn_rows(sid)
            if n == 0:
                order_file = info.get('order_file', '')
                if order_file:
                    try:
                        for _it in lanes:
                            if _it['lane'] == lane:
                                _p = lane_paths(lane, _it.get('clone', ''), root)
                                atomic_write_text(order_file, build_order(template, lane, _p['clone'], _it.get('branch', '')))
                                break
                    except Exception:
                        pass
                    if os.path.exists(order_file):
                        fn_post(order_file, sid)
                        events.append('AUDIT-REPOST %s' % lane)
                        log_event('AUDIT-REPOST %s %s' % (lane, sid), log_file)
            info['repost_checked'] = True
    # per lane
    merges_done = 0
    for item in lanes:
        lane = item['lane']
        if lane in (state.get('landed') or []):
            continue
        after = item.get('after', '-')
        clone_rel = item['clone']
        branch = item['branch']
        coder_sid = item.get('session', '')
        paths = lane_paths(lane, clone_rel, root)
        clone_abs = paths['clone']
        ret = paths['return']
        ver = paths['verdict']
        # b: FAIL newer than return -> notify coder once
        try:
            ver_mtime = os.path.getmtime(ver)
        except Exception:
            ver_mtime = 0
        try:
            ret_mtime = os.path.getmtime(ret)
        except Exception:
            ret_mtime = 0
        status = verdict_status(ver) if ver_mtime else None
        try:
            tip_time = get_tip_time(clone_abs, branch)
        except Exception:
            tip_time = 0
        try:
            _hollow = bool(ver_mtime and is_hollow_fail(ver))
        except Exception:
            _hollow = False
        if status == 'FAIL' and ver_mtime > ret_mtime and ver_mtime > tip_time and not _hollow:
            if (state.get('notified_fail') or {}).get(lane) != ver_mtime:
                msg_text = ('NEVER call the question tool. Fresh audit FAIL: read %s. '
                            'Fix every item, commit per item, no stopping, append to PAIR-RETURN, end with DONE.' % ver)
                msg_file = os.path.join(run_dir, 'train_fail_%s_%d.txt' % (lane, int(ver_mtime)))
                atomic_write_text(msg_file, msg_text)
                fn_post(msg_file, coder_sid)
                state.setdefault('notified_fail', {})[lane] = ver_mtime
                events.append('NOTIFIED-FAIL %s' % lane)
                log_event('NOTIFIED-FAIL %s %s' % (lane, ver), log_file)
        # a: RETURN DONE newer than VERDICT, tree clean -> start auditor
        try:
            ret_done = return_is_done(ret)
        except Exception:
            ret_done = False
        verdict_exists = ver_mtime > 0
        if ret_done and (not verdict_exists or ret_mtime > ver_mtime):
            try:
                branch_now = current_branch(clone_abs)
            except Exception:
                branch_now = ''
            clean = False
            try:
                clean = is_tree_clean(clone_abs)
            except Exception:
                clean = False
            prev = (state.get('audits') or {}).get(lane) or {}
            after_ok_a = (after == '-' or after in (state.get('landed') or []))
            _na, _ = _noaudit(lane, clone_abs, branch, status, ver_mtime, ret, ret_mtime, after_ok_a)
            if clean and prev.get('return_mtime') != ret_mtime and not _na:
                if pending_audits(state, lanes, root, now, cfg.get('db_path'), cfg.get('fn_live')) < cap_now:
                    order_text = build_order(template, lane, clone_abs, branch)
                    order_file = os.path.join(run_dir, 'audit_%s.txt' % lane)
                    atomic_write_text(order_file, order_text)
                    sid = fn_start('Audit %s' % lane, order_file)
                    if sid:
                        state.setdefault('audits', {})[lane] = {
                            'return_mtime': ret_mtime, 'sid': sid,
                            'start': now, 'repost_checked': False,
                            'order_file': order_file}
                        events.append('AUDIT-STARTED %s' % lane)
                        log_event('AUDIT-STARTED %s %s' % (lane, sid), log_file)
        # unparseable fresh verdict -> ask the audit session for an exact last line once;
        # silent 3 min with no verdict change and a dead session -> start a new auditor
        if ver_mtime and status is None and not (lane in (state.get('landed') or [])):
            _aud = (state.get('audits') or {}).get(lane) or {}
            _asid = _aud.get('sid', '')
            _astart = _aud.get('start', 0)
            if _asid and ver_mtime > _astart:
                _clar = (state.get('clarified') or {}).get(lane) or {}
                if _clar.get('verdict_mtime') != ver_mtime:
                    _ctext = ('Append one last line, exactly: VERDICT %s PASS or VERDICT %s FAIL <names>.' % (lane, lane))
                    _cfile = os.path.join(run_dir, 'train_clarify_%s_%d.txt' % (lane, int(ver_mtime)))
                    atomic_write_text(_cfile, _ctext)
                    try:
                        _cok = fn_post(_cfile, _asid)
                    except Exception:
                        _cok = False
                    if _cok:
                        state.setdefault('clarified', {})[lane] = {'verdict_mtime': ver_mtime, 'posted_at': now}
                        events.append('NUDGE clarify %s' % lane)
                        log_event('NUDGE clarify %s %s' % (lane, _asid), log_file)
                elif now - float(_clar.get('posted_at', 0)) > 180:
                    try:
                        _live = fn_live(_asid) if (fn_live := cfg.get('fn_live')) else session_is_live(_asid, now, cfg.get('db_path'))
                    except Exception:
                        _live = False
                    if not _live:
                        _order = build_order(template, lane, clone_abs, branch)
                        _ofile = os.path.join(run_dir, 'audit_%s.txt' % lane)
                        atomic_write_text(_ofile, _order)
                        _nsid = fn_start('Audit %s' % lane, _ofile)
                        if _nsid:
                            state.setdefault('audits', {})[lane] = {
                                'return_mtime': ret_mtime, 'sid': _nsid,
                                'start': now, 'repost_checked': False,
                                'order_file': _ofile}
                            try:
                                del state['clarified'][lane]
                            except KeyError:
                                pass
                            events.append('AUDIT-STARTED %s' % lane)
                            log_event('AUDIT-STARTED %s %s' % (lane, _nsid), log_file)
        # hollow guard-era verdict (explicit no-runs, never a real FAIL): run one real
        # audit on the standing DONE return (tree dirt does not block: the point is
        # to run the never-run tests; dirt is reported, not blocking). No coder notice.
        if ver_mtime and _hollow and status in ('FAIL', None) and not (lane in (state.get('landed') or [])):
            _ha = (state.get('audits') or {}).get(lane) or {}
            if (not _ha or _ha.get('start', 0) < ver_mtime) and (state.get('hollow_reaudit') or {}).get(lane) != ver_mtime:
                _hrd = False
                try:
                    _hrd = return_is_done(ret)
                except Exception:
                    pass
                if _hrd and pending_audits(state, lanes, root, now, cfg.get('db_path'), cfg.get('fn_live')) < cap_now:
                    _ho = build_order(template, lane, clone_abs, branch)
                    _hof = os.path.join(run_dir, 'audit_%s.txt' % lane)
                    atomic_write_text(_hof, _ho)
                    _hsid = fn_start('Audit %s' % lane, _hof)
                    if _hsid:
                        state.setdefault('audits', {})[lane] = {
                            'return_mtime': ret_mtime, 'sid': _hsid,
                            'start': now, 'repost_checked': False,
                            'order_file': _hof}
                        state.setdefault('hollow_reaudit', {})[lane] = ver_mtime
                        events.append('AUDIT-STARTED %s' % lane)
                        log_event('AUDIT-STARTED %s %s' % (lane, _hsid), log_file)
        # c: PASS verdict -> merge. Normal: verdict newer than tip. Fast: tip is only
        # one merge of int newer than the verdict (no new audit, recipe still gates).
        if status == 'PASS' and ver_mtime:
            try:
                tip = get_tip_time(clone_abs, branch)
            except Exception:
                tip = 0
            after_ok = (after == '-' or after in (state.get('landed') or []))
            normal = after_ok and ver_mtime > tip and merges_done == 0
            noaudit, noaudit_reason = False, ''
            if after_ok and not normal and merges_done == 0 and tip > ver_mtime:
                noaudit, noaudit_reason = _noaudit(lane, clone_abs, branch, status,
                                                   ver_mtime, ret, ret_mtime, after_ok)
            if (normal or noaudit) and merges_done == 0:
                tip_hash = lane_tip_hash(clone_abs, branch)
                head_hash = int_head_hash(app, train)
                tried = (state.get('merge_tried') or {}).get(lane) or {}
                if tried.get('tip') == tip_hash and tried.get('int') == head_hash:
                    continue  # same lane tip + int pair already tried+logged; retry on movement
                try:
                    _grev = int_head_for_gate(app)
                except Exception:
                    _grev = ''
                _gstatus, _gsections, _gids = read_gate_report(run_dir, _grev) if _grev else ('absent', [], [])
                _gated_off = False
                if _gstatus == 'FAIL' and gate_hold_enabled(run_dir):
                    if (state.get('gate_hold') or {}).get(_grev) != 'notified':
                        state.setdefault('gate_hold', {})[_grev] = 'notified'
                        _gdetail = (_gsections + _gids)[:14]
                        log_event('GATE-HOLD %s %s' % (_grev, _gdetail), log_file)
                        try:
                            append_train_line('- %s TRAIN GATE-HOLD %s %s - landings held, audits continue.' % (utc_now(), _grev, _gdetail))
                        except Exception:
                            pass
                        events.append('GATE-HOLD %s' % _grev)
                    continue
                elif _gstatus == 'FAIL':
                    _gated_off = True
                elif _gstatus == 'PASS':
                    try:
                        (state.get('gate_hold') or {}).pop(_grev, None)
                    except Exception:
                        pass
                if fn_merge is not None:
                    res = fn_merge(lane, clone_rel, branch, ver)
                else:
                    res = run_merge_recipe(lane, clone_rel, branch, ver, root, train,
                                           app, log_file, records_jsonl, allowed_file)
                if not (isinstance(res, dict) and 'wait_timeout' in res):
                    state.setdefault('merge_tried', {})[lane] = {'tip': tip_hash, 'int': head_hash}
                if isinstance(res, tuple):
                    state.setdefault('landed', []).append(lane)
                    # mark verdict seen for pending audit
                    if lane in (state.get('audits') or {}):
                        state['audits'][lane]['verdict_seen'] = True
                    events.append('LANDED %s' % lane)
                    if noaudit:
                        events.append('NOAUDIT-MERGE %s' % lane)
                        log_event('NOAUDIT-MERGE %s %s' % (lane, noaudit_reason), log_file)
                    if _gated_off:
                        events.append('HOLD-OFF-LAND %s' % lane)
                        log_event('HOLD-OFF-LAND %s %s' % (lane, _grev), log_file)
                    merges_done += 1
                elif isinstance(res, dict) and 'wait_timeout' in res:
                    events.append('MERGE-ATTEMPTED %s' % lane)
                elif isinstance(res, dict) and 'new_red' in res:
                    _names = [str(x) for x in (res.get('new_red') or []) if str(x).strip()]
                    _elines = res.get('first_e') or {}
                    _eshow = ['%s: %s' % (n, _elines.get(n, 'no E line')[:160]) for n in _names[:6]]
                    _ntext = ('NEVER call the question tool. New reds on int merge: %s. '
                              'First errors: %s. Fix every item, commit per item, no stopping, '
                              'append to PAIR-RETURN, end with DONE.'
                              % (', '.join(_names[:12]), ' | '.join(_eshow)[:600]))
                    _nfile = os.path.join(run_dir, 'train_newred_%s_%d.txt' % (lane, int(now)))
                    atomic_write_text(_nfile, _ntext)
                    try:
                        _nok = fn_post(_nfile, coder_sid)
                    except Exception:
                        _nok = False
                    if _nok:
                        events.append('NOTIFIED-NEWRED %s' % lane)
                        log_event('NOTIFIED-NEWRED %s %s' % (lane, ', '.join(_names[:6])[:200]), log_file)
                    events.append('MERGE-ATTEMPTED %s' % lane)
                elif isinstance(res, dict) and 'conflict' in res:
                    _cf = [x for x in (res.get('conflict') or []) if str(x).strip()]
                    state.setdefault('conflicts', {})[lane] = {'tip': tip_hash, 'files': _cf}
                    if (state.get('conflict_notified') or {}).get(lane) != tip_hash:
                        _fl = ', '.join(_cf[:12]) + (' +%d more' % (len(_cf) - 12) if len(_cf) > 12 else '')
                        _mtext = ('NEVER call the question tool. Merge conflict in %s: '
                                  'merge int (origin/int in a full clone, int in a linked worktree), '
                                  "keep BOTH sides' behaviour, your suites + golden, commit, "
                                  'last line of PAIR-RETURN exactly DONE.' % _fl)
                        _mfile = os.path.join(run_dir, 'train_conflict_%s_%d.txt' % (lane, int(now)))
                        atomic_write_text(_mfile, _mtext)
                        try:
                            _pok = fn_post(_mfile, coder_sid)
                        except Exception:
                            _pok = False
                        if _pok:
                            state.setdefault('conflict_notified', {})[lane] = tip_hash
                            events.append('NOTIFIED-CONFLICT %s' % lane)
                            log_event('NOTIFIED-CONFLICT %s %s' % (lane, _fl[:200]), log_file)
                    events.append('MERGE-ATTEMPTED %s' % lane)
                elif isinstance(res, dict) and 'stray' in res:
                    _sf = [str(x) for x in (res.get('stray') or []) if str(x).strip()]
                    _stext = ('NEVER call the question tool. Stray files added by your lane: %s. '
                              'Remove them from the branch, commit, '
                              'last line of PAIR-RETURN exactly DONE.' % ', '.join(_sf[:12]))
                    _sfile = os.path.join(run_dir, 'train_stray_%s_%d.txt' % (lane, int(now)))
                    atomic_write_text(_sfile, _stext)
                    try:
                        _sok = fn_post(_sfile, coder_sid)
                    except Exception:
                        _sok = False
                    if _sok:
                        events.append('NOTIFIED-STRAY %s' % lane)
                        log_event('NOTIFIED-STRAY %s %s' % (lane, ', '.join(_sf[:12])[:200]), log_file)
                    events.append('MERGE-ATTEMPTED %s' % lane)
                else:
                    events.append('MERGE-ATTEMPTED %s' % lane)
    # STALL NUDGE (owner order): coder idle + no fresh DONE; audit idle + no VERDICT; WATCH table; HD tick.
    try:
        fn_session = cfg.get('fn_session', None)
        db_path = cfg.get('db_path', None)

        def _idle(sid):
            if fn_session is not None:
                try:
                    return fn_session(sid)
                except Exception:
                    pass
            return session_idle_info(sid, db_path)

        state.setdefault('nudges', {})
        state.setdefault('nudge_count', {})
        state.setdefault('stall_logged', [])

        def _can(sid):
            lst = (state.get('nudges') or {}).get(sid) or []
            if not lst:
                return True
            try:
                return (now - float(lst[-1])) >= NUDGE_MIN_SEC
            except Exception:
                return True

        def _record(sid, key, label):
            state.setdefault('nudges', {}).setdefault(sid, []).append(now)
            state.setdefault('nudge_count', {})[key] = int(state['nudge_count'].get(key, 0)) + 1
            log_event('NUDGE %s' % label, log_file)
            events.append('NUDGE %s' % label)
            if int(state['nudge_count'].get(key, 0)) >= 3 and label not in (state.get('stall_logged') or []):
                state.setdefault('stall_logged', []).append(label)
                log_event('STALL %s' % label, log_file)
                events.append('STALL %s' % label)

        for item in lanes:
            lane2 = item['lane']
            if lane2 in (state.get('landed') or []):
                continue
            coder_sid = item.get('session', '')
            if not coder_sid:
                continue
            p2 = lane_paths(lane2, item.get('clone', ''), root)
            try:
                done2 = return_is_done(p2['return'])
            except Exception:
                done2 = False
            if done2:
                continue
            try:
                has_run, last_sec = _idle(coder_sid)
            except Exception:
                has_run, last_sec = (False, 0.0)
            try:
                if has_run or session_is_live(coder_sid, now, db_path):
                    continue
            except Exception:
                if has_run:
                    continue
            if last_sec and (now - last_sec) < STALL_IDLE_SEC:
                continue
            if not _can(coder_sid):
                continue
            msg_file = os.path.join(run_dir, 'train_nudge_%s_%d.txt' % (lane2, int(now)))
            atomic_write_text(msg_file, STALL_MSG)
            try:
                ok = fn_post(msg_file, coder_sid)
            except Exception:
                ok = False
            if ok:
                _record(coder_sid, lane2, lane2)
        for lane3, info3 in list((state.get('audits') or {}).items()):
            if not isinstance(info3, dict):
                continue
            if lane3 in (state.get('landed') or []):
                continue
            p3 = lane_paths(lane3, '', root)
            for it3 in lanes:
                if it3['lane'] == lane3:
                    p3 = lane_paths(lane3, it3.get('clone', ''), root)
                    break
            try:
                if os.path.exists(p3['verdict']):
                    continue
            except Exception:
                pass
            sid3 = info3.get('sid', '')
            order3 = info3.get('order_file', '')
            if not sid3 or not order3:
                continue
            branch3 = ''
            for it3b in lanes:
                if it3b['lane'] == lane3:
                    branch3 = it3b.get('branch', '')
                    break
            try:
                atomic_write_text(order3, build_order(template, lane3, p3['clone'], branch3))
            except Exception:
                pass
            if not os.path.exists(order3):
                continue
            try:
                has_run3, last3 = _idle(sid3)
            except Exception:
                has_run3, last3 = (False, 0.0)
            try:
                if has_run3 or session_is_live(sid3, now, db_path):
                    continue
            except Exception:
                if has_run3:
                    continue
            if last3 and (now - last3) < STALL_IDLE_SEC:
                continue
            if not _can(sid3):
                continue
            try:
                ok3 = fn_post(order3, sid3)
            except Exception:
                ok3 = False
            if ok3:
                _record(sid3, 'audit:' + lane3, 'audit ' + lane3)
        try:
            watch_file = cfg.get('watch_file', os.path.join(run_dir, 'TRAIN_WATCH.txt'))
            for w in parse_watch_file(watch_file):
                try:
                    if os.path.exists(w['done_file']):
                        continue
                except Exception:
                    pass
                sidw = w.get('session', '')
                if not sidw:
                    continue
                try:
                    has_runw, lastw = _idle(sidw)
                except Exception:
                    has_runw, lastw = (False, 0.0)
                try:
                    if has_runw or session_is_live(sidw, now, db_path):
                        continue
                except Exception:
                    if has_runw:
                        continue
                if lastw and (now - lastw) < STALL_IDLE_SEC:
                    continue
                if not _can(sidw):
                    continue
                msgw = os.path.join(run_dir, 'train_nudge_watch_%s_%d.txt' % (re.sub(r'[^A-Za-z0-9]+', '_', w['title']), int(now)))
                atomic_write_text(msgw, STALL_MSG)
                try:
                    okw = fn_post(msgw, sidw)
                except Exception:
                    okw = False
                if okw:
                    _record(sidw, 'watch:' + w['title'], 'WATCH ' + w['title'])
        except Exception:
            pass
        try:
            has_runh, lasth = _idle(HD_SESSION)
            try:
                hd_live = bool(has_runh or session_is_live(HD_SESSION, now, db_path))
            except Exception:
                hd_live = bool(has_runh)
            if not hd_live and (not lasth or (now - lasth) >= HD_IDLE_SEC) and _can(HD_SESSION):
                msgh = os.path.join(run_dir, 'train_nudge_HD_%d.txt' % int(now))
                atomic_write_text(msgh, HD_TICK_MSG)
                try:
                    okh = fn_post(msgh, HD_SESSION)
                except Exception:
                    okh = False
                if okh:
                    _record(HD_SESSION, 'HD', 'HD')
        except Exception:
            pass
    except Exception as _e:
        try:
            log_event('NUDGE-ERROR %s' % str(_e)[:160], log_file)
        except Exception:
            pass
    save_state_atomic(state_file, state)
    return events


def _pid_alive(pid):
    try:
        pid = int(pid)
    except Exception:
        return False
    if pid <= 0:
        return False
    try:
        if os.name == 'nt':
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x100000, False, pid)
            if not h:
                return False
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--loop', type=int, default=30)
    ap.add_argument('--sleep', type=float, default=20.0)
    ap.add_argument('--lanes-file', default=LANES_FILE)
    ap.add_argument('--state-file', default=STATE_FILE)
    ap.add_argument('--log-file', default=LOG_FILE)
    ap.add_argument('--run-dir', default=RUN)
    ap.add_argument('--root', default=ROOT)
    ap.add_argument('--train', default=TRAIN)
    ap.add_argument('--app', default=APP)
    args = ap.parse_args()
    me = os.getpid()
    pidfile = os.path.join(args.run_dir, 'train.pid')
    try:
        with open(pidfile, encoding='utf-8') as f:
            other = int((f.read() or '').strip() or '0')
    except Exception:
        other = 0
    if other and other != me and _pid_alive(other):
        try:
            log_event('REFUSE-DOUBLE-LOOP other=%d' % other, args.log_file)
        except Exception:
            pass
        print('train loop already running as PID %d' % other)
        return 2
    try:
        atomic_write_text(pidfile, str(me) + '\n')
    except Exception:
        pass
    cfg = {'root': args.root, 'run_dir': args.run_dir, 'train': args.train,
           'app': args.app, 'lanes_file': args.lanes_file,
           'state_file': args.state_file, 'log_file': args.log_file}
    for i in range(max(1, args.loop)):
        try:
            process_once(cfg)
        except Exception as e:
            try:
                log_event('LOOP-ERROR %s' % str(e)[:200], args.log_file)
            except Exception:
                pass
        if i + 1 < max(1, args.loop):
            time.sleep(max(0.0, args.sleep))


if __name__ == '__main__':
    main()
