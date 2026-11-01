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
    args = parser.parse_args(argv)
    root = repo_root()
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
