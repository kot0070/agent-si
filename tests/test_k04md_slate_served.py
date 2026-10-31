"""K04MD Slate served proofs: one named test per row M-D-D14/D21/D26/D28.

Each test boots the real app (create_app + store dir + secret_store
memory + HTTP TestClient) and drives one served route into the owned
lane files (src/agent_si/routing/*, src/agent_si/budget/*). Loopback
TEST data only; the only fake is at the urllib urlopen transport
boundary in the D21 gateway test (repo-wide FakeTransport pattern).
No mock providers in product code.
"""
import json
import os
import sys
import urllib.request as _urlreq

_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.dirname(_HERE)
_SRC = os.path.join(_WS, "src")
for _p in (_WS, _SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from agent_si.routing import types as _T  # noqa: E402

APP_TOKEN = "k04md-slate-app-token"
BAIT = "FAKE-K04MD-SLATE-0000-zzzz-not-a-real-key"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}

CANNED_TEXT = "k04md slate canned reply"
CANNED_USAGE = {"input_tokens": 4, "output_tokens": 6}

PIN_PROVIDER = "pa"
PIN_MODEL = "pa/m1"


class _FakeResp:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_urlopen(monkeypatch):
    def _fake(request, timeout=None):
        return _FakeResp(
            {"choices": [{"message": {"content": CANNED_TEXT},
                          "finish_reason": "stop"}],
             "usage": dict(CANNED_USAGE)})
    monkeypatch.setattr(_urlreq, "urlopen", _fake)


def _settings(tmp_path):
    return {"store_dir": str(tmp_path / "appdata"),
            "ui_session_token": APP_TOKEN,
            "secret_store": "memory"}


def _make_client(tmp_path):
    _steplimits._reset_state()
    app = create_app(_settings(tmp_path))
    return fastapi.testclient.TestClient(app, raise_server_exceptions=False), app


def _create_project(client):
    resp = client.post("/api/v1/projects",
                       json={"name": "p-slate", "folder_ref": "dock-slate"},
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
    raise AssertionError(f"no project id in {body!r}")


def _seed_health(app, provider=PIN_PROVIDER, model=PIN_MODEL):
    ctx = app.state.k04_ctx
    ctx.provider_health[provider] = _T.ProviderHealth(
        provider=provider, status="ONLINE")
    ctx.model_health[(provider, model)] = _T.ModelHealth(
        provider=provider, model=model, status="READY")
    ctx.provider_capabilities[provider] = ("text",)
    ctx.resource_state = {"eligible": True, "ref": "rs-k04md-slate"}
    ctx.budget_state = {"eligible": True, "ref": "bs-k04md-slate"}


def _pin_worker(client, pid, provider=PIN_PROVIDER, model=PIN_MODEL):
    resp = client.put("/api/v1/roles/pools",
                      json={"project_id": pid, "role": "worker",
                            "mode": "PINNED", "provider": provider,
                            "model": model, "pool": [],
                            "strategy": "AUTO"},
                      headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert resp.json().get("ok") is True, resp.text


def _decide(client, pid, run_id, role="worker", body=None):
    payload = {"project_id": pid, "task_id": "t1", "run_id": run_id,
               "role": role, "task_class": "coding",
               "candidates": [{"provider": PIN_PROVIDER,
                               "model": PIN_MODEL}]}
    if body:
        payload.update(body)
    return client.post("/api/v1/routing/decide", json=payload,
                       headers=HEADERS)


# M-D-D28: one routing per run via stored profiles; no eligible
# profile blocks run.
# Route: GET /api/v1/routing/roles + PUT /api/v1/roles/pools +
# POST /api/v1/routing/decide + GET /api/v1/routing/why, through
# create_app into routing/roles.py (RoleTable.resolve) and
# routing/store.py (stored profiles).
def test_k04md_d28_stored_profile_blocks_without_and_routes_with(tmp_path):
    client, app = _make_client(tmp_path)
    pid = _create_project(client)
    # No eligible profile: every role resolves BLOCKED with the
    # NO_PROFILE_BLOCKED reason (fresh install holds no model).
    roles = client.get("/api/v1/routing/roles",
                       params={"project_id": pid})
    assert roles.status_code == 200, roles.text
    assert roles.json()["project_id"] == pid, roles.text
    assert [row["role"] for row in roles.json()["roles"]] == list(_T.ROLES)
    for row in roles.json()["roles"]:
        assert row["status"] == "BLOCKED", row
        assert row["reason"].startswith("NO_PROFILE_BLOCKED"), row
    # Store the worker profile, then route once per run through it.
    _pin_worker(client, pid)
    _seed_health(app)
    first = _decide(client, pid, "r-d28-1")
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "ROUTED", first.text
    assert first.json()["selected_model"] == PIN_MODEL, first.text
    assert first.json()["eligibility_source"] == "EXPLICIT_MODEL_PIN", \
        first.text
    second = _decide(client, pid, "r-d28-2")
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "ROUTED", second.text
    assert second.json()["selected_model"] == PIN_MODEL, second.text
    assert second.json()["decision_id"] != first.json()["decision_id"], \
        (first.text, second.text)
    # Both per-run routings persisted via the stored profile.
    for resp in (first, second):
        why = client.get("/api/v1/routing/why",
                         params={"decision_id":
                                 resp.json()["decision_id"]})
        assert why.status_code == 200, why.text
        assert why.json()["decision"]["decision_id"] == \
            resp.json()["decision_id"], why.text


# M-D-D26: routing + budget duties as owned port roles; RoutingPolicy
# shape carries the frozen refs.
# Route: POST /api/v1/routing/decide + GET /api/v1/routing/why,
# through create_app into routing/router.py (selection) and
# routing/store.py (evidence snapshot with the owned-port states).
def test_k04md_d26_owned_ports_and_policy_refs(tmp_path):
    client, app = _make_client(tmp_path)
    pid = _create_project(client)
    _pin_worker(client, pid)
    _seed_health(app)
    resp = client.post(
        "/api/v1/routing/decide",
        json={"project_id": pid, "task_id": "t1", "run_id": "r-d26",
              "role": "worker", "task_class": "coding", "mode": "PINNED",
              "candidates": [{"provider": PIN_PROVIDER,
                              "model": PIN_MODEL}]},
        headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ROUTED", resp.text
    why = client.get("/api/v1/routing/why",
                     params={"decision_id": resp.json()["decision_id"]})
    assert why.status_code == 200, why.text
    body = why.json()
    decision = body["decision"]
    snapshot = body["snapshot"]
    # RoutingPolicy shape: the decision carries both frozen policy refs
    # and the snapshot pins the exact versions used.
    assert decision["routing_policy_ref"], decision
    assert decision["optimization_policy_ref"], decision
    assert list(snapshot["policy_versions"]) == [
        decision["routing_policy_ref"],
        decision["optimization_policy_ref"]], snapshot
    assert snapshot["routing_snapshot_id"] == \
        decision["routing_snapshot_id"], body
    # Owned port roles: routing ran over the budget + resource duty
    # states, recorded as plain-data snapshots (never live gates).
    assert snapshot["budget_state_snapshot"], snapshot
    assert snapshot["resource_state_snapshot"], snapshot
    assert snapshot["candidate_snapshot"], snapshot
    assert any(row.get("model") == PIN_MODEL
               for row in snapshot["candidate_snapshot"]), snapshot


# M-D-D14 (served gate): a non-default Manager model is refused
# without a recorded trigger, and routes with one.
# Route: POST /api/v1/routing/decide, through create_app into
# routing/router.py (manager trigger gate, section 3B).
def test_k04md_d14_manager_override_needs_recorded_trigger(tmp_path):
    client, app = _make_client(tmp_path)
    pid = _create_project(client)
    _pin_worker(client, pid, provider="pm", model="pm/m1")
    resp = client.post("/api/v1/routing/role",
                       json={"project_id": pid, "role": "manager",
                             "mode": "PINNED", "provider": "pm",
                             "model": "pm/m1"},
                       headers=HEADERS)
    assert resp.status_code == 200, resp.text
    _seed_health(app, provider="pm", model="pm/m1")
    override = {"override_provider": "pm", "override_model": "pm/m1",
                "mode": "PINNED",
                "candidates": [{"provider": "pm", "model": "pm/m1"}]}
    refused = client.post(
        "/api/v1/routing/decide",
        json={"project_id": pid, "task_id": "t1", "run_id": "r-d14",
              "role": "manager", "task_class": "coding", **override},
        headers=HEADERS)
    assert refused.status_code == 200, refused.text
    assert refused.json()["status"] == "BLOCKED", refused.text
    assert "recorded trigger" in refused.json()["reason"], refused.text
    allowed = client.post(
        "/api/v1/routing/decide",
        json={"project_id": pid, "task_id": "t1", "run_id": "r-d14b",
              "role": "manager", "task_class": "coding",
              "manager_trigger": "user_override",
              "manager_trigger_ref": "ui:k04md-d14", **override},
        headers=HEADERS)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["status"] == "ROUTED", allowed.text
    assert allowed.json()["selected_provider"] == "pm", allowed.text
    assert allowed.json()["selected_model"] == "pm/m1", allowed.text


# M-D-D14 (record + ledger): the swap itself is built only through
# a FallbackRecord with a canonical reason, persisted to the ledger
# store with a telemetry event.
# Product path: routing/fallback.py replace_manager_model over a real
# routing/store.py RoutingStore (owned lane files).
def test_k04md_d14_fallback_record_shape_and_ledger(tmp_path):
    from agent_si.routing import fallback as _FB
    from agent_si.routing import roles as _RL
    from agent_si.routing.store import RoutingStore

    store = RoutingStore(str(tmp_path / "rstore"))
    profile = _RL.make_default_manager_profile(
        "meta", "meta/muse-spark-1.3-contributor")
    seen = []

    class _Emitter:
        def emit(self, event):
            seen.append(event)

    record, new_profile = _FB.replace_manager_model(
        profile, to_provider="pm", to_model="pm/m1",
        reason="provider_fail", trigger="user_override",
        trigger_ref="ui:k04md-d14", project_id="p1", task_id="t1",
        run_id="r1", store=store, emitter=_Emitter())
    assert isinstance(record, _T.FallbackRecord), record
    # Frozen FallbackRecord shape: every field present and bound.
    assert record.fallback_id.startswith("fb-"), record
    assert (record.project_id, record.task_id,
            record.source_run_id) == ("p1", "t1", "r1"), record
    assert record.replacement_run_id == "r1", record
    assert record.source_attempt_id is None, record
    assert record.reason in _T.FALLBACK_REASONS, record
    assert (record.from_provider, record.from_model) == (
        "meta", "meta/muse-spark-1.3-contributor"), record
    assert (record.to_provider, record.to_model) == ("pm", "pm/m1"), \
        record
    assert record.policy_ref, record
    assert record.evidence_ref == "user_override:ui:k04md-d14", record
    # Non-default Manager model only via the record: version bumped,
    # ledger binds the record, telemetry carries the fallback reason.
    assert new_profile.version == profile.version + 1, new_profile
    assert (new_profile.provider, new_profile.model) == ("pm", "pm/m1")
    rows = store.list_fallbacks("t1")
    assert any(row.get("fallback_id") == record.fallback_id
               for row in rows), rows
    assert any(event.get("event_type") == "manager_replacement"
               and event.get("fallback_reason") == "provider_fail"
               for event in seen), seen
    # Untriggered swaps and off-enum reasons stay refused.
    try:
        _FB.replace_manager_model(
            profile, to_provider="pm", to_model="pm/m1",
            reason="provider_fail", trigger="silent_swap",
            trigger_ref="x", project_id="p1", task_id="t1", run_id="r1")
    except ValueError as exc:
        assert "recorded trigger" in str(exc), exc
    else:
        raise AssertionError("untriggered manager swap was allowed")


# M-D-D21: every real-API run goes through the provisioning gateway;
# key-only connect, raw inline material refused at the boundary.
# Route: POST /api/v1/providers/keys + POST /api/v1/providers/connect
# + GET /api/v1/providers + GET /api/v1/local/*, through create_app
# into the provisioning-gateway connect path (key refs only, never
# inline values; evidence probe over the gateway transport).
def test_k04md_d21_connect_goes_through_provisioning_gateway(
        tmp_path, monkeypatch):
    from agent_si.backend import local_connect as _local

    _patch_urlopen(monkeypatch)
    saved_paired = _local._PAIRED_SESSION_TOKEN
    saved_attached = _local._ATTACHED_RUNTIME
    _local._PAIRED_SESSION_TOKEN = None
    _local._ATTACHED_RUNTIME = None
    try:
        client, _app = _make_client(tmp_path)
        _create_project(client)
        # Real-API leg: key-only save answers an id-only ref.
        saved = client.post("/api/v1/providers/keys",
                            json={"preset_id": "openai",
                                  "key_value": BAIT},
                            headers=HEADERS)
        assert saved.status_code == 201, saved.text
        assert BAIT not in saved.text, saved.text
        key_ref = saved.json()["key_ref"]
        assert set(key_ref) <= {"secret_id", "provider_id"}, key_ref
        # Raw inline material never crosses the gateway boundary.
        raw = client.post("/api/v1/providers/connect",
                          json={"preset_id": "openai", "model": "m-d21",
                                "api_key": BAIT},
                          headers=HEADERS)
        assert raw.status_code == 400, raw.text
        assert "raw secret material refused" in raw.text, raw.text
        assert BAIT not in raw.text, raw.text
        # Key-only connect evidences the provider via the gateway.
        conn = client.post("/api/v1/providers/connect",
                           json={"preset_id": "openai", "model": "m-d21",
                                 "key_ref": key_ref},
                           headers=HEADERS)
        assert conn.status_code == 200, conn.text
        assert BAIT not in conn.text, conn.text
        listed = client.get("/api/v1/providers", headers=HEADERS)
        assert listed.status_code == 200, listed.text
        rows = {r["provider_id"]: r
                for r in listed.json()["providers"]}
        assert rows["openai"]["evidenced"] is True, rows
        assert BAIT not in listed.text, listed.text
        # Real local-AI leg: the local runtime surface attaches through
        # the same gateway seam (no live runtime here; the seam answers
        # NOT_CONFIGURED and routing continues).
        attached = client.post("/api/v1/local/connect",
                               json={"runtime_ref": "local-test-runtime"},
                               headers=HEADERS)
        assert attached.status_code == 200, attached.text
        status = client.get("/api/v1/local/status")
        assert status.status_code == 200, status.text
        assert "routing continues" in status.text, status.text
        models = client.get("/api/v1/local/models")
        assert models.status_code == 200, models.text
    finally:
        _local._ATTACHED_RUNTIME = saved_attached
        _local._PAIRED_SESSION_TOKEN = saved_paired
