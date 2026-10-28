"""Lane B2 probes: project budget gate + usage/cost telemetry (K04 code, K13 schemas).

RED-first: these tests define the contract. They fail until
src/agent_si/budget/{__init__,gate,telemetry}.py implement it.
"""
import sys
import threading
from decimal import Decimal
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_si.budget.gate import (  # noqa: E402
    BudgetBlockedError,
    BudgetGate,
    DuplicateSettlementError,
)
from agent_si.budget.telemetry import (  # noqa: E402
    CostCalculator,
    DefaultManagerProfile,
    MetricLog,
    MetricState,
    PricingSnapshot,
    RoleModelProfile,
    SecretStore,
    TelemetryEventLog,
    build_routing_reason,
    build_telemetry_event,
    make_metric,
    make_snapshot,
)


def _snapshot() -> PricingSnapshot:
    return make_snapshot(
        pricing_snapshot_id="ps-001",
        provider_id="cloud-a",
        model_id="cloud-a/model-x",
        currency="USD",
        effective_at="2026-10-26T00:00:00Z",
        source="provider_pricing_api",
        input_token_price="0.001",
        output_token_price="0.002",
        created_at="2026-10-26T00:00:00Z",
    )


def _gate(tmp_path: Path) -> BudgetGate:
    gate = BudgetGate(store_dir=tmp_path / "ledger")
    gate.configure_project(
        project_id="p1", currency="USD", budget_limit="10.00",
        soft_limit="7.00", hard_limit="10.00",
    )
    return gate


def test_parallel_reservations_never_exceed_hard(tmp_path):
    gate = _gate(tmp_path)
    results = []

    def worker(i: int):
        try:
            res = gate.compare_and_reserve(
                {
                    "project_id": "p1", "task_id": "t1", "run_id": "r1",
                    "reservation_id": f"res-{i}", "estimated_amount": "3.00",
                    "reserved_at": "2026-10-26T00:00:00Z",
                    "expires_at": "2026-10-27T00:00:00Z",
                }
            )
            results.append(res.ok)
        except Exception:  # noqa: BLE001 - contention must surface, never hang
            results.append(False)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for ok in results if ok) == 3
    state = gate.get_state("p1")
    assert Decimal(state.spent) + Decimal(state.reserved) <= Decimal(state.hard_limit)


def test_duplicate_settlement_refused(tmp_path):
    gate = _gate(tmp_path)
    gate.compare_and_reserve(
        {
            "project_id": "p1", "task_id": "t1", "run_id": "r1",
            "reservation_id": "res-1", "estimated_amount": "4.00",
            "reserved_at": "2026-10-26T00:00:00Z",
            "expires_at": "2026-10-27T00:00:00Z",
        }
    )
    first = gate.settle(
        {
            "reservation_id": "res-1", "actual_amount": "1.50",
            "provider_usage_evidence_ref": "usage-ev-1",
            "provider_request_ref": "req-1",
            "source": "provider_usage_api",
            "settled_at": "2026-10-26T01:00:00Z",
        }
    )
    assert first.status == "SETTLED"
    with pytest.raises(DuplicateSettlementError):
        gate.settle(
            {
                "reservation_id": "res-1", "actual_amount": "1.50",
                "provider_usage_evidence_ref": "usage-ev-1",
                "provider_request_ref": "req-1",
                "source": "provider_usage_api",
                "settled_at": "2026-10-26T01:00:00Z",
            }
        )
    state = gate.get_state("p1")
    assert Decimal(state.spent) == Decimal("1.50")


def test_restart_reconciles_pending(tmp_path):
    store = tmp_path / "ledger"
    gate = BudgetGate(store_dir=store)
    gate.configure_project(
        project_id="p1", currency="USD", budget_limit="10.00",
        soft_limit="7.00", hard_limit="10.00",
    )
    gate.compare_and_reserve(
        {
            "project_id": "p1", "task_id": "t1", "run_id": "r1",
            "reservation_id": "res-billed", "estimated_amount": "4.00",
            "reserved_at": "2026-10-26T00:00:00Z",
            "expires_at": "2026-10-27T00:00:00Z",
        }
    )
    gate.compare_and_reserve(
        {
            "project_id": "p1", "task_id": "t1", "run_id": "r1",
            "reservation_id": "res-unused", "estimated_amount": "2.00",
            "reserved_at": "2026-10-26T00:00:00Z",
            "expires_at": "2026-10-26T00:30:00Z",
        }
    )
    # Simulate process restart: fresh in-memory gate over the same store.
    gate2 = BudgetGate(store_dir=store)
    summary, _ = gate2._reconcile_impl(
        {
            "res-billed": {
                "actual_amount": "1.25",
                "provider_usage_evidence_ref": "usage-ev-9",
                "provider_request_ref": "req-9",
                "source": "provider_usage_api",
            },
        },
        "2026-10-26T02:00:00Z",
    )
    assert summary["settled"] == ["res-billed"]
    assert summary["released"] == ["res-unused"]
    state = gate2.get_state("p1")
    assert Decimal(state.spent) == Decimal("1.25")
    assert Decimal(state.reserved) == Decimal("0")
    # Second restart must not double-settle.
    summary2, _ = gate2._reconcile_impl({}, "2026-10-26T03:00:00Z")
    assert summary2["settled"] == []
    assert Decimal(gate2.get_state("p1").spent) == Decimal("1.25")


def test_cost_unavailable_without_snapshot():
    metric = CostCalculator.unavailable_cost(
        metric_id="m-cost-1", project_id="p1", task_id="t1", run_id="r1",
        metric_name="cost", unit="USD", source="agent_si_runtime",
        recorded_at="2026-10-26T00:00:00Z",
    )
    assert metric.state == MetricState.UNAVAILABLE
    assert metric.value is None
    assert metric.value != 0


def test_editable_budget_counts_real_usage_in_currency(tmp_path):
    gate = _gate(tmp_path)
    gate.update_limits(project_id="p1", hard_limit="20.00", soft_limit="15.00")
    gate.compare_and_reserve(
        {
            "project_id": "p1", "task_id": "t1", "run_id": "r1",
            "reservation_id": "res-1", "estimated_amount": "5.00",
            "reserved_at": "2026-10-26T00:00:00Z",
            "expires_at": "2026-10-27T00:00:00Z",
        }
    )
    gate.settle(
        {
            "reservation_id": "res-1", "actual_amount": "0.42",
            "provider_usage_evidence_ref": "usage-ev-1",
            "provider_request_ref": "req-1",
            "source": "provider_usage_api",
            "settled_at": "2026-10-26T01:00:00Z",
        }
    )
    state = gate.get_state("p1")
    assert state.currency == "USD"
    assert state.hard_limit == "20.00"
    assert Decimal(state.spent) == Decimal("0.42")


def test_every_budget_breach_recorded_as_persistent_incident(tmp_path):
    gate = _gate(tmp_path)
    gate.compare_and_reserve(
        {
            "project_id": "p1", "task_id": "t1", "run_id": "r1",
            "reservation_id": "res-fill", "estimated_amount": "10.00",
            "reserved_at": "2026-10-26T00:00:00Z",
            "expires_at": "2026-10-27T00:00:00Z",
        }
    )
    with pytest.raises(BudgetBlockedError):
        gate.compare_and_reserve(
            {
                "project_id": "p1", "task_id": "t1", "run_id": "r1",
                "reservation_id": "res-over", "estimated_amount": "0.01",
                "reserved_at": "2026-10-26T00:00:00Z",
                "expires_at": "2026-10-27T00:00:00Z",
            }
        )
    incidents = gate.list_incidents(project_id="p1")
    assert len(incidents) == 1
    assert "budget" in incidents[0].description.lower()
    persisted = list((tmp_path / "ledger").glob("incident*.json"))
    assert persisted, "breach incident must persist to the ledger store"


def test_metric_write_rejects_missing_provenance():
    log = MetricLog()
    with pytest.raises(ValueError):
        make_metric(
            metric_id="m-1", project_id="p1", task_id="t1", run_id="r1",
            metric_name="input_tokens", value=10, unit="tokens",
            state=MetricState.MEASURED, source="",
            recorded_at="2026-10-26T00:00:00Z",
        )
    with pytest.raises(ValueError):
        log.append(
            {
                "metric_id": "m-2", "project_id": "p1", "task_id": "t1",
                "run_id": "r1", "metric_name": "input_tokens", "value": None,
                "unit": "tokens", "state": MetricState.MEASURED,
                "source": "provider_usage_api",
                "recorded_at": "2026-10-26T00:00:00Z",
            }
        )


def test_historical_cost_reproduces_from_original_snapshot():
    snapshot = _snapshot()
    first = CostCalculator.cost_metric(
        metric_id="m-cost-1", project_id="p1", task_id="t1", run_id="r1",
        metric_name="cost", snapshot=snapshot, input_tokens=1000,
        output_tokens=500, source="agent_si_runtime",
        recorded_at="2026-10-26T00:00:00Z",
    )
    again = CostCalculator.cost_metric(
        metric_id="m-cost-2", project_id="p1", task_id="t1", run_id="r1",
        metric_name="cost", snapshot=snapshot, input_tokens=1000,
        output_tokens=500, source="agent_si_runtime",
        recorded_at="2026-10-27T00:00:00Z",
    )
    assert first.state == MetricState.CALCULATED
    assert first.value == again.value == "2.000000"
    assert "ps-001" in first.source


def test_telemetry_envelope_builder_and_dedupe():
    log = TelemetryEventLog()
    event = build_telemetry_event(
        event_id="ev-1", project_id="p1",
        timestamp="2026-10-26T00:00:00Z", task_id="t1", run_id="r1",
        event_type="attempt_completed",
    )
    assert event["project_id"] == "p1"
    assert event["metric_refs"] == []
    stored = log.append(event)
    assert log.append(dict(event)) is stored
    with pytest.raises(ValueError):
        build_telemetry_event(
            event_id="ev-2", project_id="p1",
            timestamp="2026-10-26T00:00:00Z", event_type="made_up_type",
        )


def test_routing_reason_carries_cost_budget_why_text():
    reason = build_routing_reason(
        estimated_cost="0.42", currency="USD", budget_remaining="9.58",
        budget_hard_limit="10.00", route="CLOUD",
        extra_text="cheapest shared-fit candidate",
    )
    for token in ("0.42", "USD", "9.58", "10.00"):
        assert token in reason


def test_role_and_manager_profiles_and_secret_refs():
    profile = RoleModelProfile(
        role="verifier", project_id="p1", mode="AUTO",
        provider="cloud-a", model="cloud-a/model-x", binding="DEFAULT",
        version=1, hash="h1",
    )
    assert profile.mode == "AUTO"
    with pytest.raises(ValueError):
        RoleModelProfile(
            role="verifier", project_id="p1", mode="SOMETIMES",
            provider="cloud-a", model="cloud-a/model-x", binding="DEFAULT",
            version=1, hash="h1",
        )
    manager = DefaultManagerProfile(
        profile_id="DMP-001", version=1, provider="meta",
        model="meta/muse-spark-1.3-contributor", binding="DEFAULT", hash="h0",
    )
    manager2 = manager.with_change(provider="cloud-a", reason="recorded fallback")
    assert manager2.version == 2
    assert manager2.provider == "cloud-a"
    with pytest.raises(ValueError):
        DefaultManagerProfile(
            profile_id="DMP-001", version=1, provider="meta",
            model="meta/muse-spark-1.3-contributor", binding="SOFT", hash="h0",
        )
    store = SecretStore()
    store.put(
        secret_id="api-key-a", provider_id="cloud-a", type="api_key",
        scope="project", source="os_store",
        created_at="2026-10-26T00:00:00Z",
        last_rotated_at="2026-10-26T00:00:00Z", secret_value="s3cr3t",
    )
    ref = store.ref("api-key-a")
    assert ref.secret_id == "api-key-a"
    assert "s3cr3t" not in repr(ref)
    assert all("s3cr3t" not in entry for entry in store.audit_log())
    store.delete("api-key-a")
    with pytest.raises(KeyError):
        store.ref("api-key-a")


def test_budget_message_literals_carry_machine_codes(tmp_path):
    gate = _gate(tmp_path)
    res = gate.compare_and_reserve(
        {
            "project_id": "p1", "task_id": "t1", "run_id": "r1",
            "reservation_id": "res-soft", "estimated_amount": "7.50",
            "reserved_at": "2026-10-26T00:00:00Z",
            "expires_at": "2026-10-27T00:00:00Z",
        }
    )
    assert res.ok
    assert res.warning is not None
    assert "soft budget limit reached" in res.warning
    assert "BUDGET_SOFT_WARN" in res.warning
    gate.compare_and_reserve(
        {
            "project_id": "p1", "task_id": "t1", "run_id": "r1",
            "reservation_id": "res-fill", "estimated_amount": "2.50",
            "reserved_at": "2026-10-26T00:00:00Z",
            "expires_at": "2026-10-27T00:00:00Z",
        }
    )
    with pytest.raises(BudgetBlockedError) as excinfo:
        gate.compare_and_reserve(
            {
                "project_id": "p1", "task_id": "t1", "run_id": "r1",
                "reservation_id": "res-over", "estimated_amount": "0.01",
                "reserved_at": "2026-10-26T00:00:00Z",
                "expires_at": "2026-10-27T00:00:00Z",
            }
        )
    assert "hard budget limit blocks" in str(excinfo.value)
    assert "BUDGET_HARD_BLOCKED" in str(excinfo.value)
    gate.settle(
        {
            "reservation_id": "res-soft", "actual_amount": "1.00",
            "provider_usage_evidence_ref": "usage-ev-1",
            "provider_request_ref": "req-1",
            "source": "provider_usage_api",
            "settled_at": "2026-10-26T01:00:00Z",
        }
    )
    with pytest.raises(DuplicateSettlementError) as dupinfo:
        gate.settle(
            {
                "reservation_id": "res-soft", "actual_amount": "1.00",
                "provider_usage_evidence_ref": "usage-ev-1",
                "provider_request_ref": "req-1",
                "source": "provider_usage_api",
                "settled_at": "2026-10-26T01:00:00Z",
            }
        )
    assert "duplicate settlement refused" in str(dupinfo.value)
    assert "DUPLICATE_SETTLEMENT_REFUSED" in str(dupinfo.value)
