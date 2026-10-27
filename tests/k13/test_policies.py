"""K13 policies + decisions tests (Manifest sections 16, 17, 25A, 26A, 21B, 19A).

RED/GREEN: these tests MUST FAIL on mutable / unversioned / non-hash-addressed
implementations (missing FrozenInstanceError, missing version bump, missing
hash recompute, silent POLICY_CONFLICT, racy counters, auto-ESCALATE) and PASS
on the frozen domain modules in src/agent_si/policies/.
"""

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from agent_si.policies import decisions, policies
from iface.frozen_manifest import manifest


def _retry_policy(**overrides):
    base = dict(policy_id="rtp-1", version=1, created_at="t0")
    base.update(overrides)
    bare = policies.RetryPolicy(hash="", **base)
    return replace(bare, hash=policies.compute_policy_hash(bare))


def test_policy_objects_frozen():
    instances = [
        policies.RoutingPolicy(policy_id="rp-1"),
        policies.OptimizationPolicy(policy_id="op-1"),
        _retry_policy(),
        policies.FallbackPolicy(policy_id="fbp-1"),
        policies.VerificationPolicy(policy_id="vp-1"),
        policies.AuditPolicy(policy_id="ap-1"),
        policies.OverridePolicy(policy_id="ovp-1"),
        policies.FailureDispositionPolicy(policy_id="fdp-1"),
    ]
    assert len(instances) == 8
    for instance in instances:
        with pytest.raises(FrozenInstanceError):
            instance.policy_id = "tampered"
        with pytest.raises(FrozenInstanceError):
            instance.hash = "tampered"
    assert instances[0].policy_id == "rp-1"


def test_policy_versioning_new_version_new_hash_old_untouched():
    old = _retry_policy()
    old_hash = old.hash
    new = policies.new_policy_version(old, executor_attempt_max=9)
    assert new.version == old.version + 1
    assert new.hash != old_hash
    assert new.hash == policies.compute_policy_hash(new)
    assert old.executor_attempt_max == policies.DEFAULTS["executor_attempt_max"]
    assert old.hash == old_hash
    assert old.version == 1
    with pytest.raises(ValueError):
        policies.new_policy_version(old, hash="supplied")


def test_policy_hash_addressing_one_content_one_hash():
    first = _retry_policy()
    assert policies.compute_policy_hash(first) == first.hash
    twin = _retry_policy()
    assert twin.hash == first.hash
    changed = policies.new_policy_version(first, provider_retry_max=7)
    assert changed.hash != first.hash


def test_policy_identity_conflict_raises():
    contract_refs = {
        "routing_policy_ref": "rp:1",
        "optimization_policy_ref": "op:1",
        "retry_policy_ref": "rtp:1",
        "fallback_policy_ref": "fbp:1",
        "verification_policy_ref": "vp:1",
        "audit_policy_ref": "ap:1",
        "override_policy_ref": "ovp:1",
    }
    nested_ok = {
        "verification.retry_policy_ref": "rtp:1",
        "verification.failure_disposition_policy_ref": "fdp:1",
        "audit.retry_policy_ref": "rtp:1",
        "audit.override_policy_ref": "ovp:1",
        "failure_disposition.retry_policy_ref": "rtp:1",
        "failure_disposition.fallback_policy_ref": "fbp:1",
        "failure_disposition.override_policy_ref": "ovp:1",
    }
    assert policies.enforce_policy_identity(contract_refs, nested_ok) is True
    nested_bad = dict(nested_ok)
    nested_bad["verification.retry_policy_ref"] = "rtp:EVIL"
    with pytest.raises(manifest.PolicyConflictError) as excinfo:
        policies.enforce_policy_identity(contract_refs, nested_bad)
    assert excinfo.value.code == manifest.POLICY_CONFLICT


def test_policy_lifecycle_status_derived_not_stored():
    record = policies.PolicyLifecycleRecord(
        policy_lifecycle_id="pl-1",
        policy_ref="rtp:1",
        policy_id="rtp-1",
        policy_version=1,
        lifecycle_sequence=1,
        event=policies.PolicyLifecycleEvent.ACTIVATED,
        created_at="t0",
    )
    assert record.status == "ACTIVE"
    assert "status" not in policies.POLICY_LIFECYCLE_FIELDS
    with pytest.raises(FrozenInstanceError):
        record.policy_version = 2
    superseded = replace(
        record,
        policy_lifecycle_id="pl-2",
        lifecycle_sequence=2,
        event=policies.PolicyLifecycleEvent.SUPERSEDED,
    )
    assert policies.derive_policy_status([record, superseded]) == "SUPERSEDED"
    assert policies.derive_policy_status([superseded, record]) == "SUPERSEDED"


def test_counter_atomicity_under_threads():
    store = policies.RestartSafeCounter()
    scope, kind, limit = "task:T1", "runtime_rework", 1000
    seen = []
    lock = threading.Lock()

    def bump():
        value = store.increment(scope, kind, limit)
        with lock:
            seen.append(value)

    threads = [threading.Thread(target=bump) for _ in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(seen) == list(range(1, 51))
    with pytest.raises(policies.CounterLimitExceededError):
        store.increment(scope, kind, 50)


def test_counter_restart_safety_from_committed_records():
    committed = [
        policies.ReworkCounterRecord(
            counter_id="c-1",
            project_id="P1",
            scope_type="TASK",
            scope_id="T1",
            counter_type=policies.ReworkCounterType.RUNTIME_REWORK,
            value=3,
            limit=5,
            updated_at="t0",
            version=3,
        ),
        policies.FallbackCounterRecord(
            counter_id="c-2",
            project_id="P1",
            task_id="T1",
            run_id="R1",
            scope_type="RUN",
            scope_id="R1",
            value=2,
            limit=4,
            updated_at="t0",
            version=2,
        ),
    ]
    store = policies.RestartSafeCounter.rehydrate(committed)
    assert store.increment("task:T1", "runtime_rework", 5) == 4
    assert store.increment("run:R1", "fallback", 4) == 3
    first = policies.bump_rework(committed[0], store)
    assert first.value == 5
    assert committed[0].value == 3
    with pytest.raises(FrozenInstanceError):
        committed[0].value = 99


def test_defaults_executor3_provider2_format1_verify1_corrections():
    assert policies.DEFAULTS["executor_attempt_max"] == 3
    assert policies.DEFAULTS["provider_retry_max"] == 2
    assert policies.DEFAULTS["format_retry_max"] == 1
    assert policies.DEFAULTS["verification_retry_max"] == 1
    assert policies.DEFAULTS["audit_correction_max"] == 2
    assert policies.DEFAULTS["verification_correction_max"] == 2
    assert policies.DEFAULTS["runtime_correction_max"] == 3
    default = policies.default_retry_policy()
    assert default.executor_attempt_max == 3
    assert default.provider_retry_max == 2
    assert default.format_retry_max == 1
    assert default.verification_retry_max == 1
    assert default.hash == policies.compute_policy_hash(default)


def test_exhaustion_never_auto_escalates():
    for exhausted in ("retry_exhausted", "fallback_exhausted"):
        disposition = policies.resolve_exhaustion(exhausted)
        assert disposition != manifest.AuditHandlingDisposition.ESCALATE
        assert disposition == manifest.AuditHandlingDisposition.FAIL
    record = policies.RetryRecord(
        retry_id="rr-1",
        project_id="P1",
        task_id="T1",
        reason="timeout",
        attempt=3,
        owner="manager",
    )
    assert policies.is_exhausted(record, _retry_policy()) is True
    assert policies.disposition_after_exhaustion(record) != "ESCALATE"


def test_decision_record_version_ordering_concurrent_edits():
    first = decisions.DecisionRecord(
        decision_id="d-1", project_id="P1", task_id="T1", version=1
    )
    second = decisions.replace_decision(first, statement="updated")
    assert second.version == 2
    assert first.version == 1
    assert decisions.resolve_latest([second, first]) is second
    assert decisions.order_decisions([second, first]) == [first, second]
    with pytest.raises(decisions.ConcurrentEditError):
        decisions.commit_decision([second], expected_version=1, record=second)
    assert decisions.commit_decision([first], expected_version=1, record=second) is second


def test_decision_record_nullable_task_run_refs():
    pre_run = decisions.DecisionRecord(decision_id="d-0", project_id="P1")
    assert pre_run.task_id is None
    assert pre_run.run_id is None
    bound = replace(pre_run, task_id="T1", run_id="R1")
    assert bound.task_id == "T1"
    assert bound.run_id == "R1"
    assert pre_run.task_id is None
    with pytest.raises(FrozenInstanceError):
        pre_run.task_id = "T9"


def test_authorization_record_r2_r3():
    director_grant = decisions.AuthorizationRecord(
        authorization_id="a-r2",
        project_id="P1",
        task_id="T1",
        risk_level=manifest.RiskLevel.MEDIUM,
        action="retry",
        scope="task",
        granted_by="director",
        granted_at="t0",
    )
    user_grant = decisions.AuthorizationRecord(
        authorization_id="a-r3",
        project_id="P1",
        task_id="T1",
        risk_level=manifest.RiskLevel.CRITICAL,
        action="accepted-risk",
        scope="task",
        granted_by="user",
        granted_at="t0",
    )
    assert decisions.tier_of(director_grant) == "R2"
    assert decisions.tier_of(user_grant) == "R3"
    with pytest.raises(decisions.AuthorizationRejectedError):
        decisions.AuthorizationRecord(
            authorization_id="a-bad",
            project_id="P1",
            task_id="T1",
            risk_level=manifest.RiskLevel.LOW,
            action="retry",
            scope="task",
            granted_by="model",
            granted_at="t0",
        )
    with pytest.raises(FrozenInstanceError):
        director_grant.action = "tampered"


def test_permission_ladder_documented():
    import inspect

    assert "R0" in inspect.getsource(decisions) and "R3" in inspect.getsource(decisions)


def test_b003_forged_authorization_rejected_vs_append_only_store():
    store = decisions.AuthorizationStore()
    grant = decisions.AuthorizationRecord(
        authorization_id="a-1",
        project_id="P1",
        task_id="T1",
        risk_level=manifest.RiskLevel.LOW,
        action="retry",
        scope="task",
        granted_by="director",
        granted_at="t0",
        evidence_ref="ev-1",
    )
    stored = store.append(grant)
    assert stored is grant
    assert store.append(grant) is grant
    forged = replace(grant, action="accepted-risk")
    with pytest.raises(decisions.AuthorizationRejectedError):
        store.append(forged)
    tampered = replace(grant, scope="workspace", granted_by="user")
    with pytest.raises(decisions.AuthorizationRejectedError):
        store.append(tampered)
    assert store.list_by("a-1")[0].action == "retry"


def test_b004_model_issued_high_risk_approval_rejected_action_blocked():
    store = decisions.AuthorizationStore()
    with pytest.raises(decisions.AuthorizationRejectedError):
        decisions.request_high_risk_approval(
            store,
            authorization_id="a-model",
            project_id="P1",
            task_id="T1",
            action="accepted-risk",
            scope="task",
            granted_by="model",
        )
    assert store.list_by("a-model") == []
    assert decisions.check_action(store, "accepted-risk", "task") == "BLOCKED"
