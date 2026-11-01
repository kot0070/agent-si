"""Lane B DEMO-3 cloud no-data demo (FROZEN-C2DEMO-V1)."""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

MODEL_LABEL = "meta/muse-spark-1.3-contributor"
DEMO_NAME = "DEMO-3-CLOUD"
WATCHER_RULE = "watcher-integrity/cloud-no-data-v1"
CAPABILITY_RULE = "NO-DATA-never-grants-LOCAL"
DEFAULT_OUT = "tools/drive/demo/artifacts"
DEFAULT_FIXTURES = "tools/drive/demo/fixtures_remote.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DEMO-3 cloud demo")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--fixtures", default=DEFAULT_FIXTURES)
    return parser.parse_args(argv)


def build_run_id(fixture_bytes: bytes) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    digest = hashlib.sha256(fixture_bytes).hexdigest()
    seq = int(digest[:8], 16) % 10000
    return f"DEMO-3-{today}-{seq:04d}"


def load_fixtures(path: str) -> tuple[dict[str, object], bytes]:
    raw = Path(path).read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("fixtures file must hold a JSON object")
    return dict(data), raw


def build_artifact(
    run_id: str, fixtures: dict[str, object]
) -> dict[str, object]:
    fixture_class = str(fixtures["fixture_class"])
    endpoint = str(fixtures["endpoint"])
    audit_policy = str(fixtures["audit_policy"])
    attempts: list[dict[str, object]] = [
        {
            "attempt_no": 1,
            "run_attempt_sequence": 1,
            "attempt_type": "INITIAL",
            "provider": "cloud",
            "model": MODEL_LABEL,
            "route": "CLOUD",
            "status": "SUCCEEDED",
            "capability_rule": CAPABILITY_RULE,
        },
        {
            "attempt_no": 2,
            "run_attempt_sequence": 2,
            "attempt_type": "RETRY",
            "provider": "cloud",
            "model": MODEL_LABEL,
            "route": "CLOUD",
            "status": "SUCCEEDED",
            "capability_rule": CAPABILITY_RULE,
        },
    ]
    return {
        "run_id": run_id,
        "demo": DEMO_NAME,
        "model": MODEL_LABEL,
        "endpoint": endpoint,
        "fixture_class": fixture_class,
        "attempts": attempts,
        "verification": {"result": "PASS", "failure_class": None},
        "audit": {
            "result": "PASS",
            "audit_requirement": audit_policy,
            "capability_rule": CAPABILITY_RULE,
        },
        "watcher_rule": WATCHER_RULE,
        "exit_code": 0,
        "cause": None,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        fixtures, raw = load_fixtures(str(args.fixtures))
        run_id = build_run_id(raw)
        artifact = build_artifact(run_id, fixtures)
        out_dir = Path(str(args.out))
        out_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = out_dir / f"{run_id}.json"
        tmp = out_dir / f"{run_id}.tmp-{os.getpid()}"
        try:
            tmp.write_text(
                json.dumps(artifact, indent=2) + "\n", encoding="utf-8"
            )
            os.replace(tmp, artifact_path)
        except OSError:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise
    except Exception as exc:
        print(f"error: {exc}")
        return 1
    print(f"run_id: {run_id}")
    print(f"artifact: {artifact_path.as_posix()}")
    return 0


# --- K10FIXT2 BEGIN (TEST FIXTURES label + provenance) ---
# The cloud demo stays as-is except this marked block, which copies the
# TEST FIXTURES label plus provenance from the fixture file into the
# verification and audit outputs. Fixtures without the label plus
# provenance are refused. Everything new in this file lives inside this
# marked block.

_K10FIXT2_LABEL = "TEST FIXTURES"


def _k10fixt2_argv_value(argv, name, default):
    items = list(argv) if argv is not None else sys.argv[1:]
    for index, token in enumerate(items):
        if token == name and index + 1 < len(items):
            return items[index + 1]
        if token.startswith(name + "="):
            return token[len(name) + 1:]
    return default


def _k10fixt2_provenance_of(fixture):
    provenance = fixture.get("provenance") if isinstance(
        fixture, dict) else None
    if not isinstance(provenance, dict):
        return {}
    return {key: provenance.get(key) for key in (
        "source", "pack_manifest_sha256", "fixture_sha256")}


_orig_main = main


def main(argv=None):
    import io as _k10fixt2_io
    from contextlib import redirect_stdout as _k10fixt2_redirect_stdout
    fixtures_arg = _k10fixt2_argv_value(
        argv, "--fixtures", "tools/drive/demo/fixtures_remote.json")
    try:
        fixture = json.loads(Path(fixtures_arg).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("error: fixture unreadable %s: %s" % (fixtures_arg, exc))
        return 1
    if not (isinstance(fixture, dict)
            and fixture.get("label") == _K10FIXT2_LABEL
            and isinstance(fixture.get("provenance"), dict)):
        print("error: fixture rows must carry the TEST FIXTURES label plus "
              "provenance")
        return 1
    buffer = _k10fixt2_io.StringIO()
    with _k10fixt2_redirect_stdout(buffer):
        code = _orig_main(argv)
    out_text = buffer.getvalue()
    sys.stdout.write(out_text)
    if code == 0:
        for line in out_text.splitlines():
            if line.startswith("artifact:"):
                raw = line.split("artifact:", 1)[1].strip()
                artifact_path = Path(raw)
                if not artifact_path.is_absolute():
                    try:
                        artifact_path = Path.cwd() / artifact_path
                    except OSError:
                        break
                try:
                    artifact = json.loads(
                        artifact_path.read_bytes().decode("utf-8"))
                except (OSError, ValueError):
                    break
                verification = artifact.get("verification")
                if isinstance(verification, dict):
                    verification["label"] = fixture.get(
                        "label", _K10FIXT2_LABEL)
                    verification["provenance"] = (
                        _k10fixt2_provenance_of(fixture))
                audit = artifact.get("audit")
                if isinstance(audit, dict):
                    audit["label"] = fixture.get(
                        "label", _K10FIXT2_LABEL)
                try:
                    tmp = artifact_path.parent / (
                        artifact_path.name + ".tmp-%d" % os.getpid())
                    tmp.write_text(
                        json.dumps(artifact, indent=2) + "\n",
                        encoding="utf-8")
                    os.replace(tmp, artifact_path)
                except OSError:
                    try:
                        tmp.unlink(missing_ok=True)
                    except OSError:
                        pass
                    return 1
                break
    return code


# --- K10FIXT2 END ---



if __name__ == "__main__":
    sys.exit(main())
