# CODER-1 Kanapka: installer-manifest release report generator (stdlib only).
"""Generate packaging/installer_manifest/release_report.json from real files.

Pattern follows the stale-branch docs/third_party_notices release-report
generator: every value is read from disk or measured by a run; a missing
source fails closed with an absent marker, never an invented value. Bytes
are deterministic: sort_keys, indent 2, ensure_ascii False, trailing
newline. Writes go through a temp file in the target folder plus replace.

Key to source path plus rule:
- version/exe: packaging/installer_manifest/MANIFEST.json (writer rule).
- sha256: packaging/installer_manifest/HASH.json sha256, re-verified
  against the frozen canonical MANIFEST bytes (mismatch -> absent).
- built_from_commit: `git rev-parse HEAD` at run time (read-only);
  "unknown" only when git cannot answer.
- signature: packaging/installer_manifest/HASH.json signature object.
- staged: pass/fail per check from SMOKE.json (regenerated, real).
- components: name/version/licence for the frozen sidecar bundle
  (pywebview, pythonnet, clr_loader, bottle, proxy_tools) plus the app
  runtime (fastapi, openai-agents, uvicorn), each measured from the
  running interpreter's installed dist metadata; absent when missing.
- bundle (FXDIR one-folder): dist/stage/AgentSI.exe (the folder exe at
  the stage root, either freeze target) plus
  dist/AgentSI-portable-0.1.0.zip (the single-top-folder portable)
  plus dist/AgentSI-setup-0.1.0.exe (the installer, once ISCC built
  it) — bytes measured, absent if missing. An exe hash alone never
  proves the build: the zip, the installer and the folder manifest
  (MANIFEST/HASH above) prove it together.
- texts: LICENSE, docs/third_party_notices/NOTICES.md,
  docs/third_party_notices/licenses/MIT_LICENSE.txt (present flags).
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

EXE_NAME = "AgentSI.exe"
VERSION = "0.1.0"

MANIFEST_PARTS = ("packaging", "installer_manifest", "MANIFEST.json")
HASH_PARTS = ("packaging", "installer_manifest", "HASH.json")
SMOKE_PARTS = ("packaging", "installer_manifest", "SMOKE.json")
REPORT_PARTS = ("packaging", "installer_manifest", "release_report.json")
NOTICES_PARTS = ("docs", "third_party_notices", "NOTICES.md")
MIT_PARTS = ("docs", "third_party_notices", "licenses", "MIT_LICENSE.txt")
LICENSE_PARTS = ("LICENSE",)

SIDECAR_COMPONENTS = (
    "pywebview",
    "pythonnet",
    "clr_loader",
    "bottle",
    "proxy_tools",
)
RUNTIME_COMPONENTS = ("fastapi", "openai-agents", "uvicorn")

BUNDLE_PATHS = (
    "dist/stage/AgentSI.exe",
    "dist/AgentSI-portable-0.1.0.zip",
    "dist/AgentSI-setup-0.1.0.exe",
)


def repo_root_default() -> Path:
    """Repo root derived from this file location (portable)."""
    return Path(__file__).resolve().parents[2]


def read_json(path: Path) -> dict | None:
    """Read a JSON object; None on any failure."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def non_empty_file(path: Path) -> bool:
    """True only for a regular file holding at least one byte."""
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def canonical_manifest_bytes(manifest: dict) -> bytes:
    """Frozen canonical form the exe-hash gate also hashes."""
    return json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def measure_commit(root: Path) -> str:
    """HEAD sha from read-only git; 'unknown' when git cannot answer."""
    try:
        proc = subprocess.run(
            ["git", "-c", "safe.directory=*", "rev-parse", "HEAD"],
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=60,
        )
    except (OSError, ValueError):
        return "unknown"
    sha = (proc.stdout or "").strip()
    if proc.returncode != 0 or len(sha) != 40:
        return "unknown"
    return sha


def measure_components() -> dict:
    """Name/version/licence measured from installed dist metadata."""
    try:
        from importlib import metadata as _metadata
    except ImportError:
        return dict.fromkeys(
            SIDECAR_COMPONENTS + RUNTIME_COMPONENTS,
            "absent:importlib.metadata",
        )
    result = {}
    for name in SIDECAR_COMPONENTS + RUNTIME_COMPONENTS:
        try:
            dist = _metadata.metadata(name)
            version = _metadata.version(name)
        except Exception:
            result[name] = "absent:not-installed"
            continue
        licence = (dist.get("License-Expression")
                   or dist.get("License") or "?")
        result[name] = {
            "version": version,
            "licence": " ".join(str(licence).split()),
        }
    return result


def measure_bundle(root: Path) -> dict:
    """Bytes per bundle path; absent marker when the file is missing."""
    result = {}
    for rel in BUNDLE_PATHS:
        path = root / rel
        try:
            if path.is_file():
                result[rel] = {"bytes": path.stat().st_size}
            else:
                result[rel] = "absent:not-built"
        except OSError:
            result[rel] = "absent:unreadable"
    return result


def build_report(root: Path) -> dict:
    """Assemble the freeze report with real measured values."""
    manifest = read_json(root.joinpath(*MANIFEST_PARTS))
    envelope = read_json(root.joinpath(*HASH_PARTS))
    smoke = read_json(root.joinpath(*SMOKE_PARTS))
    sha = None
    if manifest is not None and envelope is not None:
        recorded = envelope.get("sha256")
        try:
            actual = hashlib.sha256(
                canonical_manifest_bytes(manifest)).hexdigest()
        except (TypeError, ValueError):
            actual = None
        if isinstance(recorded, str) and recorded and recorded == actual:
            sha = recorded
    staged = {}
    if smoke is not None and isinstance(smoke.get("checks"), list):
        for entry in smoke["checks"]:
            if isinstance(entry, dict) and "name" in entry:
                staged[entry["name"]] = entry.get("result")
    signature = None
    if envelope is not None and isinstance(
            envelope.get("signature"), dict):
        signature = envelope["signature"]
    texts = {
        "LICENSE": non_empty_file(root.joinpath(*LICENSE_PARTS)),
        "NOTICES.md": non_empty_file(root.joinpath(*NOTICES_PARTS)),
        "MIT_LICENSE.txt": non_empty_file(root.joinpath(*MIT_PARTS)),
    }
    return {
        "tool": "packaging/installer_manifest/gen_release_report.py",
        "version": VERSION,
        "exe": EXE_NAME,
        "sha256": sha if sha is not None else "absent:hash-unverified",
        "built_from_commit": measure_commit(root),
        "signature": signature if signature is not None
        else "absent:no-HASH-envelope",
        "staged": staged,
        "components": measure_components(),
        "bundle": measure_bundle(root),
        "texts": texts,
    }


def hot_write(path: Path, text: str) -> None:
    """Write atomically: temp file in the target folder + replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(
        prefix=".report-", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as out:
            out.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def build_parser() -> argparse.ArgumentParser:
    """CLI: --out optional, --root optional (defaults to repo root)."""
    parser = argparse.ArgumentParser(
        prog="gen_release_report.py",
        description=(
            "Build the installer-manifest release report from real "
            "files and write release_report.json atomically."
        ),
    )
    parser.add_argument(
        "--out",
        default=None,
        help="report JSON to write "
        "(default: <root>/packaging/installer_manifest/release_report.json)",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="checkout root to inspect (default: derived from file)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point: measure, serialize, hot-write. See module docs."""
    args = build_parser().parse_args(argv)
    root = Path(args.root) if args.root else repo_root_default()
    out = Path(args.out) if args.out else root.joinpath(*REPORT_PARTS)
    try:
        report = build_report(root)
        text = json.dumps(report, indent=2, sort_keys=True,
                          ensure_ascii=False) + "\n"
        hot_write(out, text)
    except OSError as exc:
        sys.stderr.write(f"gen_release_report: ERROR: {exc}\n")
        return 2
    sys.stdout.write(f"gen_release_report: wrote {out}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
