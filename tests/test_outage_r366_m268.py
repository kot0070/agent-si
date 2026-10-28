"""M-P2-68 + R-366: helper-provider outage telemetry + observe + budget gate.

Helper-provider outage: telemetry linkage plus small audits on free models
(M-P2-68); observe reads plus budget gate on the K04 side (R-366).

RED-first behaviour tests through real entries (ProviderHealthLog,
TelemetryEventLog, BudgetGate, CostCalculator, build_routing_reason).
Doubles (journal-append, notify) live in this file only; every assert
reads REAL output. No watcher import anywhere on this path.
"""
import inspect
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_si.budget import gate as BG  # noqa: E402
from agent_si.budget import observe as OB  # noqa: E402
from agent_si.budget import telemetry as BT  # noqa: E402
from agent_si.providers.registry.health import (  # noqa: E402
    ProviderHealthLog,
)


TS = "2026-10-26T00:00:00Z"


class _Journal:
    """Test-double journal-append end of the K08 seam (this file only)."""

    def __init__(self):
        self.rows = []

    def append(self, record):
        self.rows.append(dict(record))
        return {"ok": True}


class _Notifier:
    """Test-double notify end of the K08 seam (this file only)."""

    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(dict(event))
        return {"ok": True}


def _gate():
    gate = BG.BudgetGate()
    gate.configure_project(
        project_id="p1", currency="USD", budget_limit="10.00",
        soft_limit="7.00", hard_limit="10.00",
    )
    return gate


def _priced_snapshot(snapshot_id="ps-outage-priced"):
    return BT.make_snapshot(
        pricing_snapshot_id=snapshot_id,
        provider_id="cloud-a",
        model_id="cloud-a/model-x",
        currency="USD",
        effective_at="2026-10-26T00:00:00Z",
        source="provider_pricing_api",
        input_token_price="0.001",
        output_token_price="0.002",
        created_at="2026-10-26T00:00:00Z",
    )


def _free_snapshot(snapshot_id="ps-outage-free"):
    return BT.make_snapshot(
        pricing_snapshot_id=snapshot_id,
        provider_id="cloud-free",
        model_id="cloud-free/model-f",
        currency="USD",
        effective_at="2026-10-26T00:00:00Z",
        source="provider_pricing_api",
        input_token_price="0",
        output_token_price="0",
        cached_token_price="0",
        reasoning_token_price="0",
        request_price="0",
        created_at="2026-10-26T00:00:00Z",
    )


def test_observe_maps_registry_status_incl_unknown_down():
    log = ProviderHealthLog()
    log.record("cloud-a", "i-1", "ONLINE")
    log.record("cloud-b", "i-1", "DEGRADED")
    log.record("cloud-c", "i-1", "OFFLINE")
    rows = OB.observe_services(
        log,
        [("cloud-a", "i-1"), ("cloud-b", "i-1"), ("cloud-c", "i-1"),
         ("cloud-never-seen", "i-9")],
        project_id="p1", session_token="q-1",
    )
    by_provider = {row["provider_id"]: row for row in rows}
    assert by_provider["cloud-a"]["service"] == "UP"
    assert by_provider["cloud-a"]["reason"] == ""
    assert by_provider["cloud-b"]["service"] == "DEGRADED"
    assert by_provider["cloud-c"]["service"] == "DOWN"
    assert by_provider["cloud-never-seen"]["registry_status"] == "UNKNOWN"
    assert by_provider["cloud-never-seen"]["service"] == "DOWN"
    assert by_provider["cloud-never-seen"]["reason"] == "unknown-health"
    assert OB.map_service_status("BOGUS") == ("DOWN", "unknown-health")


def test_outage_round_trip_links_telemetry_and_budget():
    log = ProviderHealthLog()
    log.record_outage("cloud-a", "i-1", error="connect timeout")
    assert OB.observe_provider(
        log, "cloud-a", "i-1",
        project_id="p1", session_token="q-1")["service"] == "DOWN"
    journal, notifier = _Journal(), _Notifier()
    telemetry_log = BT.TelemetryEventLog()
    gate = _gate()
    result = OB.link_outage(
        outage_id="out-001", provider_id="cloud-a", instance_id="i-1",
        project_id="p1", task_id="t1", run_id="r1", timestamp=TS,
        telemetry_log=telemetry_log, gate=gate,
        usage={"input_tokens": 1000, "output_tokens": 500},
        pricing_snapshot=_priced_snapshot(),
        journal_append=journal.append, notify=notifier.emit,
        session_token="q-1",
    )
    assert result["service"] == "DOWN"
    assert result["notified"] is True
    assert result["cost"]["amount"] == "2.000000"
    assert result["cost"]["state"] == "CALCULATED"
    event = telemetry_log.get("out-001")
    assert event["event_type"] == "incident_recorded"
    assert event["event_id"] == "out-001"
    incidents = gate.list_incidents("p1")
    assert [i.incident_id for i in incidents] == ["out-001"]
    assert len(journal.rows) == 1
    assert journal.rows[0]["outage_id"] == "out-001"
    assert len(notifier.events) == 1
    assert notifier.events[0]["outage_id"] == "out-001"


def test_outage_cost_unavailable_without_snapshot_never_zero():
    telemetry_log = BT.TelemetryEventLog()
    gate = _gate()
    result = OB.link_outage(
        outage_id="out-002", provider_id="cloud-a", instance_id="i-1",
        project_id="p1", task_id="t1", run_id="r1", timestamp=TS,
        telemetry_log=telemetry_log, gate=gate,
        usage={"input_tokens": 1000, "output_tokens": 500},
        pricing_snapshot=None,
        journal_append=_Journal().append, notify=_Notifier().emit,
        session_token="q-1",
    )
    assert result["cost"]["amount"] is None
    assert result["cost"]["state"] == "UNAVAILABLE"
    assert telemetry_log.get("out-002")["event_type"] == "incident_recorded"
    result2 = OB.link_outage(
        outage_id="out-003", provider_id="cloud-a", instance_id="i-1",
        project_id="p1", task_id="t1", run_id="r1", timestamp=TS,
        telemetry_log=telemetry_log, gate=gate,
        usage=None,
        pricing_snapshot=_priced_snapshot("ps-outage-priced-2"),
        journal_append=_Journal().append, notify=_Notifier().emit,
        session_token="q-1",
    )
    assert result2["cost"]["amount"] is None
    assert result2["cost"]["state"] == "UNAVAILABLE"


def test_unwired_seam_fail_closed_down_plus_local_incident():
    telemetry_log = BT.TelemetryEventLog()
    gate = _gate()
    result = OB.link_outage(
        outage_id="out-004", provider_id="cloud-a", instance_id="i-1",
        project_id="p1", task_id="t1", run_id="r1", timestamp=TS,
        telemetry_log=telemetry_log, gate=gate,
        usage={"input_tokens": 10},
        pricing_snapshot=_priced_snapshot("ps-outage-priced-3"),
        journal_append=None, notify=None,
        session_token="q-1",
    )
    assert result["service"] == "DOWN"
    assert result["reason"] == "seam-down"
    assert result["notified"] is False
    assert telemetry_log.get("out-004")["event_type"] == "incident_recorded"
    assert [i.incident_id for i in gate.list_incidents("p1")] == ["out-004"]


def test_free_audit_pick_uses_zero_price_snapshot():
    candidates = [
        {"provider_id": "cloud-a", "model": "model-x",
         "pricing_snapshot": _priced_snapshot("ps-outage-paid-pick")},
        {"provider_id": "cloud-free", "model": "model-f",
         "pricing_snapshot": _free_snapshot()},
    ]
    result = OB.pick_free_audit_model(
        candidates, project_id="p1", session_token="q-1",
        budget_remaining="10.00", budget_hard_limit="10.00",
    )
    assert result["pick"]["provider_id"] == "cloud-free"
    assert result["pick"]["model"] == "model-f"
    assert "route AUDIT selected" in result["reason"]
    assert "cloud-free/model-f" in result["reason"]


def test_no_free_audit_candidate_fail_closed():
    candidates = [
        {"provider_id": "cloud-a", "model": "model-x",
         "pricing_snapshot": _priced_snapshot("ps-outage-paid-only")},
    ]
    with pytest.raises(ValueError):
        OB.pick_free_audit_model(
            candidates, project_id="p1", session_token="q-1")


def test_gate_refuses_billable_reservation_on_down_provider():
    gate = _gate()
    request = {
        "project_id": "p1", "task_id": "t1", "run_id": "r1",
        "reservation_id": "res-outage-1", "estimated_amount": "1.00",
        "reserved_at": TS, "expires_at": "2026-10-27T00:00:00Z",
        "provider_id": "cloud-a",
    }
    with pytest.raises(BG.BudgetBlockedError) as excinfo:
        OB.reserve_checked(gate, request, "DOWN", timestamp=TS)
    assert str(excinfo.value).endswith("[PROVIDER_OUTAGE_BLOCKED]")
    assert any("cloud-a" in i.description
               for i in gate.list_incidents("p1"))
    with pytest.raises(KeyError):
        gate.get_reservation("res-outage-1")


def test_gate_override_allows_reservation_on_down_provider():
    gate = _gate()
    result = OB.reserve_checked(
        gate,
        {"project_id": "p1", "task_id": "t1", "run_id": "r1",
         "reservation_id": "res-outage-2", "estimated_amount": "1.00",
         "reserved_at": TS, "expires_at": "2026-10-27T00:00:00Z",
         "provider_id": "cloud-a"},
        "DOWN", override_ref="auth-1", timestamp=TS,
    )
    assert result.ok is True
    assert gate.get_reservation("res-outage-2").status == "ACTIVE"


def test_query_style_identity_required_never_body():
    log = ProviderHealthLog()
    log.record("cloud-a", "i-1", "ONLINE")
    row = OB.observe_provider(
        log, "cloud-a", "i-1", project_id="p1", session_token="q-1")
    assert row["service"] == "UP"
    with pytest.raises(ValueError):
        OB.observe_provider(
            log, "cloud-a", "i-1", project_id="p1", session_token="")
    with pytest.raises(ValueError):
        OB.observe_provider(
            log, "cloud-a", "i-1", project_id="", session_token="q-1")
    for fn in (OB.observe_provider, OB.observe_services,
               OB.pick_free_audit_model, OB.link_outage):
        assert "body" not in inspect.signature(fn).parameters


def test_record_outage_marks_offline_with_check_type():
    log = ProviderHealthLog()
    entry = log.record_outage("cloud-a", "i-1", error="dns failure")
    assert entry.status == "OFFLINE"
    assert log.status_of("cloud-a", "i-1") == "OFFLINE"
    assert entry.view()["check_type"] == "outage"
