import logging
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.providers.registry.key_routes import KEY_SAVE_TIMEOUT  # noqa: E402

APP_TOKEN = "k04key1-app-token"
BAIT = "FAKE-K04KEY1-BAIT-0000-zzzz-not-a-real-key"
BAIT2 = "FAKE-K04KEY1-BAIT-1111-yyyy-not-a-real-key"

HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}


def make_client(tmp_path, **extra):
    settings = {"store_dir": str(tmp_path / "appdata"),
                "ui_session_token": APP_TOKEN,
                "secret_store": "memory"}
    settings.update(extra)
    app = create_app(settings)
    return fastapi.testclient.TestClient(app), app


def test_save_connect_list_disconnect_roundtrip(tmp_path, caplog):
    client, app = make_client(tmp_path)
    assert KEY_SAVE_TIMEOUT == "KEY_SAVE_TIMEOUT"
    assert app.state.k04_ctx.credential_store is not None
    with caplog.at_level(logging.INFO):
        resp = client.post("/api/v1/providers/keys",
                           json={"preset_id": "openai", "key_value": BAIT},
                           headers=HEADERS)
    assert resp.status_code == 201, resp.text
    payload = resp.json()
    assert set(payload) == {"key_ref"}, payload
    key_ref = payload["key_ref"]
    assert key_ref["secret_id"] == "openai", payload
    assert key_ref["provider_id"] == "openai", payload
    assert BAIT not in resp.text
    assert BAIT not in str(app.state.k04_ctx.audit_sink.records)
    assert BAIT not in caplog.text
    # connect with the returned ref plus a model
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": "openai", "model": "m-k04key1",
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    assert BAIT not in conn.text
    listed = client.get("/api/v1/providers")
    assert listed.status_code == 200, listed.text
    ids = [row["provider_id"] for row in listed.json()["providers"]]
    assert "openai" in ids
    # disconnect removes the store entry
    disc = client.post("/api/v1/providers/openai/disconnect", json={},
                       headers=HEADERS)
    assert disc.status_code == 200, disc.text
    assert disc.json() == {"removed": True, "provider_id": "openai"}
    assert app.state.k04_ctx.credential_store.has("openai") is False
    assert BAIT not in str(app.state.k04_ctx.audit_sink.records)


def test_save_never_echoes_value_and_audit_clean(tmp_path, caplog):
    client, app = make_client(tmp_path)
    with caplog.at_level(logging.INFO):
        resp = client.post("/api/v1/providers/keys",
                           json={"preset_id": "openai", "key_value": BAIT2},
                           headers=HEADERS)
    assert resp.status_code == 201, resp.text
    assert BAIT2 not in resp.text
    assert BAIT2 not in str(app.state.k04_ctx.audit_sink.records)
    assert BAIT2 not in caplog.text
    # cleanup the saved entry through disconnect after a connect
    key_ref = resp.json()["key_ref"]
    conn = client.post("/api/v1/providers/connect",
                       json={"preset_id": "openai", "model": "m-clean",
                             "key_ref": key_ref},
                       headers=HEADERS)
    assert conn.status_code == 200, conn.text
    disc = client.post("/api/v1/providers/openai/disconnect", json={},
                       headers=HEADERS)
    assert disc.status_code == 200, disc.text


def test_connect_still_refuses_raw_key(tmp_path):
    client, _app = make_client(tmp_path)
    resp = client.post("/api/v1/providers/connect",
                       json={"preset_id": "openai", "model": "m-raw",
                             "key_value": BAIT},
                       headers=HEADERS)
    assert resp.status_code == 400, resp.text
    assert BAIT not in resp.text


def test_save_needs_write_guard(tmp_path):
    client, _app = make_client(tmp_path)
    no_actor = client.post("/api/v1/providers/keys",
                           json={"preset_id": "openai",
                                 "key_value": BAIT})
    assert no_actor.status_code in (401, 403), no_actor.text
    assert BAIT not in no_actor.text
    bad_token = client.post(
        "/api/v1/providers/keys",
        json={"preset_id": "openai", "key_value": BAIT},
        headers={"x-actor": "ui-probe", "x-ui-session-token": "wrong-token"})
    assert bad_token.status_code in (401, 403), bad_token.text
    assert BAIT not in bad_token.text


def test_save_bad_shapes_400(tmp_path):
    client, _app = make_client(tmp_path)
    for bad in ({}, {"preset_id": "openai"}, {"key_value": BAIT},
                {"preset_id": "no-such-preset", "key_value": BAIT},
                {"preset_id": "", "key_value": BAIT},
                {"preset_id": "openai", "key_value": ""}):
        resp = client.post("/api/v1/providers/keys", json=bad,
                           headers=HEADERS)
        assert resp.status_code == 400, (bad, resp.text)
        assert BAIT not in resp.text


def test_save_timeout_answers_code(tmp_path):
    client, app = make_client(tmp_path)

    class HangingStore:
        def set_secret(self, secret_id, value):
            time.sleep(2.0)

        def seed(self, secret_id, payload="x"):
            return None

        def has(self, secret_id):
            return False

        def delete(self, secret_id):
            raise KeyError(secret_id)

    app.state.k04_ctx.credential_store = HangingStore()
    app.state.k04_ctx.key_save_timeout_s = 0.05
    started = time.time()
    resp = client.post("/api/v1/providers/keys",
                       json={"preset_id": "openai", "key_value": BAIT},
                       headers=HEADERS)
    elapsed = time.time() - started
    assert resp.status_code == 504, resp.text
    assert resp.json().get("code") == KEY_SAVE_TIMEOUT, resp.text
    assert BAIT not in resp.text
    assert elapsed < 5.0, elapsed
