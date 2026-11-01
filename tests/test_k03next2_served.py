"""K03NEXT2 served rows through the real seam app (create_app) loopback.

Rows: B0B-UNCOVERED_ARCH-740, B0B-UNCOVERED_ARCH-741,
B0B-UNCOVERED_ARCH-745, B0B-UNCOVERED_ARCH-746,
B0B-UNCOVERED_MVP_ACCEPT-33, B0B-SDK-109, B0B-SDK-104,
B0B-UNCOVERED_MVP_ACCEPT-111 through the lane-owned k03next2 seam
routes (one served test per row; each test name carries its row id).

Every row drives its owning served route plus its owning seam entry;
no network, no doubles. Unique ids (k03next2-*) keep the global
registry/records stores isolated from every other test file. RED LIST
starts at 8 items: any route that answers 404 here becomes a defect
line plus a fix in this lane (the first run below is that RED: the
k03next2 routes do not exist yet).
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

from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "k03next2-served-token"
ACTOR = "tester-k03next2"

#: Exact shipped-preset contributor model id (never reworded).
CONTRIBUTOR_MODEL = "meta/muse-spark-1.3-contributor"

#: Auditor model outside the contributor set; plain test data standing in
#: for a provider model id at the model-provider boundary.
AUDITOR_MODEL = "meta/muse-spark-1.3-auditor"


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


def _candidate(provider, model=AUDITOR_MODEL, evidence=()):
    """One auditor candidate payload with the given capability refs."""
    return {
        "provider_id": provider,
        "model": model,
        "capability_evidence_refs": list(evidence),
    }


def _gate(client, scope, candidates=None, implementers=None,
          user_authority="USER", with_resolution=True, run_id=None,
          task_class="served-turn"):
    """POST one sourcing-gate probe; resolution defaults to a USER one."""
    body = {
        "scope": scope,
        "implementer_model_ids": (
            [CONTRIBUTOR_MODEL] if implementers is None else implementers
        ),
        "task_class": task_class,
        "minimum_level": "L2",
        "auditor_candidates": [] if candidates is None else candidates,
    }
    if run_id is not None:
        body["run_id"] = run_id
    if with_resolution:
        body["user_resolution"] = {
            "decision_id": "dec-k03next2-b0b-%s" % scope,
            "scope": scope,
            "statement": "use the sourced auditor for scope %s" % scope,
            "reason": "only USER resolves parked sourcing",
            "authority": user_authority,
            "decided_by": ACTOR,
            "visible_to_user": True,
            "user_resolution_ref": "resolve-k03next2-b0b-%s" % scope,
        }
    return client.post("/api/v1/qa/sourcing_gate/scoped", json=body)


def test_k03next2_b0b_uncovered_arch_740(client):
    """B0B-UNCOVERED_ARCH-740: sourcing independent of implementers."""
    from agent_si.assurance import audit_registry  # noqa: E402

    tag = _tag()
    provider = "provider-k03next2-b0b-740-%s" % tag
    evidence = ["cap-ev-k03next2-b0b-740-%s" % tag]
    first = _gate(
        client, "scope-k03next2-b0b-740a-%s" % tag,
        candidates=[_candidate(provider, evidence=evidence)],
        implementers=[CONTRIBUTOR_MODEL],
    )
    assert first.status_code == 200, first.text
    assert first.json()["disposition"] == "SOURCED"
    second = _gate(
        client, "scope-k03next2-b0b-740b-%s" % tag,
        candidates=[_candidate(provider, evidence=evidence)],
        implementers=["other/model-x"],
    )
    assert second.status_code == 200, second.text
    assert second.json()["disposition"] == "SOURCED"
    assert (
        second.json()["auditor"]["provider_id"],
        second.json()["auditor"]["model"],
    ) == (
        first.json()["auditor"]["provider_id"],
        first.json()["auditor"]["model"],
    )

    class _Registry(audit_registry.AuditorRegistry):
        """Concrete binding of the real sourcing entries; adds nothing."""

    registry = _Registry()
    registry.register_candidate(audit_registry.AuditorCandidate(
        provider_id=provider, provider_instance=None, model=AUDITOR_MODEL,
        capability_evidence_refs=tuple(evidence), registered_at=""))
    one = registry.select_auditor(
        "worker", (CONTRIBUTOR_MODEL,), "L2")
    two = registry.select_auditor("worker", ("other/model-x",), "L2")
    assert (two.auditor.provider_id, two.auditor.model) == (
        one.auditor.provider_id, one.auditor.model)
    assert two.auditor.session_ref != one.auditor.session_ref


def test_k03next2_b0b_uncovered_arch_741(client):
    """B0B-UNCOVERED_ARCH-741: auditor-task-class sourcing fails closed."""
    from agent_si.assurance import audit_registry  # noqa: E402

    tag = _tag()
    scope = "scope-k03next2-b0b-741-%s" % tag
    resp = _gate(
        client, scope,
        candidates=[_candidate(
            "provider-k03next2-b0b-741-%s" % tag,
            evidence=["cap-ev-k03next2-b0b-741-%s" % tag])],
        task_class="auditor",
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is False
    assert data["disposition"] == "BLOCKED"
    assert data["code"] == "NO_ELIGIBLE_AUDITOR"
    assert data["pass_prohibited"] is True
    assert data["auditor"] is None

    class _Registry(audit_registry.AuditorRegistry):
        """Concrete binding of the real sourcing entries; adds nothing."""

    registry = _Registry()
    registry.register_candidate(audit_registry.AuditorCandidate(
        provider_id="provider-k03next2-b0b-741b-%s" % tag,
        provider_instance=None, model=AUDITOR_MODEL,
        capability_evidence_refs=("cap-ev-k03next2-b0b-741b-%s" % tag,),
        registered_at=""))
    try:
        registry.select_auditor(
            "auditor", (CONTRIBUTOR_MODEL, AUDITOR_MODEL), "L2")
    except Exception as exc:
        assert getattr(exc, "code", "") == "NO_ELIGIBLE_AUDITOR"
    else:
        raise AssertionError("auditor task class sourced an auditor")
    assert registry.sourcing_state("scope-fresh-k03next2-741") == "BLOCKED"


def test_k03next2_b0b_uncovered_arch_745(client):
    """B0B-UNCOVERED_ARCH-745: parked Task until the USER resolves."""
    tag = _tag()
    scope = "scope-k03next2-b0b-745-%s" % tag
    candidates = [_candidate(
        "provider-k03next2-b0b-745-%s" % tag,
        evidence=["cap-ev-k03next2-b0b-745-%s" % tag])]

    parked = _gate(client, scope, candidates=candidates,
                   with_resolution=False)
    assert parked.status_code == 200, parked.text
    assert parked.json()["disposition"] == "BLOCKED"
    assert parked.json()["code"] == "SOURCING_UNRESOLVED"
    assert parked.json()["pass_prohibited"] is True
    assert parked.json()["auditor"] is None

    non_user = _gate(client, scope, candidates=candidates,
                     user_authority="MANAGER")
    assert non_user.status_code == 200, non_user.text
    assert non_user.json()["disposition"] == "BLOCKED"
    assert non_user.json()["code"] == "SOURCING_UNRESOLVED"
    assert non_user.json()["auditor"] is None

    resolved = _gate(client, scope, candidates=candidates)
    assert resolved.status_code == 200, resolved.text
    data = resolved.json()
    assert data["ok"] is True
    assert data["disposition"] == "SOURCED"
    assert data["sourcing_state"] == "RESOLVED"
    assert data["auditor"]["model"] == AUDITOR_MODEL


def test_k03next2_b0b_uncovered_arch_746(client):
    """B0B-UNCOVERED_ARCH-746: bare candidate ineligible; select skips it."""
    from agent_si.assurance import audit_registry  # noqa: E402

    tag = _tag()
    scope = "scope-k03next2-b0b-746-%s" % tag
    bare_provider = "provider-k03next2-b0b-746-bare-%s" % tag
    ready_provider = "provider-k03next2-b0b-746-ready-%s" % tag
    evidence = ["cap-ev-k03next2-b0b-746-%s" % tag]

    resp = _gate(
        client, scope,
        candidates=[_candidate(bare_provider),
                    _candidate(ready_provider, evidence=evidence)],
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["disposition"] == "SOURCED"
    assert data["auditor"]["provider_id"] == ready_provider
    assert data["auditor"]["model"] == AUDITOR_MODEL
    by_provider = {row["provider_id"]: row for row in data["eligibility"]}
    assert by_provider[bare_provider]["eligible"] is False
    assert by_provider[ready_provider]["eligible"] is True

    class _Registry(audit_registry.AuditorRegistry):
        """Concrete binding of the real sourcing entries; adds nothing."""

    registry = _Registry()
    registry.register_candidate(audit_registry.AuditorCandidate(
        provider_id=bare_provider, provider_instance="i-bare",
        model="model-bare-k03next2-746", capability_evidence_refs=(),
        registered_at=""))
    registry.register_candidate(audit_registry.AuditorCandidate(
        provider_id=ready_provider, provider_instance="i-ready",
        model=AUDITOR_MODEL, capability_evidence_refs=tuple(evidence),
        registered_at=""))
    assert registry.is_eligible(bare_provider,
                               "model-bare-k03next2-746") is False
    selection = registry.select_auditor("worker", (CONTRIBUTOR_MODEL,), "L2")
    assert selection.auditor.model == AUDITOR_MODEL
    assert selection.auditor.provider_id == ready_provider


def test_k03next2_b0b_uncovered_mvp_accept_33(client):
    """B0B-UNCOVERED_MVP_ACCEPT-33: gate plus deterministic verification."""
    from agent_si.assurance import audit_coordinator  # noqa: E402

    cases = [
        ("verifier_timeout", "VERIFICATION_INFRA_FAILURE"),
        ("malformed_json_output", "OUTPUT_FORMAT_FAILURE"),
        ("model_lacks_capability", "PROVIDER_OR_MODEL_CAPABILITY_FAILURE"),
        ("wrong_implementation", "IMPLEMENTATION_AC_DEFECT"),
        ("policy_violation", "SECURITY_OR_POLICY_FAILURE"),
        ("unrecognized_signal_xyz", "UNKNOWN_FAILURE"),
    ]
    for signal, expected in cases:
        resp = client.post(
            "/api/v1/qa/classify_failure",
            json={"signal": signal, "severity": "HIGH"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["failure_class"] == expected

    bad = client.post(
        "/api/v1/qa/classify_failure",
        json={"signal": 42, "severity": "HIGH"},
    )
    assert bad.status_code == 400, bad.text

    class _Coordinator(audit_coordinator.AuditCoordinator):
        """Concrete binding of the real classify entry; adds nothing."""

    seam = _Coordinator()
    for signal, expected in cases:
        assert seam.classify_failure(signal, "HIGH") == getattr(
            seam.VerificationFailureClass, expected)


def test_k03next2_b0b_sdk_109(client):
    """B0B-SDK-109: turn-cap and invalid output go through named handlers."""
    from agent_si.assurance import audit_coordinator  # noqa: E402

    tag = _tag()
    turn_ref = "turn-cap-k03next2-%s" % tag
    resp = client.post(
        "/api/v1/qa/turn_handlers",
        json={"handler": "turn_cap", "turn_ref": turn_ref,
              "budget_state_ref": "budget-k03next2-%s" % tag},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["handler"] == "turn_cap"
    assert resp.json()["ref"] == "turn-cap-refusal:%s:budget-k03next2-%s" % (
        turn_ref, tag)

    out_ref = "out-bad-k03next2-%s" % tag
    resp = client.post(
        "/api/v1/qa/turn_handlers",
        json={"handler": "invalid_output", "output_ref": out_ref,
              "reason": "bad json"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["handler"] == "invalid_output"
    assert resp.json()["ref"] == "invalid-output:%s:bad json" % out_ref

    bad = client.post(
        "/api/v1/qa/turn_handlers",
        json={"handler": "no-such-handler"},
    )
    assert bad.status_code == 400, bad.text

    class _Coordinator(audit_coordinator.AuditCoordinator):
        """Concrete binding of the real handler entries; adds nothing."""

    seam = _Coordinator()
    assert callable(seam.handle_turn_cap)
    refusal = seam.handle_turn_cap(turn_ref, "budget-k03next2-%s" % tag)
    assert refusal == "turn-cap-refusal:%s:budget-k03next2-%s" % (
        turn_ref, tag)
    outcome = seam.handle_invalid_output(out_ref, "bad json")
    assert outcome == "invalid-output:%s:bad json" % out_ref


def test_k03next2_b0b_sdk_104(client):
    """B0B-SDK-104: machine-verifiable deliverable schemas served."""
    from agent_si.assurance import audit_coordinator  # noqa: E402

    tag = _tag()
    schema_id = "schema-k03next2-%s" % tag
    resp = client.post(
        "/api/v1/qa/deliverable_schema",
        json={"schema_id": schema_id,
              "expected_outputs": ["out-1", "out-2"],
              "evidence_required": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["schema_id"] == schema_id
    assert data["version"] == 1
    assert tuple(data["expected_outputs"]) == ("out-1", "out-2")
    assert data["evidence_required"] is True
    assert data["hash"]

    again = client.post(
        "/api/v1/qa/deliverable_schema",
        json={"schema_id": schema_id,
              "expected_outputs": ["out-1", "out-2"],
              "evidence_required": True},
    )
    assert again.status_code == 200, again.text
    assert again.json()["hash"] == data["hash"]

    bad = client.post(
        "/api/v1/qa/deliverable_schema",
        json={"schema_id": "  ", "expected_outputs": ["out-1"],
              "evidence_required": True},
    )
    assert bad.status_code == 400, bad.text

    class _Coordinator(audit_coordinator.AuditCoordinator):
        """Concrete binding of the real schema entry; adds nothing."""

    seam = _Coordinator()
    schema = seam.build_deliverable_schema(
        schema_id, ("out-1", "out-2"), True)
    assert schema.schema_id == schema_id
    assert tuple(schema.expected_outputs) == ("out-1", "out-2")
    assert schema.evidence_required is True
    assert schema.hash == data["hash"]


def test_k03next2_b0b_uncovered_mvp_accept_111(client):
    """B0B-UNCOVERED_MVP_ACCEPT-111: recovery leg confirmed, then counted."""
    from agent_si.assurance import audit_coordinator  # noqa: E402

    tag = _tag()
    run_ref = "run-k03next2-r111-%s" % tag
    turn = {
        "turn_ref": "turn-k03next2-r111-%s" % tag,
        "project_id": "proj-k03next2-r111-%s" % tag,
        "task_id": "task-k03next2-r111-%s" % tag,
        "run_id": run_ref,
        "work_refs": ["work-k03next2-r111"],
        "artifact_refs": ["art-k03next2-r111"],
        "evidence_refs": ["ev-k03next2-r111"],
        "producer_session_refs": ["sess-k03next2-r111"],
        "contract_hash": "contract-k03next2-r111",
    }

    pending = client.post(
        "/api/v1/qa/recovery_confirm",
        json={"run_ref": run_ref, "verification_ref": "",
              "turn": dict(turn)},
    )
    assert pending.status_code == 200, pending.text
    assert pending.json()["confirmed"] is False

    done = client.post(
        "/api/v1/qa/recovery_confirm",
        json={"run_ref": run_ref, "verification_ref": "ver-k03next2-r111",
              "turn": dict(turn)},
    )
    assert done.status_code == 200, done.text
    data = done.json()
    assert data["confirmed"] is True
    assert data["audit_ref"] == data["audit_id"]
    assert data["check_ref"] == "context-recovery-check"

    bad = client.post(
        "/api/v1/qa/recovery_confirm",
        json={"run_ref": "  ", "verification_ref": "ver-x",
              "turn": dict(turn)},
    )
    assert bad.status_code == 400, bad.text

    class _Coordinator(audit_coordinator.AuditCoordinator):
        """Concrete binding of the real recovery entries; adds nothing."""

    seam = _Coordinator()
    assert seam.confirm_recovery_leg(run_ref, "", "").confirmed is False
    served = audit_coordinator.ServedTurn(**{
        key: (tuple(value) if key.endswith("_refs") else value)
        for key, value in turn.items()
    })
    audit_id = seam.audit_served_turn(served)
    confirmed = seam.confirm_recovery_leg(
        run_ref, "ver-k03next2-r111", audit_id)
    assert confirmed.confirmed is True
    assert confirmed.audit_ref == audit_id
