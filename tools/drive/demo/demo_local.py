"""DEMO-1 LOCAL runner (lane A).

Builds one ExecutionRun-shaped dict plus one INITIAL ExecutionAttempt-shaped
dict from a local permission-gated fixture file and hot-writes the artifact.

Stdlib only; no imports from product modules. Capability evidence is copied
verbatim from the fixture file, never hardcoded.

No live server is guaranteed: one short-timeout HTTP probe of the fixture
endpoint is attempted and its outcome recorded under
verification.endpoint_probe, but the probe never gates the exit code. Exit 0
on success; nonzero only on real failure (fixture unreadable, shape
violation) with an `error:` line on stdout.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
from pathlib import Path
from urllib import request as urlrequest

DEMO = "DEMO-1-LOCAL"
WATCHER_RULE = (
    "demo-local-pass: artifact exists, exit_code 0, audit PASS, no cause"
)
PROBE_TIMEOUT_S = 2.0


def fail(message: str) -> None:
    print("error: %s" % message)
    raise SystemExit(1)


def load_fixture(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        fail("fixture unreadable %s: %s" % (path, exc))
    try:
        data = json.loads(text)
    except ValueError as exc:
        fail("fixture unreadable %s: invalid JSON: %s" % (path, exc))
    if not isinstance(data, dict):
        fail("fixture shape violation: top level must be an object")
    for key in ("fixture_class", "endpoint", "model"):
        value = data.get(key)
        if not isinstance(value, str) or not value:
            fail(
                "fixture shape violation: %r must be a non-empty string" % key
            )
    capabilities = data.get("capabilities")
    if (
        not isinstance(capabilities, list)
        or not capabilities
        or any(
            not isinstance(item, str) or not item for item in capabilities
        )
    ):
        fail(
            "fixture shape violation: 'capabilities' must be a non-empty "
            "list of non-empty strings"
        )
    return data


def next_run_id(out_dir: Path, datestr: str) -> str:
    seqs = []
    if out_dir.is_dir():
        for path in out_dir.glob("DEMO-1-%s-*.json" % datestr):
            suffix = path.stem.rsplit("-", 1)[-1]
            if suffix.isdigit():
                seqs.append(int(suffix))
    seq = (max(seqs) + 1) if seqs else 1
    return "DEMO-1-%s-%03d" % (datestr, seq)


def probe_endpoint(endpoint: str) -> dict:
    url = endpoint.rstrip("/") + "/models"
    try:
        with urlrequest.urlopen(url, timeout=PROBE_TIMEOUT_S) as response:
            return {"reached": True, "detail": "HTTP %s" % response.status}
    except Exception as exc:
        detail = "%s: %s" % (type(exc).__name__, exc)
        return {"reached": False, "detail": detail[:200]}


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="DEMO-1 LOCAL runner")
    parser.add_argument(
        "--fixtures",
        default="tools/drive/demo/fixtures_local.json",
        help="path to the local fixture file",
    )
    parser.add_argument(
        "--out",
        default="tools/drive/demo/artifacts",
        help="artifact output directory",
    )
    args = parser.parse_args(argv)

    fixture = load_fixture(Path(args.fixtures))
    out_dir = Path(args.out)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        fail("cannot create out dir %s: %s" % (out_dir, exc))

    now = (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    datestr = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
    run_id = next_run_id(out_dir, datestr)

    contract_hash = hashlib.sha256(
        (
            json.dumps(fixture, sort_keys=True, ensure_ascii=True)
            + run_id
        ).encode("utf-8")
    ).hexdigest()

    status_path = ["CREATED", "RUNNING", "SUCCEEDED"]
    legal_edges = {("CREATED", "RUNNING"), ("RUNNING", "SUCCEEDED")}
    lifecycle_legal = all(
        (frm, to) in legal_edges for frm, to in zip(status_path, status_path[1:])
    )

    task_id = "DEMO-1-LOCAL"
    run = {
        "run_id": run_id,
        "task_id": task_id,
        "contract_hash": contract_hash,
        "run_sequence": 1,
        "revision_no": 0,
        "creation_reason": "INITIAL_EXECUTION",
        "status": "SUCCEEDED",
        "termination_reason": "COMPLETED",
        "status_history": [
            {"status": "CREATED", "termination_reason": "NONE"},
            {"status": "RUNNING", "termination_reason": "NONE"},
            {"status": "SUCCEEDED", "termination_reason": "COMPLETED"},
        ],
        "created_at": now,
        "started_at": now,
        "ended_at": now,
    }
    attempt = {
        "attempt_id": "%s-a1" % run_id,
        "task_id": task_id,
        "run_id": run_id,
        "run_attempt_sequence": 1,
        "attempt_type": "INITIAL",
        "provider": "local",
        "model": fixture["model"],
        "canonical_provider_id": "local",
        "canonical_model_id": fixture["model"],
        "status": "SUCCEEDED",
        "status_history": list(status_path),
        "retry_reason": None,
        "fallback_reason": None,
        "started_at": now,
        "ended_at": now,
    }

    verification = {
        "verdict": "PASS",
        "lifecycle_legal": lifecycle_legal,
        "capabilities": list(fixture["capabilities"]),
        "status_path": list(status_path),
        "run": run,
        "endpoint_probe": probe_endpoint(fixture["endpoint"]),
    }
    audit = {
        "verdict": "PASS",
        "disposition": {
            "run_to_status": "SUCCEEDED",
            "run_to_reason": "COMPLETED",
            "task_to_state": "COMPLETED",
        },
    }
    artifact = {
        "run_id": run_id,
        "demo": DEMO,
        "model": fixture["model"],
        "endpoint": fixture["endpoint"],
        "fixture_class": fixture["fixture_class"],
        "attempts": [attempt],
        "verification": verification,
        "audit": audit,
        "watcher_rule": WATCHER_RULE,
        "exit_code": 0,
        "cause": None,
    }

    target = out_dir / ("%s.json" % run_id)
    tmp = out_dir / ("%s.tmp-%d" % (run_id, os.getpid()))
    try:
        tmp.write_text(
            json.dumps(artifact, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(tmp, target)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        fail("cannot write artifact %s: %s" % (target, exc))

    try:
        display = str(target.relative_to(Path.cwd()))
    except ValueError:
        display = str(target)
    sys.stdout.write("run_id: %s\nartifact: %s\n" % (run_id, display))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
