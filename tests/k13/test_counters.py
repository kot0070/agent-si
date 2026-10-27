"""K13 counter + idempotency tests (Manifest sections 16, 17A, 17C, 19A).

RED before implementation (imports of the new modules fail), GREEN after:
counters counted apart, persistent/atomic/restart-safe, per-type + global
budgets, correction loop = new run with reset counters, Phase-0 separate,
and idempotent actions with prior-state verification (no blind retry of
unprotected mutation).
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from agent_si.domain import idempotency
from agent_si.runtime.scheduler import counters
from iface.frozen_manifest import manifest


def _counters(tmp_path, **budget_overrides):
    budgets = counters.CounterBudgets(**budget_overrides) if budget_overrides else counters.CounterBudgets()
    return counters.PersistentCounters(tmp_path / "counters.json", budgets)


def _action(key="k-1", **overrides):
    base = dict(
        action_id="act-1",
        project_id="P1",
        task_id="T1",
        run_id="run-1",
        idempotency_key=key,
        authorization_ref="auth-1",
        prior_state="state-0",
    )
    base.update(overrides)
    return idempotency.ActionExecution(**base)


def test_manifest_sha_pins_file():
    assert manifest.MANIFEST_SHA256 == "f256bab4d31be3cd9e86c22a1bdcef90b08ad62500a8eca2051705cc0a9b0690"
    assert manifest.verify_manifest(ROOT / "RECORDS" / "day0" / "K13_MANIFEST.md") is True
    assert manifest.verify_manifest(ROOT / "RECORDS" / "day0" / "NOPE.md") is False


def test_kinds_counted_apart(tmp_path):
    store = _counters(tmp_path)
    scope = counters.run_scope("run-1")
    store.record_initial(scope)
    store.record_retry(scope)
    store.record_retry(scope)
    store.record_fallback(scope)
    snap = store.snapshot(scope)
    assert (snap.retry_count, snap.fallback_count, snap.attempt_count) == (2, 1, 4)
    assert snap.correction_count == 0
    # retry bumps do not leak into fallback/correction and vice versa
    assert snap.retry_count != snap.fallback_count != snap.attempt_count


def test_restart_safe_resumes_values(tmp_path):
    path = tmp_path / "counters.json"
    first = counters.PersistentCounters(path)
    scope = counters.run_scope("run-9")
    first.record_initial(scope)
    first.record_retry(scope)
    first.record_fallback(scope)
    del first
    second = counters.PersistentCounters(path)
    snap = second.snapshot(scope)
    assert (snap.retry_count, snap.fallback_count, snap.correction_count, snap.attempt_count) == (1, 1, 0, 3)
    # continued increments build on reloaded state, never restart from zero
    resumed = second.record_retry(scope)
    assert (resumed.retry_count, resumed.attempt_count) == (2, 4)


def test_retry_budget_per_type_and_global(tmp_path):
    store = _counters(tmp_path, executor_attempt_max=2, global_attempt_cap=10)
    scope = counters.run_scope("run-2")
    store.record_retry(scope)
    store.record_retry(scope)
    with pytest.raises(counters.BudgetExhaustedError):
        store.record_retry(scope)
    assert store.snapshot(scope).retry_count == 2
    # global cap binds even when the per-type budget remains
    tight = _counters(tmp_path / "t2", executor_attempt_max=9, global_attempt_cap=2)
    scope2 = counters.run_scope("run-2b")
    tight.record_initial(scope2)
    tight.record_retry(scope2)
    with pytest.raises(counters.BudgetExhaustedError) as exc:
        tight.record_retry(scope2)
    assert exc.value.budget == "global"


def test_fallback_budget_run_scope(tmp_path):
    store = _counters(tmp_path, max_fallbacks_per_run=1, global_attempt_cap=99)
    scope = counters.run_scope("run-3")
    store.record_fallback(scope)
    with pytest.raises(counters.BudgetExhaustedError):
        store.record_fallback(scope)
    assert store.snapshot(scope).fallback_count == 1


def test_correction_loop_is_new_run_with_reset_counters(tmp_path):
    store = _counters(tmp_path, global_attempt_cap=99)
    old_scope = counters.run_scope("run-old")
    store.record_initial(old_scope)
    store.record_retry(old_scope)
    fresh = store.record_correction("T1", "run-new")
    assert (fresh.retry_count, fresh.fallback_count, fresh.attempt_count) == (0, 0, 0)
    assert store.snapshot(counters.task_scope("T1")).correction_count == 1
    # old run history is untouched; every correction run increments the task total
    assert store.snapshot(old_scope).retry_count == 1
    store.record_correction("T1", "run-newer")
    assert store.snapshot(counters.task_scope("T1")).correction_count == 2
    # correction budget exhausts -> ESCALATE signal, never silent reset
    bounded = _counters(tmp_path / "b", runtime_correction_max=1, global_attempt_cap=99)
    bounded.record_correction("T9", "r1")
    with pytest.raises(counters.BudgetExhaustedError):
        bounded.record_correction("T9", "r2")


def test_phase0_counters_separate(tmp_path):
    store = _counters(tmp_path, executor_attempt_max=2, global_attempt_cap=99)
    scope = counters.run_scope("run-4")
    store.record_retry(scope, phase0=True)
    store.record_retry(scope, phase0=True)
    # Phase-0 namespace holds its own counts; runtime scope is untouched
    assert store.snapshot(scope, phase0=True).retry_count == 2
    assert store.snapshot(scope).retry_count == 0
    assert store.snapshot(scope).attempt_count == 0
    # runtime budget still fully available after Phase-0 activity
    assert store.budget_remaining(scope, counters.RETRY) == 2


def test_verification_only_retry_never_touches_correction(tmp_path):
    store = _counters(tmp_path, global_attempt_cap=99)
    scope = counters.run_scope("run-5")
    store.record_initial(scope)
    before = store.snapshot(scope)
    after = store.record_verification_only(scope)
    assert after == before
    assert after.correction_count == 0
    assert after.attempt_count == before.attempt_count


def test_atomic_persist_leaves_valid_state(tmp_path):
    path = tmp_path / "counters.json"
    store = counters.PersistentCounters(path)
    store.record_retry(counters.run_scope("run-6"))
    assert path.is_file()
    assert list(tmp_path.glob("*.tmp")) == []
    import json

    doc = json.loads(path.read_text(encoding="utf-8"))
    assert set(doc["scopes"]["run:run-6"]) == {"retry", "fallback", "correction", "attempt"}


def test_counter_store_port_shape(tmp_path):
    port = counters.FileCounterStore(tmp_path / "port.json")
    assert isinstance(port, manifest.CounterStore)
    assert port.increment("s1", "retry", 2) == 1
    assert port.increment("s1", "retry", 2) == 2
    with pytest.raises(counters.BudgetExhaustedError):
        port.increment("s1", "retry", 2)
    # restart-safe through the port as well
    assert counters.FileCounterStore(tmp_path / "port.json").load("s1", "retry") == 2


def test_idempotency_key_deterministic():
    first = idempotency.derive_idempotency_key(
        project_id="P1", task_id="T1", action="charge", payload_hash="p1", contract_hash="h1"
    )
    second = idempotency.derive_idempotency_key(
        project_id="P1", task_id="T1", action="charge", payload_hash="p1", contract_hash="h1"
    )
    assert first == second and len(first) == 64
    assert (
        idempotency.derive_idempotency_key(
            project_id="P1", task_id="T1", action="charge", payload_hash="other", contract_hash="h1"
        )
        != first
    )


def test_duplicate_register_returns_stored_record(tmp_path):
    log = idempotency.ActionLog(tmp_path / "actions.json")
    stored = log.register(_action())
    duplicate = log.register(_action())
    assert duplicate == stored
    assert log.lookup("k-1") == stored


def test_settle_once_never_double_settle(tmp_path):
    log = idempotency.ActionLog(tmp_path / "actions.json")
    log.register(_action())
    log.begin("k-1")
    settled = log.settle("k-1", "SUCCEEDED", external_ref="ext-1", completed_at="t1")
    assert settled.status == idempotency.ActionExecutionStatus.SUCCEEDED
    with pytest.raises(idempotency.AlreadySettledError):
        log.settle("k-1", "FAILED")
    assert log.lookup("k-1").status == idempotency.ActionExecutionStatus.SUCCEEDED


def test_repeat_requires_matching_prior_state(tmp_path):
    log = idempotency.ActionLog(tmp_path / "actions.json")
    log.register(_action())
    assert log.verify_repeat("k-1", "state-0").action_id == "act-1"
    with pytest.raises(idempotency.PriorStateMismatchError):
        log.verify_repeat("k-1", "state-CHANGED")


def test_unprotected_mutation_retry_prohibited(tmp_path):
    log = idempotency.ActionLog(tmp_path / "actions.json")
    with pytest.raises(idempotency.UnprotectedMutationError):
        log.register(_action(key=""))
    with pytest.raises(idempotency.UnprotectedMutationError):
        log.register(_action(key="k-u", protected=False))
    with pytest.raises(idempotency.UnprotectedMutationError):
        log.verify_repeat("unknown-key", "whatever")
