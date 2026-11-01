# FXROLES chat-hierarchy save-path served proofs (RED first, then GREEN).
# Proves the chat rows persist through the SAME role-profile PUT the
# Settings editors use (PUT /api/v1/routing/role with the UI session
# token): a manager PINNED persists and GET returns it, the Agents row's
# worker+auditor dual PUT persists both, AUTO holds no provider/model,
# and the negatives (empty-store GET, unknown role, missing token,
# PINNED without model) still fail after the change.
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402

APP_TOKEN = "fxroles-app-token"
ROLE_PATH = "/api/v1/routing/role"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}

PIN_PROVIDER = "anthropic"
PIN_MODEL = "anthropic/model-2"
PID = "fxroles-p1"


def make_client(tmp_path):
    app = create_app({"store_dir": str(tmp_path / "appdata"),
                      "ui_session_token": APP_TOKEN,
                      "secret_store": "memory"})
    return fastapi.testclient.TestClient(app), app


def put_role(client, role, mode, provider=None, model=None,
             headers=HEADERS):
    body = {"project_id": PID, "role": role, "mode": mode}
    if provider is not None:
        body["provider"] = provider
    if model is not None:
        body["model"] = model
    return client.put(ROLE_PATH, json=body, headers=headers)


def get_role(client, role, project_id=PID):
    return client.get(ROLE_PATH,
                      params={"project_id": project_id, "role": role})


def test_manager_pinned_persists_and_get_returns_it(tmp_path):
    client, _app = make_client(tmp_path)
    resp = put_role(client, "manager", "PINNED", PIN_PROVIDER, PIN_MODEL)
    assert resp.status_code == 200, resp.text
    assert resp.json().get("ok") is True, resp.text
    readback = get_role(client, "manager")
    assert readback.status_code == 200, readback.text
    profile = readback.json()["profile"]
    assert profile["mode"] == "PINNED", readback.text
    assert profile["provider"] == PIN_PROVIDER, readback.text
    assert profile["model"] == PIN_MODEL, readback.text


def test_agents_dual_put_worker_and_auditor_together(tmp_path):
    client, _app = make_client(tmp_path)
    for role in ("worker", "auditor"):
        resp = put_role(client, role, "PINNED", "openai", "openai/model-1")
        assert resp.status_code == 200, (role, resp.text)
    for role in ("worker", "auditor"):
        readback = get_role(client, role)
        assert readback.status_code == 200, (role, readback.text)
        profile = readback.json()["profile"]
        assert profile["provider"] == "openai", (role, readback.text)
        assert profile["model"] == "openai/model-1", (role, readback.text)


def test_auto_holds_no_provider_or_model(tmp_path):
    client, _app = make_client(tmp_path)
    resp = put_role(client, "director", "AUTO")
    assert resp.status_code == 200, resp.text
    readback = get_role(client, "director")
    assert readback.status_code == 200, readback.text
    profile = readback.json()["profile"]
    assert profile["mode"] == "AUTO", readback.text
    assert profile["provider"] is None, readback.text
    assert profile["model"] is None, readback.text


def test_empty_store_get_still_fails_404(tmp_path):
    client, _app = make_client(tmp_path)
    readback = get_role(client, "manager", project_id="fxroles-ghost")
    assert readback.status_code == 404, readback.text


def test_unknown_role_refused_never_stored(tmp_path):
    client, _app = make_client(tmp_path)
    resp = put_role(client, "stranger", "AUTO")
    assert resp.status_code == 400, resp.text
    assert "unknown role" in resp.json().get("error", ""), resp.text
    readback = get_role(client, "stranger")
    assert readback.status_code == 400, readback.text


def test_put_without_token_refused_403(tmp_path):
    client, _app = make_client(tmp_path)
    resp = put_role(client, "manager", "PINNED", PIN_PROVIDER, PIN_MODEL,
                    headers={"x-actor": "ui-probe"})
    assert resp.status_code == 403, resp.text
    assert get_role(client, "manager").status_code == 404, resp.text


def test_put_missing_actor_refused_401(tmp_path):
    client, _app = make_client(tmp_path)
    resp = put_role(client, "manager", "PINNED", PIN_PROVIDER, PIN_MODEL,
                    headers={"x-ui-session-token": APP_TOKEN})
    assert resp.status_code == 401, resp.text
    assert get_role(client, "manager").status_code == 404, resp.text


def test_put_query_only_token_ignored_and_refused_403(tmp_path):
    client, _app = make_client(tmp_path)
    resp = client.put(ROLE_PATH + "?session_token=query-only-token",
                      json={"project_id": PID, "role": "manager",
                            "mode": "PINNED", "provider": PIN_PROVIDER,
                            "model": PIN_MODEL},
                      headers={"x-actor": "ui-probe"})
    assert resp.status_code == 403, resp.text
    assert get_role(client, "manager").status_code == 404, resp.text


def test_put_pinned_without_model_refused_400(tmp_path):
    client, _app = make_client(tmp_path)
    resp = put_role(client, "manager", "PINNED", PIN_PROVIDER)
    assert resp.status_code == 400, resp.text
    assert get_role(client, "manager").status_code == 404, resp.text
