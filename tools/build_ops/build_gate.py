# Development tool for this build, shown as written. Not part of the app.
# Machine paths, server addresses and session ids were replaced by <PLACEHOLDERS>; the logic is unchanged.
"""build_gate.py: pre-build / post-build / pre-table gate for the staged exe build.

Read-only: never builds, pushes, prints keys, or touches monitors.
Modes: pre | post | pretable | all (default all).
Exit: 0 all PASS; 1 any FAIL; 2 environment/usage error.

Reuse binding: WT dirty-scan and git running come from sync_copies.py
(dirty_files, git runner) and live-run ownership from wt_janitor.py
(live_wt_names). This gate only adds what they lack: NOW.md merged-list
ancestor checks, built_from/elsa provenance, RESULT.json table checks.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import pathlib
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    import sync_copies as sc
    import wt_janitor as wj
    _TOOLS_IMPORT_ERROR = ""
except ImportError as ex:  # reuse is mandatory: main() turns this into exit 2
    sc = None
    wj = None
    _TOOLS_IMPORT_ERROR = str(ex)
DEFAULT_ROOT = os.path.dirname(os.path.dirname(HERE))  # .../BUILD_ROOT
INSTALLB_ALLOWED = {
    "packaging/installer_manifest/HASH.json",
    "packaging/installer_manifest/HASH.json.sha256",
    "packaging/installer_manifest/MANIFEST.json",
    "packaging/installer_manifest/SMOKE.json",
}
NON_PRODUCT_PREFIXES = ("DIRECTOR/", "_task/", "tmp/")
SHA_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")
PIN_RE = re.compile(r"^[0-9a-f]{7,40}$")


def run(cmd, cwd=None, timeout=120):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout, stdin=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except Exception as ex:
        return 99, "", "%s: %s" % (type(ex).__name__, ex)


class Gate:
    def __init__(self):
        self.rows = []  # (id, verdict, evidence)

    def add(self, cid, ok, ev):
        self.rows.append((cid, "PASS" if ok else "FAIL", ev))

    def fails(self):
        return sum(1 for _, v, _ in self.rows if v == "FAIL")


def int_head(app):
    rc, out = sc.git(app, "rev-parse", "int")
    if rc != 0:
        raise RuntimeError("cannot rev-parse int in %s" % app)
    return out.strip()


def read_now(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError as ex:
        raise RuntimeError("cannot read NOW.md %s (%s)" % (path, ex))


def parse_live(text):
    m = re.search(r"LANES live:(.*?)(?:\n|$)", text)
    if not m:
        return set()
    seg = re.sub(r"\([^)]*\)", " ", m.group(1))
    toks = re.split(r"[\s,;.]+", seg)
    return {t for t in toks if t and t not in ("LANES", "live:")}


def parse_merged(text):
    m = re.search(r"[Mm]erged:(.*?)(?:;|\n)", text)
    if not m:
        return []
    seg = m.group(1).split(". ")[0]  # merged list ends at the sentence end
    lanes = []  # (lane, pin|None)
    for item in seg.split(","):
        words = item.strip().split()
        if not words:
            continue
        name, pin = words[0].strip().rstrip("."), None
        for w in words[1:]:
            w = w.strip().rstrip(".")
            if PIN_RE.match(w):
                pin = w
                break
        for lane in expand_lane(name):
            lanes.append((lane, pin))
    return lanes


def expand_lane(name):
    if "/" not in name:
        return [name] if re.match(r"^[A-Za-z0-9_.-]+$", name) else []
    a, b = name.split("/", 1)
    if b and not b[0].isalpha():
        b = re.sub(r"[0-9]+$", "", a) + b
    return [a, b]


def read_parked(path):
    try:
        txt = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return set()
    names = set()
    for line in txt.splitlines():
        t = line.strip()
        if t and not t.startswith("#"):
            names.add(t.split()[0])
    return names


def find_merge(app, branch):
    # newest merge commit on int whose message names the branch; None when absent.
    # merge-base --is-ancestor on the result proves merged-by-ancestry even
    # after the pkg/ branch ref was pruned.
    rc, out = sc.git(app, "log", "int", "--merges", "--format=%H",
                     "-F", "--grep=%s" % branch)
    if rc != 0:
        return None
    for line in out.splitlines():
        sha = line.strip()
        if sha:
            rc, par = sc.git(app, "rev-list", "--parents", "-n", "1", sha)
            if rc == 0 and len(par.split()) >= 3:
                return sha
    return None


def branch_candidates(lane):
    if lane.startswith("FX"):
        return ["pkg/" + lane]
    return ["pkg/" + lane, "pkg/FX" + lane]


def check_pre(g, app, wtroot, installb, now_text, head, root, parked):
    # P1: APP tracked clean (tracked-only per spec: staged + unstaged name lists,
    # no porcelain parsing; commands run through the sync_copies git runner)
    rc1, u = sc.git(app, "diff", "--name-only")
    rc2, s = sc.git(app, "diff", "--cached", "--name-only")
    if rc1 != 0 or rc2 != 0:
        g.add("P1 app-clean", False, "git diff failed")
    else:
        paths = sorted({l.strip() for l in (u.splitlines() + s.splitlines()) if l.strip()})
        g.add("P1 app-clean", not paths,
              "tracked clean at %s" % head[:9] if not paths
              else "tracked dirty: %s" % ", ".join(paths[:5]))
    # P2: merged lanes are ancestors of int
    # P2: merged-by-ancestry only. Pins are verified as commits ancestor of
    # int; pin-less lanes resolve to their merge commit on int (git log
    # --merges --grep) which is then verified ancestor. Branch-ref
    # existence is never consulted: pruned pkg/ branches still prove
    # through their merge commits in int history.
    lanes = parse_merged(now_text)
    if not lanes:
        g.add("P2 merged-ancestors", False, "no merged list parsed from NOW.md")
    else:
        bad, n = [], 0
        for lane, pin in lanes:
            obj, via = None, None
            if pin:
                rc, full = sc.git(app, "rev-parse", "--verify", pin + "^{commit}")
                if rc != 0:
                    bad.append("%s:badpin" % lane)
                    continue
                obj, via = full.strip(), "pin"
            else:
                for cand in branch_candidates(lane):
                    m = find_merge(app, cand)
                    if m:
                        obj, via = m, cand
                        break
                if not obj:
                    bad.append("%s(nomerge)" % lane)
                    continue
            n += 1
            rc, _ = sc.git(app, "merge-base", "--is-ancestor", obj, "int")
            if rc != 0:
                bad.append("%s:%s" % (lane, obj[:9]))
        g.add("P2 merged-ancestors", not bad,
              "%d merged-by-ancestry in int %s" % (n, head[:9]) if not bad
              else "not ancestors: %s" % ", ".join(bad[:6]))
    # P3: WT dirty-scan is sync_copies.dirty_files; liveness mark is
    # wt_janitor.live_wt_names. Gate policy on top: every dirty WT must be
    # in the NOW.md live set; INSTALLB is covered by P4.
    live = parse_live(now_text)
    try:
        run_live = wj.live_wt_names(pathlib.Path(root))
    except Exception:
        run_live = set()
    viol, scanned = [], 0
    try:
        wts = sorted(d for d in os.listdir(wtroot)
                     if os.path.isdir(os.path.join(wtroot, d))
                     and os.path.exists(os.path.join(wtroot, d, ".git")))
    except OSError as ex:
        g.add("P3 wt-lanes", False, "cannot list WT (%s)" % ex)
        wts = None
    if wts is not None:
        parked_here = sorted(d for d in wts if d in parked)
        for d in wts:
            if d == "INSTALLB" or d == "_task" or d in parked:
                continue
            dirty = sc.dirty_files(os.path.join(wtroot, d))
            if dirty is None:
                continue
            prod = sorted({f.replace("\\", "/") for f in dirty
                           if not f.replace("\\", "/").startswith(NON_PRODUCT_PREFIXES)})
            scanned += 1
            if prod and d not in live:
                tag = "live-run" if d in run_live else "non-live"
                viol.append("%s(%s:%s)" % (d, tag, prod[0]))
        ev = ("%d WT scanned via sync_copies, live=%s, only live dirty"
              % (scanned, ",".join(sorted(live)) or "-")
              if not viol else "dirty lanes outside NOW.md live: %s" % ", ".join(viol[:6]))
        ev += "; parked, not in this build: %s" % (
            ",".join(parked_here) if parked_here else "-")
        g.add("P3 wt-lanes", not viol, ev)
    # P4: INSTALLB at int head, only generated manifests dirty
    rc, ih = sc.git(installb, "rev-parse", "HEAD")
    ih = ih.strip() if rc == 0 else ""
    g.add("P4 installb-head", ih == head,
          "INSTALLB %s == int %s" % (ih[:9], head[:9]) if ih == head
          else "INSTALLB %s != int %s" % (ih[:9] or "?", head[:9]))
    dirty = sc.dirty_files(installb)
    if dirty is None:
        g.add("P4 installb-manifests", False, "sync_copies dirty scan failed")
    else:
        paths = sorted({f.replace("\\", "/") for f in dirty})
        extra = [p for p in paths if p not in INSTALLB_ALLOWED]
        g.add("P4 installb-manifests", not extra,
              "only generated manifests dirty (%d)" % len(paths) if not extra
              else "non-manifest changes: %s" % ", ".join(extra[:5]))


def first_existing(*paths):
    for p in paths:
        if os.path.isfile(p):
            return p
    return None


def gateway_sha(gateway_py, root, exe, timeout=180):
    for extra in (["-P"], []):
        cmd = [sys.executable] + extra + [gateway_py, "sha", "--root", root, "--exe", exe]
        rc, out, err = run(cmd, timeout=timeout)
        if rc == 0 and SHA_RE.match(out.strip()) and len(out.strip()) == 64:
            return out.strip().lower()
    raise RuntimeError("gateway sha failed (%s)" % (err[:160] or "rc=%s" % rc))


def check_post(g, app, gateway_py, root, portable, head):
    hj = first_existing(os.path.join(portable, "app", "HASH.json"),
                        os.path.join(portable, "HASH.json"))
    exe = first_existing(os.path.join(portable, "app", "AgentSI.exe"),
                         os.path.join(portable, "AgentSI.exe"))
    if hj is None:
        g.add("Q1 hash-commit", False, "no HASH.json under %s" % portable)
        g.add("Q2 exe-sha", False, "skipped (no HASH.json)")
        return
    try:
        hj_data = json.load(open(hj, encoding="utf-8"))
    except (OSError, ValueError) as ex:
        g.add("Q1 hash-commit", False, "cannot read %s (%s)" % (hj, ex))
        g.add("Q2 exe-sha", False, "skipped (no HASH.json)")
        return
    bfc = str(hj_data.get("built_from_commit", "")).strip()
    g.add("Q1 hash-commit", bfc.lower().startswith(head.lower()) or head.lower().startswith(bfc.lower()),
          "built_from_commit=%s vs int %s" % (bfc[:12], head[:9]))
    if exe is None:
        g.add("Q2 exe-sha", False, "staged exe missing under %s" % portable)
        return
    try:
        staged = gateway_sha(gateway_py, root, exe)
    except RuntimeError as ex:
        g.add("Q2 exe-sha", False, str(ex)[:160])
        return
    want = None
    man = first_existing(os.path.join(os.path.dirname(hj), "MANIFEST.json"))
    man_ev = ""
    if man is None:
        g.add("Q2 exe-sha", False, "no MANIFEST.json next to %s" % hj)
        return
    try:
        files = json.load(open(man, encoding="utf-8")).get("files", [])
    except (OSError, ValueError) as ex:
        g.add("Q2 exe-sha", False, "cannot read %s (%s)" % (man, ex))
        return
    cands = [e for e in files if isinstance(e, dict)
             and os.path.basename(str(e.get("path", ""))).lower() == os.path.basename(exe).lower()]
    if not cands:
        g.add("Q2 exe-sha", False, "no %s entry in %s" % (os.path.basename(exe), man))
        return
    want = str(cands[0].get("sha256", "")).strip().lower()
    man_ev = "%s[%s]" % (os.path.basename(man), cands[0].get("path"))
    g.add("Q2 exe-sha", staged == want,
          "staged %s == %s %s" % (staged[:12], man_ev, want[:12]) if staged == want
          else "staged %s != %s %s" % (staged[:12], man_ev, want[:12]))


def check_pretable(g, results, head):
    if not results:
        g.add("T table", False, "no RESULT.json files given/found")
        return
    bad = []
    for rp in results:
        try:
            prov = json.load(open(rp, encoding="utf-8")).get("provenance", {})
        except (OSError, ValueError) as ex:
            bad.append("%s(unreadable)" % os.path.basename(os.path.dirname(rp)))
            continue
        tested, behind = str(prov.get("tested_on", "")), prov.get("behind")
        same_ends = prov.get("int_at_start") == prov.get("int_at_end")
        sha_keys = [k for k in prov if "sha" in k.lower() or "hash" in k.lower()]
        sha_ok = True
        for k in sha_keys:
            if "start" in k.lower():
                mate = k.lower().replace("start", "end")
                mkey = next((m for m in sha_keys if m.lower() == mate), None)
                if mkey and prov.get(k) != prov.get(mkey):
                    sha_ok = False
        ok = (tested == head and behind == 0 and same_ends and sha_ok
              and not prov.get("stale", False))
        if not ok:
            tag = os.path.basename(os.path.dirname(rp)) or os.path.basename(rp)
            bad.append("%s(tested=%s,behind=%s,ends=%s,sha=%s,stale=%s)" % (
                tag, tested[:9], behind, "same" if same_ends else "DIFF",
                "same" if sha_ok else "DIFF", prov.get("stale")))
    g.add("T table", not bad,
          "%d RESULT.json: tested_on==%s, behind==0, start==end" % (len(results), head[:9])
          if not bad else "prov mismatch: %s" % "; ".join(bad[:6]))


def check_parallel(g, app, now_text):
    hold = "FXPARALLEL" in now_text and re.search(r"STOPPED|hold|HOLD", now_text)
    rc, tip = sc.git(app, "rev-parse", "--verify", "pkg/FXPARALLEL")
    if rc != 0:
        g.add("X fxparallel", True, "FXPARALLEL not in this build (no branch)")
        return
    tip = tip.strip()
    rc, _ = sc.git(app, "merge-base", "--is-ancestor", tip, "int")
    if rc == 0:
        g.add("X fxparallel", not hold,
              "FXPARALLEL in this build with %s%s" % (tip[:9], " BUT NOW.md holds it" if hold else ""))
    else:
        g.add("X fxparallel", True, "FXPARALLEL not in this build (branch at %s)" % tip[:9])


def collect_results(table_dir, explicit):
    out = list(explicit or [])
    if table_dir:
        out += glob.glob(os.path.join(table_dir, "**", "RESULT.json"), recursive=True)
    seen, uniq = set(), []
    for p in out:
        a = os.path.abspath(p)
        if a not in seen and os.path.isfile(a):
            seen.add(a)
            uniq.append(a)
    return sorted(uniq)


def main(argv=None):
    ap = argparse.ArgumentParser(description="build gate: pre/post/pretable checks for the staged exe build (read-only)")
    ap.add_argument("--mode", default="all", choices=["pre", "post", "pretable", "all"])
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--commit", default=None, help="commit under test (default: rev-parse int)")
    ap.add_argument("--now-file", default=None)
    ap.add_argument("--app-dir", default=None)
    ap.add_argument("--wt-root", default=None)
    ap.add_argument("--installb-dir", default=None)
    ap.add_argument("--portable-dir", default=None)
    ap.add_argument("--table-dir", default=None)
    ap.add_argument("--result", action="append", default=[], help="RESULT.json (repeatable)")
    ap.add_argument("--parked-file", default=None,
                    help="parked WT list (default DIRECTOR/TOOLS/parked_wts.txt)")
    ap.add_argument("--dry-run", action="store_true", help="read-only probe; gate never builds")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    app = a.app_dir or os.path.join(root, "APP")
    wtroot = a.wt_root or os.path.join(root, "WT")
    installb = a.installb_dir or os.path.join(wtroot, "INSTALLB")
    portable = a.portable_dir or os.path.join(installb, "dist", "portable")
    gateway = os.path.join(root, "DIRECTOR", "TOOLS", "app_realkey_session.py")
    now_file = a.now_file or os.path.join(root, "DIRECTOR", "RUN", "NOW.md")
    parked_file = a.parked_file or os.path.join(root, "DIRECTOR", "TOOLS", "parked_wts.txt")
    g = Gate()
    if sc is None or wj is None:
        print("GATE ENVIRONMENT-ERROR: cannot reuse tools (%s)" % _TOOLS_IMPORT_ERROR)
        return 2
    try:
        head = a.commit or int_head(app)
        now_text = read_now(now_file)
    except RuntimeError as ex:
        print("GATE ENVIRONMENT-ERROR: %s" % ex)
        return 2
    if a.mode in ("pre", "all"):
        check_pre(g, app, wtroot, installb, now_text, head, root, read_parked(parked_file))
    if a.mode in ("post", "all"):
        check_post(g, app, gateway, root, portable, head)
    if a.mode in ("pretable", "all"):
        tdir = a.table_dir
        if tdir is None and not a.result:
            tdir = os.path.join(root, "DIRECTOR", "AUDIT", "FINAL2PASS")
        check_pretable(g, collect_results(tdir, a.result), head)
    check_parallel(g, app, now_text)
    for cid, v, ev in g.rows:
        print("%s: %s -- %s" % (v, cid, ev))
    n = g.fails()
    print("GATE %s (%d fail, int %s)" % ("PASS" if n == 0 else "FAIL", n, head[:9]))
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
