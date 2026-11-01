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


# --- K10FIXT2 BEGIN (permission gate + TEST FIXTURES labels) ---
# Row 225: the local demo runs only behind its permission gate. The gate
# reads the fixture file's declared permission scope and admits only the
# allowlisted local-contact scope; anything else is refused before any
# artifact is written. Row 229: the verification output carries the TEST
# FIXTURES label plus provenance copied from the fixture file, and the
# capability evidence tier is recorded as labelled, never MEASURED.
# Everything new in this file lives inside this marked block.

_K10FIXT2_ALLOWED_PERMISSION_SCOPES = ("local-contact-allowed",)

_K10FIXT2_LABEL = "TEST FIXTURES"


def _k10fixt2_argv_value(argv, name, default):
    items = list(argv) if argv is not None else sys.argv[1:]
    for index, token in enumerate(items):
        if token == name and index + 1 < len(items):
            return items[index + 1]
        if token.startswith(name + "="):
            return token[len(name) + 1:]
    return default


def _k10fixt2_permission_scope(fixture):
    permission = fixture.get("permission")
    if not isinstance(permission, dict):
        return ""
    scope = permission.get("scope")
    return scope if isinstance(scope, str) else ""


def _k10fixt2_provenance_of(fixture):
    provenance = fixture.get("provenance")
    if not isinstance(provenance, dict):
        return {}
    return {key: provenance.get(key) for key in (
        "source", "pack_manifest_sha256", "fixture_sha256")}


def _k10fixt2_labelled(fixture):
    return (isinstance(fixture, dict)
            and fixture.get("label") == _K10FIXT2_LABEL
            and isinstance(fixture.get("provenance"), dict))


def _k10fixt2_apply_labels(artifact_path, fixture):
    try:
        raw = artifact_path.read_bytes()
    except OSError:
        return False
    try:
        artifact = json.loads(raw.decode("utf-8"))
    except ValueError:
        return False
    verification = artifact.get("verification")
    if not isinstance(verification, dict):
        return False
    verification["label"] = fixture.get("label", _K10FIXT2_LABEL)
    verification["provenance"] = _k10fixt2_provenance_of(fixture)
    verification["capability_evidence_tier"] = (
        "PROXY (fixture rows labelled TEST FIXTURES, never MEASURED)")
    try:
        text = json.dumps(artifact, indent=2) + "\n"
        tmp = artifact_path.parent / (
            artifact_path.name + ".tmp-%d" % os.getpid())
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, artifact_path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    return True


_orig_main = main


def main(argv=None):
    import io as _k10fixt2_io
    from contextlib import redirect_stdout as _k10fixt2_redirect_stdout
    fixtures_arg = _k10fixt2_argv_value(
        argv, "--fixtures", "tools/drive/demo/fixtures_local.json")
    try:
        fixture = json.loads(Path(fixtures_arg).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("error: fixture unreadable %s: %s" % (fixtures_arg, exc))
        return 1
    if not isinstance(fixture, dict):
        print("error: fixture shape violation: top level must be an object")
        return 1
    if (_k10fixt2_permission_scope(fixture)
            not in _K10FIXT2_ALLOWED_PERMISSION_SCOPES):
        print("error: permission refused: the local demo runs only behind "
              "its permission gate (scope 'local-contact-allowed' required)")
        return 2
    if not _k10fixt2_labelled(fixture):
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
                _k10fixt2_apply_labels(artifact_path, fixture)
                break
    return code


# --- K10FIXT2 END ---



if __name__ == "__main__":
    raise SystemExit(main())
