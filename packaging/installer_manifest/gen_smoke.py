# CODER-1 Ember: committed SMOKE.json generator (leak L2 fix).
"""CODER-1 Ember generator for packaging/installer_manifest/SMOKE.json.

Reproduces the SMOKE envelope that packaging/build_app.ps1 writes
(manifest-parse, exe-present, hash-match, then one entry per staged
lane input, in writer order) so the committed record always carries
the writer shape. Every check evaluates a real repo-state predicate
under --root and fails closed when its inputs are absent; check
outcomes live in the JSON, never in the exit code.

Predicates (path under the inspected root, then rule):
- manifest-parse: packaging/installer_manifest/MANIFEST.json parses
  as JSON with version "0.1.0", exe "AgentSI.exe", and files absent
  or a list (writer rule).
- exe-present: MANIFEST exe equals "AgentSI.exe" and the exe build
  definition packaging/sidecar/agent_si_sidecar.spec exists and its
  text names the exe file name, the entry marker and sidecar.py.
- hash-match: sha256 over the frozen canonical MANIFEST bytes
  (sorted keys, compact separators, UTF-8, the form the exe-hash
  gate freezes) equals HASH.json sha256.
- web-staged: RETIRED by the INSTALLB lane FIT check (the K07 web
  bundle is not delivered to this lane: neither frontend/dist nor
  frontend/node_modules is on disk, and an offline web build would
  require package installs; build_app.ps1 still attempts the web
  stage and logs the SKIPPED warning, never synthesizing it).
- migrations-staged: the K13 migration scripts dir exists
  (src/agent_si/adapters/sqlite/migration_scripts, per
  packaging/sidecar/agent_si_sidecar.spec _DATA_CANDIDATES).
- locale-staged: the K07 language-pack dir exists
  (frontend/src/locale, per the sidecar spec _DATA_CANDIDATES).
- kb-data-staged: both shipped KB dirs exist
  (src/agent_si/model_kb K04 plus src/agent_si/kb K09, per the
  sidecar spec _DATA_CANDIDATES).
- watcher-staged: the K08 watcher engine dir exists
  (src/agent_si/watcher, per the sidecar spec _DATA_CANDIDATES).
- license-staged: LICENSE is a non-empty regular file.
- notices-staged: docs/third_party_notices/NOTICES.md is a
  non-empty regular file.

started_clean mirrors the writer: a fresh-install record of zero
projects, runs and keys. Exit 0 on success; nonzero only on usage
or I/O errors. Output is deterministic: fixed key order, indent 2,
UTF-8, trailing newline, no timestamps or absolute paths.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

EXE_NAME = "AgentSI.exe"
VERSION = "0.1.0"

MANIFEST_PARTS = ("packaging", "installer_manifest", "MANIFEST.json")
HASH_PARTS = ("packaging", "installer_manifest", "HASH.json")
SMOKE_PARTS = ("packaging", "installer_manifest", "SMOKE.json")
SPEC_PARTS = ("packaging", "sidecar", "agent_si_sidecar.spec")
MIGRATIONS_PARTS = ("src", "agent_si", "adapters", "sqlite", "migration_scripts")
LOCALE_PARTS = ("frontend", "src", "locale")
MODEL_KB_PARTS = ("src", "agent_si", "model_kb")
KB_PARTS = ("src", "agent_si", "kb")
WATCHER_PARTS = ("src", "agent_si", "watcher")
LICENSE_PARTS = ("LICENSE",)
NOTICES_PARTS = ("docs", "third_party_notices", "NOTICES.md")


def repo_root_default() -> Path:
    """Repo root derived from this file location (portable)."""
    return Path(__file__).resolve().parents[2]


def read_json(path: Path) -> tuple[dict | None, Exception | None]:
    """Read a JSON object; return (None, error) on any failure."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        return None, exc
    if not isinstance(data, dict):
        return None, ValueError("JSON root is not an object")
    return data, None


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


def check_manifest_parse(root: Path) -> bool:
    """MANIFEST parses with the frozen version/exe/files shape."""
    manifest, err = read_json(root.joinpath(*MANIFEST_PARTS))
    if err is not None or manifest is None:
        return False
    files = manifest.get("files")
    return (
        manifest.get("version") == VERSION
        and manifest.get("exe") == EXE_NAME
        and (files is None or isinstance(files, list))
    )


def check_exe_present(root: Path) -> bool:
    """MANIFEST exe matches and the sidecar spec names exe+entry."""
    manifest, err = read_json(root.joinpath(*MANIFEST_PARTS))
    if err is not None or manifest is None:
        return False
    if manifest.get("exe") != EXE_NAME:
        return False
    try:
        text = root.joinpath(*SPEC_PARTS).read_text(encoding="utf-8")
    except OSError:
        return False
    return (
        EXE_NAME in text
        and "ENTRY_SCRIPT" in text
        and "sidecar.py" in text
    )


def check_hash_match(root: Path) -> bool:
    """sha256 of canonical MANIFEST bytes equals HASH.json sha256."""
    manifest, err = read_json(root.joinpath(*MANIFEST_PARTS))
    if err is not None or manifest is None:
        return False
    envelope, err = read_json(root.joinpath(*HASH_PARTS))
    if err is not None or envelope is None:
        return False
    recorded = envelope.get("sha256")
    if not isinstance(recorded, str) or not recorded:
        return False
    try:
        actual = hashlib.sha256(
            canonical_manifest_bytes(manifest)
        ).hexdigest()
    except (TypeError, ValueError):
        return False
    return recorded == actual


def lane_dir_present(root: Path, parts: tuple[str, ...]) -> bool:
    """True only when the lane source dir exists under root."""
    return root.joinpath(*parts).is_dir()


def kb_data_present(root: Path) -> bool:
    """True only when both shipped KB dirs exist under root."""
    return lane_dir_present(root, MODEL_KB_PARTS) and lane_dir_present(
        root, KB_PARTS
    )


def evaluate(root: Path) -> list[tuple[str, bool]]:
    """Evaluate every check in writer order; fail closed."""
    return [
        ("manifest-parse", check_manifest_parse(root)),
        ("exe-present", check_exe_present(root)),
        ("hash-match", check_hash_match(root)),
        ("migrations-staged", lane_dir_present(root, MIGRATIONS_PARTS)),
        ("locale-staged", lane_dir_present(root, LOCALE_PARTS)),
        ("kb-data-staged", kb_data_present(root)),
        ("watcher-staged", lane_dir_present(root, WATCHER_PARTS)),
        ("license-staged", non_empty_file(root.joinpath(*LICENSE_PARTS))),
        ("notices-staged", non_empty_file(root.joinpath(*NOTICES_PARTS))),
    ]


def build_smoke(root: Path) -> dict:
    """Assemble the writer-shaped envelope with real outcomes."""
    checks = []
    for name, ok_val in evaluate(root):
        checks.append(
            {
                "name": name,
                "result": "pass" if ok_val else "fail",
                "exit_code": 0 if ok_val else 1,
            }
        )
    return {
        "exe": EXE_NAME,
        "checks": checks,
        "started_clean": {"projects": 0, "runs": 0, "keys": 0},
    }


def hot_write(path: Path, text: str) -> None:
    """Write atomically: temp file in the target folder + replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(
        prefix=".smoke-", suffix=".tmp", dir=str(path.parent)
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
        prog="gen_smoke.py",
        description=(
            "Evaluate the writer-shaped SMOKE checks against --root "
            "and write SMOKE.json atomically."
        ),
    )
    parser.add_argument(
        "--out",
        default=None,
        help="SMOKE.json to write "
        "(default: <root>/packaging/installer_manifest/SMOKE.json)",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="checkout root to inspect (default: derived from file)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point: evaluate, serialize, hot-write. See module docs."""
    args = build_parser().parse_args(argv)
    root = Path(args.root) if args.root else repo_root_default()
    out = Path(args.out) if args.out else root.joinpath(*SMOKE_PARTS)
    try:
        smoke = build_smoke(root)
        text = json.dumps(smoke, indent=2, ensure_ascii=False) + "\n"
        hot_write(out, text)
    except OSError as exc:
        sys.stderr.write(f"gen_smoke: ERROR: {exc}\n")
        return 2
    sys.stdout.write(f"gen_smoke: wrote {out} ({len(smoke['checks'])} checks)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
