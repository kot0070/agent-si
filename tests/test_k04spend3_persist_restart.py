"""K04SPEND3: priced KB row survives a COLD restart and charges, no memory.

Parent binds the priced meta row through the product updater route, starts
one app (startup persists the bound catalog to kb_catalog.json), then a
FRESH interpreter subprocess with zero in-memory carryover starts a second
app from the SAME store dir: the priced row must come back from disk (F1),
and a served priced hi turn must charge spent +0.000002
((4*0.1+6*0.2)/1e6, 6dp) with a MEASURED cost
row plus a ledger row on the SAME chat project (F2). In-process-only
persist is NOT a fix, so this test never passes by global carryover.
"""
import json
import os
import subprocess
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_WS, "src")
for _p in (_WS, _SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from agent_si.model_kb import kb as _kb  # noqa: E402
from agent_si.model_kb import updater as _updater  # noqa: E402

META_PROVIDER = "meta"
META_MODEL = "muse-spark-1.3-contributor"
META_SOURCE_URL = "https://dev.meta.ai/docs/pricing-rate-limits"
META_RETRIEVED_AT = "2026-10-11"

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
from agent_si.routing import types as _T

STORE = "@@STORE@@"
APP_TOKEN = "k04spend3-app-token"
BAIT = "FAKE-K04SPEND3-0000-zzzz-not-a-real-key"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}

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
    return _FakeResp({"choices": [{"message": {"content": json.dumps(
        {"answer": "k04spend3 hi"})},
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
                if r.get("provider_id") == "@@PROV@@"
                and r.get("model_id") == "@@MODEL@@"]
        result["rows"] = len(rows)
        if len(rows) != 1:
            result["error"] = "priced row missing after cold restart"
            print(json.dumps(result))
            return 1
        fields = rows[0]["fields"]
        if fields["input_token_price"]["value"] != 0.1:
            result["error"] = "input price lost: %r" % (fields,)
            print(json.dumps(result))
            return 1
        if fields["output_token_price"]["value"] != 0.2:
            result["error"] = "output price lost: %r" % (fields,)
            print(json.dumps(result))
            return 1
        _real_urlopen = _urlreq.urlopen
        _urlreq.urlopen = _fake
        client = _tc.TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/v1/projects",
                           json={"name": "p-spend3", "folder_ref": "dock-s3"},
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
            model=None, binding="DEFAULT", version=1, hash="seed-spend3"))
        resp = client.post("/api/v1/providers/keys",
                           json={"preset_id": "meta", "key_value": BAIT},
                           headers=HEADERS)
        assert resp.status_code == 201, resp.text
        conn = client.post("/api/v1/providers/connect",
                           json={"preset_id": "meta", "model": "@@MODEL@@",
                                 "key_ref": resp.json()["key_ref"]},
                           headers=HEADERS)
        assert conn.status_code == 200, conn.text
        resp = client.get("/api/v1/budget", params={"project_id": pid},
                          headers=HEADERS)
        assert resp.status_code == 200, resp.text
        before = resp.json().get("budget", {}).get("spent", "0")
        try:
            chat = client.post("/api/v1/chat/stream",
                               json={"project": pid, "message": "hi priced"},
                               headers=HEADERS)
        finally:
            _urlreq.urlopen = _real_urlopen
        assert chat.status_code == 200, chat.text
        assert "NO_PROVIDER_BOUND" not in chat.text, chat.text
        resp = client.get("/api/v1/budget", params={"project_id": pid},
                          headers=HEADERS)
        after = resp.json().get("budget", {}).get("spent", "0")
        result["spent_before"] = str(before)
        result["spent_after"] = str(after)
        from decimal import Decimal as _Dec
        if _Dec(str(after)) - _Dec(str(before)) != _Dec("0.000002"):
            result["error"] = "spent delta wrong: %r -> %r" % (before, after)
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


def _bind_priced_meta_via_updater(seed):
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
    assert _updater.validate_proposal(base, proposal) == []
    result = _updater.apply_proposal(base, proposal, user_confirmed=True)
    assert result["applied"] is True
    return _kb.bind_catalog(result["catalog"])


def test_priced_row_survives_cold_restart_and_charges(tmp_path):
    """F1+F2 cold proof: fresh interpreter, same store dir, price+charge."""
    from agent_si.backend.app import create_app
    from agent_si.backend.orchestration import steplimits as _steplimits

    seed = _kb.bound_catalog()
    prev_persist = getattr(_kb, "_PERSIST_DIR", None)
    _bind_priced_meta_via_updater(seed)
    try:
        store_dir = str(tmp_path / "appdata-cold")
        _steplimits._reset_state()
        create_app({"store_dir": store_dir,
                    "ui_session_token": "k04spend3-seed-token",
                    "secret_store": "memory"})
        persisted = _kb.persist_path()
        assert persisted and os.path.isfile(persisted), persisted
        driver = (_DRIVER.replace("@@WS@@", _WS.replace("\\", "\\\\"))
                        .replace("@@STORE@@", store_dir.replace("\\", "\\\\"))
                        .replace("@@PROV@@", META_PROVIDER)
                        .replace("@@MODEL@@", META_MODEL))
        script = str(tmp_path / "cold_driver.py")
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
        assert payload.get("same_project_rows", 0) > 0, payload
    finally:
        _kb.bind_catalog(seed)
        try:
            _kb.set_persist_dir(prev_persist)
        except Exception:
            pass
