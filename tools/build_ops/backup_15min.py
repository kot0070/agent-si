# Development tool for this build, shown as written. Not part of the app.
# Machine paths, server addresses and session ids were replaced by <PLACEHOLDERS>; the logic is unchanged.
"""15-min backup: APP git bundle + zips of TOOLS/INBOX/RUN/kit. One pass per call; --loop repeats every 15 min. No pruning."""
import os
import zipfile
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("<BUILD_ROOT>")
APP_DIR = ROOT / "APP"
SOURCES = {
    "TOOLS": ROOT / "DIRECTOR" / "TOOLS",
    "INBOX": ROOT / "DIRECTOR" / "INBOX",
    "RUN": ROOT / "DIRECTOR" / "RUN",
    "kit": ROOT / "kit",
}
DEST_ROOT = Path("<BACKUP_ROOT>")
INTERVAL_S = 2 * 60 * 60  # 04.11: 60 -> 120 min, disk; 03.11: 15 -> 60 min, a 1.4 GB copy takes 3.5 min of CPU next to the local model and C: would fill before the deadline


#: Run products, not sources: live browser profiles hold locked files, exe copies are rebuilt.
SKIP_DIRS = {"webview2", "EBWebView", "node_modules", "__pycache__", "exe", "appdata", "dist",
             "CLEANTEST", "VID2", ".venv", "venv", "tmp"}  # 04.11: copies grew to 18 GB and filled C:
MAX_FILE_BYTES = 50 * 1024 * 1024


def zip_tree(src: Path, target: Path) -> list:
    """Zip src; a locked or oversized file is listed and skipped, it never stops the backup."""
    skipped = []
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.endswith(".frames")]
            for fname in files:
                path = Path(folder) / fname
                try:
                    if path.stat().st_size > MAX_FILE_BYTES:
                        skipped.append(str(path))
                        continue
                    zf.write(path, path.relative_to(src.parent))
                except (OSError, ValueError):
                    skipped.append(str(path))
    return skipped


def one_pass() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = DEST_ROOT / stamp
    dest.mkdir(parents=True, exist_ok=True)
    bundle = dest / "app-all.bundle"
    r = subprocess.run(
        ["git", "-C", str(APP_DIR), "bundle", "create", str(bundle), "--all"],
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if r.returncode != 0:
        print("BUNDLE_FAIL rc=" + str(r.returncode) + " " + r.stderr[-500:])
    for name, src in SOURCES.items():
        if src.is_dir():
            skipped = zip_tree(src, dest / (name + ".zip"))
            if skipped:
                print("SKIPPED %s %d files, first: %s" % (name, len(skipped), skipped[0]))
        else:
            print("SKIP missing " + str(src))
    print("BACKUP_DONE " + str(dest))
    return dest


def main() -> int:
    if "--loop" in sys.argv[1:]:
        while True:
            one_pass()
            time.sleep(INTERVAL_S)
    else:
        one_pass()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
