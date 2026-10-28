# K04P2-CHATSAVE chat-model save route tests (RED first, then GREEN).
# Handler level (the K02 header binding is carried by ctx.session_token;
# the URL query is never a token channel here) plus served-app level
# (real create_app + TestClient over a real registry dir).
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import pools_routes as PR
from agent_si.providers.registry import facades as FAC
from agent_si.providers.registry import provider_routes as PVR
from agent_si.providers.registry.contracts import SecretRef
from agent_si.routing import roles as RL
from agent_si.routing import store as ST
from agent_si.routing import telemetry_port as TP
from agent_si.routing import types as T

APP_TOKEN = "hdr-app-token"
LOOPBACK = "http://127.0.0.1:9/v1"
CHAT_URL = "/api/v1/roles/chat-model"


def make_ctx(tmp_path, *, session_token=None, emitter=True, sink=True):
    store = ST.RoutingStore(str(tmp_path / "data"))
    ctx = PR.RoutingCtx(store=store, role_table=RL.RoleTable(store), kb=None)
    if session_token is not None:
        ctx.session_token = session_token
    events = []
    if emitter:
        emitter_obj = TP.TelemetryEmitter()
        emitter_obj.add_sink(events.append)
        ctx.emitter = emitter_obj
    else:
        ctx.emitter = None
    audit = None
    if sink:
        _api, _credstore, audit = FAC.ephemeral_stack()
    ctx.audit_sink = audit
    return ctx, store, events, audit


def seed_worker_profile(ctx, project_id="p1"):
    profile = T.RoleModelProfile(
        role="worker", project_id=project_id, mode="AUTO",
        provider=None, model=None, binding="DEFAULT", version=1,
        hash="seed")
    ctx.role_table.set_profile(profile)
    return profile


def test_no_header_binding_refused_401(tmp_path):
    ctx, _store, _events, _audit = make_ctx(tmp_path)
    status, payload = PR.put_chat_model(
        ctx, {}, {"project_id": "p1", "model_id": "openai/model-1"})
    assert status == 401, payload
    assert payload.get("code") == "CONTEXT_MISSING"


def test_query_only_token_ignored_and_refused_401(tmp_path):
    ctx, _store, _events, _audit = make_ctx(tmp_path)
    seed_worker_profile(ctx)
    status, payload = PR.put_chat_model(
        ctx, {"session_token": "query-only-token"},
        {"project_id": "p1", "model_id": "openai/model-1"})
    assert status == 401, payload
    assert PR.get_chat_record(ctx, "p1") is None


def test_body_token_field_refused_400(tmp_path):
    ctx, _store, _events, _audit = make_ctx(tmp_path, session_token="good")
    status, payload = PR.put_chat_model(
        ctx, {},
        {"project_id": "p1", "model_id": "m", "session_token": "x"})
    assert status == 400, payload


def test_body_shape_400s(tmp_path):
    ctx, _store, _events, _audit = make_ctx(tmp_path, session_token="good")
    bad_bodies = (
        {"project_id": "p1"},
        {"model_id": "m"},
        {"project_id": "p1", "model_id": ""},
        {"project_id": "", "model_id": "m"},
        {"project_id": "p1", "model_id": "m", "role": "worker"},
        None,
    )
    for bad in bad_bodies:
        status, payload = PR.put_chat_model(ctx, {}, bad)
        assert status == 400, (bad, payload)


def test_unknown_project_404(tmp_path):
    ctx, _store, _events, _audit = make_ctx(tmp_path, session_token="good")
    status, payload = PR.put_chat_model(
        ctx, {}, {"project_id": "ghost", "model_id": "openai/model-1"})
    assert status == 404, payload


def test_persist_and_registry_readback(tmp_path):
    ctx, store, events, audit = make_ctx(tmp_path, session_token="good")
    seed_worker_profile(ctx)
    status, payload = PR.put_chat_model(
        ctx, {}, {"project_id": "p1", "model_id": "openai/model-1"})
    assert status == 200, payload
    assert payload == {"ok": True, "project_id": "p1",
                       "model_id": "openai/model-1"}
    assert PR.get_chat_record(ctx, "p1") == {
        "project_id": "p1", "model_id": "openai/model-1"}
    store2 = ST.RoutingStore(str(tmp_path / "data"))
    ctx2 = PR.RoutingCtx(store=store2, role_table=RL.RoleTable(store2),
                         kb=None)
    assert PR.get_chat_record(ctx2, "p1") == {
        "project_id": "p1", "model_id": "openai/model-1"}
    assert any(record.get("project_id") == "p1"
               and record.get("model_id") == "openai/model-1"
               for record in audit.records)
    assert any(event.get("model") == "openai/model-1" for event in events)


def test_chat_get_lists_saved_model(tmp_path):
    api, credstore, _sink = FAC.ephemeral_stack()
    credstore.seed("s-chat")
    api.register_provider(
        {"provider_id": "openai", "type": "openai",
         "base_url": LOOPBACK},
        SecretRef(secret_id="s-chat", provider_id="openai"),
        model="openai/model-1", evidence_ref="ev-chat")
    pctx = PVR.ProviderCtx(facade=api, models={"openai": ["openai/model-1"]})
    status, payload = PVR.chat_models(pctx, {"project_id": "p1"}, None)
    assert status == 200, payload
    assert {"provider_id": "openai", "model": "openai/model-1"} in payload[
        "models"]


def test_seam_down_fail_closed(tmp_path):
    ctx, _store, _events, _audit = make_ctx(
        tmp_path, session_token="good", sink=False)
    seed_worker_profile(ctx)
    status, payload = PR.put_chat_model(
        ctx, {}, {"project_id": "p1", "model_id": "m"})
    assert status == 500, payload
    assert "DOWN" in payload.get("error", "")
    assert PR.get_chat_record(ctx, "p1") is None
    ctx2, _s2, _e2, _a2 = make_ctx(
        tmp_path, session_token="good", emitter=False)
    status2, payload2 = PR.put_chat_model(
        ctx2, {}, {"project_id": "p1", "model_id": "m"})
    assert status2 == 500, payload2
    assert PR.get_chat_record(ctx2, "p1") is None


def make_client(tmp_path):
    from agent_si.backend.app import create_app
    import fastapi.testclient
    app = create_app({"store_dir": str(tmp_path / "appdata"),
                      "ui_session_token": APP_TOKEN})
    return fastapi.testclient.TestClient(app), app


def test_app_no_header_401(tmp_path):
    client, _app = make_client(tmp_path)
    resp = client.put(CHAT_URL,
                      json={"project_id": "p1", "model_id": "m"})
    assert resp.status_code == 401, resp.text


def test_app_wrong_header_401(tmp_path):
    client, _app = make_client(tmp_path)
    resp = client.put(CHAT_URL,
                      json={"project_id": "p1", "model_id": "m"},
                      headers={"x-ui-session-token": "wrong-token"})
    assert resp.status_code == 401, resp.text


def test_app_query_only_401(tmp_path):
    client, _app = make_client(tmp_path)
    resp = client.put(CHAT_URL + "?session_token=query-only-token",
                      json={"project_id": "p1", "model_id": "m"})
    assert resp.status_code == 401, resp.text


def test_app_unknown_project_404(tmp_path):
    client, _app = make_client(tmp_path)
    resp = client.put(CHAT_URL,
                      json={"project_id": "ghost",
                            "model_id": "openai/model-1"},
                      headers={"x-ui-session-token": APP_TOKEN})
    assert resp.status_code == 404, resp.text


def test_app_save_persist_and_readback(tmp_path):
    client, app = make_client(tmp_path)
    seed_worker_profile(app.state.k04_ctx)
    resp = client.put(CHAT_URL,
                      json={"project_id": "p1",
                            "model_id": "openai/model-1"},
                      headers={"x-ui-session-token": APP_TOKEN})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "project_id": "p1",
                           "model_id": "openai/model-1"}
    assert PR.get_chat_record(app.state.k04_ctx, "p1") == {
        "project_id": "p1", "model_id": "openai/model-1"}
    retry = client.put(CHAT_URL + "?session_token=junk-token",
                       json={"project_id": "p1",
                             "model_id": "openai/model-1"},
                       headers={"x-ui-session-token": APP_TOKEN})
    assert retry.status_code == 200, retry.text
    old = client.get("/api/v1/roles/pools",
                     params={"project_id": "p1"})
    assert old.status_code == 200, old.text
