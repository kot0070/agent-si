# K04G CODER-2 Heron — 4 dispatch proofs, one test per row, via create_app.
# Self-sufficient: portable sys.path bootstrap (src + repo root for iface),
# memory secret store, fresh app per test over a tmp store dir. No fakes:
# every leg drives the real dispatch (create_app + TestClient) into the
# real routing package (roles / pools / store / telemetry_port).
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.abspath(os.path.join(_HERE, "..", ".."))
_SRC = os.path.join(_WS, "src")
for _p in (_SRC, _WS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("AGENT_SI_SECRET_STORE", "memory")

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.routing import types as T  # noqa: E402
import fastapi.testclient as ftc  # noqa: E402

_TOKEN = "k04g-coder2-token"


def _client(tmp_path):
    """Fresh served app per test (real dispatch, isolated store)."""
    app = create_app({"store_dir": str(tmp_path),
                      "secret_store": "memory",
                      "ui_session_token": _TOKEN})
    return ftc.TestClient(app)


def _auth():
    return {"x-actor": "k04g-coder2",
            "x-ui-session-token": _TOKEN}


# B0B-BP02-9: GET /api/v1/routing/roles served via roles.RoleTable.resolve.
def test_k04g_coder2_bp02_9_roles_served(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/api/v1/routing/roles",
                      params={"project_id": "p1"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == "p1"
    assert [row["role"] for row in body["roles"]] == list(T.ROLES)
    for row in body["roles"]:
        assert row["mode"] is None
        assert row["provider"] is None
        assert row["model"] is None
        assert row["status"] == "BLOCKED"
        assert row["reason"].startswith("NO_PROFILE_BLOCKED"), row


# B0B-BP03-9: GET /api/v1/routing/picker served via pools.picker_options.
def test_k04g_coder2_bp03_9_picker_served(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/api/v1/routing/picker",
                      params={"project_id": "p1", "role": "worker",
                              "purpose": "vision"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "worker"
    assert body["purpose"] == "vision"
    options = body["options"]
    assert [opt["key"] for opt in options] == ["opt-1", "opt-2"]
    for opt in options:
        assert opt["label"].startswith("Option ")
        assert "description" in opt and opt["description"]
    assert "gpt-4o" not in resp.text

    bad = client.get("/api/v1/routing/picker",
                     params={"project_id": "p1", "role": "ghost"})
    assert bad.status_code == 400, bad.text


# B0B-SDK-114: GET /api/v1/routing/suggest served via pools.suggest_strongest.
def test_k04g_coder2_sdk_114_suggest_served(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/api/v1/routing/suggest",
                      params={"provider": "openai", "purpose": "vision"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider"] == "openai"
    assert body["model"] == "gpt-4o"
    assert body["purpose"] == "vision"
    assert "openai" in body["reason"]

    missing = client.get("/api/v1/routing/suggest", params={})
    assert missing.status_code == 400, missing.text


# B0B-SDK-32: POST /api/v1/routing/role served via roles.set_profile +
# telemetry_port.routing_event, persisted through store; read back via GET.
def test_k04g_coder2_sdk_32_setrole_served(tmp_path):
    client = _client(tmp_path)
    denied = client.post("/api/v1/routing/role",
                         json={"project_id": "p1", "role": "worker",
                               "mode": "PINNED", "provider": "openai",
                               "model": "gpt-4o"})
    assert denied.status_code == 401, denied.text

    resp = client.post("/api/v1/routing/role",
                       json={"project_id": "p1", "role": "worker",
                             "mode": "PINNED", "provider": "openai",
                             "model": "gpt-4o"},
                       headers=_auth())
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True
    profile = resp.json()["profile"]
    assert (profile["role"], profile["mode"], profile["provider"],
            profile["model"]) == ("worker", "PINNED", "openai", "gpt-4o")

    readback = client.get("/api/v1/routing/role",
                          params={"project_id": "p1", "role": "worker"})
    assert readback.status_code == 200, readback.text
    assert readback.json()["profile"] == profile

    listed = client.get("/api/v1/routing/roles",
                        params={"project_id": "p1"})
    assert listed.status_code == 200, listed.text
    worker = [row for row in listed.json()["roles"]
              if row["role"] == "worker"][0]
    assert worker["mode"] == "PINNED"
    assert worker["status"] == "PINNED_UNHEALTHY", worker
