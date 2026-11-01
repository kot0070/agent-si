"""K03WIRE served wiring: the 13 unwired K03 rows over create_app routes.

Drives the real app built by create_app through an HTTP test client.
Every row test below drives ONLY its frozen create_app route (the
served claim uses the route, never a direct unit call) over the real
product entries: AuditCoordinator.audit_served_turn (1283|7),
assurance_coordinator.run_assurance (1293|199),
audit_with_fresh_auditor (1300|9-13), record_pair_reuse plus the
unrecorded-reuse refusal (1301|13), the catalog
version/changelog/proposal flow (1317|200), the runner contract
(1318|201), checker.verify_run over real tool rows and real files
(1353|R-304), contributor refusal plus accepted-risk default-off
(1387|R-355), close_stage row ids (1413|M-P1-41), the four built-in
test bases (1425|M-P3-120), the global default-ON switch
(1442|M-P4-154), fail-closed sourcing BLOCKED (1595|B0B-BP07-14) and
the auditor-task-class sourcing refusal (1596|B0B-BP07-17).

RED: the twelve frozen routes are not registered yet, so every row
case below fails (404, no served result).
"""

import json
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

from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "k03wire-served-token"
ACTOR = "tester-k03wire"

#: Exact shipped-preset contributor model id (never reworded).
CONTRIBUTOR_MODEL = "meta/muse-spark-1.3-contributor"

#: Auditor model outside the contributor set; plain test data standing
#: in for a provider model id at the model-provider boundary.
AUDITOR_MODEL = "meta/muse-spark-1.3-auditor"


def _auth(token=TEST_TOKEN, actor=ACTOR):
    headers = {}
    if actor is not None:
        headers["x-actor"] = actor
    if token is not None:
        headers["x-ui-session-token"] = token
    return headers


@pytest.fixture
def client(tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    settings = {"ui_session_token": TEST_TOKEN, "store_dir": str(store)}
    app = create_app(dict(settings))
    return TestClient(app)


def _tag():
    return uuid.uuid4().hex[:12]


def _turn(tag, work=True):
    return {
        "project_id": "k03wire-p-%s" % tag,
        "task_id": "k03wire-t-%s" % tag,
        "run_id": "run-k03wire-%s" % tag,
        "contract_hash": "contract-k03wire-%s" % tag,
        "work_refs": ["work-k03wire-%s" % tag] if work else [],
        "artifact_refs": [],
        "evidence_refs": [],
        "producer_session_refs": [],
    }


def test_1283_served_turn_empty_refused(client):
    tag = _tag()
    refused = client.post(
        "/api/v1/assurance/served-turn", json=_turn(tag, work=False),
        headers=_auth(),
    )
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"]["code"] == "EMPTY_WORK_REFUSED"
    served = client.post(
        "/api/v1/assurance/served-turn", json=_turn(tag, work=True),
        headers=_auth(),
    )
    assert served.status_code == 200, served.text
    assert served.json()["audit_id"]


def test_1293_run_assurance_gate(client, tmp_path):
    tag = _tag()
    proj = tmp_path / ("proj-%s" % tag)
    proj.mkdir()
    body = _turn(tag, work=True)
    body["project_dir"] = str(proj)
    body["tool_rows"] = []
    resp = client.post(
        "/api/v1/assurance/run", json=body, headers=_auth())
    assert resp.status_code == 200, resp.text
    outcome = resp.json()
    assert outcome["phase"] == "VERIFY_REFUSED"
    assert outcome["audit_id"] is None
    assert outcome["finalization_id"] is None
    assert outcome["status_trail"] == ["RUNNING", "VERIFYING", "FAILED"]


def test_1300_fresh_auditor_per_call(client):
    tag = _tag()
    pinned = client.post(
        "/api/v1/assurance/served-turn", json=_turn(tag, work=True),
        headers=_auth(),
    )
    assert pinned.status_code == 200, pinned.text
    assert pinned.json()["audit_id"]
    first = client.post(
        "/api/v1/assurance/fresh-audit", json=_turn(tag, work=True),
        headers=_auth(),
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/v1/assurance/fresh-audit", json=_turn(tag, work=True),
        headers=_auth(),
    )
    assert second.status_code == 200, second.text
    assert first.json()["audit_id"] != second.json()["audit_id"]
    assert (first.json()["audit_session_ref"]
            != second.json()["audit_session_ref"])


def test_1301_pair_reuse_gate(client):
    tag = _tag()
    decision_id = "reuse-k03wire-%s" % tag
    body = _turn(tag, work=True)
    body["decision"] = {
        "decision_id": decision_id,
        "project_id": body["project_id"],
        "scope": "scope-k03wire-%s" % tag,
        "statement": "reuse pair for re-audit",
        "reason": "same pair keeps context",
        "authority": "USER",
        "decided_by": ACTOR,
        "visible_to_user": True,
        "user_resolution_ref": "resolution-%s" % tag,
    }
    body["reuse_ref"] = decision_id
    reused = client.post(
        "/api/v1/assurance/pair-reuse", json=body, headers=_auth())
    assert reused.status_code == 200, reused.text
    assert reused.json()["pair_reuse_decision_id"] == decision_id
    assert reused.json()["reused_audit_id"]
    body = _turn("unrec-%s" % tag, work=True)
    body["reuse_ref"] = "unrecorded-k03wire-%s" % tag
    refused = client.post(
        "/api/v1/assurance/pair-reuse", json=body, headers=_auth())
    assert refused.status_code == 409, refused.text


def test_1317_catalog_version_changelog(client):
    tag = _tag()
    ref = "catalog-k03wire-%s" % tag
    recorded = client.get(
        "/api/v1/teststage/catalog/versions",
        params={"op": "record", "catalog_ref": ref, "version": 1,
                "change_notes": "initial catalog %s" % tag},
    )
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["version"] == 1
    proposed = client.get(
        "/api/v1/teststage/catalog/versions",
        params={"op": "propose", "catalog_ref": ref, "from_version": 1,
                "to_version": 2, "changes": "second change %s" % tag},
    )
    assert proposed.status_code == 200, proposed.text
    assert proposed.json()["status"] == "PENDING"
    proposal_id = proposed.json()["proposal_id"]
    decided = client.get(
        "/api/v1/teststage/catalog/versions",
        params={"op": "approve", "proposal_id": proposal_id,
                "approver": "owner-k03wire", "approved": "true"},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "APPROVED"
    read = client.get(
        "/api/v1/teststage/catalog/versions",
        params={"catalog_ref": ref},
    )
    assert read.status_code == 200, read.text
    assert read.json()["current_version"]["version"] == 2
    assert len(read.json()["changelog"]) == 2


def test_1318_runner_contract(client):
    tag = _tag()
    contract = client.get("/api/v1/teststage/runner-contract")
    assert contract.status_code == 200, contract.text
    assert contract.json()["contract_version"] == "runner-contract/1"
    # FXTESTS1: op=run carries a non-catalog id with no base; unknown
    # ids are refused, never PASS without a real run.
    builtin = client.get(
        "/api/v1/teststage/runner-contract",
        params={"op": "run", "project_id": "k03wire-p-%s" % tag,
                "runtime": "python", "test_id": "t-k03wire-%s" % tag,
                "runner_id": "builtin-k03wire"},
    )
    assert builtin.status_code == 400, builtin.text
    assert builtin.json()["detail"]["code"] == "UNKNOWN_TEST_ID"
    runner_id = "user-k03wire-%s" % tag
    refused = client.get(
        "/api/v1/teststage/runner-contract",
        params={"op": "run", "project_id": "k03wire-p-%s" % tag,
                "runtime": "python", "test_id": "t-k03wire-%s" % tag,
                "runner_id": runner_id},
    )
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"]["code"] == "UNAPPROVED_USER_RUNNER"
    approved = client.get(
        "/api/v1/teststage/runner-contract",
        params={"op": "approve", "runner_id": runner_id,
                "approver": "owner-k03wire"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approved"] is True
    rerun = client.get(
        "/api/v1/teststage/runner-contract",
        params={"op": "run", "project_id": "k03wire-p-%s" % tag,
                "runtime": "python", "test_id": "t-k03wire-%s" % tag,
                "runner_id": runner_id},
    )
    assert rerun.status_code == 400, rerun.text
    assert rerun.json()["detail"]["code"] == "UNKNOWN_TEST_ID"


def test_1353_verify_run(client, tmp_path):
    tag = _tag()
    proj = tmp_path / ("verify-%s" % tag)
    proj.mkdir()
    rows = [
        {"tool": "writer", "evidence_ref": "tool-ev-k03wire-%s" % tag,
         "ok": True},
    ]
    with open(proj / "tool_rows.jsonl", "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    with open(proj / "result.json", "w", encoding="utf-8") as handle:
        handle.write('{"ok": true}\n')
    with open(proj / "tool_rows.jsonl", encoding="utf-8") as handle:
        read_rows = [json.loads(line) for line in handle if line.strip()]
    body = {
        "project_id": "k03wire-p-%s" % tag,
        "task_id": "k03wire-t-%s" % tag,
        "run_id": "run-k03wire-%s" % tag,
        "contract_hash": "contract-k03wire-%s" % tag,
        "project_dir": str(proj),
        "tool_rows": read_rows,
        "criteria": [
            {
                "ac_id": "ac-k03wire-%s" % tag,
                "evidence_required": True,
                "evidence_refs": [
                    "tool-ev-k03wire-%s" % tag, "result.json"],
                "severity": "MEDIUM",
                "verification_method": "grounded-evidence",
            },
        ],
    }
    passed = client.post(
        "/api/v1/assurance/verify-run", json=body, headers=_auth())
    assert passed.status_code == 200, passed.text
    assert passed.json()["verification_id"]
    assert passed.json()["result"] == "PASS"
    body["criteria"] = [
        {
            "ac_id": "ac-k03wire-missing-%s" % tag,
            "evidence_required": True,
            "evidence_refs": ["missing-ev-k03wire-%s" % tag],
            "severity": "HIGH",
            "verification_method": "grounded-evidence",
        },
    ]
    failed = client.post(
        "/api/v1/assurance/verify-run", json=body, headers=_auth())
    assert failed.status_code == 200, failed.text
    assert failed.json()["result"] != "PASS"


def test_1387_refusal_and_risk_default_off(client):
    tag = _tag()
    body = _turn(tag, work=True)
    body["implementer_model_ids"] = [CONTRIBUTOR_MODEL]
    body["auditor_candidates"] = [{
        "provider_id": "provider-k03wire-%s" % tag,
        "model": CONTRIBUTOR_MODEL,
        "capability_evidence_refs": ["cap-ev-k03wire-%s" % tag],
    }]
    refused = client.post(
        "/api/v1/assurance/fresh-audit", json=body, headers=_auth())
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "AUDIT_INDEPENDENCE_REJECTED"
    defaults = client.get("/api/v1/assurance/risk-defaults")
    assert defaults.status_code == 200, defaults.text
    assert defaults.json()["allowed"] is False
    assert defaults.json()["policy_ref"] is None


def test_1413_close_stage_row(client):
    tag = _tag()
    served = client.post(
        "/api/v1/assurance/served-turn", json=_turn(tag, work=True),
        headers=_auth(),
    )
    assert served.status_code == 200, served.text
    audit_id = served.json()["audit_id"]
    scope = "scope-k03wire-%s" % tag
    closed = client.post(
        "/api/v1/assurance/stages/close",
        json={"task_id": "k03wire-t-%s" % tag, "scope_id": scope,
              "audit_id": audit_id},
        headers=_auth(),
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["row_id"] == "k03wire-t-%s/%s/%s" % (
        tag, scope, audit_id)


def test_1425_four_test_bases(client):
    resp = client.get("/api/v1/teststage/test-bases")
    assert resp.status_code == 200, resp.text
    builtins = resp.json()["builtins"]
    assert [row["base_id"] for row in builtins] == [
        "base-code-fast", "base-code-full", "base-ai-judge",
        "base-human-operated",
    ]
    assert [row["kind"] for row in builtins] == [
        "CODE", "CODE", "AI", "HUMAN"]


def test_1442_global_default_on(client):
    tag = _tag()
    resp = client.get(
        "/api/v1/teststage/settings/defaults",
        params={"project_id": "fresh-k03wire-%s" % tag},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["global_default_on"] is True
    assert resp.json()["enabled"] is True


def test_1595_sourcing_blocked(client):
    tag = _tag()
    resp = client.get(
        "/api/v1/assurance/sourcing-state",
        params={"scope": "scope-fresh-k03wire-%s" % tag},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "BLOCKED"


def test_1596_auditor_task_class_refused(client):
    tag = _tag()
    resp = client.get(
        "/api/v1/assurance/sourcing-state",
        params={"scope": "scope-nc-k03wire-%s" % tag,
                "task_class": "auditor"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "BLOCKED"
    assert resp.json()["code"] == "NO_ELIGIBLE_AUDITOR"


def test_negative_unmounted_claim_fails(client):
    tag = _tag()
    bypass = client.post(
        "/api/v1/assurance/wire-bypass-claim",
        json=_turn(tag, work=True),
        headers=_auth(),
    )
    assert bypass.status_code == 404, bypass.text
    missing = client.get("/api/v1/assurance/wire-bypass-claim")
    assert missing.status_code == 404, missing.text
