"""K10INSTALL headless installer build: offline artifact plus hash record.

Packages the served entries (backend app plus frontend index) from this
checkout into one deterministic zip under dist/ and records sha256
hashes of the artifact and every input. Fully offline: stdlib only, no
network, no keys, no installs. Rebuilds are byte-identical (fixed zip
metadata), so a twice-restart hash compare proves a clean repeat.
"""

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

TOOL = "packaging/installer/build.py"
FIXED_DATE = (1980, 1, 1, 0, 0, 0)
ENTRIES = {
    "backend_app": "src/agent_si/backend/app.py",
    "frontend_index": "frontend/index.html",
    "frontend_entry": "frontend/src/app/main.tsx",
    "frontend_lockfile": "frontend/package-lock.json",
    "pyproject": "pyproject.toml",
    "start_tool": "tools/start.py",
    "license": "LICENSE",
    "notices": "docs/third_party_notices/NOTICES.md",
    "license_mit": "licenses/MIT_LICENSE.txt",
}

# --- FXSETUP: Inno Setup compile step --------------------------------------
# Version matches the frozen portable contract (build_app.ps1,
# packaging/tauri/tauri.conf.json, pyproject.toml): single source here
# only for the setup file name; the .iss carries the same default.
SETUP_VERSION = "0.1.0"
ISS_REL = "packaging/installer/agent_si.iss"
SUMS_NAME = "SHA256SUMS.txt"

# Stage leaves that prove a used data folder rode into the installer
# payload: project data, key material, or test output. A fresh
# install must start clean, so any of these fails the setup build.
DIRTY_DIR_LEAVES = frozenset(
    {"data", "projects", "runs", "keys", "secrets", "test-results"})
DIRTY_FILE_NAMES = frozenset({".env"})
DIRTY_FILE_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".pem")


def scan_stage_clean(stage_dir) -> list:
    """List payload violations under a stage folder; [] means clean."""
    stage = Path(stage_dir)
    if not stage.is_dir():
        return [f"stage folder absent: {stage}"]
    violations = []
    for path in sorted(stage.rglob("*")):
        rel = path.relative_to(stage).as_posix()
        leaf = path.name.lower()
        if path.is_dir():
            if leaf in DIRTY_DIR_LEAVES:
                violations.append(rel + "/")
        elif leaf in DIRTY_FILE_NAMES or leaf.endswith(DIRTY_FILE_SUFFIXES):
            violations.append(rel)
    return violations


def iscc_candidates() -> list:
    """ISCC.exe locations in probe order: PATH, per-user, Program Files."""
    cands = []
    found = shutil.which("ISCC.exe") or shutil.which("iscc")
    if found:
        cands.append(found)
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        cands.append(os.path.join(
            local, "Programs", "Inno Setup 6", "ISCC.exe"))
    for var in ("ProgramFiles", "ProgramW6432"):
        base = os.environ.get(var, "")
        if base:
            cands.append(os.path.join(base, "Inno Setup 6", "ISCC.exe"))
    base86 = os.environ.get("PROGRAMFILES(X86)", "")
    if base86:
        cands.append(os.path.join(base86, "Inno Setup 6", "ISCC.exe"))
    return cands


def find_iscc():
    """First existing ISCC.exe, or None when Inno Setup 6 is absent."""
    for cand in iscc_candidates():
        if cand and os.path.isfile(cand):
            return cand
    return None


def record_setup_hash(dist_dir, setup_path):
    """Add the setup exe sha256 to SHA256SUMS.txt next to the portable.

    Idempotent: an existing line for the same file name is replaced,
    other lines are kept, entries are sorted by file name.
    Returns the SHA256SUMS.txt path.
    """
    dist = Path(dist_dir)
    sums_path = dist / SUMS_NAME
    rows = {}
    if sums_path.is_file():
        for line in sums_path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 2 and len(parts[0]) == 64:
                rows[parts[-1]] = parts[0]
    rows[Path(setup_path).name] = sha256_file(Path(setup_path))
    sums_path.write_text(
        "".join(f"{rows[name]}  {name}\n" for name in sorted(rows)),
        encoding="utf-8")
    return sums_path


def compile_setup(root, version=SETUP_VERSION) -> int:
    """Compile agent_si.iss with ISCC; record hashes. 0 on success."""
    iscc = find_iscc()
    if iscc is None:
        print("installer setup FAILED: ISCC.exe (Inno Setup 6) not found "
              "on PATH, under %LOCALAPPDATA%\\Programs\\Inno Setup 6, or "
              "under Program Files. Install Inno Setup 6, then rerun "
              "with --setup. Never skipped silently.",
              file=sys.stderr)
        return 2
    iss = root / ISS_REL
    if not iss.is_file():
        print(f"installer setup FAILED: missing {ISS_REL}", file=sys.stderr)
        return 1
    stage = root / "dist" / "stage"
    violations = scan_stage_clean(stage)
    if violations:
        print("installer setup FAILED: stage folder not clean, "
              "refusing to ship user data in the payload: "
              + ", ".join(violations), file=sys.stderr)
        return 1
    out_dir = root / "dist"
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"AgentSI-setup-{version}.exe"
    cmd = [iscc, f"/O{out_dir}", f"/F{base[:-len('.exe')]}",
           f"/DAppVersion={version}", str(iss)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    tail = (proc.stdout + "\n" + proc.stderr).strip().splitlines()[-10:]
    if proc.returncode != 0:
        print(f"installer setup FAILED: ISCC.exe exited "
              f"{proc.returncode}: " + " / ".join(tail), file=sys.stderr)
        return 1
    setup_path = out_dir / base
    if not setup_path.is_file():
        print(f"installer setup FAILED: ISCC.exe reported success but "
              f"{base} is absent. ISCC output tail: " + " / ".join(tail),
              file=sys.stderr)
        return 1
    record_setup_hash(out_dir, setup_path)
    portable_zip = out_dir / f"AgentSI-portable-{version}.zip"
    if portable_zip.is_file():
        record_setup_hash(out_dir, portable_zip)
    print(f"installer setup ok: {setup_path} "
          f"sha256={sha256_file(setup_path)}")
    return 0


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_entries(root: Path) -> tuple:
    status = {n: ("ok" if (root / r).is_file() else "missing")
              for n, r in ENTRIES.items()}
    missing = [n for n, v in status.items() if v != "ok"]
    return status, missing


def build_zip(root: Path, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(out_path.parent), suffix=".tmp")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in sorted(ENTRIES.values()):
                data = (root / name).read_bytes()
                info = zipfile.ZipInfo(name, date_time=FIXED_DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                zf.writestr(info, data)
        os.replace(tmp, out_path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def rel_posix(path, root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(
            root.resolve()).as_posix()
    except ValueError:
        return os.path.relpath(os.path.abspath(path),
                               os.path.abspath(root)).replace(os.sep, "/")


def write_record(path: str, record: dict) -> None:
    target = Path(path)
    if target.parent and not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="build.py",
        description="Offline headless installer build for the served entries.")
    parser.add_argument("--out", default=None,
                        help="artifact path (else dist/k10installer.zip)")
    parser.add_argument("--record", default=None,
                        help="write the JSON hash record to this path")
    parser.add_argument("--tag", default="",
                        help="label stored in the record")
    parser.add_argument("--setup", action="store_true",
                        help="compile packaging/installer/agent_si.iss "
                             "with ISCC.exe into dist/AgentSI-setup-"
                             "<version>.exe and record its sha256")
    args = parser.parse_args(argv)
    root = repo_root()
    if args.setup:
        return compile_setup(root)
    status, missing = check_entries(root)
    if missing:
        print(f"installer build not ready, missing: {missing}",
              file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else root / "dist" / "k10installer.zip"
    build_zip(root, out)
    record = {
        "tool": TOOL,
        "tag": args.tag,
        "root": ".",
        "artifact": rel_posix(out, root),
        "offline": True,
        "entries": dict(status),
        "sha256": {n: sha256_file(root / r) for n, r in ENTRIES.items()},
    }
    record["sha256"]["artifact"] = sha256_file(out)
    if args.record:
        write_record(args.record, record)
        print(f"recorded {args.record}")
    else:
        print(json.dumps(record, indent=2, sort_keys=True))
    print(f"artifact {out} sha256={record['sha256']['artifact']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
