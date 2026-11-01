"""Lane B forced-failure detection demo (FROZEN-C2DEMO-V1)."""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

MODEL_LABEL = "meta/muse-spark-1.3-contributor"
DEMO_NAME = "DEMO-FORCED-FAILURE"
WATCHER_RULE = "watcher-integrity/forced-failure-detection-v1"
FAILURE_CLASS = "OUTPUT_FORMAT_FAILURE"
CAUSE_CODE = "FORCED_FAILURE_DETECTED"
DEFAULT_OUT = "tools/drive/demo/artifacts"
DEFAULT_FIXTURES = "tools/drive/demo/fixtures_remote.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Forced-failure demo")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--fixtures", default=DEFAULT_FIXTURES)
    return parser.parse_args(argv)


def build_run_id(fixture_bytes: bytes) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    digest = hashlib.sha256(fixture_bytes).hexdigest()
    seq = int(digest[:8], 16) % 10000
    return f"DEMO-4-{today}-{seq:04d}"


def load_fixtures(path: str) -> tuple[dict[str, object], bytes]:
    raw = Path(path).read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("fixtures file must hold a JSON object")
    return dict(data), raw


def build_artifact(
    run_id: str, fixtures: dict[str, object], digest: str
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
            "status": "FAILED",
        },
        {
            "attempt_no": 2,
            "run_attempt_sequence": 2,
            "attempt_type": "FALLBACK",
            "provider": "cloud",
            "model": MODEL_LABEL,
            "route": "CLOUD",
            "status": "SUCCEEDED",
        },
    ]
    verification: dict[str, object] = {
        "result": "FAIL",
        "failure_class": FAILURE_CLASS,
    }
    audit: dict[str, object] = {
        "result": "FAIL",
        "audit_requirement": audit_policy,
    }
    cause: dict[str, object] = {
        "code": CAUSE_CODE,
        "detail": f"first leg failed with {FAILURE_CLASS}",
        "fallback": "FALLBACK correction recorded as attempt 2",
        "telemetry_event_id": f"telemetry-{digest[:12]}",
    }
    return {
        "run_id": run_id,
        "demo": DEMO_NAME,
        "model": MODEL_LABEL,
        "endpoint": endpoint,
        "fixture_class": fixture_class,
        "attempts": attempts,
        "verification": verification,
        "audit": audit,
        "watcher_rule": WATCHER_RULE,
        "exit_code": 0,
        "cause": cause,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        fixtures, raw = load_fixtures(str(args.fixtures))
        run_id = build_run_id(raw)
        digest = hashlib.sha256(raw).hexdigest()
        artifact = build_artifact(run_id, fixtures, digest)
        verification = artifact["verification"]
        audit = artifact["audit"]
        assert isinstance(verification, dict)
        assert isinstance(audit, dict)
        if verification.get("result") == "FAIL":
            if audit.get("result") == "PASS":
                print("error: audit PASS on failed verification")
                return 1
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
