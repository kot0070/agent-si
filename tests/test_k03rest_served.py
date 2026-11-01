"""K03REST coder-A rows 1-6 served proof (Ostoja): M-P3-120, M-P4-154,
M-P4-155, M-R-REAL-API, B0B-BP07-14, B0B-BP07-17 through the real seam
app (create_app) with TestClient loopback.

Every row drives its owning served route plus its owning seam function;
no network, no doubles. Unique ids (k03rest-*) keep the global
stage/catalog/registry stores isolated from every other test file.
RED LIST starts at 0 items: any route that answers 404 here becomes a
defect line plus a fix in this lane.
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
from agent_si.qa_catalog import qa_catalog  # noqa: E402
from agent_si.test_runners import permission_ladder  # noqa: E402
from agent_si.test_runners import stage_runner  # noqa: E402
from agent_si.test_runners import test_bases  # noqa: E402
from agent_si.test_runners import test_planner  # noqa: E402

TEST_TOKEN = "k03rest-served-token"
ACTOR = "tester-k03rest"

#: Exact shipped-preset contributor model id (never reworded).
CONTRIBUTOR_MODEL = "meta/muse-spark-1.3-contributor"

#: Auditor model outside the contributor set; plain test data standing in
#: for a provider model id at the model-provider boundary.
AUDITOR_MODEL = "meta/muse-spark-1.3-auditor"

CONTRACT = "contract-hash-k03rest"


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


class _SourcingRegistry(audit_registry.AuditorRegistry):
    """Concrete test binding of the real sourcing entries; adds nothing."""


def _create_task(client, title="assure me"):
    resp = client.post(
        "/api/v1/projects",
        json={"name": "k03rest", "folder_ref": "folder-k03rest"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    project_id = resp.json()["project"]["project_id"]
    resp = client.post(
        "/api/v1/projects/%s/tasks" % project_id,
        json={"title": title, "scope": ["scope-k03rest"]},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    task = resp.json()["task"]
    return project_id, task["task_id"]


def _body(project_id, task_id, run_id, proj_dir, evidence="ev-k03rest-1",
          candidates="eligible", implementers="contributor",
          task_class="served-turn", minimum_level="L2",
          with_pair_reuse=True):
    if implementers == "contributor":
        implementer_ids = [CONTRIBUTOR_MODEL]
    else:
        implementer_ids = list(implementers)
    if candidates == "eligible":
        auditor_candidates = [{
            "provider_id": "provider-k03rest-a",
            "model": AUDITOR_MODEL,
            "capability_evidence_refs": ["cap-ev-k03rest-1"],
        }]
    elif candidates == "contributor":
        auditor_candidates = [{
            "provider_id": "provider-k03rest-b",
            "model": CONTRIBUTOR_MODEL,
            "capability_evidence_refs": ["cap-ev-k03rest-2"],
        }]
    elif candidates == "bare":
        auditor_candidates = [{
            "provider_id": "provider-k03rest-c",
            "model": AUDITOR_MODEL,
            "capability_evidence_refs": [],
        }]
    else:
        auditor_candidates = []
    payload = {
        "project_id": project_id,
        "task_id": task_id,
        "run_id": run_id,
        "contract_hash": CONTRACT,
        "project_dir": str(proj_dir),
        "work_refs": ["work-k03rest-1"],
        "artifact_refs": ["art-k03rest-1"],
        "evidence_refs": [evidence],
        "producer_session_refs": ["sess-prod-k03rest-1"],
        "tool_rows": [
            {"tool": "writer", "evidence_ref": evidence, "ok": True},
        ],
        "criteria": [{
            "ac_id": "ac-k03rest-1",
            "evidence_required": True,
            "evidence_refs": [evidence],
            "severity": "MEDIUM",
            "verification_method": "grounded-evidence",
        }],
        "implementer_model_ids": implementer_ids,
        "auditor_candidates": auditor_candidates,
        "task_class": task_class,
        "minimum_level": minimum_level,
    }
    if with_pair_reuse:
        payload["pair_reuse"] = {
            "decision_id": "pair-k03rest-%s" % run_id,
            "project_id": project_id,
            "scope": "scope-k03rest-%s" % run_id,
            "statement": "reuse auditor pair for repeat turn",
            "reason": "same scope repeat, recorded before reuse",
            "authority": "USER",
            "decided_by": ACTOR,
            "visible_to_user": True,
            "user_resolution_ref": "resolve-k03rest-%s" % run_id,
        }
    return payload


def test_k03rest_m_p3_120_served(client):
    """M-P3-120: four built-in bases with CODE/AI/HUMAN kinds, plus attach."""
    resp = client.get("/api/v1/teststage/bases")
    assert resp.status_code == 200, resp.text
    rows = resp.json()["bases"]
    builtin = [row for row in rows if row["origin"] == "builtin"]
    assert len(builtin) == 4, rows
    assert [row["base_id"] for row in builtin] == list(
        test_bases.BUILTIN_TEST_BASES)
    assert [row["kind"] for row in builtin] == ["CODE", "CODE", "AI", "HUMAN"]

    resp = client.post(
        "/api/v1/teststage/bases/attach",
        json={"base_id": "user-k03rest-base", "kind": "QUANTUM"},
    )
    assert resp.status_code == 400, resp.text
    assert "UNKNOWN_EXECUTION_KIND" in resp.text

    base_id = "user-k03rest-base-%s" % _tag()
    resp = client.post(
        "/api/v1/teststage/bases/attach",
        json={"base_id": base_id, "kind": "CODE"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["origin"] == "attached"

    resp = client.post(
        "/api/v1/teststage/bases/attach",
        json={"base_id": base_id, "kind": "CODE"},
    )
    assert resp.status_code == 400, resp.text
    assert "BASE_ALREADY_ATTACHED" in resp.text

    assert test_bases.base_kind(base_id) == "CODE"
    assert [row.base_id for row in test_bases.list_bases()[:4]] == list(
        test_bases.BUILTIN_TEST_BASES)
    with pytest.raises(Exception) as exc_info:
        test_bases.base_kind("base-nope-k03rest")
    assert getattr(exc_info.value, "code", "") == "UNKNOWN_TEST_BASE"


def test_k03rest_m_p4_154_served(client):
    """M-P4-154: local tests default ON globally, per-project switch, view."""
    project = "k03rest-proj154-%s" % _tag()
    assert qa_catalog.local_tests_enabled(project) is True
    resp = client.get(
        "/api/v1/teststage/local-tests", params={"project_id": project})
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is True

    resp = client.post(
        "/api/v1/teststage/local-tests",
        json={"project_id": project, "enabled": False,
              "updated_at": "2026-10-31T00:00:00+00:00"},
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
              "updated_at": "2026-10-31T00:00:00+00:00"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is True

    resp = client.get(
        "/api/v1/teststage/tests-view",
        params={"plan_id": "plan-k03rest", "run_id": "run-k03rest"},
    )
    assert resp.status_code == 200, resp.text
    view = resp.json()
    assert view["settings_controls"] == []
    assert view["remaining"] == view["active"] - view["passed"]
    seam = qa_catalog.build_tests_view("plan-k03rest", "run-k03rest")
    assert list(seam.settings_controls) == []


def test_k03rest_m_p4_155_served(client):
    """M-P4-155: catalog plan, one permission dialog each, run view."""
    tag = _tag()
    project = "k03rest-proj155-%s" % tag
    run_id = "run-k03rest-155-%s" % tag
    resp = client.post(
        "/api/v1/teststage/plans",
        json={"catalog_ids": ["t-boot", "t-ai-judge", "t-manual-check"],
              "project_id": project,
              "run_id": run_id,
              "catalog_ref": "catalog-frozen-v1",
              "derived_by_model": CONTRIBUTOR_MODEL},
    )
    assert resp.status_code == 200, resp.text
    plan = resp.json()
    assert plan["test_ids"] == ["t-boot", "t-ai-judge", "t-manual-check"]
    assert plan["kind_counts"] == {"CODE": 1, "AI": 1, "HUMAN": 1}
    assert sum(plan["kind_counts"].values()) == len(plan["test_ids"]) == 3
    assert len(plan["oracle_refs"]) == 3
    seam_plan = test_planner.derive_plan(
        ["t-boot", "t-ai-judge", "t-manual-check"], project, run_id,
        "catalog-frozen-v1", CONTRIBUTOR_MODEL)
    assert test_planner.kind_total(seam_plan) == len(
        seam_plan.test_ids) == 3
    assert dict(seam_plan.kind_counts) == {"CODE": 1, "AI": 1, "HUMAN": 1}

    asked_at = "2026-10-31T00:00:00+00:00"
    resp = client.post(
        "/api/v1/teststage/permissions/ask",
        json={"project_id": project, "asked_at": asked_at},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["rung_ids"] == list(permission_ladder.ladder_rungs())
    assert len(resp.json()["rung_ids"]) == 8

    again = client.post(
        "/api/v1/teststage/permissions/ask",
        json={"project_id": project, "asked_at": asked_at},
    )
    assert again.status_code == 400, again.text
    assert "LADDER_ALREADY_ASKED" in again.text

    resp = client.post(
        "/api/v1/teststage/runs/start",
        json={"project_id": project, "plan_id": plan["plan_id"],
              "run_id": run_id},
    )
    assert resp.status_code == 200, resp.text
    for test_id in ("t-k03rest-155-a", "t-k03rest-155-b"):
        resp = client.post(
            "/api/v1/teststage/runs/results",
            json={"run_id": run_id, "test_id": test_id, "status": "PASS",
                  "output_ref": "out://%s" % test_id, "reason": None},
        )
        assert resp.status_code == 200, resp.text
    counters = client.get(
        "/api/v1/teststage/runs/counters", params={"run_id": run_id})
    assert counters.status_code == 200, counters.text
    assert counters.json()["passed"] == 2
    assert counters.json()["remaining"] == 0
    seam_counters = stage_runner.stage_counters(run_id)
    assert seam_counters.passed == 2
    assert seam_counters.remaining == 0

    resp = client.post(
        "/api/v1/teststage/runs/finish", json={"run_id": run_id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "RESULTS"

    resp = client.post(
        "/api/v1/teststage/permissions/ask",
        json={"project_id": project, "asked_at": asked_at},
    )
    assert resp.status_code == 200, resp.text
    run2 = "run-k03rest-155b-%s" % tag
    resp = client.post(
        "/api/v1/teststage/runs/start",
        json={"project_id": project, "plan_id": plan["plan_id"],
              "run_id": run2},
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        "/api/v1/teststage/runs/results",
        json={"run_id": run2, "test_id": "t-k03rest-155-c",
              "status": "PASS", "output_ref": "out://t-k03rest-155-c",
              "reason": None},
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        "/api/v1/teststage/runs/finish", json={"run_id": run2})
    assert resp.status_code == 200, resp.text


def test_k03rest_m_r_real_api_served(client):
    """M-R-REAL-API: provider leg via gateway, recorded spend, near-cap ASK."""
    tag = _tag()
    project = "k03rest-projapi-%s" % tag
    run_id = "run-k03rest-api-%s" % tag
    leg = {"project_id": project, "task_id": "task-k03rest-api-%s" % tag,
           "run_id": run_id, "estimated_amount": 10.0,
           "provider_request_ref": "preq-k03rest-1-%s" % tag,
           "model": CONTRIBUTOR_MODEL}
    resp = client.post("/api/v1/teststage/runs/spend-leg", json=leg)
    assert resp.status_code == 200, resp.text
    reservation = resp.json()
    assert reservation["reservation_id"].startswith("res-")
    assert reservation["model"] == CONTRIBUTOR_MODEL

    settle = {"settlement": {
        "settlement_id": "stl-k03rest-1-%s" % tag,
        "reservation_id": reservation["reservation_id"],
        "provider_usage_evidence_ref": "usage-k03rest-1-%s" % tag,
        "provider_request_ref": leg["provider_request_ref"],
        "dedupe_key": "dd-k03rest-1-%s" % tag,
        "actual_amount": 9.5,
        "status": "PENDING"}}
    resp = client.post("/api/v1/teststage/runs/spend-settle", json=settle)
    assert resp.status_code == 200, resp.text
    settled = resp.json()
    assert settled["status"] == "SETTLED"
    assert settled["provider_usage_evidence_ref"] == (
        "usage-k03rest-1-%s" % tag)

    near = dict(leg, estimated_amount=950.0,
                provider_request_ref="preq-k03rest-near-%s" % tag,
                run_id="run-k03rest-apinear-%s" % tag)
    resp = client.post("/api/v1/teststage/runs/spend-leg", json=near)
    assert resp.status_code == 200, resp.text
    near_reservation = resp.json()["reservation_id"]
    held = {"settlement": {
        "settlement_id": "stl-k03rest-near-%s" % tag,
        "reservation_id": near_reservation,
        "provider_usage_evidence_ref": "usage-k03rest-near-%s" % tag,
        "provider_request_ref": near["provider_request_ref"],
        "dedupe_key": "dd-k03rest-near-%s" % tag,
        "actual_amount": 940.0,
        "status": "PENDING"}}
    resp = client.post("/api/v1/teststage/runs/spend-settle", json=held)
    assert resp.status_code == 400, resp.text
    assert "CAP_ASK_UNRESOLVED" in resp.text

    with pytest.raises(Exception) as exc_info:
        stage_runner.gateway_spend_leg(
            project, "task-k03rest-x", "run-k03rest-x", 60.0,
            "preq-k03rest-x", CONTRIBUTOR_MODEL)
    assert getattr(exc_info.value, "code", "") == "BUDGET_SOFT_WARN"
    with pytest.raises(Exception) as exc_info:
        stage_runner.gateway_spend_leg(
            project, "task-k03rest-x", "run-k03rest-x", 6000.0,
            "preq-k03rest-x", CONTRIBUTOR_MODEL)
    assert getattr(exc_info.value, "code", "") == "BUDGET_HARD_BLOCKED"


def test_k03rest_b0b_bp07_14_served(client, dirs):
    """B0B-BP07-14: no eligible auditor emits BLOCKED and offers config."""
    _store, proj = dirs
    project_id, task_id = _create_task(client)
    run_id = "run-k03rest-bp0714-%s" % _tag()
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
    assert data["verification_result"] == "PASS"
    assert audit_records._records_for_run(run_id) == ()
    turns = client.get("/api/v1/tasks/%s/turns" % task_id).json()["turns"]
    assert turns and "BLOCKED" in turns[-1]["observation"]

    registry = _SourcingRegistry()
    with pytest.raises(Exception) as exc_info:
        registry.select_auditor("served-turn", (CONTRIBUTOR_MODEL,), "L2")
    assert getattr(exc_info.value, "code", "") == "NO_ELIGIBLE_AUDITOR"
    scope = "scope-k03rest-bp0714-%s" % _tag()
    assert registry.sourcing_state(scope) == "BLOCKED"
    decision = audit_registry.SourcingDecision(
        decision_id="dec-k03rest-bp0714-%s" % scope,
        project_id=project_id,
        scope=scope,
        statement="use provider-k03rest-a auditor",
        reason="only provider with capability evidence on file",
        authority="USER",
        decided_by=ACTOR,
        visible_to_user=True,
        user_resolution_ref="resolve-k03rest-bp0714-%s" % scope,
        created_at="2026-10-31T00:00:00+00:00",
    )
    registry.resolve_sourcing(decision)
    assert registry.sourcing_state(scope) == "RESOLVED"


def test_k03rest_b0b_bp07_17_served(client, dirs):
    """B0B-BP07-17: sourcing stays fail-closed when it cannot complete."""
    _store, proj = dirs
    project_id, task_id = _create_task(client)
    tag = _tag()
    run_id = "run-k03rest-bp0717-%s" % tag
    resp = client.post(
        "/api/v1/assurance/finalize",
        json=_body(project_id, task_id, run_id, proj, candidates="bare"),
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["phase"] == "BLOCKED"
    assert resp.json()["code"] == "NO_ELIGIBLE_AUDITOR"
    assert resp.json()["audit_id"] is None
    assert audit_records._records_for_run(run_id) == ()

    auditor_run = "run-k03rest-bp0717-aud-%s" % tag
    resp = client.post(
        "/api/v1/assurance/finalize",
        json=_body(project_id, task_id, auditor_run, proj,
                   task_class="auditor"),
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["phase"] == "BLOCKED"
    assert resp.json()["audit_id"] is None

    repeat = client.post(
        "/api/v1/assurance/finalize",
        json=_body(project_id, task_id, run_id, proj, candidates="bare",
                   with_pair_reuse=False),
        headers=_auth(),
    )
    assert repeat.status_code == 200, repeat.text
    assert repeat.json()["phase"] == "BLOCKED"
    assert repeat.json()["audit_id"] is None
    assert audit_records._records_for_run(run_id) == ()

    registry = _SourcingRegistry()
    with pytest.raises(Exception) as exc_info:
        registry.select_auditor(
            "served-turn", (CONTRIBUTOR_MODEL, AUDITOR_MODEL), "L2")
    assert getattr(exc_info.value, "code", "") == "NO_ELIGIBLE_AUDITOR"
    with pytest.raises(Exception) as exc_info:
        registry.select_auditor("auditor", (CONTRIBUTOR_MODEL,), "L2")
    assert getattr(exc_info.value, "code", "") == "NO_ELIGIBLE_AUDITOR"
    assert registry.check_separate_model(
        CONTRIBUTOR_MODEL, (CONTRIBUTOR_MODEL,)) is False


def test_k03rest_b0b_bp07_18_served(client):
    """B0B-BP07-18: sourcing gate BLOCKED until sourcing succeeds."""
    resp = client.post(
        "/api/v1/qa/sourcing_gate/basic",
        json={"implementer_model_ids": [CONTRIBUTOR_MODEL],
              "task_class": "served-turn", "minimum_level": "L2"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is False
    assert data["disposition"] == "BLOCKED"
    assert data["code"] == "NO_ELIGIBLE_AUDITOR"
    assert data["pass_prohibited"] is True
    assert data["audit_id"] is None
    assert data["auditor"] is None

    resp = client.post(
        "/api/v1/qa/sourcing_gate/basic",
        json={"implementer_model_ids": [CONTRIBUTOR_MODEL],
              "task_class": "served-turn", "minimum_level": "L2",
              "auditor_candidates": [{
                  "provider_id": "provider-k03rest-18",
                  "model": AUDITOR_MODEL,
                  "capability_evidence_refs": ["cap-ev-k03rest-18"]}]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["disposition"] == "SOURCED"
    assert data["pass_prohibited"] is False
    assert data["auditor"]["model"] == AUDITOR_MODEL
    assert data["auditor"]["model"] not in (CONTRIBUTOR_MODEL,)

    registry = _SourcingRegistry()
    with pytest.raises(Exception) as exc_info:
        registry.select_auditor("served-turn", (CONTRIBUTOR_MODEL,), "L2")
    assert getattr(exc_info.value, "code", "") == "NO_ELIGIBLE_AUDITOR"
    registry.register_candidate(audit_registry.AuditorCandidate(
        provider_id="provider-k03rest-18b", provider_instance=None,
        model=AUDITOR_MODEL,
        capability_evidence_refs=("cap-ev-k03rest-18b",),
        registered_at=""))
    selection = registry.select_auditor(
        "served-turn", (CONTRIBUTOR_MODEL,), "L2")
    assert selection.auditor.model not in (CONTRIBUTOR_MODEL,)

    bad = client.post(
        "/api/v1/qa/sourcing_gate/basic",
        json={"implementer_model_ids": [CONTRIBUTOR_MODEL],
              "auditor_candidates": ["not-an-object"]},
    )
    assert bad.status_code == 400, bad.text


def test_k03rest_b0b_bp07_20_served(client):
    """B0B-BP07-20: registry gate reports eligibility plus lookup verdict."""
    tag = _tag()
    provider = "provider-k03rest-20-%s" % tag
    resp = client.post(
        "/api/v1/qa/registry_gate",
        json={"provider_id": provider, "model": AUDITOR_MODEL,
              "implementer_model_ids": [CONTRIBUTOR_MODEL]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["eligible"] is False
    assert data["code"] == "NO_ELIGIBLE_AUDITOR"
    assert data["disposition"] == "BLOCKED"
    assert data["pass_allowed"] is False

    resp = client.post(
        "/api/v1/qa/registry_gate",
        json={"provider_id": provider, "model": AUDITOR_MODEL,
              "capability_evidence_refs": ["cap-ev-k03rest-20-%s" % tag],
              "implementer_model_ids": [CONTRIBUTOR_MODEL]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["eligible"] is True
    assert data["disposition"] == "SOURCED"
    assert data["pass_allowed"] is True

    registry = _SourcingRegistry()
    registry.register_candidate(audit_registry.AuditorCandidate(
        provider_id=provider, provider_instance=None, model=AUDITOR_MODEL,
        capability_evidence_refs=(), registered_at=""))
    assert registry.is_eligible(provider, AUDITOR_MODEL) is False
    registry.note_capability_evidence(
        provider, AUDITOR_MODEL, "cap-ev-k03rest-20-%s" % tag)
    assert registry.is_eligible(provider, AUDITOR_MODEL) is True

    bad = client.post("/api/v1/qa/registry_gate", json={})
    assert bad.status_code == 400, bad.text


def test_k03rest_sdk_107_served(client):
    """SDK-107: semantic/security verdict FAILs closed, PASSes grounded."""
    from agent_si.assurance import audit_coordinator  # noqa: E402

    tag = _tag()
    crit = "crit-k03rest-107-%s" % tag
    ev = "ev-k03rest-107-%s" % tag
    resp = client.post(
        "/api/v1/qa/semantic_security/lenient",
        json={"criterion_refs": [crit], "evidence_refs": [ev]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["verdict"] == "PASS"
    assert data["checked_criteria"] == 1
    assert data["checked_evidence"] == 1

    resp = client.post(
        "/api/v1/qa/semantic_security/lenient",
        json={"criterion_refs": [crit], "evidence_refs": []},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["verdict"] == "FAIL"

    resp = client.post("/api/v1/qa/semantic_security/lenient", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["verdict"] == "FAIL"

    # Protocol has default bodies; instantiate via a concrete subclass.
    class _ConcreteCoordinator(audit_coordinator.AuditCoordinator):
        pass

    assert _ConcreteCoordinator(
    ).check_semantic_and_security((crit,), (ev,)) == "PASS"
    assert _ConcreteCoordinator(
    ).check_semantic_and_security((crit,), ()) == "FAIL"
