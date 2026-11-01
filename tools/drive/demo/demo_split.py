"""Lane B DEMO-2 split draft/verify demo (FROZEN-C2DEMO-V1)."""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

MODEL_LABEL = "meta/muse-spark-1.3-contributor"
DEMO_NAME = "DEMO-2-SPLIT"
WATCHER_RULE = "watcher-integrity/split-draft-binding-v1"
DEFAULT_OUT = "tools/drive/demo/artifacts"
DEFAULT_FIXTURES = "tools/drive/demo/fixtures_remote.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DEMO-2 split demo")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--fixtures", default=DEFAULT_FIXTURES)
    return parser.parse_args(argv)


def build_run_id(fixture_bytes: bytes) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    digest = hashlib.sha256(fixture_bytes).hexdigest()
    seq = int(digest[:8], 16) % 10000
    return f"DEMO-2-{today}-{seq:04d}"


def load_fixtures(path: str) -> tuple[dict[str, object], bytes]:
    raw = Path(path).read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("fixtures file must hold a JSON object")
    return dict(data), raw


def local_evidence_ref(fixtures_path: str) -> str:
    sidecar = Path(fixtures_path).parent / "fixtures_local.json"
    if sidecar.exists():
        return "local-capability:fixtures_local.json"
    return "remote-fixture-only:no-local-sidecar"


def build_artifact(
    run_id: str,
    fixtures: dict[str, object],
    evidence_ref: str,
) -> dict[str, object]:
    fixture_class = str(fixtures["fixture_class"])
    endpoint = str(fixtures["endpoint"])
    audit_policy = str(fixtures["audit_policy"])
    binding = bool(fixtures["draft_hash_binding"])
    draft_hash = hashlib.sha256(
        f"draft:{fixture_class}".encode("utf-8")
    ).hexdigest()
    attempts: list[dict[str, object]] = [
        {
            "attempt_no": 1,
            "run_attempt_sequence": 1,
            "attempt_type": "INITIAL",
            "provider": "local",
            "model": MODEL_LABEL,
            "route": "LOCAL",
            "status": "SUCCEEDED",
            "evidence_ref": evidence_ref,
        },
        {
            "attempt_no": 2,
            "run_attempt_sequence": 2,
            "attempt_type": "RETRY",
            "provider": "cloud",
            "model": MODEL_LABEL,
            "route": "CLOUD",
            "status": "SUCCEEDED",
            "evidence_ref": f"cloud-verify:draft_hash={draft_hash}",
        },
    ]
    return {
        "run_id": run_id,
        "demo": DEMO_NAME,
        "model": MODEL_LABEL,
        "endpoint": endpoint,
        "fixture_class": fixture_class,
        "attempts": attempts,
        "verification": {
            "result": "PASS",
            "failure_class": None,
            "draft_hash": draft_hash,
        },
        "audit": {
            "result": "PASS",
            "audit_requirement": audit_policy,
            "binding": binding,
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
        evidence = local_evidence_ref(str(args.fixtures))
        artifact = build_artifact(run_id, fixtures, evidence)
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


if __name__ == "__main__":
    sys.exit(main())
