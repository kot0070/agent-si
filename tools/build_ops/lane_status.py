# Development tool for this build, shown as written. Not part of the app.
# Machine paths, server addresses and session ids were replaced by <PLACEHOLDERS>; the logic is unchanged.
"""Lane + people status from the train files and the OpenCode session DB (read-only).

CLI prints the classic table (byte-identical to the old script). The
reading lives in lane_rows()/people_rows() so owner_board.py shares it
instead of copying it (BOARD TRUTH 2026-11-02).
"""
import sqlite3
import os
import time
import re
import subprocess
import json

DB = os.path.expanduser(r'~/.local/share/opencode/opencode.db')
ROOT = r'<BUILD_ROOT>'

OTHERS = [('HD2', '<SESSION_ID>'), ('Train', '<SESSION_ID>'),
          ('Gate', '<SESSION_ID>'), ('Incident', '<SESSION_ID>'),
          ('DocRestore', '<SESSION_ID>'), ('S6', '<SESSION_ID>'),
          ('Walk', '<SESSION_ID>'), ('Class', '<SESSION_ID>')]


def _connect(db=None):
    return sqlite3.connect('file:%s?mode=ro' % (db or DB), uri=True, timeout=5)


def age_of(con, now_ms, sid):
    """(idle_min, last_type4, last_tool) for one session; (huge, '-', '') when unknown."""
    try:
        r = con.execute("select max(time_updated),count(*) from session_message where session_id=?", (sid,)).fetchone()
        last = con.execute("select type,data from session_message where session_id=? order by seq desc limit 1", (sid,)).fetchone()
    except Exception:
        return 10 ** 9, '-', ''
    k = ''
    if last:
        try:
            for p in (json.loads(last[1]).get('content') or [])[::-1]:
                if p.get('type') == 'tool':
                    k = p.get('name', '') + ':' + p.get('state', {}).get('status', '')
                    break
                if p.get('type') == 'text':
                    k = 'txt:' + p.get('text', '')[-40:].replace('\n', ' ')
                    break
        except Exception:
            pass
    return int((now_ms - (r[0] or 0)) / 60000), last[0][:4] if last else '-', k


def _git(d, *x):
    return subprocess.run(['git', '-c', 'safe.directory=*', '-C', d, *x], capture_output=True, text=True, encoding='utf-8',
                          errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout.strip()


def _lane_files(d, lane):
    rp = os.path.join(d, '_task', lane, 'PAIR-RETURN.md')
    vp = os.path.join(d, '_task', lane, 'VERDICT.md')
    ret = ''
    if os.path.exists(rp):
        t = open(rp, encoding='utf-8', errors='replace').read().rstrip()
        ret = time.strftime('%H:%M', time.localtime(os.path.getmtime(rp))) + ('D' if t.endswith('DONE') else '')
    ver, ver_mtime = '', None
    if os.path.exists(vp):
        t = open(vp, encoding='utf-8', errors='replace').read().rstrip().splitlines()
        ver = time.strftime('%H:%M', time.localtime(os.path.getmtime(vp))) + ' ' + (t[-1][:32] if t else '')
        try:
            ver_mtime = os.path.getmtime(vp)
        except OSError:
            ver_mtime = None
    return ret, ver, ver_mtime


def lane_rows(root=ROOT, db=None, now_ms=None):
    """One dict per TRAIN_LANES.txt lane: lane/cl/br/sid/landed/idle/ltype/ltool/tip/dirty/ret/verdict/verdict_mtime."""
    try:
        con = _connect(db)
    except Exception:
        con = None
    now = now_ms if now_ms is not None else time.time() * 1000
    try:
        st = json.load(open(os.path.join(root, 'DIRECTOR', 'RUN', 'TRAIN_STATE.json'), encoding='utf-8')) \
            if os.path.exists(os.path.join(root, 'DIRECTOR', 'RUN', 'TRAIN_STATE.json')) else {}
    except Exception:
        st = {}
    landed = st.get('landed', [])
    rows = []
    try:
        lines = open(os.path.join(root, 'DIRECTOR', 'RUN', 'TRAIN_LANES.txt'), encoding='utf-8')
    except OSError:
        if con is not None:
            try:
                con.close()
            except Exception:
                pass
        return rows
    with lines:
        for ln in lines:
            p = [x.strip() for x in ln.split('|')]
            if len(p) < 4 or not p[3].startswith('ses_'):
                continue
            lane, cl, br, sid = p[:4]
            d = os.path.join(root, cl)
            a = age_of(con, now, sid) if con is not None else (10 ** 9, '-', '')
            try:
                tip = _git(d, 'log', '-1', '--format=%h %cd', '--date=format:%H:%M', br) or \
                    _git(d, 'log', '-1', '--format=%h %cd', '--date=format:%H:%M')
                dirty = len(_git(d, 'status', '--porcelain').splitlines())
            except Exception:
                tip, dirty = '', 0
            ret, ver, ver_mtime = _lane_files(d, lane)
            rows.append({"lane": lane, "cl": cl, "br": br, "sid": sid, "landed": lane in landed,
                         "idle": a[0], "ltype": a[1], "ltool": a[2], "tip": tip, "dirty": dirty,
                         "ret": ret, "verdict": ver, "verdict_mtime": ver_mtime})
    if con is not None:
        try:
            con.close()
        except Exception:
            pass
    return rows


def people_rows(specs=None, db=None, now_ms=None):
    """[(tag, idle_min, last_type4, last_tool)] for named sessions (HD2 etc.)."""
    try:
        con = _connect(db)
    except Exception:
        return [(t, 10 ** 9, '-', '') for t, _s in (specs or OTHERS)]
    now = now_ms if now_ms is not None else time.time() * 1000
    out = [(t,) + age_of(con, now, sid) for t, sid in (specs or OTHERS)]
    try:
        con.close()
    except Exception:
        pass
    return out


def sub_count(parent_sid, db=None):
    """Running sub-sessions of a parent (session_v2.parent_id, not suspended); -1 when the DB cannot be read."""
    try:
        con = _connect(db)
    except Exception:
        return -1
    try:
        n = con.execute("select count(*) from session_v2 where parent_id=? and time_suspended is null", (parent_sid,)).fetchone()
        return int(n[0])
    except Exception:
        return -1
    finally:
        try:
            con.close()
        except Exception:
            pass


def main():
    rows = lane_rows()
    print('LANE      land idle type last                                      commit dirty ret verdict')
    for r in rows:
        print(f"{r['lane']:9} {'Y' if r['landed'] else '-':4} {r['idle']:4} {r['ltype']:4} {r['ltool'][:40]:40} "
              f"{r['tip'][:13]:13} {r['dirty']:3} {r['ret']:7} {r['verdict']}")
    print('--- others')
    for t, idle, lt, k in people_rows():
        print(f"{t:10} idle {idle:4} {lt:4} {k[:70]}")


if __name__ == '__main__':
    main()
