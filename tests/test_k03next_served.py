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


# K03NEXT rows B0B-BP07-18/20, B0B-SDK-107, B0B-BP07-53/54,
# B0B-UNCOVERED_ARCH-652/653/654 through the lane-owned k03next seam
# routes (create_app with TestClient loopback).
#
# Every row drives its owning served route plus its owning seam entry;
# no network, no doubles. Unique ids (k03next-b0b-*) keep the global
# registry/records stores isolated from every other test file. RED LIST
# starts at 0 items: any route that answers 404 here becomes a defect
# line plus a fix in this lane (the first run below is that RED: the
# k03next routes do not exist yet).


def _k03next_gate(client, scope, candidates=None, implementers=None,
                  user_authority="USER", with_resolution=True, run_id=None):
    """POST one sourcing-gate probe; resolution defaults to a USER one."""
    body = {
        "scope": scope,
        "implementer_model_ids": (
            [CONTRIBUTOR_MODEL] if implementers is None else implementers
        ),
        "task_class": "served-turn",
        "minimum_level": "L2",
        "auditor_candidates": [] if candidates is None else candidates,
    }
    if run_id is not None:
        body["run_id"] = run_id
    if with_resolution:
        body["user_resolution"] = {
            "decision_id": "dec-k03next-b0b-%s" % scope,
            "scope": scope,
            "statement": "use the sourced auditor for scope %s" % scope,
            "reason": "only USER resolves parked sourcing",
            "authority": user_authority,
            "decided_by": ACTOR,
            "visible_to_user": True,
            "user_resolution_ref": "resolve-k03next-b0b-%s" % scope,
        }
    return client.post("/api/v1/qa/sourcing_gate", json=body)


def _k03next_candidate(provider, model=AUDITOR_MODEL, evidence=()):
    """One auditor candidate payload with the given capability refs."""
    return {
        "provider_id": provider,
        "model": model,
        "capability_evidence_refs": list(evidence),
    }


def test_k03next_b0b_bp07_18(client):
    """B0B-BP07-18: BLOCKED until sourcing succeeds; PASS prohibited."""
    tag = _tag()
    scope = "scope-k03next-b0b-18-%s" % tag

    resp = _k03next_gate(client, scope)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is False
    assert data["disposition"] == "BLOCKED"
    assert data["code"] == "NO_ELIGIBLE_AUDITOR"
    assert data["pass_prohibited"] is True
    assert data["audit_id"] is None
    assert data["auditor"] is None

    good = _k03next_gate(
        client, scope,
        candidates=[_k03next_candidate(
            "provider-k03next-b0b-18-%s" % tag,
            evidence=["cap-ev-k03next-b0b-18-%s" % tag])],
    )
    assert good.status_code == 200, good.text
    sourced = good.json()
    assert sourced["ok"] is True
    assert sourced["disposition"] == "SOURCED"
    assert sourced["code"] is None
    assert sourced["pass_prohibited"] is False
    assert sourced["auditor"]["model"] == AUDITOR_MODEL
    assert sourced["auditor"]["model"] not in [CONTRIBUTOR_MODEL]
    assert sourced["auditor"]["session_ref"].startswith("auditor-session-")

    bad = client.post(
        "/api/v1/qa/sourcing_gate",
        json={"scope": scope, "auditor_candidates": ["not-an-object"]},
    )
    assert bad.status_code == 400, bad.text


def test_k03next_b0b_bp07_20(client):
    """B0B-BP07-20: the registry answers NO_ELIGIBLE_AUDITOR at the gate."""
    from agent_si.assurance import audit_registry  # noqa: E402

    tag = _tag()
    scope = "scope-k03next-b0b-20-%s" % tag
    provider = "provider-k03next-b0b-20-%s" % tag

    resp = _k03next_gate(
        client, scope,
        candidates=[_k03next_candidate(provider)],
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is False
    assert data["disposition"] == "BLOCKED"
    assert data["code"] == "NO_ELIGIBLE_AUDITOR"
    assert data["pass_prohibited"] is True
    assert data["audit_id"] is None
    assert data["auditor"] is None
    assert data["eligibility"] == [{
        "provider_id": provider, "model": AUDITOR_MODEL, "eligible": False,
    }]

    class _Registry(audit_registry.AuditorRegistry):
        """Concrete binding of the real sourcing entries; adds nothing."""

    registry = _Registry()
    try:
        registry.select_auditor("served-turn", (CONTRIBUTOR_MODEL,), "L2")
    except Exception as exc:
        assert getattr(exc, "code", "") == "NO_ELIGIBLE_AUDITOR"
    else:
        raise AssertionError("select_auditor sourced with zero candidates")


def test_k03next_b0b_sdk_107(client):
    """B0B-SDK-107: semantic/security criteria checked beyond schema."""
    from agent_si.assurance import audit_coordinator  # noqa: E402

    tag = _tag()
    crit = "crit-k03next-b0b-107-%s" % tag
    ev = "ev-k03next-b0b-107-%s" % tag

    resp = client.post(
        "/api/v1/qa/semantic_security",
        json={"criterion_refs": [crit], "evidence_refs": [ev]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["verdict"] == "PASS"
    assert data["checked_criteria"] == 1
    assert data["checked_evidence"] == 1

    shapely_but_empty = client.post(
        "/api/v1/qa/semantic_security",
        json={"criterion_refs": [crit], "evidence_refs": []},
    )
    assert shapely_but_empty.status_code == 200, shapely_but_empty.text
    assert shapely_but_empty.json()["verdict"] == "FAIL"

    no_criteria = client.post(
        "/api/v1/qa/semantic_security",
        json={"criterion_refs": [], "evidence_refs": [ev]},
    )
    assert no_criteria.status_code == 200, no_criteria.text
    assert no_criteria.json()["verdict"] == "FAIL"

    bad = client.post(
        "/api/v1/qa/semantic_security",
        json={"criterion_refs": "not-a-list", "evidence_refs": []},
    )
    assert bad.status_code == 400, bad.text

    class _Coordinator(audit_coordinator.AuditCoordinator):
        """Concrete binding of the real check entries; adds nothing."""

    seam = _Coordinator()
    assert seam.check_semantic_and_security((crit,), (ev,)) == "PASS"
    assert seam.check_semantic_and_security((crit,), ()) == "FAIL"
    assert seam.check_semantic_and_security((), (ev,)) == "FAIL"

def test_k03next_b0b_bp07_53(client):
    """B0B-BP07-53: sourcing gated on an explicit USER decision."""
    tag = _tag()
    scope = "scope-k03next-b0b-53-%s" % tag
    candidates = [_k03next_candidate(
        "provider-k03next-b0b-53-%s" % tag,
        evidence=["cap-ev-k03next-b0b-53-%s" % tag])]

    parked = _k03next_gate(client, scope, candidates=candidates,
                           with_resolution=False)
    assert parked.status_code == 200, parked.text
    assert parked.json()["disposition"] == "BLOCKED"
    assert parked.json()["pass_prohibited"] is True
    assert parked.json()["auditor"] is None

    non_user = _k03next_gate(client, scope, candidates=candidates,
                             user_authority="MANAGER")
    assert non_user.status_code == 200, non_user.text
    assert non_user.json()["disposition"] == "BLOCKED"
    assert non_user.json()["code"] == "SOURCING_UNRESOLVED"
    assert non_user.json()["auditor"] is None

    resolved = _k03next_gate(client, scope, candidates=candidates)
    assert resolved.status_code == 200, resolved.text
    data = resolved.json()
    assert data["disposition"] == "SOURCED"
    assert data["sourcing_state"] == "RESOLVED"
    assert data["auditor"]["model"] == AUDITOR_MODEL


def test_k03next_b0b_bp07_54(client):
    """B0B-BP07-54: fail-closed BLOCKED until the USER resolves sourcing."""
    tag = _tag()
    scope = "scope-k03next-b0b-54-%s" % tag
    run_id = "run-k03next-b0b-54-%s" % tag
    candidates = [_k03next_candidate(
        "provider-k03next-b0b-54-%s" % tag,
        evidence=["cap-ev-k03next-b0b-54-%s" % tag])]

    resp = _k03next_gate(client, scope, candidates=candidates,
                         with_resolution=False, run_id=run_id)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is False
    assert data["disposition"] == "BLOCKED"
    assert data["code"] == "SOURCING_UNRESOLVED"
    assert data["pass_prohibited"] is True
    assert data["audit_id"] is None
    assert data["auditor"] is None
    assert data["options"], "BLOCKED sourcing must document how to resolve"
    assert any("USER" in option for option in data["options"])
    assert audit_records._records_for_run(run_id) == ()

    resolved = _k03next_gate(client, scope, candidates=candidates,
                             run_id=run_id)
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["disposition"] == "SOURCED"
    assert resolved.json()["audit_id"] is None


def test_k03next_b0b_uncovered_arch_652(client):
    """ARCH-652: missing capability evidence keeps the candidate out."""
    from agent_si.assurance import audit_registry  # noqa: E402

    tag = _tag()
    scope = "scope-k03next-b0b-652-%s" % tag
    provider = "provider-k03next-b0b-652-%s" % tag

    resp = _k03next_gate(
        client, scope, candidates=[_k03next_candidate(provider)])
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["disposition"] == "BLOCKED"
    assert data["code"] == "NO_ELIGIBLE_AUDITOR"
    assert data["eligibility"] == [{
        "provider_id": provider, "model": AUDITOR_MODEL, "eligible": False,
    }]

    class _Registry(audit_registry.AuditorRegistry):
        """Concrete binding of the real sourcing entries; adds nothing."""

    registry = _Registry()
    registry.register_candidate(audit_registry.AuditorCandidate(
        provider_id=provider, provider_instance=None, model=AUDITOR_MODEL,
        capability_evidence_refs=(), registered_at=""))
    assert registry.is_eligible(provider, AUDITOR_MODEL) is False
    registry.note_capability_evidence(
        provider, AUDITOR_MODEL, "cap-ev-k03next-b0b-652-%s" % tag)
    assert registry.is_eligible(provider, AUDITOR_MODEL) is True

    evidenced = _k03next_gate(
        client, scope,
        candidates=[_k03next_candidate(
            provider, evidence=["cap-ev-k03next-b0b-652-%s" % tag])],
    )
    assert evidenced.status_code == 200, evidenced.text
    assert evidenced.json()["disposition"] == "SOURCED"
    assert evidenced.json()["eligibility"] == [{
        "provider_id": provider, "model": AUDITOR_MODEL, "eligible": True,
    }]


def test_k03next_b0b_uncovered_arch_653(client):
    """ARCH-653: no eligible auditor forces BLOCKED, never self-audit."""
    tag = _tag()
    scope = "scope-k03next-b0b-653-%s" % tag
    run_id = "run-k03next-b0b-653-%s" % tag

    resp = _k03next_gate(client, scope, run_id=run_id)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is False
    assert data["disposition"] == "BLOCKED"
    assert data["code"] == "NO_ELIGIBLE_AUDITOR"
    assert data["pass_prohibited"] is True
    assert data["audit_id"] is None
    assert data["auditor"] is None
    assert audit_records._records_for_run(run_id) == ()

    auditor_class = _k03next_gate(
        client, scope,
        candidates=[_k03next_candidate(
            "provider-k03next-b0b-653-%s" % tag,
            evidence=["cap-ev-k03next-b0b-653-%s" % tag])],
    )
    assert auditor_class.status_code == 200, auditor_class.text
    assert auditor_class.json()["disposition"] == "SOURCED"

    from agent_si.assurance import audit_registry  # noqa: E402

    class _Registry(audit_registry.AuditorRegistry):
        """Concrete binding of the real sourcing entries; adds nothing."""

    with_auditor_class = client.post(
        "/api/v1/qa/sourcing_gate",
        json={"scope": scope,
              "implementer_model_ids": [CONTRIBUTOR_MODEL],
              "task_class": "auditor", "minimum_level": "L2",
              "auditor_candidates": [_k03next_candidate(
                  "provider-k03next-b0b-653b-%s" % tag,
                  evidence=["cap-ev-k03next-b0b-653b-%s" % tag])],
              "user_resolution": {
                  "decision_id": "dec-k03next-b0b-653b-%s" % tag,
                  "scope": scope,
                  "statement": "auditor task class must fail closed",
                  "reason": "auditor-task-class sourcing never self-sources",
                  "authority": "USER",
                  "decided_by": ACTOR,
                  "visible_to_user": True,
                  "user_resolution_ref": "resolve-k03next-b0b-653b-%s" % tag,
              }},
    )
    assert with_auditor_class.status_code == 200, with_auditor_class.text
    assert with_auditor_class.json()["disposition"] == "BLOCKED"
    assert with_auditor_class.json()["auditor"] is None


def test_k03next_b0b_uncovered_arch_654(client):
    """ARCH-654: L2 holds only while the auditor id leaves the set."""
    from agent_si.assurance import audit_registry  # noqa: E402

    tag = _tag()
    scope = "scope-k03next-b0b-654-%s" % tag

    resp = _k03next_gate(
        client, scope,
        candidates=[_k03next_candidate(
            "provider-k03next-b0b-654-%s" % tag,
            evidence=["cap-ev-k03next-b0b-654-%s" % tag])],
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["disposition"] == "SOURCED"
    assert data["independence_level"] == "L2"
    assert data["separate_model"] is True
    assert data["auditor"]["model"] == AUDITOR_MODEL
    assert data["auditor"]["model"] not in [CONTRIBUTOR_MODEL]

    contributor_only = _k03next_gate(
        client, "scope-k03next-b0b-654b-%s" % tag,
        candidates=[_k03next_candidate(
            "provider-k03next-b0b-654b-%s" % tag,
            model=CONTRIBUTOR_MODEL,
            evidence=["cap-ev-k03next-b0b-654b-%s" % tag])],
    )
    assert contributor_only.status_code == 200, contributor_only.text
    assert contributor_only.json()["disposition"] == "BLOCKED"
    assert contributor_only.json()["code"] == "NO_ELIGIBLE_AUDITOR"
    assert contributor_only.json()["separate_model"] is False

    class _Registry(audit_registry.AuditorRegistry):
        """Concrete binding of the real sourcing entries; adds nothing."""

    registry = _Registry()
    assert registry.check_separate_model(
        AUDITOR_MODEL, (CONTRIBUTOR_MODEL,)) is True
    assert registry.check_separate_model(
        CONTRIBUTOR_MODEL, (CONTRIBUTOR_MODEL,)) is False
