"""K04NEXT4 CODER-A served proofs: budget caps plus shipped KB.

Row M-P2-63: per-trial billed spend settles into the monthly cap; the
served budget page warns at the soft cap and the hard cap blocks with a
persistent incident.
Row M-P3-124: the shipped model KB file/format validates served, and a
served AUTO decision reads fit-price-quality per shipped candidate into
its evidence (fail-closed with stable codes while the seed is honest
UNKNOWN; routed-on-shipped needs the model_kb risk/quality/fit mapping,
recorded NOT-DONE waits-for-pkg in CODER-A-RETURN.md).
Real modules only; no mocks for the claim. Loopback TestClient only.
"""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


_HDRS = {"x-actor": "ui-next4a", "x-ui-session-token": "ui-next4a"}

_TS = "2026-10-26T00:00:00Z"
_TS2 = "2026-10-26T01:00:00Z"


# M-P2-63: billed spend per trial vs monthly cap; warn plus block.
def test_m_p2_63_billed_spend_per_trial_warn_then_monthly_cap_block_served(
        tmp_path):
    """Row M-P2-63: per-trial billed spend settles into the monthly cap.

    Trial 1 reserves plus settles its billed spend; trial 2 settles too
    so the committed total crosses the soft cap (served warn flag plus
    warning on the budget page); trial 3 would breach the monthly hard
    cap (block plus incident, page still served with settled spend).
    """
    from agent_si.budget.gate import BudgetBlockedError

    client = _client(tmp_path)
    gate = client.app.state.k04_ctx.budget_state
    gate.configure_project(
        project_id="p1", currency="USD", budget_limit="10.00",
        soft_limit="7.00", hard_limit="10.00",
    )
    first = gate.compare_and_reserve({
        "project_id": "p1", "task_id": "t1", "run_id": "r1",
        "reservation_id": "res-n4a-trial-1", "estimated_amount": "5.00",
        "reserved_at": _TS, "expires_at": "2026-10-27T00:00:00Z"})
    assert first.ok, first
    assert first.warning is None, first
    settled = gate.settle({
        "reservation_id": "res-n4a-trial-1", "source": "provider-receipt",
        "settled_at": _TS2, "actual_amount": "5.00",
        "provider_usage_evidence_ref": "u-n4a-trial-1"})
    assert settled.status == "SETTLED", settled
    second = gate.compare_and_reserve({
        "project_id": "p1", "task_id": "t1", "run_id": "r2",
        "reservation_id": "res-n4a-trial-2", "estimated_amount": "2.50",
        "reserved_at": _TS, "expires_at": "2026-10-27T00:00:00Z"})
    assert second.ok, second
    assert second.warning is not None, second
    assert "BUDGET_SOFT_WARN" in second.warning, second.warning
    settled2 = gate.settle({
        "reservation_id": "res-n4a-trial-2", "source": "provider-receipt",
        "settled_at": _TS2, "actual_amount": "2.50",
        "provider_usage_evidence_ref": "u-n4a-trial-2"})
    assert settled2.status == "SETTLED", settled2
    resp = client.get("/api/v1/budget", params={"project_id": "p1"})
    assert resp.status_code == 200, resp.text
    budget = resp.json()["budget"]
    assert budget["spent"] == "7.50", budget
    assert budget.get("warned") is True, budget
    assert "BUDGET_SOFT_WARN" in (budget.get("warning") or ""), budget
    with pytest.raises(BudgetBlockedError):
        gate.compare_and_reserve({
            "project_id": "p1", "task_id": "t1", "run_id": "r3",
            "reservation_id": "res-n4a-trial-3", "estimated_amount": "5.00",
            "reserved_at": _TS, "expires_at": "2026-10-27T00:00:00Z"})
    incidents = gate.list_incidents("p1")
    assert any("hard budget limit" in i.description for i in incidents), [
        i.description for i in incidents]
    served = client.get("/api/v1/budget", params={"project_id": "p1"})
    assert served.status_code == 200, served.text
    assert served.json()["budget"]["spent"] == "7.50", served.text


# M-P3-124: shipped model KB format; AUTO reads fit-price-quality.
def test_m_p3_124_shipped_kb_format_auto_reads_fit_price_quality_served(
        tmp_path):
    """Row M-P3-124: the shipped KB carries schema plus manifest plus
    version, and a served AUTO decision reads per-candidate
    fit-price-quality from the shipped format into its evidence."""
    from agent_si.model_kb import kb as KBM

    client = _client(tmp_path)
    status = client.get("/api/v1/kb/status")
    assert status.status_code == 200, status.text
    overall = status.json()["overall"]
    assert overall["kb_version"] == 1, overall
    assert overall["last_source"] == "shipped-seed", overall
    catalog = KBM.bound_catalog()
    assert KBM.validate_catalog(catalog) == [], catalog
    assert {"format", "manifest", "version", "models"} <= set(catalog), catalog
    ctx = client.app.state.k04_ctx
    ctx.resource_state = {"eligible": True, "ref": "rs-next4a"}
    body = {
        "project_id": "p1", "task_id": "t1", "run_id": "r1",
        "role": "worker", "task_class": "coding", "mode": "AUTO",
        "candidates": [
            {"provider": "openai", "model": "gpt-4o"},
            {"provider": "openai", "model": "gpt-4o-mini"},
        ],
    }
    resp = client.post("/api/v1/routing/decide", json=body, headers=_HDRS)
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["status"] == "BLOCKED", payload
    assert payload["decision_id"], payload
    reason = payload["reason"]
    assert "HARD_CAPABILITY_FILTER" in reason, reason
    assert "gpt-4o" in reason, reason
    assert "gpt-4o-mini" in reason, reason
    assert "policy_view=required_quality>=" in reason, reason
    assert ("kb_read: openai/gpt-4o fit=unknown "
            "price=unknown-expensive quality=none") in reason, reason
    assert ("kb_read: openai/gpt-4o-mini fit=unknown "
            "price=unknown-expensive quality=none") in reason, reason
    why = client.get(
        "/api/v1/routing/decision/%s/why" % payload["decision_id"])
    assert why.status_code == 200, why.text
    assert why.json()["decision"]["decision_id"] == payload["decision_id"]
