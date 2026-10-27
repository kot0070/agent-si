"""K09-C KB write-route token refusal through the K02 app seam.

Drives the three USER-write KB routes (POST /kb/attach, /kb/detach,
/kb/retrieve) through the frozen K02 seam app (create_app) with
TestClient: no token -> 401 and wrong token -> 403, and the KB
implementation is never called on a refused request. The KB routes are
wired into the seam app (register_kb_routes), never a separate app.

RED while src/agent_si/backend/app.py is absent from this workspace
(K02 integration pending): the client fixture imports the frozen seam
name, so each test fails on its own with a create_app ModuleNotFoundError
while collection still succeeds. GREEN when the seam app serves the KB
routes behind the USER_WRITE guard.
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

from src.agent_si.backend import kb_routes

TEST_TOKEN = "k09c-routes-auth-token"
TEST_SETTINGS = {"testing": True, "ui_session_token": TEST_TOKEN}

WRITE_ROUTES = ("/kb/attach", "/kb/detach", "/kb/retrieve")


# FAKE-OF: src/agent_si/kb/retriever.py attach_kb/detach_kb/retrieve.
# Refusal spies: fail closed (raise) if a refused request ever reaches
# the KB implementation.
@pytest.fixture
def _refusal_spies(monkeypatch):
    calls = []

    def _spy(name):
        def _impl(*args, **kwargs):
            calls.append(name)
            raise AssertionError(
                "KB implementation %r called on a refused request" % (name,)
            )

        return _impl

    monkeypatch.setattr(
        kb_routes._behaviour, "attach_kb", _spy("attach_kb"))
    monkeypatch.setattr(
        kb_routes._behaviour, "detach_kb", _spy("detach_kb"))
    monkeypatch.setattr(
        kb_routes._behaviour, "retrieve", _spy("retrieve"))
    return calls


@pytest.fixture
def client():
    from agent_si.backend.app import create_app
    app = create_app(dict(TEST_SETTINGS))
    kb_routes.register_kb_routes(app)
    return TestClient(app)


@pytest.mark.parametrize("path", WRITE_ROUTES)
def test_write_route_without_token_refused(client, _refusal_spies, path):
    resp = client.post(path)
    assert resp.status_code == 401
    assert _refusal_spies == []


@pytest.mark.parametrize("path", WRITE_ROUTES)
def test_write_route_with_wrong_token_refused(
        client, _refusal_spies, path):
    resp = client.post(
        path,
        headers={"x-actor": "tester-k09c",
                 "x-ui-session-token": "wrong-token"},
    )
    assert resp.status_code == 403
    assert _refusal_spies == []
