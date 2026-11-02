# FXSAVED item 1: GET /api/v1/roles/chat-model reads the saved pick.
# RED first: no GET handler is served yet (expect 200, get 404/405).
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import pools_routes as PR
from agent_si.routing import roles as RL
from agent_si.routing import store as ST
from agent_si.routing import telemetry_port as TP
from agent_si.providers.registry import facades as FAC

APP_TOKEN = "hdr-fxsaved-get"
GET_URL = "/api/v1/roles/chat-model"


def make_ctx(tmp_path, **kw):
    store = ST.RoutingStore(str(tmp_path / "data"))
    ctx = PR.RoutingCtx(store=store, role_table=RL.RoleTable(store), kb=None)
    return ctx, store


def seed_worker(ctx, project_id="p1"):
    profile = RL.__dict__ and None
    import agent_si.routing.types as T
    ctx.role_table.set_profile(T.RoleModelProfile(
        role="worker", project_id=project_id, mode="AUTO",
        provider=None, model=None, binding="DEFAULT", version=1,
        hash="seed"))


def test_get_returns_null_when_nothing_saved(tmp_path):
    ctx, _store = make_ctx(tmp_path)
    seed_worker(ctx)
    status, payload = PR.get_chat_model(ctx, {"project_id": "p1"}, None)
    assert status == 200, payload
    assert payload == {"project_id": "p1", "model_id": None}


def test_get_returns_saved_model(tmp_path):
    ctx, _store = make_ctx(tmp_path)
    seed_worker(ctx)
    import agent_si.routing.types as T
    ctx2 = ctx
    PR._save_chat_record(ctx2.store, "p1", "openai/model-1")
    status, payload = PR.get_chat_model(ctx, {"project_id": "p1"}, None)
    assert status == 200, payload
    assert payload == {"project_id": "p1", "model_id": "openai/model-1"}


def test_get_needs_project_id(tmp_path):
    ctx, _store = make_ctx(tmp_path)
    status, _payload = PR.get_chat_model(ctx, {}, None)
    assert status == 400


def test_app_serves_get_chat_model(tmp_path):
    from agent_si.backend.app import create_app
    import fastapi.testclient
    app = create_app({"store_dir": str(tmp_path / "appdata"),
                      "ui_session_token": APP_TOKEN})
    seed_worker(app.state.k04_ctx)
    client = fastapi.testclient.TestClient(app)
    resp = client.get(GET_URL, params={"project_id": "p1"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"project_id": "p1", "model_id": None}
    put = client.put(GET_URL,
                     json={"project_id": "p1",
                           "model_id": "openai/model-1"},
                     headers={"x-ui-session-token": APP_TOKEN})
    assert put.status_code == 200, put.text
    again = client.get(GET_URL, params={"project_id": "p1"})
    assert again.status_code == 200, again.text
    assert again.json() == {"project_id": "p1",
                            "model_id": "openai/model-1"}
