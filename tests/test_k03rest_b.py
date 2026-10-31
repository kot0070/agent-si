"""K03REST2 coder-B rows arch_622, mvp_accept_117, mvp_accept_224 served proof.

Each row drives its owning served route through the real seam
(create_app with TestClient loopback) plus its owning seam function;
no network, no doubles. Unique ids (k03rest-b-*) keep the global
stage/catalog/registry stores isolated from every other test file.
"""

import os
import sys
import uuid

from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.assurance import audit_coordinator  # noqa: E402
from agent_si.assurance import audit_registry  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "k03rest-b-served-token"

#: Exact shipped-preset contributor model id (never reworded).
CONTRIBUTOR_MODEL = "meta/muse-spark-1.3-contributor"

CONTRACT = "contract-hash-k03rest-b"


class _K03restAudit(audit_coordinator.AuditCoordinator):
    """Concrete binding of the real audit entries; adds no behavior."""


class _K03restRegistry(audit_registry.AuditorRegistry):
    """Concrete binding of the real sourcing entries; adds no behavior."""


def _tag():
    return uuid.uuid4().hex[:12]


def _client(tmp_path):
    store = tmp_path / "store-b"
    store.mkdir(exist_ok=True)
    settings = {"ui_session_token": TEST_TOKEN, "store_dir": str(store)}
    return TestClient(create_app(dict(settings)))


def test_k03rest_b_arch_622_served(tmp_path):
    """ARCH-622: missing evidence fails the criterion closed, never silent."""
    client = _client(tmp_path)
    tag = _tag()
    criterion = "crit-k03rest-b-622-%s" % tag

    resp = client.post(
        "/api/v1/k03rest/evidence_criterion",
        json={"criterion_id": criterion, "evidence_refs": []},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["criterion_id"] == criterion
    assert data["result"] == "FAIL"
    assert data["silent_pass"] is False

    resp = client.post(
        "/api/v1/k03rest/evidence_criterion",
        json={"criterion_id": criterion, "evidence_refs": ["ev-k03rest-b-%s" % tag]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["result"] == "PASS"
    assert resp.json()["silent_pass"] is False

    bad = client.post(
        "/api/v1/k03rest/evidence_criterion",
        json={"criterion_id": "", "evidence_refs": []},
    )
    assert bad.status_code == 400, bad.text

    seam = _K03restAudit()
    assert seam.fail_criterion_on_missing_evidence(criterion, ()) == "FAIL"
    assert seam.fail_criterion_on_missing_evidence(
        criterion, ("ev-k03rest-b-%s" % tag,)) == "PASS"


def test_k03rest_b_mvp_accept_117_served(tmp_path):
    """MVP_ACCEPT-117: re-audit bounded by the correction budget (limit 2)."""
    client = _client(tmp_path)
    tag = _tag()
    project = "k03rest-b-117-%s" % tag
    task = "task-k03rest-b-117-%s" % tag
    run = "run-k03rest-b-117-%s" % tag
    payload = {
        "project_id": project,
        "task_id": task,
        "run_id": run,
        "contract_hash": CONTRACT,
        "work_refs": ["work-k03rest-b-117-%s" % tag],
        "artifact_refs": ["art-k03rest-b-117-%s" % tag],
        "evidence_refs": ["ev-k03rest-b-117-%s" % tag],
        "producer_session_refs": ["sess-prod-k03rest-b-117-%s" % tag],
        "reaudits": 2,
    }
    resp = client.post("/api/v1/k03rest/correction_budget", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    rows = data["audits"]
    assert len(rows) == 3, rows
    assert len({row["audit_id"] for row in rows}) == 3, rows
    assert rows[0]["result"] == "BLOCKED"
    assert rows[0]["handling"] == "BLOCK"
    assert rows[2]["result"] == "REWORK"
    assert rows[2]["handling"] == "ESCALATE"
    assert data["budget"] == {
        "scope_id": "%s/%s/%s" % (project, task, CONTRACT),
        "used": 2,
        "limit": 2,
    }
    assert data["fresh_sessions_distinct"] is True

    empty = client.post(
        "/api/v1/k03rest/correction_budget",
        json=dict(payload, run_id="run-k03rest-b-117-empty-%s" % tag,
                  work_refs=[], artifact_refs=[]),
    )
    assert empty.status_code == 400, empty.text

    seam = _K03restAudit()
    first = seam.audit_with_fresh_auditor(audit_coordinator.ServedTurn(
        turn_ref="turn-k03rest-b-117-%s" % tag,
        project_id="k03rest-b-117-seam-%s" % tag,
        task_id="task-k03rest-b-117-seam-%s" % tag,
        run_id="run-k03rest-b-117-seam-%s" % tag,
        work_refs=("work-k03rest-b-117-seam-%s" % tag,),
        artifact_refs=("art-k03rest-b-117-seam-%s" % tag,),
        evidence_refs=("ev-k03rest-b-117-seam-%s" % tag,),
        producer_session_refs=("sess-k03rest-b-117-seam-%s" % tag,),
        contract_hash=CONTRACT,
    ))
    second = seam.reaudit(first, None)
    third = seam.reaudit(second, None)
    assert len({first, second, third}) == 3
    budget = seam.remaining_correction_budget(
        "k03rest-b-117-seam-%s/task-k03rest-b-117-seam-%s/%s"
        % (tag, tag, CONTRACT))
    assert budget.limit == 2


def test_k03rest_b_mvp_accept_224_served(tmp_path):
    """MVP_ACCEPT-224: unresolved provider dependency fails closed w/options."""
    client = _client(tmp_path)
    tag = _tag()
    provider = "provider-k03rest-b-224-%s" % tag
    model = "model-k03rest-b-224-%s" % tag
    scope = "scope-k03rest-b-224-%s" % tag

    resp = client.post(
        "/api/v1/k03rest/provider_dependency",
        json={"provider_id": provider, "model": model, "scope": scope,
              "implementer_model_ids": [CONTRIBUTOR_MODEL]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is False
    assert data["provider_id"] == provider
    assert data["model"] == model
    assert data["eligible"] is False
    assert data["code"] == "NO_ELIGIBLE_AUDITOR"
    assert data["disposition"] == "BLOCKED"
    assert data["pass_allowed"] is False
    assert len(data["options"]) == 3
    assert all(isinstance(option, str) and option for option in data["options"])

    bad = client.post(
        "/api/v1/k03rest/provider_dependency",
        json={"provider_id": provider},
    )
    assert bad.status_code == 400, bad.text

    seam = _K03restRegistry()
    seam.register_candidate(audit_registry.AuditorCandidate(
        provider_id=provider,
        provider_instance=None,
        model=model,
        capability_evidence_refs=(),
        registered_at="",
    ))
    assert seam.is_eligible(provider, model) is False
    try:
        seam.select_auditor("served-turn", (CONTRIBUTOR_MODEL,), "L2")
    except audit_registry.NoEligibleAuditorError as exc:
        assert exc.code == "NO_ELIGIBLE_AUDITOR"
    else:  # pragma: no cover - fail-closed must raise
        raise AssertionError("select_auditor passed without eligibility")
    assert seam.sourcing_state(scope) == "BLOCKED"
    resolved = seam.resolve_sourcing(audit_registry.SourcingDecision(
        decision_id="dec-k03rest-b-224-%s" % tag,
        project_id="k03rest-b-224-%s" % tag,
        scope=scope,
        statement="use provider %s auditor" % provider,
        reason="only provider with capability evidence on file",
        authority="USER",
        decided_by="tester-k03rest-b",
        visible_to_user=True,
        user_resolution_ref="resolve-k03rest-b-224-%s" % tag,
        created_at="2026-10-31T00:00:00+00:00",
    ))
    assert resolved.user_resolution_ref == "resolve-k03rest-b-224-%s" % tag
    assert seam.sourcing_state(scope) == "RESOLVED"
