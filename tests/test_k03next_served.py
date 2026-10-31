"""K03NEXT served rows: 7, 199, 200, 201, 246, R-338, R-347, R-355, R-368,
M-P1-41 through the real seam app (create_app) with TestClient loopback.

Every row drives its owning served route; no network, no doubles. Unique
ids (k03next-*) keep the global audit/stage/catalog stores isolated from
every other test file. RED LIST starts at 0 items: any route that answers
404 here becomes a defect line plus a fix in this lane.
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
from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "k03next-served-token"
ACTOR = "tester-k03next"

#: Exact shipped-preset contributor model id (never reworded).
CONTRIBUTOR_MODEL = "meta/muse-spark-1.3-contributor"

#: Auditor model outside the contributor set; plain test data standing in
#: for a provider model id at the model-provider boundary.
AUDITOR_MODEL = "meta/muse-spark-1.3-auditor"

CONTRACT = "contract-hash-k03next"


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
        json={"name": "k03next", "folder_ref": "folder-k03next"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    project_id = resp.json()["project"]["project_id"]
    resp = client.post(
        "/api/v1/projects/%s/tasks" % project_id,
        json={"title": title, "scope": ["scope-k03next"]},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    task = resp.json()["task"]
    return project_id, task["task_id"]


def _body(project_id, task_id, run_id, proj_dir, evidence="ev-k03next-1",
          candidates="eligible", implementers="contributor",
          with_pair_reuse=True):
    if implementers == "contributor":
        implementer_ids = [CONTRIBUTOR_MODEL]
    else:
        implementer_ids = list(implementers)
    if candidates == "eligible":
        auditor_candidates = [{
            "provider_id": "provider-k03next-a",
            "model": AUDITOR_MODEL,
            "capability_evidence_refs": ["cap-ev-k03next-1"],
        }]
    elif candidates == "contributor":
        auditor_candidates = [{
            "provider_id": "provider-k03next-b",
            "model": CONTRIBUTOR_MODEL,
            "capability_evidence_refs": ["cap-ev-k03next-2"],
        }]
    else:
        auditor_candidates = []
    payload = {
        "project_id": project_id,
        "task_id": task_id,
        "run_id": run_id,
        "contract_hash": CONTRACT,
        "project_dir": str(proj_dir),
        "work_refs": ["work-k03next-1"],
        "artifact_refs": ["art-k03next-1"],
        "evidence_refs": [evidence],
        "producer_session_refs": ["sess-prod-k03next-1"],
        "tool_rows": [
            {"tool": "writer", "evidence_ref": evidence, "ok": True},
        ],
        "criteria": [{
            "ac_id": "ac-k03next-1",
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
            "decision_id": "pair-k03next-%s" % run_id,
            "project_id": project_id,
            "scope": "scope-k03next-%s" % run_id,
            "statement": "reuse auditor pair for repeat turn",
            "reason": "same scope repeat, recorded before reuse",
            "authority": "USER",
            "decided_by": ACTOR,
            "visible_to_user": True,
            "user_resolution_ref": "resolve-k03next-%s" % run_id,
        }
    return payload


def test_row7_assurance_on_served_turn(client, dirs):
    """Row 7: the served turn verifies, fresh-audits, then closes."""
    _store, proj = dirs
    project_id, task_id = _create_task(client)
    tag = _tag()
    run_id = "run-k03next-r7-%s" % tag
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
    assert data["close_row_id"] and audit_id in data["close_row_id"]
    stored = audit_records._fetch_record(audit_id)
    assert stored is not None
    assert stored.run_id == run_id
    assert stored.contract_hash == CONTRACT
    turns = client.get("/api/v1/tasks/%s/turns" % task_id).json()["turns"]
    assert any(
        audit_id in trip["action"]
        and data["close_row_id"] in trip["observation"]
        for trip in turns
    )
    second_run = "run-k03next-r7b-%s" % tag
    resp2 = client.post(
        "/api/v1/assurance/finalize",
        json=_body(project_id, task_id, second_run, proj),
        headers=_auth(),
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["audit_id"] != audit_id


def test_row199_pass_only_after_assertion(client, dirs):
    """Row 199: no PASS verdict without the passing verification assertion."""
    _store, proj = dirs
    project_id, task_id = _create_task(client)
    run_id = "run-k03next-r199-%s" % _tag()
    bad = _body(project_id, task_id, run_id, proj,
                evidence="ev-missing-k03next")
    bad["tool_rows"] = [
        {"tool": "writer", "evidence_ref": "ev-other-k03next", "ok": True},
    ]
    resp = client.post(
        "/api/v1/assurance/finalize",
        json=bad,
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["verification_result"] != "PASS"
    assert data["phase"] == "VERIFY_REFUSED"
    assert data["audit_id"] is None
    assert data["close_row_id"] is None
    assert audit_records._records_for_run(run_id) == ()
    turns = client.get("/api/v1/tasks/%s/turns" % task_id).json()["turns"]
    assert turns and "audit-" not in turns[-1]["action"]
    good_run = "run-k03next-r199b-%s" % _tag()
    resp2 = client.post(
        "/api/v1/assurance/finalize",
        json=_body(project_id, task_id, good_run, proj),
        headers=_auth(),
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["verification_result"] == "PASS"
    assert resp2.json()["audit_id"]


def test_row200_catalog_versions_changelog(client):
    """Row 200: versions record with a change note; the changelog reads back."""
    ref = "k03next-catalog-row200"
    resp = client.post(
        "/api/v1/teststage/catalog/versions/record",
        json={"catalog_ref": ref, "version": 1,
              "change_notes": "initial frozen set",
              "recorded_at": "2026-10-30T00:00:00+00:00"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["version"] == 1

    resp = client.get(
        "/api/v1/teststage/catalog/changelog", params={"catalog_ref": ref})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["rows"]) == 1

    resp = client.post(
        "/api/v1/teststage/catalog/versions/record",
        json={"catalog_ref": ref, "version": 2, "change_notes": "  ",
              "recorded_at": "2026-10-30T00:00:00+00:00"},
    )
    assert resp.status_code == 400, resp.text
    assert "CHANGELOG_ENTRY_MISSING" in resp.text

    resp = client.post(
        "/api/v1/teststage/catalog/proposals",
        json={"catalog_ref": ref, "from_version": 1, "to_version": 2,
              "changes": ["add t-k03next probe"],
              "proposed_at": "2026-10-30T00:00:00+00:00"},
    )
    assert resp.status_code == 200, resp.text
    proposal = resp.json()
    assert proposal["status"] == "PENDING"
    assert "t-k03next" in proposal["changelog"]

    resp = client.post(
        "/api/v1/teststage/catalog/proposals/approve",
        json={"proposal_id": "prop-nope-row200", "approver": "owner",
              "approved": True, "decided_at": "2026-10-30T00:00:00+00:00"},
    )
    assert resp.status_code == 400, resp.text
    assert "PROPOSAL_NOT_FOUND" in resp.text

    resp = client.post(
        "/api/v1/teststage/catalog/proposals/approve",
        json={"proposal_id": proposal["proposal_id"], "approver": "owner",
              "approved": True, "decided_at": "2026-10-30T00:00:00+00:00"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "APPROVED"

    resp = client.post(
        "/api/v1/teststage/catalog/proposals/approve",
        json={"proposal_id": proposal["proposal_id"], "approver": "owner",
              "approved": True, "decided_at": "2026-10-30T00:00:00+00:00"},
    )
    assert resp.status_code == 400, resp.text
    assert "PROPOSAL_ALREADY_DECIDED" in resp.text

    resp = client.get(
        "/api/v1/teststage/catalog/changelog", params={"catalog_ref": ref})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["rows"]) == 2


def test_row201_runner_contract_plus_user_approval(client):
    """Row 201: project profile in, evidence out; user runners need approval."""
    profile = {"project_id": "k03next-proj201", "profile_name": "default",
               "runtime": "local", "base_id": "base-code-fast"}
    resp = client.post(
        "/api/v1/teststage/runners/run",
        json={"profile": profile, "test_id": "t-boot",
              "runner_id": "builtin-code"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["evidence_ref"].startswith("evidence://k03next-proj201/")
    assert body["contract_version"] == "runner-contract/1"

    resp = client.post(
        "/api/v1/teststage/runners/run",
        json={"profile": profile, "test_id": "t-boot",
              "runner_id": "user-k03next-custom"},
    )
    assert resp.status_code == 400, resp.text
    assert "UNAPPROVED_USER_RUNNER" in resp.text

    resp = client.post(
        "/api/v1/teststage/runners/approve",
        json={"runner_id": "user-k03next-custom", "approver": "owner"},
    )
    assert resp.status_code == 200, resp.text

    resp = client.post(
        "/api/v1/teststage/runners/run",
        json={"profile": profile, "test_id": "t-boot",
              "runner_id": "user-k03next-custom"},
    )
    assert resp.status_code == 200, resp.text
    assert "user-k03next-custom" in resp.json()["evidence_ref"]

    resp = client.post(
        "/api/v1/teststage/runners/run",
        json={"profile": profile, "test_id": "t-boot", "runner_id": ""},
    )
    assert resp.status_code == 400, resp.text
    assert "UNKNOWN_RUNNER" in resp.text

    resp = client.post(
        "/api/v1/teststage/runners/run",
        json={"profile": {"project_id": "", "runtime": "local"},
              "test_id": "t-boot", "runner_id": "builtin-code"},
    )
    assert resp.status_code == 400, resp.text
    assert "RUNNER_PROFILE_INVALID" in resp.text


def test_row246_test_stage_proof_filed(client):
    """Row 246: every recorded result files its proof (output ref)."""
    tag = _tag()
    project_id = "k03next-proj246-%s" % tag
    plan_id = "plan-k03next-246-%s" % tag
    run_id = "run-k03next-246-%s" % tag
    resp = client.post(
        "/api/v1/teststage/runs/start",
        json={"project_id": project_id, "plan_id": plan_id,
              "run_id": run_id},
    )
    assert resp.status_code == 200, resp.text

    resp = client.post(
        "/api/v1/teststage/runs/results",
        json={"run_id": run_id, "test_id": "t-k03next-246-a",
              "status": "PASS", "output_ref": "out://proof-246-a",
              "reason": None},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["output_ref"] == "out://proof-246-a"

    resp = client.post(
        "/api/v1/teststage/runs/results",
        json={"run_id": run_id, "test_id": "t-k03next-246-b",
              "status": "PASS", "output_ref": "out://proof-246-b",
              "reason": None},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["output_ref"] == "out://proof-246-b"

    refused = client.post(
        "/api/v1/teststage/runs/results",
        json={"run_id": run_id, "test_id": "t-k03next-246-c",
              "status": "BLOCKED", "output_ref": "out://proof-246-c",
              "reason": None},
    )
    assert refused.status_code == 400, refused.text
    assert "STATUS_REASON_MISSING" in refused.text

    resp = client.post(
        "/api/v1/teststage/runs/results",
        json={"run_id": run_id, "test_id": "t-k03next-246-c",
              "status": "BLOCKED", "output_ref": "out://proof-246-c",
              "reason": "waiting on owner sign-off"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["output_ref"] == "out://proof-246-c"

    counters = client.get(
        "/api/v1/teststage/runs/counters", params={"run_id": run_id})
    assert counters.status_code == 200, counters.text
    assert counters.json()["passed"] == 2


def test_row_r338_tests_from_catalog(client):
    """Row R-338: the served plan derives its tests from catalog ids."""
    tag = _tag()
    resp = client.post(
        "/api/v1/teststage/plans",
        json={"catalog_ids": ["t-boot", "t-login", "t-ai-judge"],
              "project_id": "k03next-proj338-%s" % tag,
              "run_id": "run-k03next-338-%s" % tag,
              "catalog_ref": "catalog-frozen-v1",
              "derived_by_model": CONTRIBUTOR_MODEL},
    )
    assert resp.status_code == 200, resp.text
    plan = resp.json()
    assert plan["test_ids"] == ["t-boot", "t-login", "t-ai-judge"]
    assert plan["kind_counts"] == {"CODE": 2, "AI": 1}

    refused = client.post(
        "/api/v1/teststage/plans",
        json={"catalog_ids": ["not-a-catalog-id!!"],
              "project_id": "k03next-proj338-%s" % tag,
              "run_id": "run-k03next-338-bad-%s" % tag,
              "catalog_ref": "catalog-frozen-v1",
              "derived_by_model": CONTRIBUTOR_MODEL},
    )
    assert refused.status_code == 400, refused.text
    assert "UNKNOWN_TEST_ID" in refused.text

    empty = client.post(
        "/api/v1/teststage/plans",
        json={"catalog_ids": [],
              "project_id": "k03next-proj338-%s" % tag,
              "run_id": "run-k03next-338-empty-%s" % tag,
              "catalog_ref": "catalog-frozen-v1",
              "derived_by_model": CONTRIBUTOR_MODEL},
    )
    assert empty.status_code == 400, empty.text
    assert "EMPTY_TEST_PLAN" in empty.text


def test_row_r347_local_tests_switch(client):
    """Row R-347: local tests default ON; the one switch flips per project."""
    project = "k03next-proj347-%s" % _tag()
    resp = client.get(
        "/api/v1/teststage/local-tests", params={"project_id": project})
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is True

    resp = client.post(
        "/api/v1/teststage/local-tests",
        json={"project_id": project, "enabled": False,
              "updated_at": "2026-10-30T00:00:00+00:00"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is False

    resp = client.get(
        "/api/v1/teststage/local-tests", params={"project_id": project})
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is False

    resp = client.post(
        "/api/v1/teststage/local-tests",
        json={"project_id": project, "enabled": True,
              "updated_at": "2026-10-30T00:00:00+00:00"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is True


def _stage_start(client, project_id, plan_id, run_id):
    resp = client.post(
        "/api/v1/teststage/runs/start",
        json={"project_id": project_id, "plan_id": plan_id,
              "run_id": run_id},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _stage_record(client, run_id, test_id):
    resp = client.post(
        "/api/v1/teststage/runs/results",
        json={"run_id": run_id, "test_id": test_id, "status": "PASS",
              "output_ref": "out://%s" % test_id, "reason": None},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_row_r355_every_pass_audited(client, dirs):
    """Row R-355: the served PASS finish carries a stored PASS audit."""
    _store, proj = dirs
    project_id, task_id = _create_task(client)
    tag = _tag()
    run_id = "run-k03next-r355-%s" % tag
    plan_id = "plan-k03next-r355-%s" % tag
    _stage_start(client, project_id, plan_id, run_id)
    _stage_record(client, run_id, "t-k03next-355-1")
    resp = client.post(
        "/api/v1/teststage/runs/finish",
        json=_body(project_id, task_id, run_id, proj),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["state"] == "RESULTS"
    assert data["verification_result"] == "PASS"
    audit_id = data["audit_id"]
    assert audit_id and audit_id.startswith("audit-")
    stored = audit_records._fetch_record(audit_id)
    assert stored is not None
    assert stored.run_id == run_id
    assert stored.contract_hash == CONTRACT
    assert data["verdict"] == stored.result.value
    turns = client.get("/api/v1/tasks/%s/turns" % task_id).json()["turns"]
    assert any(
        audit_id in trip["action"]
        and stored.result.value in trip["observation"]
        for trip in turns
    )
    refused_run = "run-k03next-r355-refused-%s" % tag
    refused_plan = "plan-k03next-r355-refused-%s" % tag
    _stage_start(client, project_id, refused_plan, refused_run)
    _stage_record(client, refused_run, "t-k03next-355-2")
    bad = _body(project_id, task_id, refused_run, proj,
                evidence="ev-missing-k03next-355")
    bad["tool_rows"] = [
        {"tool": "writer", "evidence_ref": "ev-other-k03next-355",
         "ok": True},
    ]
    resp = client.post("/api/v1/teststage/runs/finish", json=bad)
    assert resp.status_code == 200, resp.text
    assert resp.json()["audit_id"] is None
    assert audit_records._records_for_run(refused_run) == ()


def test_row_r368_plan_kinds_sum(client):
    """Row R-368: per-kind counts on the served plan sum to the total."""
    tag = _tag()
    resp = client.post(
        "/api/v1/teststage/plans",
        json={"catalog_ids": ["t-boot", "t-ai-judge", "t-manual-check"],
              "project_id": "k03next-proj368-%s" % tag,
              "run_id": "run-k03next-368-%s" % tag,
              "catalog_ref": "catalog-frozen-v1",
              "derived_by_model": CONTRIBUTOR_MODEL},
    )
    assert resp.status_code == 200, resp.text
    plan = resp.json()
    counts = plan["kind_counts"]
    assert counts == {"CODE": 1, "AI": 1, "HUMAN": 1}
    assert sum(counts.values()) == len(plan["test_ids"]) == 3
    assert plan["priority"] == ["t-boot", "t-ai-judge", "t-manual-check"]
    assert len(plan["oracle_refs"]) == 3


def test_row_mp1_41_stage_close_leaves_queryable_row(client, dirs):
    """Row M-P1-41: closing the stage leaves a row the counters expose."""
    _store, proj = dirs
    project_id, task_id = _create_task(client)
    tag = _tag()
    run_id = "run-k03next-mp141-%s" % tag
    plan_id = "plan-k03next-mp141-%s" % tag
    _stage_start(client, project_id, plan_id, run_id)
    _stage_record(client, run_id, "t-k03next-mp141-1")
    resp = client.post(
        "/api/v1/teststage/runs/finish",
        json=_body(project_id, task_id, run_id, proj),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["state"] == "RESULTS"
    assert data["phase"] == "CLOSED"
    audit_id = data["audit_id"]
    assert audit_id and audit_id.startswith("audit-")
    close_row_id = data["close_row_id"]
    assert close_row_id and audit_id in close_row_id

    counters = client.get(
        "/api/v1/teststage/runs/counters", params={"run_id": run_id})
    assert counters.status_code == 200, counters.text
    queried = counters.json()
    assert queried["audit_id"] == audit_id
    assert queried["close_row_id"] == close_row_id
    assert queried["verdict"] == data["verdict"]
    assert queried["phase"] == "CLOSED"
