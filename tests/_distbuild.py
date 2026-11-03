"""Shared vite-build gate for dist-serving visual tests (FXBUILDRACE).

The gate pool runs one test file per process; several files building
frontend/dist concurrently corrupt it (vite emptyDir/prepareOutDir
race: one build wipes dist while another reads it). This helper
serializes the build with a cross-process directory lock: the first
holder builds, the rest reuse the finished dist.

Tests only: never imported by product code. The underscore module
name keeps pytest from collecting this file as a test module.
"""
import os
import shutil
import subprocess
import time

LOCK_WAIT_S = 1500
LOCK_POLL_S = 0.5
LOCK_STALE_S = 30 * 60


def _state_dir(ws):
    d = os.path.join(ws, "_task", "tmp", "fxbuild")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def _src_max_mtime(ws):
    frontend = os.path.join(ws, "frontend")
    latest = 0.0
    tops = [os.path.join(frontend, n) for n in
            ("package.json", "vite.config.ts", "vite.config.js",
             "vite.config.mts", "vite.config.cjs")]
    for p in tops:
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        if m > latest:
            latest = m
    src = os.path.join(frontend, "src")
    for root, _dirs, files in os.walk(src):
        for f in files:
            try:
                m = os.path.getmtime(os.path.join(root, f))
            except OSError:
                continue
            if m > latest:
                latest = m
    return latest


def _acquire(lock_dir):
    deadline = time.time() + LOCK_WAIT_S
    while True:
        try:
            os.mkdir(lock_dir)
            return
        except FileExistsError:
            try:
                age = time.time() - os.path.getctime(lock_dir)
            except OSError:
                continue
            if age > LOCK_STALE_S:
                try:
                    os.rmdir(lock_dir)
                except OSError:
                    pass
                continue
        except OSError:
            pass
        if time.time() > deadline:
            raise AssertionError(
                "dist build lock wait timed out: %s" % lock_dir)
        time.sleep(LOCK_POLL_S)


def _fresh(dist_index, marker, src_max):
    try:
        return (os.path.isfile(dist_index)
                and os.path.isfile(marker)
                and os.path.getmtime(marker) >= src_max)
    except OSError:
        return False


def build_once(ws):
    """Build frontend/dist once per frontend source state (file-locked)."""
    frontend = os.path.join(ws, "frontend")
    dist_index = os.path.join(frontend, "dist", "index.html")
    state = _state_dir(ws)
    marker = os.path.join(state, "dist.marker")
    lock_dir = os.path.join(state, "dist.lock.d")
    src_max = _src_max_mtime(ws)
    if _fresh(dist_index, marker, src_max):
        return
    _acquire(lock_dir)
    try:
        if _fresh(dist_index, marker, src_max):
            return
        npm = shutil.which("npm")
        assert npm is not None, "npm not found on PATH"
        if os.name == "nt":
            completed = subprocess.run(
                '"%s" --prefix frontend run build' % npm, cwd=ws,
                shell=True, capture_output=True, text=True, timeout=900)
        else:
            completed = subprocess.run(
                [npm, "--prefix", "frontend", "run", "build"], cwd=ws,
                capture_output=True, text=True, timeout=900)
        tail = (completed.stdout + completed.stderr)[-2000:]
        assert completed.returncode == 0, "build failed:\n" + tail
        assert os.path.isfile(dist_index), \
            "dist/index.html missing after build"
        try:
            with open(marker, "w") as fh:
                fh.write(repr(src_max) + "\n")
        except OSError:
            pass
    finally:
        try:
            os.rmdir(lock_dir)
        except OSError:
            pass
