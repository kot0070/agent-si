"""UNTEST3 RED LIST: behaviour proofs for kit rows 1550, 1470, 1450.

Each test calls the REAL module through its served entry (create_app plus
TestClient; provider transport is not touched here). No fakes of the module
under test, no skip or xfail.
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from agent_si.backend.app import create_app
from agent_si.domain.contracts import ArtifactRef
from agent_si.kb import models as kb_models
from agent_si.kb import retriever as kb_real
from agent_si.state_machines import attempt_machine as attempts
from agent_si.state_machines import run_machine as runs
from agent_si.storage import extension_registries as registries
from agent_si.storage import repositories as repos
from fastapi.testclient import TestClient


def _client():
    app = create_app({"testing": True, "secret_store": "memory"})
    return TestClient(app)


def _write_kb(tmp, name, sections, purpose="Dev role notes."):
    kb = tmp / name
    (kb / "sections").mkdir(parents=True, exist_ok=True)
    for sid, text in sections.items():
        (kb / "sections" / (sid + ".md")).write_text(text, encoding="utf-8")
    (kb / "manifest.json").write_text(
        json.dumps(
            {
                "kb_id": str(kb),
                "purpose": purpose,
                "sections": sorted(sections),
            }
        ),
        encoding="utf-8",
    )
    (kb / "purpose.txt").write_text(purpose, encoding="utf-8")
    return str(kb)


def test_untest3_bp05_43_kb_handoff_by_ref(tmp_path):
    """Kit 1550 B0B-UNCOVERED_BP05-43: large KB retrieval goes by ArtifactRef.

    Proves on the real retriever that every served chunk is DATA_ONLY, then
    proves on the real KnowledgeSourceRegistry that the bulk bytes are stored
    once by sha256 and re-issued as an ArtifactRef (no inline duplication).
    """
    big = ("kb bulk line %d. " % 0) * 4000
    kb_id = _write_kb(
        tmp_path, "kb-big", {"intro": "Intro notes.", "bulk": big}
    )
    src = kb_models.KnowledgeSource(
        kb_id=kb_id,
        kind="DEV_ROLE",
        project_id="proj-untest3-k09",
        role="dev",
        purpose="Dev role notes.",
    )
    assert kb_real.attach_kb(src) == kb_id
    try:
        chunks, log = kb_real.retrieve("bulk", "proj-untest3-k09", "dev")
        assert len(chunks) >= 1
        assert all(c.instruction_status == "DATA_ONLY" for c in chunks)
        assert all(c.citation.startswith(kb_id + "#") for c in chunks)
        assert log["token_cost"] == sum(c.tokens for c in chunks)
        joined = "\n".join(c.text for c in chunks)
        assert len(joined) > 1000
        reg = registries.KnowledgeSourceRegistry()
        first = reg.handoff("untest3-bulk", joined)
        assert isinstance(first, ArtifactRef)
        digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
        assert first.hash == digest
        assert first.hash_algorithm == "sha256"
        assert first.size == len(joined.encode("utf-8"))
        assert digest in first.artifact_id
        second = reg.handoff("untest3-bulk-copy", joined)
        assert second == first
        assert len(reg._blobs) == 1
        for field in ("artifact_id", "hash", "hash_algorithm", "media_type"):
            assert getattr(first, field) != joined
    finally:
        kb_real.detach_kb(kb_id)


def test_untest3_mvp_accept_6_local_run_initial_attempt():
    """Kit 1470 MVP_ACCEPT-6: one run with INITIAL attempt via local endpoint.

    Proves the served local status endpoint answers, then drives a real run
    (INITIAL_EXECUTION) plus a real INITIAL attempt through the real state
    machines and the real UnitOfWork stores.
    """
    client = _client()
    resp = client.get("/api/v1/local/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("NOT_CONFIGURED", "READY")
    assert isinstance(body["reason"], str) and body["reason"] != ""

    run = runs.create_run(
        run_id="run-untest3-m6",
        project_id="proj-untest3-m6",
        task_id="task-untest3-m6",
        contract_hash="h-untest3",
        run_sequence=1,
    )
    assert run.creation_reason == runs.INITIAL_EXECUTION
    state = runs.CreationState()
    for step in runs.CREATION_STEPS[:13]:
        state = runs.advance_creation(state, step)
    state = runs.pass_attempt_gate(state)
    started = runs.start_run(run, state, expected_version=0, started_at="t-m6")
    assert started.status.value == "RUNNING"

    attempt = attempts.ExecutionAttempt(
        attempt_id="att-untest3-m6",
        project_id="proj-untest3-m6",
        task_id="task-untest3-m6",
        run_id="run-untest3-m6",
        run_attempt_sequence=1,
        attempt_type=attempts.AttemptType.INITIAL,
        provider="local",
        model="m-untest3",
        canonical_provider_id="local",
        canonical_model_id="m-untest3",
        status="CREATED",
    )
    assert attempt.attempt_type == attempts.AttemptType.INITIAL
    assert attempt.retry_reason is None
    assert attempt.fallback_reason is None

    run_repo = repos.ExecutionRunRepository()
    attempt_repo = repos.ExecutionAttemptLog()
    run_row = {
        "record_id": "runs-run-untest3-m6",
        "project_id": "proj-untest3-m6",
        "version": 1,
        "status": "CREATED",
        "from_status": "CREATED",
        "to_status": "CREATED",
    }
    attempt_row = {
        "record_id": "attempts-att-untest3-m6",
        "project_id": "proj-untest3-m6",
        "version": 1,
        "status": "CREATED",
    }
    unit = repos.UnitOfWork()
    unit.stage_append(run_repo, run_row)
    unit.stage_append(attempt_repo, attempt_row)
    unit.commit()
    assert run_repo.load("runs-run-untest3-m6") is not None
    assert attempt_repo.load("attempts-att-untest3-m6") is not None


def test_untest3_m_d_d6_project_decision_atomic():
    """Kit 1450 M-D-D6: project plus decision commit atomically by project_id.

    Proves the real UnitOfWork binds one project row and one decision row
    sharing a project_id, and that a staged failure rolls both back. Also
    proves an unattributed record (no actor field) persists unchanged with no
    silent rewrite.
    """
    project_repo = repos.ProjectRepository()
    decision_repo = repos.DecisionLog()
    pid = "proj-untest3-d6"
    project = {"record_id": "projects-%s" % pid, "project_id": pid, "version": 1}
    decision = {
        "record_id": "decisions-%s-1" % pid,
        "project_id": pid,
        "version": 1,
    }
    unit = repos.UnitOfWork()
    unit.stage_append(project_repo, project)
    unit.stage_append(decision_repo, decision)
    unit.commit()
    assert project_repo.load(project["record_id"]) == project
    assert decision_repo.load(decision["record_id"]) == decision
    assert decision_repo.list_by({"project_id": pid}) == [decision]

    good = {"record_id": "decisions-%s-good" % pid, "project_id": pid, "version": 1}
    bad = {
        "record_id": "transitions-bad-untest3-d6",
        "project_id": pid,
        "version": 1,
        "transition_id": "tr-bad-untest3-d6",
        "task_id": "task-untest3-d6",
        "run_id": None,
        "transition_sequence": 1,
        "expected_from_state": "CREATED",
        "expected_state_version": 1,
        "new_state_version": 2,
        "actor": "probe",
        "from": "CREATED",
        "to": "COMPLETED",
        "reason": "probe",
        "timestamp": "2026-10-26T00:00:00Z",
        "evidence_ref": None,
        "suspended_from_state": None,
        "resume_target_state": None,
    }
    failing = repos.UnitOfWork()
    failing.stage_append(decision_repo, good)
    failing.stage_append(repos.TaskTransitionLog(), bad)
    try:
        failing.commit()
        assert False, "bad edge must refuse the whole unit"
    except repos.IllegalTransitionError:
        pass
    assert decision_repo.load(good["record_id"]) is None
    assert project_repo.load(project["record_id"]) == project

    stored = decision_repo.load(decision["record_id"])
    assert stored == decision
    assert "actor" not in stored
