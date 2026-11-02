"""Served spend for the priced meta contributor row via the updater.

Through the REAL app (create_app + store dir + secret_store memory +
HTTP TestClient) with a fake ONLY at urllib urlopen. The priced row
arrives as a NORMAL KB record through the product updater route
(fetch_source plus propose_update plus apply_proposal with explicit
user confirmation, then kb.bind_catalog): the base holds an honest
all-UNKNOWN meta row, the fetched JSON carries ONLY the owner MODEL_KB
facts below, UNKNOWN stays UNKNOWN.

Model facts (owner model-KB meta section):
- "Model ID: muse-spark-1.3-contributor
  (https://dev.meta.ai/docs/models, retrieved 2026-10-11)."
- "Price input per 1M tokens: 0.1
  (https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11)."
- "Price output per 1M tokens: 0.2
  (https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11)."
- "Price currency: USD
  (https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11)."
- "Price date: UNKNOWN (checked
  https://dev.meta.ai/docs/pricing-rate-limits, retrieved 2026-10-11)."
Usage {input_tokens:4, output_tokens:6} must charge exactly
(4*0.1 + 6*0.2)/1e6 = 0.0000016 -> 0.000002 (6dp) and leave a MEASURED
cost row (MODEL_KB prices are per 1M tokens, meta.md:96-97).
"""
import json
import os
import sys
import urllib.request as _urlreq
from decimal import Decimal

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_WS, "src")
for _p in (_WS, _SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fastapi.testclient  # noqa: E402

from agent_si.backend import modelkb as _modelkb  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from agent_si.model_kb import kb as _kb  # noqa: E402
from agent_si.model_kb import updater as _updater  # noqa: E402
from agent_si.routing import types as _T  # noqa: E402

APP_TOKEN = "k04mr07b-app-token"
BAIT = "FAKE-K04MR07B-0000-zzzz-not-a-real-key"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}

CANNED_TEXT = "k04mr07b canned reply"
CANNED_USAGE = {"input_tokens": 4, "output_tokens": 6}

META_PROVIDER = "meta"
META_MODEL = "muse-spark-1.3-contributor"
META_SOURCE_URL = "https://dev.meta.ai/docs/pricing-rate-limits"
META_RETRIEVED_AT = "2026-10-11"
EXPECTED_DELTA = Decimal("0.000002")


class _FakeResp:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ok_body():
    return {"choices": [{"message": {"content": CANNED_TEXT},
                         "finish_reason": "stop"}],
            "usage": dict(CANNED_USAGE)}


def _patch_urlopen(monkeypatch):
    def _fake(request, timeout=None):
        return _FakeResp(_ok_body())
    monkeypatch.setattr(_urlreq, "urlopen", _fake)


def _settings(tmp_path):
    return {"store_dir": str(tmp_path / "appdata"),
            "ui_session_token": APP_TOKEN,
            "secret_store": "memory"}


def _make_client(tmp_path):
    _steplimits._reset_state()
    app = create_app(_settings(tmp_path))
    return fastapi.testclient.TestClient(app, raise_server_exceptions=False), app


def _bind_priced_meta_via_updater(seed):
    """Bind the meta row priced ONLY through the updater propose/apply route.

    Base: the seed rows plus one honest all-UNKNOWN meta row. Fetched
    document: the four priced fields from meta.md:96-99, nothing else.
    Returns the bound priced catalog.
    """
    kept = [row for row in seed.get("models", [])
            if not (isinstance(row, dict)
                    and row.get("provider_id") == META_PROVIDER
                    and row.get("model_id") == META_MODEL)]
    base = _kb.make_catalog(
        [_kb.make_model_row(META_PROVIDER, META_MODEL)] + kept,
        kb_version=int(seed.get("version", {}).get("kb_version", 1)),
        updated_at=seed.get("version", {}).get("updated_at", _kb.UNKNOWN),
        change_log=list(seed.get("version", {}).get("change_log", [])),
        sources=tuple(seed.get("manifest", {}).get("sources", ())))
    fetched_doc = {"models": [{
        "provider_id": META_PROVIDER,
        "model_id": META_MODEL,
        "fields": {"currency": "USD",
                   "input_token_price": 0.1,
                   "output_token_price": 0.2}}]}
    fetched_text = _updater.fetch_source(
        META_SOURCE_URL, lambda url: json.dumps(fetched_doc))
    assert fetched_text is not None
    proposal = _updater.propose_update(
        base, META_SOURCE_URL, fetched_text, META_RETRIEVED_AT)
    errors = _updater.validate_proposal(base, proposal)
    assert errors == [], errors
    assert len(proposal["changes"]) == 3, proposal
    result = _updater.apply_proposal(base, proposal, user_confirmed=True)
    assert result["applied"] is True
    return _kb.bind_catalog(result["catalog"])


def _create_project(client):
    resp = client.post("/api/v1/projects",
                       json={"name": "p-mr07b", "folder_ref": "dock-mr07b"},
                       headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    proj = body.get("project") if isinstance(body, dict) else None
    if isinstance(proj, dict):
        for key in ("project_id", "id", "record_id"):
            if proj.get(key):
                return str(proj.get(key))
    for key in ("project_id", "id"):
        if body.get(key):
            return str(body.get(key))
    raise AssertionError("no project id in %r" % (body,))


def _connect(client, preset_id, model, bait):
    resp = client.post("/api/v1/providers/keys",
                       json={"preset_id": preset_id, "key_value": bait},
                       headers=HEADERS)
    assert resp.status_code == 201, resp.text
    key_ref = resp.json()["key_ref"]
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": preset_id, "model": model,
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    return conn


def _seed_worker(app, pid):
    ctx = app.state.k04_ctx
    profile = _T.RoleModelProfile(
        role="worker", project_id=pid, mode="AUTO",
        provider=None, model=None, binding="DEFAULT", version=1,
        hash="seed-mr07b")
    ctx.role_table.set_profile(profile)


def _budget_spent(client, pid):
    resp = client.get("/api/v1/budget", params={"project_id": pid},
                      headers=HEADERS)
    assert resp.status_code == 200, resp.text
    budget = resp.json().get("budget", {})
    return Decimal(str(budget.get("spent", "0")))


def _cost_rows(app):
    from agent_si.telemetry import run_store as _store

    stored = _store.load_store(
        store_dir=getattr(app.state, "k02r3_store_dir", None))
    return [r for r in stored.get("metric_records", [])
            if r.get("metric_name") == "cost"]


def test_meta_model_card_served_shows_price(tmp_path):
    """GET KB model card (real get_models over the bound catalog) shows it."""
    seed = _kb.bound_catalog()
    _bind_priced_meta_via_updater(seed)
    try:
        cards = _modelkb.get_models([META_PROVIDER], META_MODEL)
        assert len(cards) == 1, cards
        fields = cards[0]["fields"]
        assert fields["input_token_price"]["value"] == 0.1, fields
        assert fields["output_token_price"]["value"] == 0.2, fields
        assert fields["currency"]["value"] == "USD", fields
        for name in ("input_token_price", "output_token_price",
                     "currency"):
            assert fields[name]["source"] == META_SOURCE_URL, fields
            assert fields[name]["retrieved_at"] == META_RETRIEVED_AT, fields
        assert fields["price_effective_at"]["value"] == "UNKNOWN", fields
    finally:
        _kb.bind_catalog(seed)


def test_meta_priced_row_charges_spent_and_measured_cost(tmp_path, monkeypatch):
    _patch_urlopen(monkeypatch)
    from agent_si.runtime import manager as _mgr
    from agent_si.telemetry import run_store as _store

    seed = _kb.bound_catalog()
    prev_gate = getattr(_mgr, "_BUDGET_GATE", None)
    prev_dir = _store.bound_store_dir()
    _bind_priced_meta_via_updater(seed)
    try:
        rows = [r for r in _kb.bound_catalog().get("models", [])
                if r.get("provider_id") == META_PROVIDER
                and r.get("model_id") == META_MODEL]
        assert len(rows) == 1, _kb.bound_catalog().get("models", [])
        fields = rows[0]["fields"]
        assert fields["input_token_price"]["value"] == 0.1, fields
        assert fields["output_token_price"]["value"] == 0.2, fields
        assert fields["input_token_price"]["source"] == META_SOURCE_URL
        assert fields["input_token_price"]["retrieved_at"] == META_RETRIEVED_AT
        assert fields["currency"]["value"] == "USD"
        client, app = _make_client(tmp_path)
        pid = _create_project(client)
        _seed_worker(app, pid)
        _connect(client, "meta", META_MODEL, BAIT)
        before = _budget_spent(client, pid)
        chat = client.post("/api/v1/chat/stream",
                           json={"project": pid, "message": "hi priced meta"},
                           headers=HEADERS)
        assert chat.status_code == 200, chat.text
        assert "NO_PROVIDER_BOUND" not in chat.text, chat.text
        after = _budget_spent(client, pid)
        assert after > before, (before, after)
        assert after - before == EXPECTED_DELTA, (before, after)
        costs = _cost_rows(app)
        assert costs, "no cost rows recorded"
        measured = [r for r in costs if r.get("state") == "MEASURED"]
        assert measured, costs
        assert any(float(r.get("value") or 0) > 0 for r in measured), costs
    finally:
        _kb.bind_catalog(seed)
        try:
            _mgr.set_budget_gate(prev_gate)
        except Exception:
            pass
        try:
            _store.bind_store_dir(prev_dir)
        except Exception:
            pass

def test_kb_price_lookup_resolves_exact_full_model_id():
    """K04SPEND2 L3: the ledger price lookup resolves the exact full id.

    Frozen contract pins meta/muse-spark-1.3-contributor (never the bare
    short id): the manager lookup strips the provider prefix exactly and
    finds the same priced pair as the bare id.
    """
    from agent_si.runtime import manager as _mgr

    seed = _kb.bound_catalog()
    _bind_priced_meta_via_updater(seed)
    try:
        full = _mgr._kb_price_for_manager(
            META_PROVIDER, META_PROVIDER + "/" + META_MODEL)
        bare = _mgr._kb_price_for_manager(META_PROVIDER, META_MODEL)
        assert full == (0.1, 0.2), full
        assert bare == full, (bare, full)
    finally:
        _kb.bind_catalog(seed)


def test_full_model_id_served_charges_spent_and_measured_cost(
        tmp_path, monkeypatch):
    """K04SPEND2 live shape: connect with the exact full model id.

    Same served path as
    test_meta_priced_row_charges_spent_and_measured_cost, but the provider
    is connected with the exact full id from the frozen contract; the turn
    still charges spent +0.000002 and records a MEASURED cost row.
    """
    _patch_urlopen(monkeypatch)
    from agent_si.runtime import manager as _mgr
    from agent_si.telemetry import run_store as _store

    seed = _kb.bound_catalog()
    prev_gate = getattr(_mgr, "_BUDGET_GATE", None)
    prev_dir = _store.bound_store_dir()
    _bind_priced_meta_via_updater(seed)
    try:
        client, app = _make_client(tmp_path)
        pid = _create_project(client)
        _seed_worker(app, pid)
        _connect(client, "meta", META_PROVIDER + "/" + META_MODEL, BAIT)
        before = _budget_spent(client, pid)
        chat = client.post("/api/v1/chat/stream",
                           json={"project": pid, "message": "hi priced meta"},
                           headers=HEADERS)
        assert chat.status_code == 200, chat.text
        assert "NO_PROVIDER_BOUND" not in chat.text, chat.text
        after = _budget_spent(client, pid)
        assert after - before == EXPECTED_DELTA, (before, after)
        costs = _cost_rows(app)
        measured = [r for r in costs if r.get("state") == "MEASURED"]
        assert measured, costs
        assert any(float(r.get("value") or 0) > 0 for r in measured), costs
    finally:
        _kb.bind_catalog(seed)
        try:
            _mgr.set_budget_gate(prev_gate)
        except Exception:
            pass
        try:
            _store.bind_store_dir(prev_dir)
        except Exception:
            pass
