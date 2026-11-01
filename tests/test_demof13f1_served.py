"""DEMOF13W served proof: F13 install-permission ask-once plus F1 catalog run.

Both cases drive the real app built by create_app over HTTP; the two
demo routes are wired inside create_app from the product modules
(src/agent_si/toolguard/permissions.py plus
src/agent_si/qa_catalog/qa_catalog.py). RED: routes absent from bare
create_app, so both cases answer 404 until the DEMOF13W mounts block
lands. No lane register helper is used or imported here.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "demof13w-served-token"


@pytest.fixture
def client(tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    settings = {"ui_session_token": TEST_TOKEN, "store_dir": str(store)}
    app = create_app(dict(settings))
    return TestClient(app)


def test_f13_ask_once_persisted(client):
    first = client.post(
        "/api/v1/permissions/check", json={"tool_id": "tool-demo-f13"}
    )
    assert first.status_code == 200
    assert first.json() == {"allowed": True, "asked_once": False}
    second = client.post(
        "/api/v1/permissions/check", json={"tool_id": "tool-demo-f13"}
    )
    assert second.status_code == 200
    assert second.json() == {"allowed": True, "asked_once": True}


def test_f13_ask_once_survives_rebuild(tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    settings = {"ui_session_token": TEST_TOKEN, "store_dir": str(store)}
    first = TestClient(create_app(dict(settings))).post(
        "/api/v1/permissions/check", json={"tool_id": "tool-demo-f13"}
    )
    assert first.status_code == 200
    assert first.json() == {"allowed": True, "asked_once": False}
    rebuilt = TestClient(create_app(dict(settings))).post(
        "/api/v1/permissions/check", json={"tool_id": "tool-demo-f13"}
    )
    assert rebuilt.status_code == 200
    assert rebuilt.json() == {"allowed": True, "asked_once": True}


def test_f1_catalog_run_via_route(client):
    resp = client.post(
        "/api/v1/catalog/run", json={"suite": "catalog-frozen-v1"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "ran": 6}
