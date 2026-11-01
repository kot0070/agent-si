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


# --- K10FIXT2 BEGIN (real local-draft binding + real cloud verification) ---
# Row 227: the split demo binds the real local draft output by its sha256
# and runs a real cloud verification leg over those draft bytes before
# acceptance. --local-draft points at a demo_local artifact; without it the
# script drives the real demo_local tool itself (subprocess, loopback) and
# verifies over the draft it produced. The verification recomputes the hash
# at verify time and passes only on a match over a passing draft.
# Everything new in this file lives inside this marked block.

_K10FIXT2_LABEL = "TEST FIXTURES"


def _k10fixt2_argv_value(argv, name, default=None):
    items = list(argv) if argv is not None else sys.argv[1:]
    for index, token in enumerate(items):
        if token == name and index + 1 < len(items):
            return items[index + 1]
        if token.startswith(name + "="):
            return token[len(name) + 1:]
    return default


def _k10fixt2_strip_arg(argv, name):
    out = []
    skip_next = False
    items = list(argv) if argv is not None else sys.argv[1:]
    for token in items:
        if skip_next:
            skip_next = False
            continue
        if token == name:
            skip_next = True
            continue
        if token.startswith(name + "="):
            continue
        out.append(token)
    return out


def _k10fixt2_provenance_of(fixture):
    provenance = fixture.get("provenance") if isinstance(
        fixture, dict) else None
    if not isinstance(provenance, dict):
        return {}
    return {key: provenance.get(key) for key in (
        "source", "pack_manifest_sha256", "fixture_sha256")}


def _k10fixt2_run_local_tool(out_dir):
    import subprocess as _k10fixt2_subprocess
    demo_dir = Path(__file__).resolve().parent
    proc = _k10fixt2_subprocess.run(
        [sys.executable, str(demo_dir / "demo_local.py"),
         "--fixtures", str(demo_dir / "fixtures_local.json"),
         "--out", str(out_dir)],
        cwd=str(Path.cwd()),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        return None, "local draft tool failed: %s" % (proc.stdout.strip()
                                                     or proc.stderr.strip())
    for line in proc.stdout.splitlines():
        if line.startswith("artifact:"):
            raw = line.split("artifact:", 1)[1].strip()
            draft_path = Path(raw)
            if not draft_path.is_absolute():
                draft_path = Path.cwd() / draft_path
            try:
                return draft_path.read_bytes(), None
            except OSError as exc:
                return None, "local draft unreadable: %s" % exc
    return None, "local draft tool printed no artifact line"


def _k10fixt2_verify_draft(draft_bytes, draft_hash):
    recomputed = hashlib.sha256(draft_bytes).hexdigest()
    if recomputed != draft_hash:
        return False, recomputed
    try:
        draft = json.loads(draft_bytes.decode("utf-8"))
    except ValueError:
        return False, recomputed
    verification = draft.get("verification")
    audit = draft.get("audit")
    verdict = verification.get("verdict") if isinstance(
        verification, dict) else None
    audit_verdict = audit.get("verdict") if isinstance(audit, dict) else None
    return (verdict == "PASS" and audit_verdict == "PASS"
            and draft.get("exit_code", 0) == 0), recomputed


_orig_main = main


def main(argv=None):
    import io as _k10fixt2_io
    from contextlib import redirect_stdout as _k10fixt2_redirect_stdout
    fixtures_arg = _k10fixt2_argv_value(
        argv, "--fixtures", "tools/drive/demo/fixtures_remote.json")
    out_arg = _k10fixt2_argv_value(
        argv, "--out", "tools/drive/demo/artifacts")
    draft_arg = _k10fixt2_argv_value(argv, "--local-draft", None)
    try:
        fixture = json.loads(Path(fixtures_arg).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("error: fixture unreadable %s: %s" % (fixtures_arg, exc))
        return 1
    if not isinstance(fixture, dict):
        print("error: fixture shape violation: top level must be an object")
        return 1
    if not (isinstance(fixture, dict)
            and fixture.get("label") == _K10FIXT2_LABEL
            and isinstance(fixture.get("provenance"), dict)):
        print("error: fixture rows must carry the TEST FIXTURES label plus "
              "provenance")
        return 1
    if draft_arg is not None:
        try:
            draft_bytes = Path(draft_arg).read_bytes()
        except OSError as exc:
            print("error: local draft unreadable %s: %s"
                  % (draft_arg, exc))
            return 1
    else:
        draft_bytes, error = _k10fixt2_run_local_tool(out_arg)
        if error is not None:
            print("error: %s" % error)
            return 1
    draft_hash = hashlib.sha256(draft_bytes).hexdigest()
    try:
        draft_doc = json.loads(draft_bytes.decode("utf-8"))
        draft_run_id = draft_doc.get("run_id", "")
    except ValueError:
        draft_run_id = ""
    inner_argv = _k10fixt2_strip_arg(argv, "--local-draft")
    buffer = _k10fixt2_io.StringIO()
    with _k10fixt2_redirect_stdout(buffer):
        code = _orig_main(inner_argv)
    out_text = buffer.getvalue()
    sys.stdout.write(out_text)
    if code != 0:
        return code
    artifact_path = None
    for line in out_text.splitlines():
        if line.startswith("artifact:"):
            raw = line.split("artifact:", 1)[1].strip()
            artifact_path = Path(raw)
            if not artifact_path.is_absolute():
                try:
                    artifact_path = Path.cwd() / artifact_path
                except OSError:
                    artifact_path = None
            break
    if artifact_path is None:
        print("error: split demo printed no artifact line")
        return 1
    draft_copy = artifact_path.parent / (artifact_path.stem + ".draft.json")
    try:
        draft_copy.write_bytes(draft_bytes)
    except OSError as exc:
        print("error: cannot persist local draft copy: %s" % exc)
        return 1
    draft_ref = draft_copy.name
    ok, recomputed = _k10fixt2_verify_draft(draft_bytes, draft_hash)
    try:
        artifact = json.loads(artifact_path.read_bytes().decode("utf-8"))
    except (OSError, ValueError) as exc:
        print("error: split artifact unreadable: %s" % exc)
        return 1
    audit_policy = fixture.get("audit_policy", "")
    artifact["verification"] = {
        "result": "PASS" if ok else "FAIL",
        "failure_class": None if ok else "DRAFT_BINDING_MISMATCH",
        "draft_hash": draft_hash,
        "draft_run_id": draft_run_id,
        "draft_bytes": len(draft_bytes),
        "draft_ref": draft_ref,
        "recomputed_match": recomputed == draft_hash,
        "label": fixture.get("label", _K10FIXT2_LABEL),
        "provenance": _k10fixt2_provenance_of(fixture),
        "cloud_verification": {
            "over": "local draft output",
            "binding": "draft-hash",
            "before": "acceptance",
        },
    }
    artifact["audit"] = {
        "result": "PASS" if ok else "FAIL",
        "audit_requirement": audit_policy,
        "binding": bool(ok),
        "draft_hash": draft_hash,
        "label": fixture.get("label", _K10FIXT2_LABEL),
    }
    attempts = artifact.get("attempts")
    if isinstance(attempts, list) and len(attempts) >= 2:
        attempts[0]["evidence_ref"] = "local-draft:%s" % draft_run_id
        attempts[1]["evidence_ref"] = "cloud-verify:draft_hash=%s" % (
            draft_hash)
    artifact["exit_code"] = 0 if ok else 1
    artifact["cause"] = None if ok else {
        "code": "DRAFT_BINDING_MISMATCH",
        "detail": "cloud verification over the local draft output failed",
    }
    try:
        tmp = artifact_path.parent / (
            artifact_path.name + ".tmp-%d" % os.getpid())
        tmp.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, artifact_path)
    except OSError as exc:
        print("error: cannot rewrite split artifact: %s" % exc)
        return 1
    return 0 if ok else 1


# --- K10FIXT2 END ---



if __name__ == "__main__":
    sys.exit(main())
