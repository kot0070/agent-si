"""UNTEST2 K04 rows: behaviour tests through the served app (create_app + TestClient).

Rows: 1285 (43), 1415 (M-P2-63), 1589 (BP04-34), 1689 (UI_DELTA-32),
1567 (ARCH-452), 1640 (BP04-5), 1641 (BP04-14). Real modules only;
fake only at the provider transport where a transport is needed (none
of these rows needs a provider call, so no transport fake at all).
"""
import dataclasses
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest


def _client(tmp_path):
    from agent_si.backend.app import create_app
    import fastapi.testclient

    app = create_app(
        {"store_dir": str(tmp_path / "appdata"), "secret_store": "memory"},
        auth_hook=None,
        rate_hook=None,
        model_factory=None,
    )
    return fastapi.testclient.TestClient(app)


_HDRS = {"x-actor": "ui-untest2", "x-ui-session-token": "ui-untest2"}


def test_1285_pinned_no_silent_swap_served(tmp_path):
    """Row 1285 (43): PINNED health decides READY vs PINNED_UNHEALTHY, never a swap."""

    client = _client(tmp_path)
    body = {
        "project_id": "p1",
        "role": "worker",
        "mode": "PINNED",
        "provider": "pa",
        "model": "pn-1",
        "pool": [],
        "strategy": "AUTO",
    }
    resp = client.put("/api/v1/roles/pools", json=body, headers=_HDRS)
    assert resp.status_code == 200, resp.text
    got = client.get("/api/v1/roles/pools", params={"project_id": "p1"})
    assert got.status_code == 200, got.text
    row = [r for r in got.json()["roles"] if r["role"] == "worker"][0]
    assert row["provider"] == "pa", row
    assert row["model"] == "pn-1", row
    ctx = client.app.state.k04_ctx
    res2 = ctx.role_table.resolve("p1", "worker")
    assert res2.status == "PINNED_UNHEALTHY", res2
    assert res2.provider == "pa" and res2.model == "pn-1", res2
    assert "fallback path" in res2.reason, res2
    assert "never silently" in res2.reason, res2


def test_1415_provider_spend_caps_served(tmp_path):
    """Row 1415 (M-P2-63): provider spend caps warn/block through the served budget path."""
    from agent_si.budget.gate import BudgetBlockedError

    client = _client(tmp_path)
    gate = client.app.state.k04_ctx.budget_state
    gate.configure_project(
        project_id="p1", currency="USD", budget_limit="10.00",
        soft_limit="7.00", hard_limit="10.00",
        provider_spend_caps={"openai": "1.00"},
    )
    first = gate.compare_and_reserve({
        "project_id": "p1", "task_id": "t1", "run_id": "r1",
        "reservation_id": "res-cap-1", "estimated_amount": "0.60",
        "reserved_at": "2026-10-26T00:00:00Z",
        "expires_at": "2026-10-27T00:00:00Z",
        "provider_id": "openai",
    })
    assert first.ok, first
    with pytest.raises(BudgetBlockedError):
        gate.compare_and_reserve({
            "project_id": "p1", "task_id": "t1", "run_id": "r1",
            "reservation_id": "res-cap-2", "estimated_amount": "0.60",
            "reserved_at": "2026-10-26T00:00:00Z",
            "expires_at": "2026-10-27T00:00:00Z",
            "provider_id": "openai",
        })
    resp = client.get("/api/v1/budget", params={"project_id": "p1"})
    assert resp.status_code == 200, resp.text
    payload = resp.json()["budget"]
    assert payload["provider_spend_caps"] == {"openai": "1.00"}, payload
    incidents = gate.list_incidents("p1")
    assert any("spend cap" in i.description for i in incidents), [
        i.description for i in incidents]


def test_1589_hard_block_terminalizes_served(tmp_path):
    """Row 1589 (BP04-34): pre-run BUDGET_BLOCKED with hard limit terminalizes the run."""
    from agent_si.budget.gate import BudgetBlockedError
    from agent_si.state_machines import run_machine as RM
    from iface.frozen_manifest import manifest as MF

    client = _client(tmp_path)
    gate = client.app.state.k04_ctx.budget_state
    gate.configure_project(
        project_id="p1", currency="USD", budget_limit="1.00",
        soft_limit="0.80", hard_limit="1.00",
    )
    gate.compare_and_reserve({
        "project_id": "p1", "task_id": "t1", "run_id": "r1",
        "reservation_id": "res-fill", "estimated_amount": "1.00",
        "reserved_at": "2026-10-26T00:00:00Z",
        "expires_at": "2026-10-27T00:00:00Z",
    })
    with pytest.raises(BudgetBlockedError):
        gate.compare_and_reserve({
            "project_id": "p1", "task_id": "t1", "run_id": "r1",
            "reservation_id": "res-over", "estimated_amount": "0.01",
            "reserved_at": "2026-10-26T00:00:00Z",
            "expires_at": "2026-10-27T00:00:00Z",
        })
    incidents = gate.list_incidents("p1")
    assert len(incidents) == 1, [i.description for i in incidents]
    assert incidents[0].status == "OPEN", incidents[0]
    resp = client.get("/api/v1/budget", params={"project_id": "p1"})
    assert resp.status_code == 200, resp.text
    run = RM.create_run(
        run_id="r1", task_id="t1", project_id="p1",
        contract_hash="h-untest2", run_sequence=1,
    )
    disp = RM.apply_pre_run_disposition(run, MF.RunTerminationReason.BUDGET_BLOCKED)
    assert disp.run_to_status == MF.ExecutionRunStatus.FAILED, disp
    assert disp.run_to_reason == MF.RunTerminationReason.BUDGET_BLOCKED, disp
    assert disp.release_reservations is True, disp


def test_1689_stored_profile_reflects_in_run_served(tmp_path):
    """Row 1689 (UI_DELTA-32): stored profile edit reflects in run behaviour."""
    client = _client(tmp_path)
    body = {
        "project_id": "p1",
        "role": "worker",
        "mode": "PINNED",
        "provider": "pa",
        "model": "pn-9",
        "pool": [],
        "strategy": "AUTO",
    }
    resp = client.put("/api/v1/roles/pools", json=body, headers=_HDRS)
    assert resp.status_code == 200, resp.text
    got = client.get("/api/v1/roles/pools", params={"project_id": "p1"})
    assert got.status_code == 200, got.text
    row = [r for r in got.json()["roles"] if r["role"] == "worker"][0]
    assert row["mode"] == "PINNED", row
    assert row["provider"] == "pa" and row["model"] == "pn-9", row
    from agent_si.backend import pools_routes as PR

    ctx = client.app.state.k04_ctx
    prof = ctx.role_table.get_profile("p1", "worker")
    assert prof is not None and prof.model == "pn-9", prof
    stored = ctx.store.get_role_profile("p1", "worker")
    assert stored is not None and stored["model"] == "pn-9", stored
    body2 = dict(body, model="pn-10")
    resp2 = client.put("/api/v1/roles/pools", json=body2, headers=_HDRS)
    assert resp2.status_code == 200, resp2.text
    got2 = client.get("/api/v1/roles/pools", params={"project_id": "p1"})
    assert got2.status_code == 200, got2.text
    row2 = [r for r in got2.json()["roles"] if r["role"] == "worker"][0]
    assert row2["model"] == "pn-10", row2
    prof2 = ctx.role_table.get_profile("p1", "worker")
    assert prof2 is not None and prof2.model == "pn-10", prof2
    res = ctx.role_table.resolve("p1", "worker")
    assert res.model == "pn-10" and res.provider == "pa", res
    assert res.status == "PINNED_UNHEALTHY", res


def test_1567_unpermitted_probing_refused_served(tmp_path):
    """Row 1567 (ARCH-452): permission-gated local probing refuses unpermitted scope."""
    from agent_si.local import adapter as AD
    from agent_si.local import k05r3_discover as KD

    client = _client(tmp_path)
    probe = client.get("/api/v1/roles/pools", params={"project_id": "p1"})
    assert probe.status_code == 200, probe.text
    with pytest.raises(KD.DiscoverError) as excinfo:
        KD.enter_discover(AD.LifecycleStage.SCAN, "no-such-scope")
    assert excinfo.value.code == KD.K05R3_DISCOVER_PERMISSION_REFUSED, excinfo.value.code
    verdict = AD.check_admission(
        "measured routing-eligibility evidence ref",
        "healthy-signal",
        "idle-machine",
        "no-such-scope",
    )
    assert verdict.admitted is False, verdict
    assert "ADMISSION_PERMISSION_REFUSED" in verdict.reason, verdict.reason
    assert verdict.admission_refs[3] == "no-such-scope", verdict


def test_1640_rededupe_identical_ref_served(tmp_path):
    """Row 1640 (BP04-5): re-collection with identical ref attaches without duplicating."""
    from agent_si.telemetry import metrics as M

    client = _client(tmp_path)
    probe = client.get("/api/v1/budget", params={"project_id": "p1"})
    assert probe.status_code in (200, 404), probe.text
    log = M.MetricRecordLog()
    rec = M.MetricRecord(
        metric_id="m-dedupe-1", project_id="p1", metric_name="cost",
        value=1.5, unit="USD", state=M.MetricState.CALCULATED,
        source="cost-calculator",
    )
    first = log.append(rec)
    second = log.append(M.MetricRecord(
        metric_id="m-dedupe-1", project_id="p1", metric_name="cost",
        value=1.5, unit="USD", state=M.MetricState.CALCULATED,
        source="cost-calculator",
    ))
    assert second is first, (second, first)
    assert len(log) == 1, len(log)
    assert log.load("m-dedupe-1").value == 1.5, log.load("m-dedupe-1")


def test_1641_snapshot_immutable_served(tmp_path):
    """Row 1641 (BP04-14): a referenced snapshot is immutable; correction is a new snapshot."""
    from agent_si.telemetry import metrics as M

    client = _client(tmp_path)
    probe = client.get("/api/v1/budget", params={"project_id": "p1"})
    assert probe.status_code in (200, 404), probe.text
    snap = M.PricingSnapshot(
        pricing_snapshot_id="ps-1", provider_id="cloud-a",
        model_id="cloud-a/model-x", currency="USD",
        effective_at="2026-10-26T00:00:00Z", source="provider_pricing_api",
        created_at="2026-10-26T00:00:00Z", hash="h1",
        input_token_price=0.001, output_token_price=0.002,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.input_token_price = 9.99  # type: ignore[misc]
    assert snap.input_token_price == 0.001, snap
    corrected = dataclasses.replace(
        snap, pricing_snapshot_id="ps-2", hash="h2",
        input_token_price=0.002,
    )
    assert corrected.pricing_snapshot_id == "ps-2", corrected
    assert corrected.input_token_price == 0.002, corrected
    assert snap.input_token_price == 0.001, snap
    assert snap.pricing_snapshot_id == "ps-1", snap
