"""FXKB served proof: F09 KB Update + F03 AUTO + F12 spent, one root cause.

Row map (row -> route -> test):
  F09 KB Update meta row persists   POST /api/v1/kb/update
                                    (+ GET /api/v1/kb/status stamp+source)
                                    -> test_fxkb_update_adds_meta_row_served
                                       test_fxkb_cold_restart_auto_spent_served
                                       (persist half, fresh interpreter)
  F03 routing auto 200 meta + why   GET /api/v1/routing/auto (no connected
                                    param; registry-ONLINE default)
                                    -> test_fxkb_update_adds_meta_row_served
                                       (in-process half)
                                       test_fxkb_cold_restart_auto_spent_served
                                       (cold half)
  F12 budget spent greater than 0   POST /api/v1/chat/stream (keyed TEST chat
                                    on the TEST project)
                                    + GET /api/v1/budget
                                    + telemetry run-store ledger row
                                    -> test_fxkb_cold_restart_auto_spent_served

Shared root cause: the model KB ships no row for the connected meta
model, so the updater path cannot source it, AUTO resolves nobody, and
the runtime charge gate finds no price. The fix sources the connected
meta row (staged per-field prices) through the updater apply path,
binds plus persists it; AUTO defaults to registry-ONLINE providers;
spent follows from the persisted priced row.

Every test drives REAL product code under src/agent_si/. No network:
the provider transport (urllib urlopen) is faked in-process exactly like
the sibling K04 lanes; keys are bait (never real). Fixtures live only in
this file. No product file is changed by this lane's tests.
"""
import json
import os
import subprocess
import sys
import urllib.request as _urlreq

_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.dirname(_HERE)
_SRC = os.path.join(_WS, "src")
for _p in (_WS, _SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fastapi.testclient as _tc  # noqa: E402

from agent_si.model_kb import kb as _kb  # noqa: E402
from agent_si.model_kb import loader as _loader  # noqa: E402
from agent_si.model_kb import updater as _updater  # noqa: E402

META_PROVIDER = "meta"
META_MODEL = "muse-spark-1.3-contributor"
OPENAI_PROVIDER = "openai"
OPENAI_MODEL = "gpt-4o"
ENVELOPE = _loader.STAGED_PROVIDER_ENVELOPES[META_PROVIDER]
RETRIEVED = _loader.STAGED_SECTIONS_RETRIEVED_AT
PRICING_URL = "https://dev.meta.ai/docs/pricing-rate-limits"
ALLOWLISTED = _updater.KB_SOURCE_ALLOWLIST[0] + "/models"
DAY = "2026-10-11"

APP_TOKEN = "fxkb-app-token"
BAIT = "FAKE-FXKB-BAIT-0000-zzzz-not-a-real-key"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}


def _staged_meta_prices():
    for model_id, fields in _loader.staged_section_rows().get(
            META_PROVIDER, []):
        if model_id == META_MODEL:
            return (fields["input_token_price"][0],
                    fields["output_token_price"][0])
    raise AssertionError("no staged meta contributor row")


META_IN, META_OUT = _staged_meta_prices()


class _FakeResp:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_chat(request, timeout=None):
    # Director-protocol answer shape: one provider call answers the turn.
    return _FakeResp({"choices": [{"message": {"content": json.dumps(
        {"answer": "fxkb hi"})},
                                   "finish_reason": "stop"}],
                      "usage": {"input_tokens": 4, "output_tokens": 6}})


def _settings(store_dir):
    return {"store_dir": store_dir,
            "ui_session_token": APP_TOKEN,
            "secret_store": "memory"}


def _create_project(client):
    resp = client.post("/api/v1/projects",
                       json={"name": "fxkb-test", "folder_ref": "dock-fxkb"},
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


def _save_and_connect(client):
    resp = client.post("/api/v1/providers/keys",
                       json={"preset_id": META_PROVIDER,
                             "key_value": BAIT},
                       headers=HEADERS)
    assert resp.status_code == 201, resp.text
    assert BAIT not in resp.text
    key_ref = resp.json()["key_ref"]
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": META_PROVIDER,
                             "model": META_MODEL,
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    assert BAIT not in conn.text
    return key_ref


def _base_catalog():
    row = _kb.make_model_row("openai", "gpt-4o")
    return _kb.make_catalog([row], kb_version=1, updated_at=DAY)


def test_fxkb_propose_stages_unknown_row_as_added():
    """Updater rows for connected-but-unknown models stage as added."""
    catalog = _base_catalog()
    doc = {"models": [{"provider_id": META_PROVIDER,
                       "model_id": META_MODEL,
                       "fields": {"currency": "USD",
                                  "input_token_price": 0.1}}]}
    proposal = _updater.propose_update(
        catalog, ALLOWLISTED, json.dumps(doc), DAY)
    assert proposal["changes"] == []
    assert len(proposal["added"]) == 1
    item = proposal["added"][0]
    assert (item["provider_id"], item["model_id"]) == (
        META_PROVIDER, META_MODEL)
    assert _updater.validate_proposal(catalog, proposal) == []
    result = _updater.apply_proposal(catalog, proposal, user_confirmed=True)
    assert result["version"] == 2
    row = _loader.find_row(result["catalog"], META_PROVIDER, META_MODEL)
    assert row["fields"]["input_token_price"]["value"] == 0.1
    assert row["fields"]["currency"]["source"] == ALLOWLISTED
    assert row["fields"]["purpose"]["value"] == "UNKNOWN"
    assert _kb.validate_catalog(result["catalog"]) == []
    assert catalog["version"]["kb_version"] == 1


def test_fxkb_added_unknown_field_still_rejected():
    """Unknown field names never slip in through the added path."""
    catalog = _base_catalog()
    doc = {"models": [{"provider_id": META_PROVIDER,
                       "model_id": META_MODEL,
                       "fields": {"mind_control": True}}]}
    proposal = _updater.propose_update(
        catalog, ALLOWLISTED, json.dumps(doc), DAY)
    assert proposal["added"] == []
    assert proposal["rejected"] != []
    assert _updater.validate_proposal(catalog, proposal) != []


def test_fxkb_propose_from_field_data_keeps_per_field_sources():
    """Staged per-field sources survive the proposal (never the envelope)."""
    catalog = _base_catalog()
    entries = [{"provider_id": META_PROVIDER, "model_id": META_MODEL,
                "field": "input_token_price", "new": META_IN,
                "source": PRICING_URL, "retrieved_at": RETRIEVED}]
    proposal = _updater.propose_from_field_data(
        catalog, entries, ENVELOPE, RETRIEVED)
    assert _updater.validate_proposal(catalog, proposal) == []
    result = _updater.apply_proposal(catalog, proposal, user_confirmed=True)
    row = _loader.find_row(result["catalog"], META_PROVIDER, META_MODEL)
    assert row["fields"]["input_token_price"]["value"] == META_IN
    assert row["fields"]["input_token_price"]["source"] == PRICING_URL
    assert row["fields"]["input_token_price"]["retrieved_at"] == RETRIEVED


def test_fxkb_apply_merges_added_into_existing_row():
    """An added entry for a raced-into-base row merges, never duplicates.

    The proposal stages against a base without the row; by apply time
    the row is on file: the staged fields merge into it, no duplicate
    row, version still bumps by one.
    """
    catalog = _base_catalog()
    entries = [{"provider_id": META_PROVIDER, "model_id": META_MODEL,
                "field": "output_token_price", "new": META_OUT,
                "source": PRICING_URL, "retrieved_at": RETRIEVED}]
    proposal = _updater.propose_from_field_data(
        catalog, entries, ENVELOPE, RETRIEVED)
    assert len(proposal["added"]) == 1
    raced = _kb.make_catalog(
        catalog["models"] + [_kb.make_model_row(META_PROVIDER, META_MODEL)],
        kb_version=1, updated_at=DAY)
    result = _updater.apply_proposal(raced, proposal, user_confirmed=True)
    rows = [r for r in result["catalog"]["models"]
            if r.get("provider_id") == META_PROVIDER]
    assert len(rows) == 1
    assert rows[0]["fields"]["output_token_price"]["value"] == META_OUT
    assert rows[0]["fields"]["output_token_price"]["source"] == PRICING_URL
    assert result["version"] == 2
    assert _kb.validate_catalog(result["catalog"]) == []


def test_fxkb_update_adds_meta_row_served(tmp_path, monkeypatch):
    """F09 KB Update adds the connected meta row; F03 AUTO 200 meta + why."""
    from agent_si.backend.app import create_app
    from agent_si.backend.orchestration import steplimits as _steplimits

    monkeypatch.setattr(_urlreq, "urlopen", _fake_chat)
    seed = _kb.bound_catalog()
    prev_persist = getattr(_kb, "_PERSIST_DIR", None)
    store = str(tmp_path / "appdata-fxkb")
    try:
        _steplimits._reset_state()
        app = create_app(_settings(store))
        client = _tc.TestClient(app, raise_server_exceptions=False)
        _create_project(client)
        _save_and_connect(client)
        before = client.get("/api/v1/kb/status", headers=HEADERS)
        assert before.status_code == 200, before.text
        v0 = before.json()["overall"]["kb_version"]
        anon = client.post("/api/v1/kb/update",
                           json={"approved_by_user": True})
        assert anon.status_code == 401, anon.text
        denied = client.post("/api/v1/kb/update", json={},
                             headers=HEADERS)
        assert denied.status_code == 400, denied.text
        assert "approved_by_user" in denied.text
        resp = client.post("/api/v1/kb/update",
                           json={"approved_by_user": True},
                           headers=HEADERS)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["applied"] is True
        assert body["kb_version"] == v0 + 1
        assert body["providers"] == [META_PROVIDER]
        assert body["models"] == ["%s/%s" % (META_PROVIDER, META_MODEL)]
        row = _loader.find_row(
            _kb.bound_catalog(), META_PROVIDER, META_MODEL)
        assert row is not None
        assert row["fields"]["input_token_price"]["value"] == META_IN
        assert row["fields"]["output_token_price"]["value"] == META_OUT
        assert PRICING_URL in row["fields"]["input_token_price"]["source"]
        assert row["fields"]["input_token_price"]["retrieved_at"] == RETRIEVED
        status = client.get("/api/v1/kb/status", headers=HEADERS)
        assert status.status_code == 200, status.text
        overall = status.json()["overall"]
        assert overall["kb_version"] == v0 + 1
        assert overall["updated_at"] > RETRIEVED and "T" in overall["updated_at"]
        assert overall["last_source"] == ENVELOPE
        persisted = _kb.persist_path()
        assert persisted and os.path.isfile(persisted), persisted
        auto = client.get("/api/v1/routing/auto", headers=HEADERS)
        assert auto.status_code == 200, auto.text
        assert auto.json()["manager"] == META_PROVIDER
        assert auto.json()["model"] == META_MODEL
        why = auto.json()["why"]
        assert why["connected"] == [META_PROVIDER]
        assert isinstance(why["reason"], str) and why["reason"]
        narrow = client.get("/api/v1/routing/auto",
                            params={"connected": META_PROVIDER},
                            headers=HEADERS)
        assert narrow.status_code == 200, narrow.text
        assert narrow.json() == {"manager": META_PROVIDER,
                                 "model": META_MODEL}
        off = client.get("/api/v1/routing/auto",
                         params={"connected": "openai"},
                         headers=HEADERS)
        assert off.status_code == 422, off.text
        bad = client.get("/api/v1/routing/auto",
                         params={"task_type": "teleport"},
                         headers=HEADERS)
        assert bad.status_code == 422, bad.text
    finally:
        _kb.bind_catalog(seed)
        try:
            _kb.set_persist_dir(prev_persist)
        except Exception:
            pass


_DRIVER = r'''
import json, os, sys, urllib.request as _urlreq

_WS = "@@WS@@"
_SRC = os.path.join(_WS, "src")
for _p in (_WS, _SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fastapi.testclient as _tc
from agent_si.backend.app import create_app as _create_app
from agent_si.backend.orchestration import steplimits as _steplimits
from agent_si.model_kb import kb as _kb
from agent_si.model_kb import loader as _ldr
from agent_si.routing import types as _T

STORE = "@@STORE@@"
APP_TOKEN = "fxkb-app-token"
BAIT = "FAKE-FXKB-BAIT-0000-zzzz-not-a-real-key"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}
PROV = "@@PROV@@"
MODEL = "@@MODEL@@"

class _FakeResp:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")
    def read(self):
        return self._raw
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False

def _fake(request, timeout=None):
    # Director-protocol answer shape: one provider call answers the turn.
    return _FakeResp({"choices": [{"message": {"content": json.dumps(
        {"answer": "fxkb hi"})},
                                   "finish_reason": "stop"}],
                      "usage": {"input_tokens": 4, "output_tokens": 6}})

def main():
    result = {"ok": False}
    try:
        _steplimits._reset_state()
        app = _create_app({"store_dir": STORE,
                           "ui_session_token": APP_TOKEN,
                           "secret_store": "memory"})
        rows = [r for r in _kb.bound_catalog().get("models", [])
                if r.get("provider_id") == PROV
                and r.get("model_id") == MODEL]
        result["rows"] = len(rows)
        if len(rows) != 1:
            result["error"] = "priced row missing after cold restart"
            print(json.dumps(result))
            return 1
        fields = rows[0]["fields"]
        staged = {m: f for m, f in (_ldr.staged_section_rows().get(
            PROV, []))}[MODEL]
        exp_in = staged["input_token_price"][0]
        exp_out = staged["output_token_price"][0]
        if fields["input_token_price"]["value"] != exp_in:
            result["error"] = "input price lost: %r" % (
                fields["input_token_price"],)
            print(json.dumps(result))
            return 1
        if fields["output_token_price"]["value"] != exp_out:
            result["error"] = "output price lost: %r" % (
                fields["output_token_price"],)
            print(json.dumps(result))
            return 1
        client = _tc.TestClient(app, raise_server_exceptions=False)
        auto = client.get("/api/v1/routing/auto", headers=HEADERS)
        result["auto"] = auto.status_code
        if auto.status_code != 200:
            result["error"] = "cold AUTO not 200: %r" % (auto.text,)
            print(json.dumps(result))
            return 1
        if auto.json().get("manager") != PROV:
            result["error"] = "cold AUTO not meta: %r" % (auto.text,)
            print(json.dumps(result))
            return 1
        if auto.json().get("model") != MODEL:
            result["error"] = "cold AUTO model wrong: %r" % (auto.text,)
            print(json.dumps(result))
            return 1
        why = auto.json().get("why") or {}
        if why.get("connected") != [PROV]:
            result["error"] = "cold AUTO why wrong: %r" % (auto.text,)
            print(json.dumps(result))
            return 1
        _real_urlopen = _urlreq.urlopen
        _urlreq.urlopen = _fake
        try:
            resp = client.post("/api/v1/projects",
                               json={"name": "fxkb-test",
                                     "folder_ref": "dock-fxkb-cold"},
                               headers=HEADERS)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            proj = body.get("project") if isinstance(body, dict) else None
            pid = None
            if isinstance(proj, dict):
                for key in ("project_id", "id", "record_id"):
                    if proj.get(key):
                        pid = str(proj.get(key))
                        break
            if pid is None:
                for key in ("project_id", "id"):
                    if body.get(key):
                        pid = str(body.get(key))
                        break
            assert pid, body
            result["project"] = pid
            ctx = app.state.k04_ctx
            ctx.role_table.set_profile(_T.RoleModelProfile(
                role="worker", project_id=pid, mode="AUTO", provider=None,
                model=None, binding="DEFAULT", version=1,
                hash="seed-fxkb"))
            resp = client.post("/api/v1/providers/keys",
                               json={"preset_id": PROV,
                                     "key_value": BAIT},
                               headers=HEADERS)
            assert resp.status_code == 201, resp.text
            assert BAIT not in resp.text
            resp = client.get("/api/v1/budget",
                              params={"project_id": pid}, headers=HEADERS)
            assert resp.status_code == 200, resp.text
            before = resp.json().get("budget", {}).get("spent", "0")
            chat = client.post("/api/v1/chat/stream",
                               json={"project": pid,
                                     "message": "fxkb TEST hi"},
                               headers=HEADERS)
            assert chat.status_code == 200, chat.text
            assert "NO_PROVIDER_BOUND" not in chat.text, chat.text
            resp = client.get("/api/v1/budget",
                              params={"project_id": pid}, headers=HEADERS)
            after = resp.json().get("budget", {}).get("spent", "0")
        finally:
            _urlreq.urlopen = _real_urlopen
        result["spent_before"] = str(before)
        result["spent_after"] = str(after)
        from decimal import Decimal as _Dec
        exp = ((_Dec(str(exp_in)) * 4 + _Dec(str(exp_out)) * 6
                ) / _Dec(1000000)).quantize(_Dec("0.000001"))
        if _Dec(str(after)) - _Dec(str(before)) != exp:
            result["error"] = "spent delta wrong: %r -> %r (want %s)" % (
                before, after, exp)
            print(json.dumps(result))
            return 1
        if _Dec(str(after)) <= _Dec(str(before)):
            result["error"] = "spent did not grow"
            print(json.dumps(result))
            return 1
        from agent_si.telemetry import run_store as _store
        stored = _store.load_store(
            store_dir=getattr(app.state, "k02r3_store_dir", None))
        costs = [r for r in stored.get("metric_records", [])
                 if r.get("metric_name") == "cost"]
        same = [r for r in stored.get("metric_records", [])
                if r.get("project_id") == pid]
        result["cost_rows"] = len(costs)
        result["same_project_rows"] = len(same)
        measured = [r for r in costs if r.get("state") == "MEASURED"]
        if not measured or not any(float(r.get("value") or 0) > 0
                                   for r in measured):
            result["error"] = "no MEASURED cost row: %r" % (costs,)
            print(json.dumps(result))
            return 1
        if not any(r.get("metric_name") == "tokens_total"
                   and r.get("project_id") == pid for r in same):
            result["error"] = "no ledger tokens row on chat project"
            print(json.dumps(result))
            return 1
        result["ok"] = True
        print(json.dumps(result))
        return 0
    except Exception as exc:
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
        print(json.dumps(result))
        return 1

sys.exit(main())
'''


def test_fxkb_cold_restart_auto_spent_served(tmp_path, monkeypatch):
    """F09 persist + F03 AUTO + F12 spent across a cold restart.

    Parent binds the priced meta row through POST /api/v1/kb/update,
    then a FRESH interpreter subprocess with zero in-memory carryover
    starts a second app from the SAME store dir: the priced row must
    come back from disk, AUTO must resolve meta with a why-record, and
    a served keyed TEST chat must charge spent with a MEASURED cost row
    plus a ledger tokens row on the SAME chat project.
    """
    from agent_si.backend.app import create_app
    from agent_si.backend.orchestration import steplimits as _steplimits

    monkeypatch.setattr(_urlreq, "urlopen", _fake_chat)
    seed = _kb.bound_catalog()
    prev_persist = getattr(_kb, "_PERSIST_DIR", None)
    try:
        store_dir = str(tmp_path / "appdata-cold")
        _steplimits._reset_state()
        app = create_app(_settings(store_dir))
        client = _tc.TestClient(app, raise_server_exceptions=False)
        _create_project(client)
        _save_and_connect(client)
        resp = client.post("/api/v1/kb/update",
                           json={"approved_by_user": True},
                           headers=HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json()["applied"] is True, resp.text
        persisted = _kb.persist_path()
        assert persisted and os.path.isfile(persisted), persisted
        driver = (_DRIVER.replace("@@WS@@", _WS.replace("\\", "\\\\"))
                        .replace("@@STORE@@",
                                 store_dir.replace("\\", "\\\\"))
                        .replace("@@PROV@@", META_PROVIDER)
                        .replace("@@MODEL@@", META_MODEL))
        script = str(tmp_path / "cold_driver_fxkb.py")
        with open(script, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(driver)
        proc = subprocess.run(
            [sys.executable, script],
            cwd=_WS, capture_output=True, text=True, timeout=240)
        assert proc.returncode == 0, (
            "cold restart driver failed rc=%s stdout=%r stderr=%r"
            % (proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:]))
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        assert payload.get("ok") is True, payload
        assert payload.get("rows") == 1, payload
        assert payload.get("auto") == 200, payload
        assert payload.get("same_project_rows", 0) > 0, payload
    finally:
        _kb.bind_catalog(seed)
        try:
            _kb.set_persist_dir(prev_persist)
        except Exception:
            pass

def _save_and_connect_openai(client):
    resp = client.post("/api/v1/providers/keys",
                       json={"preset_id": OPENAI_PROVIDER,
                             "key_value": BAIT},
                       headers=HEADERS)
    assert resp.status_code == 201, resp.text
    assert BAIT not in resp.text
    key_ref = resp.json()["key_ref"]
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": OPENAI_PROVIDER,
                             "model": OPENAI_MODEL,
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    assert BAIT not in conn.text
    return key_ref


def test_fxkb_openai_only_auditor_eligible_served(tmp_path, monkeypatch):
    """F04 auditor-eligibility re-check on staged B1 KB rows (openai-only).

    RED without B1 rows: the seed bound catalog carries the openai row
    with every field UNKNOWN, so the staged-rows consumer yields no
    capability evidence and the real AuditorRegistry stays
    NO_ELIGIBLE_AUDITOR with openai as the only other model.
    GREEN with B1 rows: after the served POST /api/v1/kb/update stages
    the openai row with sourced fields, the same consumer yields
    evidence refs and the openai candidate selects at L2.
    Still ineligible afterwards: empty-model pairs and UNKNOWN-price
    rows never yield evidence (prices are never invented).
    """
    from agent_si.assurance import audit_registry as _areg
    from agent_si.backend.app import create_app
    from agent_si.backend.orchestration import steplimits as _steplimits
    from agent_si.kb import retriever as _kbsev

    class _ProofRegistry(_areg.AuditorRegistry):
        """Concrete binding of the real sourcing entries; adds nothing."""

    def _candidate(refs):
        return _areg.AuditorCandidate(
            provider_id=OPENAI_PROVIDER, provider_instance=None,
            model=OPENAI_MODEL, capability_evidence_refs=tuple(refs),
            registered_at="")

    monkeypatch.setattr(_urlreq, "urlopen", _fake_chat)
    seed = _kb.bound_catalog()
    prev_persist = getattr(_kb, "_PERSIST_DIR", None)
    try:
        _steplimits._reset_state()
        app = create_app(_settings(str(tmp_path / "appdata-fb2b4")))
        client = _tc.TestClient(app, raise_server_exceptions=False)
        _create_project(client)
        _save_and_connect_openai(client)
        assert _kbsev.auditor_capability_evidence(
            OPENAI_PROVIDER, OPENAI_MODEL) == ()
        red = _ProofRegistry()
        red.register_candidate(_candidate(()))
        assert red.is_eligible(OPENAI_PROVIDER, OPENAI_MODEL) is False
        try:
            red.select_auditor("worker", (_areg.MODEL_ID,), "L2")
        except _areg.NoEligibleAuditorError as exc:
            assert exc.code == _areg.NO_ELIGIBLE_AUDITOR
        else:
            raise AssertionError("RED leg selected without B1 rows")
        resp = client.post("/api/v1/kb/update",
                           json={"approved_by_user": True},
                           headers=HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json()["applied"] is True, resp.text
        assert OPENAI_PROVIDER in resp.json()["providers"], resp.text
        refs = _kbsev.auditor_capability_evidence(
            OPENAI_PROVIDER, OPENAI_MODEL)
        assert len(refs) >= 1, refs
        green = _ProofRegistry()
        green.register_candidate(_candidate(refs))
        assert green.is_eligible(OPENAI_PROVIDER, OPENAI_MODEL) is True
        selection = green.select_auditor("worker", (_areg.MODEL_ID,), "L2")
        assert selection.auditor.provider_id == OPENAI_PROVIDER
        assert selection.auditor.model == OPENAI_MODEL
        assert selection.independence_level == "L2"
        assert _kbsev.auditor_capability_evidence(OPENAI_PROVIDER, "") == ()
        assert _kbsev.auditor_capability_evidence("", OPENAI_MODEL) == ()
        import copy as _copy
        _no_price = _copy.deepcopy(_kb.bound_catalog())
        _row = _loader.find_row(_no_price, OPENAI_PROVIDER, OPENAI_MODEL)
        assert _row is not None
        for _price_field in ("input_token_price", "output_token_price"):
            _row["fields"][_price_field] = {"value": "UNKNOWN",
                                            "source": "UNKNOWN",
                                            "retrieved_at": "UNKNOWN"}
        _kb.bind_catalog(_no_price)
        assert _kbsev.auditor_capability_evidence(
            OPENAI_PROVIDER, OPENAI_MODEL) == ()
        _probe = _ProofRegistry()
        _probe.register_candidate(_candidate(()))
        assert _probe.is_eligible(OPENAI_PROVIDER, OPENAI_MODEL) is False
    finally:
        _kb.bind_catalog(seed)
        try:
            _kb.set_persist_dir(prev_persist)
        except Exception:
            pass
