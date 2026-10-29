"""K03MNT1 served assurance mount: verify then fresh-audit then finalize.

Drives the real app built by create_app with a store dir through an
HTTP test client. The served finalize runs the real verification
checker, then a real fresh-auditor audit, then closes the stage with
the real close_stage; the audit id, verdict and close row are recorded
onto the task turns so the existing read route exposes them.

RED: POST /api/v1/assurance/finalize is not mounted yet, so every
case below fails (404, no audit record, no turns row).
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

from agent_si.assurance import audit_records  # noqa: E402
from agent_si.assurance import audit_registry  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "k03mnt1-served-token"
ACTOR = "tester-k03mnt1"

#: Exact shipped-preset contributor model id (never reworded).
CONTRIBUTOR_MODEL = "meta/muse-spark-1.3-contributor"

#: Auditor model outside the contributor set; plain test data standing
#: in for a provider model id at the model-provider boundary.
#: FAKE-OF: src/agent_si/providers/registry/provider_api.py.
AUDITOR_MODEL = "meta/muse-spark-1.3-auditor"

CONTRACT = "contract-hash-k03mnt1"


def _auth(token=TEST_TOKEN, actor=ACTOR):
    headers = {}
    if actor is not None:
        headers["x-actor"] = actor
    if token is not None:
        headers["x-ui-session-token"] = token
    return headers


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


def _create_task(client, title="assure me"):
    resp = client.post(
        "/api/v1/projects",
        json={"name": "k03mnt1", "folder_ref": "folder-k03mnt1"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    project_id = resp.json()["project"]["project_id"]
    resp = client.post(
        "/api/v1/projects/%s/tasks" % project_id,
        json={"title": title, "scope": ["scope-k03mnt1"]},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    task = resp.json()["task"]
    return project_id, task["task_id"]


def _body(project_id, task_id, run_id, proj_dir, evidence="ev-k03mnt1-1",
          candidates="eligible", implementers="contributor",
          with_pair_reuse=True):
    if implementers == "contributor":
        implementer_ids = [CONTRIBUTOR_MODEL]
    else:
        implementer_ids = list(implementers)
    if candidates == "eligible":
        auditor_candidates = [{
            "provider_id": "provider-k03mnt1-a",
            "model": AUDITOR_MODEL,
            "capability_evidence_refs": ["cap-ev-k03mnt1-1"],
        }]
    elif candidates == "contributor":
        auditor_candidates = [{
            "provider_id": "provider-k03mnt1-b",
            "model": CONTRIBUTOR_MODEL,
            "capability_evidence_refs": ["cap-ev-k03mnt1-2"],
        }]
    else:
        auditor_candidates = []
    payload = {
        "project_id": project_id,
        "task_id": task_id,
        "run_id": run_id,
        "contract_hash": CONTRACT,
        "project_dir": str(proj_dir),
        "work_refs": ["work-k03mnt1-1"],
        "artifact_refs": ["art-k03mnt1-1"],
        "evidence_refs": [evidence],
        "producer_session_refs": ["sess-prod-k03mnt1-1"],
        "tool_rows": [
            {"tool": "writer", "evidence_ref": evidence, "ok": True},
        ],
        "criteria": [{
            "ac_id": "ac-k03mnt1-1",
            "evidence_required": True,
            "evidence_refs": [evidence],
            "severity": "MEDIUM",
            "verification_method": "grounded-evidence",
        }],
        "implementer_model_ids": implementer_ids,
        "auditor_candidates": auditor_candidates,
        "task_class": "served-turn",
        "minimum_level": "L2",
    }
    if with_pair_reuse:
        payload["pair_reuse"] = {
            "decision_id": "pair-k03mnt1-%s" % run_id,
            "project_id": project_id,
            "scope": "scope-k03mnt1-%s" % run_id,
            "statement": "reuse auditor pair for repeat turn",
            "reason": "same scope repeat, recorded before reuse",
            "authority": "USER",
            "decided_by": ACTOR,
            "visible_to_user": True,
            "user_resolution_ref": "resolve-k03mnt1-%s" % run_id,
        }
    return payload


def test_passing_verification_reaches_fresh_audit_and_close_row(
        client, dirs):
    _store, proj = dirs
    project_id, task_id = _create_task(client)
    tag = _tag()
    run_id = "run-k03mnt1-pass-%s" % tag
    resp = client.post(
        "/api/v1/assurance/finalize",
        json=_body(project_id, task_id, run_id, proj),
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["verification_result"] == "PASS"
    audit_id = data["audit_id"]
    assert audit_id and audit_id.startswith("audit-")
    assert data["auditor"]["model"] == AUDITOR_MODEL
    assert data["auditor"]["model"] not in data["implementer_model_ids"]
    scope = "%s/%s/%s" % (project_id, task_id, CONTRACT)
    assert data["close_row_id"] == "%s/%s/%s" % (task_id, scope, audit_id)
    stored = audit_records._fetch_record(audit_id)
    assert stored is not None
    assert stored.run_id == run_id
    assert stored.contract_hash == CONTRACT
    assert stored.context_session_ref != "sess-prod-k03mnt1-1"
    assert len(stored.producer_session_refs) == 1
    assert stored.context_session_ref not in stored.producer_session_refs
    assert audit_records._records_for_run(run_id) == (stored,)
    decision_id = "pair-k03mnt1-%s" % run_id
    assert audit_registry._find_pair_reuse(decision_id) is not None
    turns = client.get("/api/v1/tasks/%s/turns" % task_id).json()["turns"]
    assert any(
        audit_id in trip["action"]
        and str(stored.result.value) in trip["observation"]
        and data["close_row_id"] in trip["observation"]
        for trip in turns
    )
    second_run = "run-k03mnt1-pass2-%s" % tag
    resp2 = client.post(
        "/api/v1/assurance/finalize",
        json=_body(project_id, task_id, second_run, proj),
        headers=_auth(),
    )
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert data2["audit_id"] != audit_id
    stored2 = audit_records._fetch_record(data2["audit_id"])
    assert stored2.context_session_ref != stored.context_session_ref


def test_failed_verification_never_reaches_audit(client, dirs):
    _store, proj = dirs
    project_id, task_id = _create_task(client)
    run_id = "run-k03mnt1-fail-%s" % _tag()
    payload = _body(project_id, task_id, run_id, proj,
                    evidence="ev-missing-k03mnt1")
    payload["tool_rows"] = [
        {"tool": "writer", "evidence_ref": "ev-other-k03mnt1", "ok": True},
    ]
    resp = client.post(
        "/api/v1/assurance/finalize",
        json=payload,
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["phase"] == "VERIFY_REFUSED"
    assert data["audit_id"] is None
    assert data["close_row_id"] is None
    assert audit_records._records_for_run(run_id) == ()
    turns = client.get("/api/v1/tasks/%s/turns" % task_id).json()["turns"]
    assert turns and "audit-" not in turns[-1]["action"]


def test_contributor_in_auditor_set_is_refused(client, dirs):
    _store, proj = dirs
    project_id, task_id = _create_task(client)
    run_id = "run-k03mnt1-contrib-%s" % _tag()
    resp = client.post(
        "/api/v1/assurance/finalize",
        json=_body(project_id, task_id, run_id, proj,
                   candidates="contributor"),
        headers=_auth(),
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "AUDIT_INDEPENDENCE_REJECTED"
    assert audit_records._records_for_run(run_id) == ()


def test_no_eligible_auditor_gives_blocked(client, dirs):
    _store, proj = dirs
    project_id, task_id = _create_task(client)
    run_id = "run-k03mnt1-noaud-%s" % _tag()
    resp = client.post(
        "/api/v1/assurance/finalize",
        json=_body(project_id, task_id, run_id, proj, candidates="none"),
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["phase"] == "BLOCKED"
    assert data["code"] == "NO_ELIGIBLE_AUDITOR"
    assert data["audit_id"] is None
    assert audit_records._records_for_run(run_id) == ()
    turns = client.get("/api/v1/tasks/%s/turns" % task_id).json()["turns"]
    assert turns and "BLOCKED" in turns[-1]["observation"]


def test_unknown_task_gives_honest_404(client, dirs):
    _store, proj = dirs
    payload = _body("proj-k03mnt1-ghost", "task-k03mnt1-ghost",
                    "run-k03mnt1-ghost", proj, with_pair_reuse=False)
    resp = client.post(
        "/api/v1/assurance/finalize", json=payload, headers=_auth())
    assert resp.status_code == 404, resp.text


def _stage_start(client, project_id, plan_id, run_id):
    resp = client.post(
        "/api/v1/teststage/runs/start",
        json={"project_id": project_id, "plan_id": plan_id,
              "run_id": run_id},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _stage_record(client, run_id, test_id="t-k03mnt1-1"):
    resp = client.post(
        "/api/v1/teststage/runs/results",
        json={"run_id": run_id, "test_id": test_id, "status": "PASS",
              "output_ref": "out://%s" % test_id, "reason": None},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _stage_finish_body(project_id, task_id, run_id, proj_dir,
                       evidence="ev-k03mnt1-1", candidates="eligible",
                       implementers="contributor", with_pair_reuse=True):
    return _body(project_id, task_id, run_id, proj_dir,
                 evidence=evidence, candidates=candidates,
                 implementers=implementers,
                 with_pair_reuse=with_pair_reuse)


def test_stage_finish_runs_assurance_chain_and_closes(client, dirs):
    _store, proj = dirs
    project_id, task_id = _create_task(client)
    tag = _tag()
    run_id = "run-k03mnt1-stage-pass-%s" % tag
    plan_id = "plan-k03mnt1-stage-%s" % tag
    _stage_start(client, project_id, plan_id, run_id)
    _stage_record(client, run_id)
    payload = _stage_finish_body(project_id, task_id, run_id, proj)
    resp = client.post("/api/v1/teststage/runs/finish", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["state"] == "RESULTS"
    assert data["verification_result"] == "PASS"
    audit_id = data["audit_id"]
    assert audit_id and audit_id.startswith("audit-")
    assert data["phase"] == "CLOSED"
    assert data["close_row_id"] and audit_id in data["close_row_id"]
    assert data["verdict"]
    stored = audit_records._fetch_record(audit_id)
    assert stored is not None
    assert stored.run_id == run_id
    assert stored.contract_hash == CONTRACT
    assert stored.context_session_ref != "sess-prod-k03mnt1-1"
    counters = client.get(
        "/api/v1/teststage/runs/counters",
        params={"run_id": run_id}).json()
    assert counters["audit_id"] == audit_id
    assert counters["verdict"] == data["verdict"]
    assert counters["phase"] == "CLOSED"
    turns = client.get("/api/v1/tasks/%s/turns" % task_id).json()["turns"]
    assert any(audit_id in trip["action"]
               and str(stored.result.value) in trip["observation"]
               for trip in turns)
    second_run = "run-k03mnt1-stage-pass2-%s" % tag
    second_plan = "plan-k03mnt1-stage2-%s" % tag
    _stage_start(client, project_id, second_plan, second_run)
    _stage_record(client, second_run)
    resp2 = client.post(
        "/api/v1/teststage/runs/finish",
        json=_stage_finish_body(project_id, task_id, second_run, proj))
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert data2["audit_id"] != audit_id
    stored2 = audit_records._fetch_record(data2["audit_id"])
    assert stored2.context_session_ref != stored.context_session_ref


def test_stage_finish_failed_verify_does_not_close(client, dirs):
    _store, proj = dirs
    project_id, task_id = _create_task(client)
    run_id = "run-k03mnt1-stage-fail-%s" % _tag()
    plan_id = "plan-k03mnt1-stage-fail-%s" % run_id
    _stage_start(client, project_id, plan_id, run_id)
    _stage_record(client, run_id)
    bad = _stage_finish_body(project_id, task_id, run_id, proj,
                             evidence="ev-missing-k03mnt1")
    bad["tool_rows"] = [
        {"tool": "writer", "evidence_ref": "ev-other-k03mnt1", "ok": True},
    ]
    resp = client.post("/api/v1/teststage/runs/finish", json=bad)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["phase"] == "VERIFY_REFUSED"
    assert data["audit_id"] is None
    assert data["close_row_id"] is None
    assert data["state"] != "RESULTS"
    assert audit_records._records_for_run(run_id) == ()
    counters = client.get(
        "/api/v1/teststage/runs/counters",
        params={"run_id": run_id}).json()
    assert counters["phase"] == "VERIFY_REFUSED"
    assert counters["audit_id"] is None
    good = _stage_finish_body(project_id, task_id, run_id, proj)
    resp2 = client.post("/api/v1/teststage/runs/finish", json=good)
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["state"] == "RESULTS"
    assert resp2.json()["audit_id"]


def test_stage_finish_contributor_only_is_refused(client, dirs):
    _store, proj = dirs
    project_id, task_id = _create_task(client)
    run_id = "run-k03mnt1-stage-contrib-%s" % _tag()
    plan_id = "plan-k03mnt1-stage-contrib-%s" % run_id
    _stage_start(client, project_id, plan_id, run_id)
    _stage_record(client, run_id)
    resp = client.post(
        "/api/v1/teststage/runs/finish",
        json=_stage_finish_body(project_id, task_id, run_id, proj,
                                candidates="contributor"))
    assert resp.status_code == 400, resp.text
    assert "AUDIT_INDEPENDENCE_REJECTED" in resp.text
    assert audit_records._records_for_run(run_id) == ()
    counters = client.get(
        "/api/v1/teststage/runs/counters",
        params={"run_id": run_id}).json()
    assert counters["phase"] == "REFUSED"
    assert counters["code"] == "AUDIT_INDEPENDENCE_REJECTED"
    resp2 = client.post(
        "/api/v1/teststage/runs/finish",
        json=_stage_finish_body(project_id, task_id, run_id, proj))
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["state"] == "RESULTS"


def test_stage_finish_no_auditor_gives_blocked(client, dirs):
    _store, proj = dirs
    project_id, task_id = _create_task(client)
    run_id = "run-k03mnt1-stage-noaud-%s" % _tag()
    plan_id = "plan-k03mnt1-stage-noaud-%s" % run_id
    _stage_start(client, project_id, plan_id, run_id)
    _stage_record(client, run_id)
    resp = client.post(
        "/api/v1/teststage/runs/finish",
        json=_stage_finish_body(project_id, task_id, run_id, proj,
                                candidates="none"))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["phase"] == "BLOCKED"
    assert data["code"] == "NO_ELIGIBLE_AUDITOR"
    assert data["audit_id"] is None
    assert data["state"] != "RESULTS"
    assert audit_records._records_for_run(run_id) == ()
    counters = client.get(
        "/api/v1/teststage/runs/counters",
        params={"run_id": run_id}).json()
    assert counters["phase"] == "BLOCKED"
    turns = client.get("/api/v1/tasks/%s/turns" % task_id).json()["turns"]
    assert turns and "BLOCKED" in turns[-1]["observation"]
    resp2 = client.post(
        "/api/v1/teststage/runs/finish",
        json=_stage_finish_body(project_id, task_id, run_id, proj))
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["state"] == "RESULTS"
