#!/usr/bin/env python3
# Development tool for this build, shown as written. Not part of the app.
# Machine paths, server addresses and session ids were replaced by <PLACEHOLDERS>; the logic is unchanged.
"""INT GATE: owner's order - after merges test by CODE first, before any build.
G1 commits lost? G2 code hit? G3 function. G4 from source. G5 coverage.
Usage: int_gate.py [--fast|--full] [--rev HASH] [--watch]
No model calls. Output short: one line per check + names of reds only.
"""
import argparse
import concurrent.futures
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

WS = pathlib.Path(r"<BUILD_ROOT>")
APP = WS / "APP"
GATE = WS / "WT" / "GATE"
DIRECTOR = WS / "DIRECTOR"
RUN = DIRECTOR / "RUN"
TOOLS = DIRECTOR / "TOOLS"
RC5 = "3762273d9cf458330b308ab639d0bb8bcd05cd53"
LANES_FIXED = ["FXCOPY","FXHYGIENE","FXPROVCHIPS","FXTELEM","FXR1B","FXR2B","FXR2C",
  "FXDOCSEND","FXR4B","FXR4A","FXR3B","FXDOCSTXT","FXSHIPFIX","FXRESP","FXCTX","FXWIN","FXSPEED"]
TOOL_PY = r"<PYTHON313_EXE>"
VENV_PY = r"<VENV_PYTHON_EXE>"
GOLDEN = "tests/test_golden_user_path.py"


# One exact superseded commit (exact full hash, no glob, no lane-wide rule,
# no prefix match): a71194e is a one-line re-indent of the old JSX comment
# form and must never merge; int keeps the same note as // (tsc-safe,
# written by FXHOTJSX 2065fc4). G1 notes it `superseded`; G2 skips exactly
# the old line for that lane at that path, only while the new line is in int.
SUPERSEDED = {
    "a71194ed41bb1d066fc6650fa624997a3820d716": {
        "lane": "FXBTN",
        "path": "frontend/src/settings/ProvidersPage/LeftoverFinder.tsx",
        "old": "{/* FXBTN: one spaced action row; cancel reads quiet. */}",
        "new": "// FXBTN: one spaced action row; cancel reads quiet.",
        "reason": "one-line re-indent of the JSX comment form; int keeps the // form (tsc); must never merge",
    },
}


def _is_superseded_line(lane, path, stripped_line, int_rev="int"):
    """True only for the exact SUPERSEDED old line, lane and path, and only
    while the new line is present in int at that path."""
    for h, e in SUPERSEDED.items():
        if lane == e["lane"] and path == e["path"] and stripped_line == e["old"]:
            rc, blob = git(["show", "%s:%s" % (int_rev, path)], timeout=60)
            if rc == 0 and e["new"] in [l.strip() for l in blob.splitlines()]:
                return True
    return False
ROOT_ALLOW = frozenset([".gitattributes", ".gitignore", "HACKATHON_CONTRIBUTIONS.md",
  "LICENSE", "LINT.md", "README.md", "app-config.example.json", "env.example",
  "mypy.ini", "pyproject.toml", "pytest.ini", "ruff.toml"])

def _hidden():
    # Windows: no console windows for any child (git, pwsh, pytest, node);
    # pytest children then share the hidden console instead of popping their own.
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


# Windowless browser sink. webbrowser.open() (sidecar.py:331) walks _tryorder
# and falls through to real Chrome unless the first entry returns True:
# GenericBrowser returns (exit == 0), BackgroundBrowser (still running).
# A bare exe exits nonzero on a URL arg -> fallthrough -> Chrome. So the sink
# must exit 0: BROWSER carries %s so get() shlex-splits it into
# GenericBrowser([pythonw, -c, pass, url]); pythonw runs "pass", exits 0,
# returns True, has no console by construction. Never Chrome, never a window.
NOOP_BROWSER = "<VENV_PYTHONW_EXE> -c pass %s"


def test_env(extra=None):
    # src on the path for every gate child: backend/* tests do not self-insert
    # src the way APP/tests do (P2-G4 class of bug: bare probe/pool runs).
    e = {"AGENT_SI_SECRET_STORE": "memory", "BROWSER": NOOP_BROWSER,
         "PYTHONPATH": str(GATE / "src")}
    if extra:
        e.update(extra)
    return e


def run(cmd, cwd, timeout=120, env=None, shell=False):
    e = dict(os.environ)
    if env:
        e.update(env)
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           shell=shell, env=e, **_hidden())
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as ex:
        out = ""
        try:
            out = (ex.stdout or b"").decode("utf-8", "replace") if isinstance(ex.stdout, bytes) else str(ex.stdout or "")
        except Exception:
            pass
        return 124, "TIMEOUT " + out

def git(args, cwd=APP, timeout=120):
    return run(["git"] + args, cwd, timeout=timeout)

def int_hash():
    rc, out = git(["rev-parse", "int"])
    return out.strip().split()[0] if rc == 0 and out.strip() else ""

def merged_lane_set(int_rev):
    base = RC5
    try:
        rc, out = git(["log", "%s..%s" % (base, int_rev), "--merges", "--format=%s"])
    except Exception:
        return set()
    found = set()
    if rc == 0:
        for ln in out.splitlines():
            m = re.search(r"pkg/([A-Za-z0-9_]+)", ln)
            if m:
                found.add(m.group(1).strip())
    return found

def load_lanes():
    lanes = list(LANES_FIXED)
    f = RUN / "TRAIN_LANES.txt"
    if f.is_file():
        try:
            for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
                s = ln.strip()
                if not s or s.startswith("#"):
                    continue
                lane = s.split("|")[0].strip().split()[0]
                # allow forms like pkg/FXR1B -> FXR1B
                if "/" in lane:
                    lane = lane.split("/")[-1].strip()
                if lane and lane not in lanes:
                    lanes.append(lane)
        except OSError:
            pass
    return lanes

def lane_branch(lane):
    for cand in ["pkg/%s" % lane, "origin/pkg/%s" % lane]:
        rc, _ = git(["rev-parse", "--verify", cand])
        if rc == 0:
            return cand
    # case-insensitive fallback
    rc, out = git(["branch", "-a", "--list", "*%s*" % lane])
    if rc == 0:
        for ln in out.splitlines():
            s = ln.strip().lstrip("* ").strip()
            if s.endswith(lane) and ("pkg/" in s or lane in s):
                return s.replace("remotes/", "")
    return None

def golden_allowed():
    f = RUN / "GOLDEN_ALLOWED.txt"
    nums = set()
    if f.is_file():
        for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
            s = ln.strip()
            m = re.search(r"(\d+)", s)
            if m:
                nums.add(m.group(1).zfill(2))
    return nums  # e.g. {"02","10"}

def marker_rows(grep_out):
    return [l.strip()[:160] for l in grep_out.splitlines() if l.strip()]


def reds_group(first_e):
    """Group key for one failure line: same root cause reads as one group."""
    s = (first_e or "").strip()[:200]
    s = re.sub(r"[A-Za-z]:[\\/]\S+", "<PATH>", s)
    s = re.sub(r"[\w\-.\\/]+?\.(py|tsx|ts|js|json|md)", "<FILE>", s)
    s = re.sub(r"\d+", "#", s)
    return s


def reds_table(rows):
    """rows: [(id, first_e)]. Markdown table, biggest group first."""
    groups = {}
    order = []
    for rid, fe in rows:
        gg = reds_group(fe)
        if gg not in groups:
            groups[gg] = []
            order.append(gg)
        groups[gg].append((rid, (fe or "").strip()[:200]))
    ranked = sorted(order, key=lambda gg: -len(groups[gg]))
    out = ["| id | group | first E |", "|---|---|---|"]
    for gg in ranked:
        for rid, fe in groups[gg]:
            out.append("| %s | %s | %s |" % (rid.replace("|", "/"),
                                             gg.replace("|", "/"),
                                             fe.replace("|", "/")))
    return "\n".join(out)


def root_strays(names):
    return sorted({s for s in (n.strip() for n in names)
                   if s and "/" not in s and s not in ROOT_ALLOW})


# ---------- G1 ----------
def g1(int_rev):
    lost = []
    notes = []
    merged = merged_lane_set(int_rev)
    for lane in load_lanes():
        br = lane_branch(lane)
        if not br:
            if lane in merged:
                lost.append("LOST-LANE-NOBRANCH %s" % lane)
            else:
                notes.append("parked, not in this build: %s" % lane)
            continue
        if lane not in merged and lane not in LANES_FIXED:
            notes.append("parked, not in this build: %s (no merge into int)" % lane)
            continue
        rc, mb = git(["merge-base", "int", br])
        mb = mb.strip().split()[0] if rc == 0 else ""
        if not mb:
            continue
        rc, out = git(["log", "--no-merges", "--format=%H %s", "%s..%s" % (mb, br)])
        commits = [l for l in out.splitlines() if l.strip()] if rc == 0 else []
        if not commits:
            continue
        rc2, chout = git(["cherry", "int", br])
        patch_present = set()
        if rc2 == 0:
            for ln in chout.splitlines():
                ln = ln.strip()
                if ln.startswith("-"):
                    parts = ln.split()
                    if len(parts) >= 2:
                        patch_present.add(parts[1])
        for cl in commits:
            h, _, subj = cl.partition(" ")
            h = h.strip()
            rc3, _ = git(["merge-base", "--is-ancestor", h, "int"])
            if rc3 == 0:
                continue
            if h in SUPERSEDED and lane == SUPERSEDED[h]["lane"]:
                notes.append("superseded %s %s" % (lane, h[:12]))
                continue
            if h in patch_present:
                notes.append("%s %s patch-in" % (lane, h[:8]))
                continue
            lost.append("LOST %s %s %s" % (lane, h[:12], subj[:100]))
    # FXSPEED S3-only + FXR1A/FXLOOP shared-commit note (informational)
    notes.append("note FXSPEED-merged-S3-only patch-id decides, not hash")
    notes.append("note FXR1A+FXLOOP shared commits: patch-in is not a loss")
    ok = (len(lost) == 0)
    return ok, lost, notes

# ---------- G2 ----------
def g2(int_rev):
    hits = []
    problems = []
    merged = merged_lane_set(int_rev)
    for lane in load_lanes():
        br = lane_branch(lane)
        if not br:
            continue
        if lane not in merged and lane not in LANES_FIXED:
            continue
        rc, mb = git(["merge-base", "int", br])
        mb = mb.strip().split()[0] if rc == 0 else ""
        if not mb:
            continue
        rc, diff = git(["diff", "-U0", "%s..%s" % (mb, br), "--"], timeout=180)
        if rc != 0:
            continue
        cur = None
        added = []  # (file, line)
        for ln in diff.splitlines():
            if ln.startswith("+++ b/"):
                cur = ln[6:].strip()
            elif ln.startswith("+") and not ln.startswith("+++"):
                t = ln[1:]
                if t.strip() == "":
                    continue
                if cur:
                    added.append((cur, t))
        for (path, line) in added[:4000]:
            s = line.strip()
            if len(s) < 3:
                continue
            if _is_superseded_line(lane, path, s, int_rev):
                continue
            # present at same path in int?
            rc2, blob = git(["show", "int:%s" % path], timeout=60)
            if rc2 == 0 and s in blob:
                continue
            # moved elsewhere?
            rc3, gout = git(["grep", "-F", "--", s, "int", "--"], timeout=120)
            # git grep syntax: git grep -F -e PATTERN int -- ; fix call
            if rc3 != 0:
                rc3, gout = git(["grep", "-F", "-e", s, "int"], timeout=120)
            if rc3 == 0 and gout.strip():
                continue  # moved is fine
            # gone: who removed?
            rc4, lout = git(["log", "--format=%H %s", "-S", s, "--", "int"], timeout=180)
            remover = ""
            if rc4 == 0 and lout.strip():
                remover = lout.splitlines()[0][:120]
            # same-lane rework or OTHER?
            same = False
            rh = remover.split()[0] if remover else ""
            if rh:
                r2, _ = git(["merge-base", "--is-ancestor", rh, br])
                if r2 == 0:
                    same = True
                if lane.lower() in remover.lower():
                    same = True
            is_merge = False
            if rh:
                r3, pout = git(["rev-list", "--parents", "-n", "1", rh])
                if r3 == 0 and len(pout.strip().split()) > 2:
                    is_merge = True
            if same and not is_merge:
                continue  # same-lane rework, not a HIT
            hits.append("HIT %s | %s | %.100s | removed by %s" % (lane, path, s, remover[:100] if remover else "unknown"))
        # test files added by lane must exist in int, none deleted
        rc, anames = git(["diff", "--diff-filter=A", "--name-only", "%s..%s" % (mb, br), "--"], timeout=120)
        if rc == 0:
            for p in anames.splitlines():
                p = p.strip()
                if not p:
                    continue
                low = p.lower()
                is_test = ("tests/" in p.replace("\\", "/") or "test_" in low or low.endswith(".test.ts") or low.endswith(".test.tsx") or "__tests__" in p)
                if not is_test:
                    continue
                rc5, _ = git(["cat-file", "-e", "int:%s" % p])
                if rc5 != 0:
                    problems.append("TEST-GONE %s added file missing in int: %s" % (lane, p))
        rc, dnames = git(["diff", "--diff-filter=D", "--name-only", "%s..%s" % (mb, br), "--"], timeout=120)
        if rc == 0:
            for p in dnames.splitlines():
                p = p.strip()
                if p:
                    problems.append("TEST-DELETED %s deleted by lane-vs-int diff: %s" % (lane, p))
    # conflict markers in int: real markers only, anchored at line start
    # (a fixture string like fxmerge.js:24 holding "<<<<<<< HEAD" is not one)
    rc, mout = git(["grep", "-n", "-E", "^(<<<<<<<|>>>>>>>)( |$)", "int"], timeout=120)
    if rc == 0 and mout.strip():
        rows = marker_rows(mout)
        problems.append("MARKERS %d real conflict markers in int" % len(rows))
        problems.extend(rows[:5])
    # stray files directly at repo root (allow-listed legit names only)
    rc, rootout = git(["ls-tree", "-r", "--name-only", "int"], timeout=120)
    if rc == 0:
        for s in root_strays(rootout.splitlines()):
            problems.append("ROOT-STRAY %s" % s)
    ok = (len(hits) == 0 and len(problems) == 0)
    return ok, hits, problems

# ---------- G3 helpers ----------
def ensure_frontend_deps():
    fe = GATE / "frontend"
    nm = fe / "node_modules"
    if nm.is_dir():
        return True, "deps present"
    lock = fe / "package-lock.json"
    if not lock.is_file():
        return False, "no package-lock"
    rc, out = run(["cmd", "/c", "npm ci --no-audit --no-fund"], fe, timeout=900)
    ok = (GATE / "frontend" / "node_modules").is_dir()
    tail = "\n".join(out.splitlines()[-3:])[:300]
    return ok, tail

def run_golden():
    env = test_env()
    gf = GATE / GOLDEN
    if not gf.is_file():
        return None, "no golden file"
    cmd = [VENV_PY, "-m", "pytest", GOLDEN, "-q", "-p", "no:cacheprovider", "--timeout=120"]
    rc, out = run(cmd, GATE, timeout=900, env=env)
    allowed = golden_allowed()
    reds = []
    for ln in out.splitlines():
        if ln.startswith("FAILED") or "::" in ln and "failed" in ln.lower():
            pass
        m = re.search(r"(FAILED\s+)?(\S+::test_golden_(\d+)[\w]*)", ln)
        if m and ("FAIL" in ln or "failed" in ln.lower() or ln.startswith("FAILED")):
            reds.append(ln.strip()[:200])
    # also parse FAILED lines
    for ln in out.splitlines():
        s = ln.strip()
        if s.startswith("FAILED"):
            if s not in reds:
                reds.append(s[:200])
    # filter allowed
    strict_reds = []
    for r in reds:
        m = re.search(r"golden_(\d+)", r)
        num = m.group(1).zfill(2) if m else ""
        if num and num in allowed:
            continue
        strict_reds.append(r)
    line = out.splitlines()[-1][:200] if out.splitlines() else ""
    ok = (rc == 0) or (len(strict_reds) == 0 and len(reds) > 0)
    # rc!=0 but only allowed reds -> treat as PASS-with-allowed
    detail = "allowed=%s reds=%d strict=%d | %s" % (",".join(sorted(allowed)), len(reds), len(strict_reds), line)
    return (len(strict_reds) == 0), detail + (" || " + " // ".join(reds[:10]) if reds else "")

def is_allowed_golden_red(line):
    m = re.search(r"golden_(\d+)", line)
    num = m.group(1).zfill(2) if m else ""
    return bool(num) and num in golden_allowed()


def _is_collectible_test(path):
    """True when pytest can collect tests from a changed tests/ file.

    Support files (conftest.py, __init__.py, non-test_*.py helpers)
    collect nothing: a bare pytest run exits 5 (no tests ran) and
    reds the gate for a file that cannot fail.
    """
    base = str(path or "").rsplit("/", 1)[-1]
    if base in ("conftest.py", "__init__.py"):
        return False
    return base.startswith("test_") or base.endswith("_test.py")


def _normalize_pytest_rc(rc, failcases):
    """Gate verdict for one pytest file run: exit 5 with no recorded
    failure means nothing ran and nothing failed (support file)."""
    if rc == 5 and not failcases:
        return 0
    return rc


def changed_tests_since(last_hash, cur_hash):
    if not last_hash:
        last_hash = RC5
    rc, out = git(["diff", "--name-only", "%s..%s" % (last_hash, cur_hash), "--", "tests"], timeout=120)
    files = []
    if rc == 0:
        for ln in out.splitlines():
            s = ln.strip()
            if s == GOLDEN:
                continue  # golden covered by the GOLDEN check with GOLDEN_ALLOWED
            if s.endswith(".py") and s.startswith("tests/"):
                if not _is_collectible_test(s):
                    continue
                p = GATE / s
                if p.is_file():
                    files.append(s)
    return files

def last_gate_hash():
    cands = [p for p in RUN.glob("GATE_*.md")
             if re.fullmatch(r"GATE_[0-9a-f]{12}\.md", p.name)]
    if not cands:
        return ""
    cands.sort(key=lambda p: p.stat().st_mtime)
    try:
        txt = cands[-1].read_text(encoding="utf-8", errors="replace")
        m = re.search(r"\bint\s+([0-9a-f]{7,40})\b", txt)
        if m:
            return m.group(1)
        m2 = re.search(r"\b([0-9a-f]{40})\b", txt)
        if m2:
            return m2.group(1)
    except OSError:
        pass
    return ""

def tsc_check():
    fe = GATE / "frontend"
    cmd = ["node", "node_modules/typescript/bin/tsc", "--noEmit", "-p", "."]
    nsrc = 0
    inc = ""
    try:
        cfg = json.loads((fe / "tsconfig.json").read_text(encoding="utf-8", errors="replace"))
        inc = ",".join(cfg.get("include", []) or [])
    except OSError:
        pass
    try:
        src = fe / "src"
        if src.is_dir():
            nsrc = sum(1 for _ in list(src.rglob("*.ts")) + list(src.rglob("*.tsx")))
    except OSError:
        pass
    # negative control proven once 2026-11-02: throwaway copy of this frontend
    # + src/__gate_proof_error__.ts (number = "not-a-number") -> rc=1,
    # "error TS2322: Type 'string' is not assignable to type 'number'".
    rc, out = run(cmd, fe, timeout=600)
    errs = [l.strip()[:200] for l in out.splitlines() if "error" in l.lower()][:10]
    msg = "cmd=node node_modules/typescript/bin/tsc --noEmit -p . rc=%d files=%d include=[%s]" % (rc, nsrc, inc)
    if nsrc == 0 or "src" not in inc:
        return False, msg + " EMPTY-PROJECT-REFUSED (not proof of a whole-project run)"
    if rc != 0:
        return False, msg + " || " + " // ".join(errs)
    return True, msg + " tsc PASS (neg-control 2026-11-02: injected TS2322 -> rc=1)"

def vitest_full():
    fe = GATE / "frontend"
    cmd = ["node", "--preserve-symlinks-main", "node_modules/vitest/vitest.mjs", "run", "--maxWorkers=2"]
    nfiles = 0
    try:
        nfiles = sum(1 for _ in list((fe / "src").rglob("*.test.ts")) + list((fe / "src").rglob("*.test.tsx")))
    except OSError:
        pass
    rc, out = run(cmd, fe, timeout=1200)
    n_f = n_t = 0
    m = re.search(r"Test Files\s+(\d+)\s+passed", out)
    if m:
        n_f = int(m.group(1))
    m = re.search(r"Tests\s+(\d+)\s+passed", out)
    if m:
        n_t = int(m.group(1))
    reds = [l.strip()[:200] for l in out.splitlines() if "FAIL" in l or "failed" in l.lower()][:10]
    failrows = []
    tok = ""
    for ln in out.splitlines():
        s = ln.strip()
        if "❯" in s and ".test." in s:
            parts = s.split()
            tok = parts[1] if len(parts) > 1 else s[:80]
            failrows.append(("FAIL " + tok, s[:200]))
        elif s.startswith("×") and tok:
            failrows.append(("FAIL " + tok, s[:200]))
    msg = ("cmd=node --preserve-symlinks-main node_modules/vitest/vitest.mjs run --maxWorkers=2 "
           "rc=%d testfiles=%d filesPassed=%d testsPassed=%d(expected>900)" % (rc, nfiles, n_f, n_t))
    if rc == 0 and n_t >= 900 and n_f > 0:
        return True, msg, [], failrows
    if rc == 0 and (n_t == 0 or n_f == 0):
        return False, msg + " NOCOUNT (cannot prove the suite ran)", reds, failrows
    if rc == 0:
        return False, msg + " COUNT-LOW", reds, failrows
    return False, msg + " || " + " // ".join(reds), reds, failrows

def vite_build():
    fe = GATE / "frontend"
    cmd = ["node", "node_modules/vite/bin/vite.js", "build"]
    rc, out = run(cmd, fe, timeout=1200)
    dist = fe / "dist"
    nfiles = 0
    has_index = False
    try:
        if dist.is_dir():
            nfiles = sum(1 for _ in dist.rglob("*") if _.is_file())
            has_index = (dist / "index.html").is_file()
    except OSError:
        pass
    msg = ("cmd=node node_modules/vite/bin/vite.js build rc=%d dist_files=%d index=%s" %
           (rc, nfiles, "yes" if has_index else "no"))
    if rc != 0:
        reds = [l.strip()[:200] for l in out.splitlines() if "error" in l.lower()][:5]
        return False, msg + " || " + " // ".join(reds)
    if not has_index or nfiles == 0:
        return False, msg + " EMPTY-DIST-REFUSED (no proof of a real build)"
    tail = out.splitlines()[-1][:200] if out.splitlines() else ""
    return True, msg + " | " + tail

def stub_scan():
    tool = TOOLS / "muse" / "stub_scan.py"
    rc, out = run([VENV_PY, str(tool), "--tree", str(GATE)], GATE, timeout=600)
    rows = [l.strip()[:160] for l in out.splitlines() if l.startswith("STUB") or l.startswith("FAKE") or l.startswith("WIRE")]
    extra = [l.strip()[:200] for l in out.splitlines()
             if l.startswith("FROZEN-REAL") or l.startswith("NO-HASH")]
    msg = ("%d rows" % len(rows) if rows else "clean")
    if extra:
        msg += " // " + " // ".join(extra)
    return rc == 0, (msg, rows)

def list_pytest_files():
    files = sorted((GATE / "tests").glob("test_*.py")) if (GATE / "tests").is_dir() else []
    rel = [p.relative_to(GATE).as_posix() for p in files]
    be = []
    if (GATE / "backend").is_dir():
        for p in sorted((GATE / "backend").rglob("test_*.py")):
            rel.append(p.relative_to(GATE).as_posix())
    return rel

def load_times():
    f = RUN / "GATE_TIMES.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_times(d):
    try:
        (RUN / "GATE_TIMES.json").write_text(json.dumps(d, indent=1), encoding="utf-8")
    except OSError:
        pass


def free_gb():
    """Free RAM in GiB (ctypes, no deps). Pool stops taking files below 6."""
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            return m.ullAvailPhys / (1024 ** 3)
    except Exception:
        pass
    return 99.0


def run_pytest_one(pyfile, tag):
    """One file, one process, own --basetemp. Returns result dict."""
    tmp = GATE / "_task" / "tmp" / ("%s_%s" % (tag, pathlib.Path(pyfile).stem))
    try:
        tmp.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    xml = tmp / "junit.xml"
    cmd = [VENV_PY, "-m", "pytest", pyfile, "-q", "-p", "no:cacheprovider",
           "--timeout=120", "--basetemp", str(tmp), "--junitxml", str(xml)]
    t0 = time.time()
    rc, out = run(cmd, GATE, timeout=600, env=test_env())
    wall = time.time() - t0
    reds = [l.strip()[:220] for l in out.splitlines()
            if (l.strip().startswith("FAILED") or l.strip().startswith("ERROR"))]
    failcases = failcases_of(xml, t0)
    if rc != 0 and not failcases:
        reds.append("NOJUNIT %s" % pyfile)
    rc = _normalize_pytest_rc(rc, failcases)
    tail = out.splitlines()[-1][:200] if out.splitlines() else ""
    return {"file": pyfile, "rc": rc, "wall": wall, "out": out,
            "tail": tail, "reds": reds, "failcases": failcases}


def failcases_of(xml, since_ts):
    """(nodeid, first-E) from a junit xml, only if written after since_ts.

    A crashed/timed-out run leaves the previous run's xml behind; counting it
    would gate RED on a ghost file (R15). Stale or missing xml -> []."""
    try:
        if not (os.path.isfile(str(xml)) and os.path.getmtime(str(xml)) >= since_ts - 5):
            return []
    except OSError:
        return []
    import xml.etree.ElementTree as ET
    try:
        root = ET.parse(str(xml)).getroot()
    except Exception:
        return []
    out = []
    for tc in root.iter("testcase"):
        for bad in list(tc):
            if bad.tag in ("failure", "error"):
                msg = (bad.get("message") or "").strip()
                txt = (bad.text or "").strip().splitlines()
                first = msg or next((l.strip() for l in txt if l.strip()), "")
                out.append((tc.get("classname", "") + "::" + tc.get("name", ""), first))
                break
    return out


def run_pool(files, tag):
    """Pool of 10, one file per process, RAM floor 6 GiB free.
    Returns (results, flaky, still). Rerun result is what counts."""
    results = {}
    pending = list(files)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        futs = {}
        while pending or futs:
            while pending and len(futs) < 10 and free_gb() >= 6.0:
                f = pending.pop(0)
                futs[ex.submit(run_pytest_one, f, tag)] = f
            if not futs:
                time.sleep(5)
                continue
            done, _ = concurrent.futures.wait(
                futs, timeout=10,
                return_when=concurrent.futures.FIRST_COMPLETED)
            for fu in done:
                f = futs.pop(fu)
                try:
                    results[f] = fu.result()
                except Exception as exn:
                    results[f] = {"file": f, "rc": 1, "wall": 0.0,
                                  "out": str(exn)[:300], "tail": "pool error",
                                  "reds": ["POOL-ERR %s" % f], "failcases": []}
    try:
        times = load_times()
        for f, r in results.items():
            times[f] = round(r["wall"], 1)
        save_times(times)
    except Exception:
        pass
    flaky = []
    still = {}
    for f in sorted(f for f, r in results.items() if r["rc"] != 0):
        rr = run_pytest_one(f, tag + "_rerun")
        if rr["rc"] == 0:
            flaky.append("FLAKY %s" % f)
        else:
            first = ""
            for ln in rr["out"].splitlines():
                if "AssertionError" in ln or re.search(r"^\s*assert\b", ln):
                    first = ln.strip()[:200]
                    break
            still[f] = "RED %s %s" % (f, first)
    return results, flaky, still


def affected_since(base, rev):
    """affected_tests.py once per range (zero tokens). Returns (py_tests, warn)."""
    rc, out = git(["diff", "--name-only", "%s..%s" % (base, rev)])
    if rc != 0:
        return [], "diff-failed"
    changed = [l.strip() for l in out.splitlines() if l.strip()]
    if not changed:
        return [], ""
    cmd = [VENV_PY, str(TOOLS / "muse" / "affected_tests.py"), str(GATE)] + changed
    rc, out = run(cmd, GATE, timeout=600, env=test_env())
    if rc != 0:
        return [], "affected-tool-failed"
    tests, warn = [], ""
    for ln in out.splitlines():
        s = ln.strip()
        if s.startswith("WARN"):
            warn = s
        elif s.endswith(".py") and s != GOLDEN:
            p = GATE / s
            if p.is_file():
                tests.append(s)
    return sorted(set(tests)), warn

def pytest_full():
    """Whole python suite through the 10-wide file pool. Same pool as CHANGED.
    Returns (ok, tail, preds, failcases)."""
    files = list_pytest_files()
    times = load_times()
    files = sorted(files, key=lambda f: times.get(f, 30.0), reverse=True)
    results, flaky, still = run_pool(files, "full")
    all_reds = []
    for r in results.values():
        all_reds.extend(r["reds"])
    failcases = []
    for r in results.values():
        failcases.extend(r["failcases"])
    ok = (len(still) == 0)
    tail = ("pool=10 files=%d reds=%d flaky=%d still=%d" %
            (len(results), len(all_reds), len(flaky), len(still)))
    return ok, tail, sorted(still.values()) + flaky + all_reds[:10], failcases

# ---------- G4 ----------
def g4(int_rev):
    # No build, no exe: analyse juror_walk steps for source-mode feasibility + smoke source backend import
    jw = TOOLS / "live_drive" / "juror_walk.py"
    try:
        src = jw.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False, "no juror_walk.py", []
    exe_only = []
    # heuristics: steps needing exe binary, CDP launch, gateway real key, provider model calls
    patterns = [
        ("start_nokey/exe launch", "needs exe binary: SKIP (source has no exe)"),
        ("gateway_start/real key", "needs real-key gateway: SKIP (no real-model calls)"),
        ("W08|W09|W10|W11 keyed/model", "needs provider model: SKIP mock-boundary or skip"),
        ("cdp_up/playwright attach", "needs running window: runnable from source with vite build"),
    ]
    for name, why in patterns:
        if re.search(name, src):
            exe_only.append("SKIP %s: %s" % (name, why))
    # source smoke: vite dist exists? backend import?
    fe_dist = GATE / "frontend" / "dist"
    has_dist = fe_dist.is_dir()
    rc, out = run([VENV_PY, "-c", "import agent_si.backend.app as m; print(hasattr(m,'create_app'))"], GATE, timeout=120,
                  env=test_env({"AGENT_SI_ALLOW_MULTI": "1"}))
    smoke = "backend-import %s" % ("OK" if rc == 0 and "True" in out else "FAIL " + out.strip()[-200:])
    # try source-mode switch note: only add if small; do not break exe mode
    ok = (rc == 0)
    detail = "%s; dist=%s" % (smoke, "present" if has_dist else "absent(run vite build first)")
    return ok, detail, exe_only

# ---------- G5 ----------
def g5():
    rows_f = TOOLS / "live_drive" / "rows.json"
    try:
        data = json.loads(rows_f.read_text(encoding="utf-8"))
    except Exception as e:
        return False, "rows.json unreadable %s" % str(e)[:120], []
    funcs = data.get("functions", data if isinstance(data, list) else [])
    gaps = []
    maps = []
    # index test files by content
    test_files = list_pytest_files()
    fe_tests = []
    fe_dir = GATE / "frontend" / "src"
    if fe_dir.is_dir():
        for p in fe_dir.rglob("*.test.*"):
            fe_tests.append(p.relative_to(GATE).as_posix())
    all_test_paths = test_files + fe_tests
    contents = {}
    for rel in all_test_paths[:400]:
        try:
            contents[rel] = (GATE / rel).read_text(encoding="utf-8", errors="replace")[:20000]
        except OSError:
            contents[rel] = ""
    def find_row(rid, testids, path, labels):
        cands = []
        for rel, txt in contents.items():
            if rid and rid in txt:
                return rel
            cands.append((rel, txt))
        for tid in (testids or []):
            for rel, txt in contents.items():
                if tid and tid in txt:
                    return rel
        if path and path != "-":
            key = path.rsplit("/", 1)[-1]
            for rel, txt in contents.items():
                if key and key in txt:
                    return rel
        return ""
    for fn in funcs:
        rid = fn.get("id", "")
        hit = find_row(rid, fn.get("testids", []), fn.get("path", ""), fn.get("labels", []))
        if hit:
            maps.append("%s -> %s" % (rid, hit))
        else:
            gaps.append("GAP %s (%s)" % (rid, fn.get("expect", "")[:80]))
    for fid in ["F%02d" % i for i in range(1, 15)]:
        found = any(fid in txt or fid in rel for rel, txt in contents.items())
        if not found:
            gaps.append("GAP %s (no code-level test)" % fid)
        else:
            maps.append("%s -> code test" % fid)
    laptop = {
        "wrong key": ["wrong", "provider"],
        "restart + key kept": ["restart", "persist"],
        "double click": ["double", "click"],
        "live permission card": ["permission", "approval"],
        "Ukrainian task": ["ukrain", "ukrainian", "locale"],
        "language after restart": ["locale", "language"],
        "Team off": ["team", "off"],
    }
    for label, keys in laptop.items():
        hit = ""
        for rel, txt in contents.items():
            low = txt.lower()
            if all(k in low for k in keys):
                hit = rel
                break
        if hit:
            maps.append("laptop:%s -> %s" % (label, hit))
        else:
            gaps.append("GAP laptop:%s" % label)
    ok = True  # G5 never fails the gate; gaps route to walk/live legs
    return ok, "%d mapped %d gaps" % (len(maps), len(gaps)), gaps

# ---------- runners ----------
def do_fast(int_rev, last_hash):
    walls = {}
    lines = []
    t0 = time.time(); ok1, lost, notes1 = g1(int_rev); walls["G1"] = time.time() - t0
    lines.append(("G1", ok1, "%d lost" % len(lost), lost[:10]))
    t0 = time.time(); ok2, hits, probs = g2(int_rev); walls["G2"] = time.time() - t0
    lines.append(("G2", ok2, "%d hits %d problems" % (len(hits), len(probs)), (hits + probs)[:10]))
    t0 = time.time(); okd, dmsg = ensure_frontend_deps(); walls["DEPS"] = time.time() - t0
    lines.append(("DEPS", okd, dmsg, []))
    t0 = time.time(); okg, gmsg = run_golden(); walls["GOLDEN"] = time.time() - t0
    lines.append(("GOLDEN", okg, gmsg, []))
    t0 = time.time()
    base = last_hash or RC5
    chg = changed_tests_since(base, int_rev)
    aff, warn = affected_since(base, int_rev)
    files = sorted(set(chg) | set(aff))
    chg_ok = True
    chg_reds = []
    chg_msg = "changed=0 since %s (golden covered by GOLDEN)" % (last_hash or RC5[:7])
    if files:
        t1 = time.time()
        results, flaky, still = run_pool(files, "chg")
        chg_ok = (len(still) == 0)
        for f in sorted(still):
            chg_reds.append(still[f][:200])
        chg_reds.extend(flaky[:10])
        n_all = sum(1 for r in results.values() if r["rc"] == 0)
        chg_msg = ("pool=10 files=%d (changed=%d affected=%d) pass=%d reds=%d flaky=%d still=%d in %.0fs%s" %
                   (len(results), len(chg), len(aff), n_all,
                    sum(len(r["reds"]) for r in results.values()),
                    len(flaky), len(still), time.time() - t1,
                    " AFFECTED-WARN " + warn if warn else ""))
    walls["CHANGED"] = time.time() - t0
    lines.append(("CHANGED", chg_ok, chg_msg, chg_reds[:10]))
    t0 = time.time(); okt, tmsg = tsc_check(); walls["TSC"] = time.time() - t0
    lines.append(("TSC", okt, tmsg, []))
    return lines, walls

def do_full(int_rev):
    walls = {}
    lines = []
    t0 = time.time(); ok1, lost, n1 = g1(int_rev); walls["G1"] = time.time() - t0
    lines.append(("G1", ok1, "%d lost" % len(lost), lost[:10]))
    t0 = time.time(); ok2, hits, probs = g2(int_rev); walls["G2"] = time.time() - t0
    lines.append(("G2", ok2, "%d hits %d problems" % (len(hits), len(probs)), (hits + probs)[:10]))
    t0 = time.time(); okd, dmsg = ensure_frontend_deps(); walls["DEPS"] = time.time() - t0
    lines.append(("DEPS", okd, dmsg, []))
    t0 = time.time(); okp, ptail, preds, failcases = pytest_full(); walls["PYTEST"] = time.time() - t0
    lines.append(("PYTEST", okp, ptail, preds[:15]))
    t0 = time.time(); okt, tmsg = tsc_check(); walls["TSC"] = time.time() - t0
    lines.append(("TSC", okt, tmsg, []))
    t0 = time.time(); okv, vtail, vreds, vfailrows = vitest_full(); walls["VITEST"] = time.time() - t0
    lines.append(("VITEST", okv, vtail, vreds[:10]))
    t0 = time.time(); okb, btail = vite_build(); walls["VITEBUILD"] = time.time() - t0
    lines.append(("VITEBUILD", okb, btail, []))
    t0 = time.time(); oks, (smsg, srows) = stub_scan(); walls["STUBSCAN"] = time.time() - t0
    lines.append(("STUBSCAN", oks, smsg, srows))
    t0 = time.time(); ok4, d4, skips = g4(int_rev); walls["G4"] = time.time() - t0
    lines.append(("G4", ok4, d4, skips[:10]))
    t0 = time.time(); ok5, d5, gaps = g5(); walls["G5"] = time.time() - t0
    lines.append(("G5", ok5, d5, gaps[:30]))
    reds_rows = list(failcases) + list(vfailrows)
    for r in srows:
        m = re.search(r"\S+:\d+", r)
        reds_rows.append(("STUB " + (m.group(0) if m else r), r))
    return lines, walls, reds_rows

def write_report(int_rev, mode, lines, walls, reds_rows=None):
    h = int_rev[:12] if len(int_rev) >= 12 else int_rev
    rep = RUN / ("GATE_%s.md" % h)
    tot_fail = sum(0 if ok else 1 for _, ok, _, _ in lines)
    with open(str(rep), "w", encoding="utf-8") as f:
        f.write("# GATE %s %s int %s\n\n" % (mode.upper(), h, int_rev))
        for name, ok, msg, reds in lines:
            f.write("## %s %s wall=%.0fs %s\n" % (name, "PASS" if ok else "FAIL", walls.get(name, 0), msg))
            for r in (reds or []):
                f.write("- %s\n" % r)
        f.write("\nwalls: %s\n" % json.dumps({k: round(v, 1) for k, v in walls.items()}))
        if mode == "full":
            f.write("\n## REDS TABLE\n" + reds_table(reds_rows or []) + "\n")
    # TRAIN_LOG line
    counts = "%d/%d" % (sum(0 if ok else 1 for _, ok, _, _ in lines), len(lines))
    status = "PASS" if all(ok for _, ok, _, _ in lines) else "FAIL"
    try:
        with open(str(RUN / "TRAIN_LOG.txt"), "a", encoding="utf-8") as f:
            f.write("GATE %s %s %s\n" % (status, h, counts))
    except OSError:
        pass
    # CHANGELOG one line
    try:
        cl = TOOLS / "CHANGELOG.md"
        with open(str(cl), "a", encoding="utf-8") as f:
            f.write("\n2026-11-02 | DIRECTOR/TOOLS/int_gate.py | GATE %s %s %s %s | int-gate baseline | %s" % (
                mode.upper(), status, h, counts, rep.name))
    except OSError:
        pass
    return rep

def sync_gate(rev):
    """Point the GATE clone at rev. Every full/fast run goes through here,
    so a report always tests the rev it names (regression: flag revs)."""
    try:
        run(["git", "fetch", "origin", "int:int"], GATE, timeout=300)
    except Exception:
        pass
    return run(["git", "checkout", "--detach", rev], GATE, timeout=300)


def run_full_on(rev):
    """Checkout rev, then full-test exactly that tree.
    Returns (rep, tested, lines)."""
    sync_gate(rev)
    lines, walls, reds_rows = do_full(rev)
    rep = write_report(rev, "full", lines, walls, reds_rows)
    return rep, rev, lines


def consume_flag(tested):
    """Unlink GATE_FULL.flag only if it still names the rev just tested
    (a flag written during the run belongs to the next run)."""
    flag = RUN / "GATE_FULL.flag"
    try:
        cur = flag.read_text(encoding="utf-8").strip().split()[0]
    except (OSError, IndexError):
        return False
    if cur != tested:
        return False
    try:
        flag.unlink()
    except OSError:
        return False
    return True


def watch_once(last):
    """One poll iteration. Returns the new last (rev already gated)."""
    cur = int_hash()
    flag = RUN / "GATE_FULL.flag"
    if flag.is_file():
        try:
            rev = flag.read_text(encoding="utf-8").strip().split()[0]
        except (OSError, IndexError):
            rev = ""
        if rev:
            print("WATCH full-flag %s" % rev, flush=True)
            rc, _ = git(["rev-parse", rev])
            tested = rev if rc == 0 else cur
            rep, tested, _ = run_full_on(tested)
            print("WATCH full done %s" % rep.name, flush=True)
            consume_flag(tested)
            return tested
    if cur and cur != last:
        lh = last_gate_hash()
        sync_gate(cur)
        lines, walls = do_fast(cur, lh)
        rep = write_report(cur, "fast", lines, walls)
        for name, ok, msg, reds in lines:
            print("%s %s %s" % (name, "PASS" if ok else "FAIL", msg), flush=True)
            for r in (reds or [])[:10]:
                print("  %s" % r, flush=True)
        print("WATCH fast done %s" % rep.name, flush=True)
        return cur
    return last


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--rev", default="")
    ap.add_argument("--watch", action="store_true")
    a = ap.parse_args(argv)
    mode = "full" if a.full else "fast"
    if a.watch:
        last = ""
        print("WATCH start poll int every 60s", flush=True)
        while True:
            last = watch_once(last)
            time.sleep(60)
        return 0
    rev = a.rev.strip() or int_hash()
    if a.full:
        rep, _, lines = run_full_on(rev)
    else:
        sync_gate(rev)
        lh = last_gate_hash()
        lines, walls = do_fast(rev, lh)
        rep = write_report(rev, "fast", lines, walls)
    for name, ok, msg, reds in lines:
        print("%s %s %s" % (name, "PASS" if ok else "FAIL", msg), flush=True)
        for r in (reds or [])[:10]:
            print("  %s" % r, flush=True)
    print("REPORT %s" % rep, flush=True)
    return 0 if all(ok for _, ok, _, _ in lines) else 1

if __name__ == "__main__":
    sys.exit(main())
