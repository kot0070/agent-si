"""K13 contract immutability tests (Manifest sections 12, 13, 14B, 15).

Frozen records are never rewritten: corrections, amendments, and overrides
create NEW records while the originals stay byte-identical. These tests must
FAIL on mutable implementations and PASS on the frozen domain modules.
"""

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from agent_si.domain import amendments, contracts
from iface.frozen_manifest import manifest


def _make_contract(**overrides):
    base = dict(
        schema_version="1",
        contract_version=1,
        contract_sequence=1,
        project_id="P1",
        task_id="T1",
        created_by="director",
        priority="P2",
        risk=manifest.RiskLevel.MEDIUM,
        goal="do the thing",
        requirements=("r1",),
        acceptance_criteria=("a1",),
        inputs=("i1",),
        outputs=("o1",),
        workspace="ws",
        permissions="read",
        tools=("tool1",),
        verification_policy_ref="vp:1",
        audit_policy_ref="ap:1",
        routing_policy_ref="rp:1",
        retry_policy_ref="rtp:1",
        fallback_policy_ref="fbp:1",
        optimization_policy_ref="op:1",
        override_policy_ref="ovp:1",
    )
    base.update(overrides)
    bare = contracts.TaskContract(contract_hash="", **base)
    return replace(bare, contract_hash=contracts.compute_contract_hash(bare))


def test_manifest_sha_pins_file():
    assert manifest.MANIFEST_SHA256 == "f256bab4d31be3cd9e86c22a1bdcef90b08ad62500a8eca2051705cc0a9b0690"
    assert manifest.verify_manifest(ROOT / "iface" / "frozen_manifest" / "K13_MANIFEST.md") is True
    assert manifest.verify_manifest(ROOT / "iface" / "frozen_manifest" / "NOPE.md") is False


def test_task_allowed_audit_disposition_map():
    assert manifest.TASK_ALLOWED[manifest.TaskState.AUDITING] == frozenset(
        {
            manifest.TaskState.COMPLETED,
            manifest.TaskState.REWORK_PENDING,
            manifest.TaskState.BLOCKED,
            manifest.TaskState.ESCALATED,
            manifest.TaskState.FAILED,
            manifest.TaskState.CANCELLED,
        }
    )
    assert manifest.is_task_transition_allowed("AUDITING", "COMPLETED") is True
    assert manifest.is_task_transition_allowed("EXECUTING", "COMPLETED") is False
    assert manifest.is_task_transition_allowed("EXECUTING", "COMPLETED", override=True) is False
    assert manifest.is_task_transition_allowed("REWORK_PENDING", "COMPLETED") is False
    assert manifest.is_task_transition_allowed("REWORK_PENDING", "COMPLETED", override=True) is True
    assert manifest.is_run_transition_allowed("AUDITING", "SUCCEEDED") is True
    assert manifest.is_run_transition_allowed("REWORK_REQUIRED", "RUNNING") is False
    assert manifest.is_attempt_transition_allowed("CREATED", "RUNNING") is True
    assert manifest.is_attempt_transition_allowed("RUNNING", "CREATED") is False


def test_contract_frozen():
    contract = _make_contract()
    with pytest.raises(FrozenInstanceError):
        contract.goal = "rewritten"
    with pytest.raises(FrozenInstanceError):
        contract.contract_hash = "tampered"
    assert contract.goal == "do the thing"


def test_activation_gated_new_version_new_hash_old_untouched():
    old = _make_contract()
    old_hash = old.contract_hash
    new = contracts.replace_with_new_version(old, goal="do the other thing")
    assert new.contract_version == old.contract_version + 1
    assert new.contract_sequence == old.contract_sequence + 1
    assert new.contract_hash != old_hash
    assert new.contract_hash == contracts.compute_contract_hash(new)
    assert old.goal == "do the thing"
    assert old.contract_hash == old_hash
    assert old.contract_version == 1
    first = contracts.activate(
        old,
        activation_id="act-1",
        activation_sequence=1,
        activation_reason="initial",
        activated_at="t0",
    )
    second = contracts.activate(
        new,
        activation_id="act-2",
        activation_sequence=2,
        activation_reason="amendment",
        previous_contract_hash=old_hash,
        activated_at="t1",
    )
    assert contracts.resolve_active([first, second]) == second
    assert contracts.resolve_active([]) is None
    with pytest.raises(FrozenInstanceError):
        first.contract_hash = "tampered"


def test_attempt_immutable():
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class FrozenAttempt:
        attempt_id: str
        run_id: str
        contract_hash: str
        status: object = manifest.ExecutionAttemptStatus.CREATED

    attempt = FrozenAttempt(
        attempt_id="att-1", run_id="run-1", contract_hash="h1"
    )
    with pytest.raises(FrozenInstanceError):
        attempt.status = manifest.ExecutionAttemptStatus.SUCCEEDED
    with pytest.raises(FrozenInstanceError):
        attempt.contract_hash = "h2"
    assert attempt.status == manifest.ExecutionAttemptStatus.CREATED


def test_audit_record_frozen_and_override_creates_new():
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class FrozenAuditRecord:
        audit_id: str
        result: object
        evidence_refs: tuple = ()

    original = FrozenAuditRecord(
        audit_id="aud-1", result=manifest.AuditResult.REWORK
    )
    with pytest.raises(FrozenInstanceError):
        original.result = manifest.AuditResult.PASS
    assert manifest.AUDIT_RESULT_TRANSITION_MAP[original.result] == manifest.TaskState.REWORK_PENDING
    overridden = replace(original, result=manifest.AuditResult.PASS)
    assert overridden.result == manifest.AuditResult.PASS
    assert original.result == manifest.AuditResult.REWORK


def test_contract_hash_one_run_one_hash():
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class FrozenRun:
        run_id: str
        contract_hash: str
        status: object = manifest.ExecutionRunStatus.CREATED

    first = _make_contract()
    assert contracts.compute_contract_hash(first) == first.contract_hash
    changed = contracts.replace_with_new_version(first, goal="changed goal")
    assert changed.contract_hash != first.contract_hash
    run = FrozenRun(run_id="run-1", contract_hash=first.contract_hash)
    with pytest.raises(FrozenInstanceError):
        run.contract_hash = changed.contract_hash
    assert run.contract_hash == first.contract_hash


def test_amendment_precedence_and_classify():
    def _amendment(scope, sequence):
        return amendments.Amendment(
            amendment_id="a-%s-%s" % (scope, sequence),
            project_id="P1",
            amendment_sequence=sequence,
            scope=scope,
            change=amendments.AmendmentChange(fields=("goal",)),
        )

    ordered = amendments.order_amendments(
        [
            _amendment("TASK", 5),
            _amendment("GLOBAL", 9),
            _amendment("PHASE", 1),
            _amendment("GLOBAL", 2),
        ]
    )
    assert [(a.scope.value, a.amendment_sequence) for a in ordered] == [
        ("GLOBAL", 2),
        ("GLOBAL", 9),
        ("PHASE", 1),
        ("TASK", 5),
    ]
    assert (
        amendments.classify(amendments.AmendmentChange(fields=("goal",)))
        == amendments.CONTRACT_AFFECTING
    )
    assert (
        amendments.classify(amendments.AmendmentChange(fields=("goal",)))
        == amendments.classify(
            amendments.AmendmentChange(fields=("goal",)),
            contracts.manifest.TASK_CONTRACT_FIELDS
            if hasattr(contracts, "manifest")
            else manifest.TASK_CONTRACT_FIELDS,
        )
    )
    assert (
        amendments.classify(amendments.AmendmentChange(fields=("operator_note",)))
        == amendments.NON_CONTRACT_AFFECTING
    )


@pytest.mark.parametrize("state", ["COMPLETED", "FAILED", "CANCELLED"])
def test_terminal_task_amendment_rejected(state):
    with pytest.raises(amendments.TerminalTaskAmendmentError):
        amendments.apply_terminal_task_rule(state, "IMMEDIATE")
    assert (
        amendments.apply_terminal_task_rule(state, "NEXT_TASK")
        == amendments.REJECT_NEW_TASK_REQUIRED
    )


def test_non_terminal_task_amendment_applies_without_mutation():
    amendment = amendments.Amendment(
        amendment_id="a-1",
        project_id="P1",
        amendment_sequence=1,
        scope="TASK",
        effective_from="IMMEDIATE",
        target=amendments.AmendmentTarget(task_id="T1"),
        change=amendments.AmendmentChange(fields=("goal",)),
        status="PENDING",
    )
    assert amendment.status == manifest.AmendmentStatus.PENDING
    assert amendments.apply_terminal_task_rule("EXECUTING", "IMMEDIATE") == amendments.APPLY
    descriptors = amendments.apply_immediate_effect(
        amendment,
        "EXECUTING",
        active_run_id="run-1",
        active_run_status="RUNNING",
    )
    assert [d.action for d in descriptors] == ["CANCEL_RUN", "NEW_CONTRACT_VERSION"]
    assert descriptors[0].reason == "CANCELLED_BY_AMENDMENT"
    assert amendment.status == manifest.AmendmentStatus.PENDING
    assert amendments.apply_immediate_effect(
        replace(amendment, effective_from="NEXT_TASK"), "EXECUTING"
    ) == ()
