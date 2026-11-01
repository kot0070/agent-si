"""MH-4 served proof (Heron): verifier/auditor runs read-only.

Drives the real app built by create_app through an HTTP test client.
POST /api/v1/qa/verifier_readonly runs the real verification
checker entry over the project dir (tree hash before and after proves
the run changed nothing), judges the verifier write set through the
real R-304 file-contract entry (checked_written must be 0) and mints
one audit through the real audit entry whose stored record proves the
producer session set and the auditor context session are disjoint. A
presented verifier write attempt is refused with VERIFIER_WRITE_REJECTED
before anything runs, minting no audit and changing no file.

Every check drives its owning served route plus its owning seam entry;
no network, no doubles. Unique ids (k03mh4-*) keep the global
registry/records stores isolated from every other test file.
"""

import os
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.assurance import audit_coordinator, audit_records  # noqa: E402
from agent_si.assurance.verification import checker  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "k03mh4-served-token"

CONTRACT = "contract-hash-k03mh4"


@pytest.fixture
def dirs(tmp_path):
    store = tmp_path / "store"
    proj = tmp_path / "proj"
    store.mkdir()
    proj.mkdir()
    return store, proj


@pytest.fixture
def client(dirs):
    store, _proj = dirs
    settings = {"ui_session_token": TEST_TOKEN, "store_dir": str(store)}
    app = create_app(dict(settings))
    return TestClient(app)


def _tag():
    return uuid.uuid4().hex[:12]


def _body(project_dir, evidence="ev-k03mh4-1", producer="sess-prod-k03mh4-1",
          run_id="run-k03mh4-1", attempted_writes=()):
    payload = {
        "project_id": "proj-k03mh4",
        "task_id": "task-k03mh4",
        "run_id": run_id,
        "contract_hash": CONTRACT,
        "project_dir": str(project_dir),
        "tool_rows": [
            {"tool": "writer", "evidence_ref": evidence, "ok": True},
        ],
        "criteria": [{
            "ac_id": "ac-k03mh4-1",
            "evidence_required": True,
            "evidence_refs": [evidence],
            "severity": "MEDIUM",
            "verification_method": "grounded-evidence",
        }],
        "producer_session_refs": [producer],
        "work_refs": ["work-k03mh4-1"],
        "artifact_refs": ["art-k03mh4-1"],
        "evidence_refs": [evidence],
    }
    if attempted_writes:
        payload["attempted_writes"] = list(attempted_writes)
    return payload


def _tree_bytes(project_dir):
    """Map every file under the dir to its bytes (read-only snapshot)."""
    snapshot = {}
    for root, _dirs, files in os.walk(str(project_dir)):
        for name in sorted(files):
            full = os.path.join(root, name)
            with open(full, "rb") as handle:
                snapshot[os.path.relpath(full, str(project_dir))] = (
                    handle.read()
                )
    return snapshot


def test_k03mh4_verifier_readonly_served(client, dirs):
    """MH-4: verifier runs read-only; record proves disjoint sessions."""
    _store, proj = dirs
    tag = _tag()
    evidence = "ev-k03mh4-%s" % tag
    producer = "sess-prod-k03mh4-%s" % tag
    run_id = "run-k03mh4-%s" % tag
    witness = proj / ("witness-%s.txt" % tag)
    witness.write_text("mh4 fixture", encoding="utf-8")

    resp = client.post(
        "/api/v1/qa/verifier_readonly",
        json=_body(proj, evidence=evidence, producer=producer,
                   run_id=run_id),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["verification_result"] == "PASS"
    assert data["verification_id"]
    assert data["tree_files"] >= 1
    assert data["tree_hash_before"] == data["tree_hash_after"]
    assert data["read_only"] is True
    assert data["contract_verdict"] == "PASS"
    assert data["checked_written"] == 0
    assert data["write_set"] == []
    audit_id = data["audit_id"]
    assert audit_id and audit_id.startswith("audit-")
    assert data["auditor_session_ref"]
    assert data["auditor_session_ref"] not in (
        data["producer_session_refs"]
    )
    assert data["producer_auditor_disjoint"] is True

    stored = audit_records._fetch_record(audit_id)
    assert stored is not None
    assert stored.context_session_ref == data["auditor_session_ref"]
    assert stored.context_session_ref not in (
        stored.producer_session_refs
    )
    assert set(stored.producer_session_refs) == {producer}

    before = _tree_bytes(proj)
    record = checker.verify_run(
        project_dir=str(proj),
        tool_rows=tuple(_body(
            proj, evidence=evidence, producer=producer,
            run_id=run_id)["tool_rows"]),
        criteria=tuple(_body(
            proj, evidence=evidence, producer=producer,
            run_id=run_id)["criteria"]),
        project_id="proj-k03mh4",
        task_id="task-k03mh4",
        run_id="run-k03mh4-direct-%s" % tag,
        contract_hash=CONTRACT,
    )
    assert record.result.value == "PASS"
    assert _tree_bytes(proj) == before

    class _Coordinator(audit_coordinator.AuditCoordinator):
        """Concrete binding of the real audit entry; adds nothing."""

    seam = _Coordinator()
    served = audit_coordinator.ServedTurn(
        turn_ref="turn-k03mh4-direct-%s" % tag,
        project_id="proj-k03mh4",
        task_id="task-k03mh4",
        run_id="run-k03mh4-direct-%s" % tag,
        work_refs=("work-k03mh4-1",),
        artifact_refs=("art-k03mh4-1",),
        evidence_refs=(evidence,),
        producer_session_refs=(producer,),
        contract_hash=CONTRACT,
    )
    direct_id = seam.audit_served_turn(served)
    direct = audit_records._fetch_record(direct_id)
    assert direct is not None
    assert direct.context_session_ref not in (producer,)
    assert _tree_bytes(proj) == before


def test_k03mh4_write_attempt_rejected_served(client, dirs):
    """MH-4: verifier write attempt rejected; nothing minted, nothing set."""
    _store, proj = dirs
    tag = _tag()
    evidence = "ev-k03mh4w-%s" % tag
    producer = "sess-prod-k03mh4w-%s" % tag
    run_id = "run-k03mh4w-%s" % tag
    witness = proj / ("witness-%s.txt" % tag)
    witness.write_text("mh4 fixture", encoding="utf-8")
    before = _tree_bytes(proj)

    resp = client.post(
        "/api/v1/qa/verifier_readonly",
        json=_body(proj, evidence=evidence, producer=producer,
                   run_id=run_id,
                   attempted_writes=["write-k03mh4w-%s" % tag]),
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["code"] == "VERIFIER_WRITE_REJECTED"
    assert audit_records._records_for_run(run_id) == ()
    assert _tree_bytes(proj) == before
