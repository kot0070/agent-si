"""K04NEXT4 budget/model-KB seam: 7 rows proved served (REAL app + TestClient).

Served = each test boots the served app (create_app + TestClient, memory
secret store) and hits a real HTTP route, then asserts the row behavior
against the real product module (no fakes in product; no network; no keys).

Row -> route -> test:
- M-P2-63 -> POST /api/v1/budget/k04next4/trial-cap ->
  test_k04n4_p2_63_trial_vs_monthly_cap_served
- M-P3-124 -> GET /api/v1/budget/k04next4/kb-auto ->
  test_k04n4_p3_124_kb_auto_fit_price_quality_served
- M-P4-144 -> GET /api/v1/budget/k04next4/leftover-keys +
  POST /api/v1/budget/k04next4/leftover-delete ->
  test_k04n4_p4_144_lists_own_prefix_user_click_delete_served
- M-P4-145 -> GET list + POST delete missing/other ->
  test_k04n4_p4_145_names_dates_only_never_touches_others_served
- M-P4-146 -> POST delete live-linked ->
  test_k04n4_p4_146_live_linked_never_deletable_served
- M-P4-147 -> POST delete confirm/token ->
  test_k04n4_p4_147_confirm_and_session_token_served
- M-P4-148 -> POST delete audit ->
  test_k04n4_p4_148_audit_logged_by_name_real_reasons_served
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402

APP_TOKEN = "k04n4-app-token"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}
PREFIX = "app:"


def _settings(tmp_path):
    return {"store_dir": str(tmp_path / "appdata"),
            "ui_session_token": APP_TOKEN,
            "secret_store": "memory"}


def _client(tmp_path):
    os.environ["AGENT_SI_SECRET_STORE"] = "memory"
    app = create_app(_settings(tmp_path))
    return fastapi.testclient.TestClient(
        app, raise_server_exceptions=False), app


# [M-P2-63]: billed spend per trial vs monthly cap; warn plus block.
def test_k04n4_p2_63_trial_vs_monthly_cap_served(tmp_path):
    client, app = _client(tmp_path)
    resp = client.post(
        "/api/v1/budget/k04next4/trial-cap",
        json={"project_id": "k04n4-p63", "currency": "USD",
              "monthly_cap": "10.00", "soft_limit": "7.00"},
        headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == "k04n4-p63", body
    assert body["monthly_cap"] == "10.00", body
    assert body["billed_spent"] == "6.00", body
    assert "BUDGET_SOFT_WARN" in body["warning"], body
    assert body["blocked_code"] == "BUDGET_HARD_BLOCKED", body
    assert body["incident_id"].startswith("inc-k04n4-p63-"), body
    assert body["override_ok"] is True, body
    assert body["override_reservation_id"], body
    from agent_si.budget.gate import BudgetGate
    import glob as _glob
    persisted = _glob.glob(os.path.join(
        str(tmp_path / "appdata" / "budget"), "incident-*.json"))
    assert persisted, "breach incident must persist to the ledger store"
    fresh = BudgetGate(store_dir=str(tmp_path / "appdata" / "budget"))
    state = fresh.get_state("k04n4-p63")
    assert state.spent == "6.00", state.to_dict()


# [M-P3-124]: shipped model KB format; AUTO reads fit-price-quality.
def test_k04n4_p3_124_kb_auto_fit_price_quality_served(tmp_path):
    client, _app = _client(tmp_path)
    resp = client.get("/api/v1/budget/k04next4/kb-auto",
                      params={"connected": "openai",
                              "task_type": "coding"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["format"] == "p17ub-kb/1", body
    assert body["pick"] is not None, body
    assert body["pick"]["model_id"] == "cheap-strong", body
    assert body["pick"]["provider_id"] == "openai", body
    reason = body["reason"].lower()
    assert "coding" in reason, body
    assert "fit" in reason, body
    assert "price" in reason, body
    assert "quality" in reason, body
    assert body["excluded_unconnected"] == ["anthropic"], body
    rejected = body.get("rejected", [])
    assert any("ghost" in str(r).lower() or "unknown" in str(r).lower()
               for r in rejected), body
    assert all(r.get("kb_status") in ("in-base", "not-in-base")
               for r in body["ranked"] + body["excluded"]), body


def _seed(client, entries, live=()):
    resp = client.post(
        "/api/v1/budget/k04next4/leftover-seed",
        json={"app_prefix": PREFIX,
              "entries": entries, "live": list(live)},
        headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _list(client):
    resp = client.get("/api/v1/budget/k04next4/leftover-keys",
                      params={"app_prefix": PREFIX})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _delete(client, name, confirmed=True, token=APP_TOKEN,
            reason="user-confirmed-cleanup", headers=None):
    payload = {"name": name, "app_prefix": PREFIX,
               "confirmed": confirmed,
               "session_token": token, "reason": reason}
    if token is None:
        del payload["session_token"]
    resp = client.post("/api/v1/budget/k04next4/leftover-delete",
                       json=payload,
                       headers=HEADERS if headers is None else headers)
    return resp


# [M-P4-144]: leftover-key finder lists product-prefixed entries,
# user-click delete.
def test_k04n4_p4_144_lists_own_prefix_user_click_delete_served(tmp_path):
    client, _app = _client(tmp_path)
    _seed(client, [{"name": "app:old-1", "last_used_at": "2026-10-20"},
                   {"name": "app:old-2", "last_used_at": "2026-10-21"},
                   {"name": "other:key", "last_used_at": "2026-10-22"}])
    listed = _list(client)
    names = [e["name"] for e in listed["entries"]]
    assert names == ["app:old-1", "app:old-2"], listed
    resp = _delete(client, "app:old-1")
    assert resp.status_code == 200, resp.text
    assert resp.json().get("removed") is True, resp.text
    listed2 = _list(client)
    assert [e["name"] for e in listed2["entries"]] == ["app:old-2"], listed2


# [M-P4-145]: finder shows names plus dates only, never touches others.
def test_k04n4_p4_145_names_dates_only_never_touches_others_served(tmp_path):
    client, _app = _client(tmp_path)
    _seed(client, [{"name": "app:one", "last_used_at": "2026-10-20",
                    "secret_value": "must-never-surface"},
                   {"name": "other:key", "last_used_at": "2026-10-22"}])
    listed = _list(client)
    assert listed == {"entries": [{"name": "app:one",
                                   "last_used_at": "2026-10-20"}]}, listed
    dumped = str(listed)
    assert "must-never-surface" not in dumped, dumped
    assert "other:key" not in dumped, dumped
    resp = _delete(client, "other:key")
    assert resp.status_code == 403, resp.text
    assert resp.json().get("code") == "NOT_OWN_PREFIX", resp.text
    resp2 = _delete(client, "app:gone")
    assert resp2.status_code == 404, resp2.text
    assert resp2.json().get("code") == "NOT_FOUND", resp2.text
    listed2 = _list(client)
    assert listed2 == listed, listed2


# [M-P4-146]: live-provider-linked entry never deletable.
def test_k04n4_p4_146_live_linked_never_deletable_served(tmp_path):
    client, _app = _client(tmp_path)
    _seed(client, [{"name": "app:live-1", "last_used_at": "2026-10-20"}],
          live=["app:live-1"])
    resp = _delete(client, "app:live-1")
    assert resp.status_code == 409, resp.text
    assert resp.json().get("code") == "LIVE_LINKED", resp.text
    listed = _list(client)
    assert [e["name"] for e in listed["entries"]] == ["app:live-1"], listed


# [M-P4-147]: explicit confirm per entry and behind session token.
def test_k04n4_p4_147_confirm_and_session_token_served(tmp_path):
    client, _app = _client(tmp_path)
    _seed(client, [{"name": "app:one", "last_used_at": "2026-10-20"}])
    resp = _delete(client, "app:one", confirmed=False)
    assert resp.status_code == 400, resp.text
    assert resp.json().get("code") == "CONFIRM_REQUIRED", resp.text
    resp2 = _delete(client, "app:one", confirmed=True, token=None)
    assert resp2.status_code == 401, resp2.text
    assert resp2.json().get("code") == "TOKEN_REQUIRED", resp2.text
    resp3 = client.post("/api/v1/budget/k04next4/leftover-delete",
                        json={"name": "app:one", "app_prefix": PREFIX,
                              "confirmed": True,
                              "session_token": APP_TOKEN},
                        headers={"x-actor": "ui-probe"})
    assert resp3.status_code in (401, 403), resp3.text
    listed = _list(client)
    assert [e["name"] for e in listed["entries"]] == ["app:one"], listed


# [M-P4-148]: credential deletion audit-logged by entry name, real reasons.
def test_k04n4_p4_148_audit_logged_by_name_real_reasons_served(tmp_path):
    client, app = _client(tmp_path)
    _seed(client, [{"name": "app:one", "last_used_at": "2026-10-20"}])
    resp = _delete(client, "app:one", reason="user-confirmed-cleanup")
    assert resp.status_code == 200, resp.text
    sink = app.state.k04_ctx.audit_sink
    records = list(getattr(sink, "records", []))
    hits = [r for r in records if isinstance(r, dict)
            and r.get("entry") == "app:one"]
    assert hits, records
    rec = hits[-1]
    assert rec["entry"] == "app:one", rec
    assert rec["reason"] == "user-confirmed-cleanup", rec
    assert rec.get("at"), rec
    assert "secret" not in str(rec).lower() or "secret" in "user", rec
    resp2 = _delete(client, "app:missing", reason="user-confirmed-cleanup")
    assert resp2.status_code == 404, resp2.text
    assert resp2.json().get("code") == "NOT_FOUND", resp2.text
    assert resp2.json().get("reason") == "NOT_FOUND", resp2.text
