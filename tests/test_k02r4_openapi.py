"""K02R4 OpenAPI schema answers 200 and covers every mounted route (M-SCHEMA).

Row LIVE0-07: the OpenAPI and docs schema answer, no 500. Drives the
real seam app (create_app) with TestClient: GET /openapi.json is 200,
every mounted API route path appears in the schema (including the chat
stream route, the chat cancel route, and the agents live route), the
route count is unchanged by schema generation, and create_app still
imports and mounts routes after the annotation fix.
"""

import os
import sys

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "k02r4-openapi-token"
TEST_SETTINGS = {"testing": True, "ui_session_token": TEST_TOKEN}

REQUIRED_PATHS = (
    "/api/v1/chat/stream",
    "/api/v1/chat/cancel",
    "/api/v1/agents/live",
)


def _mounted_api_paths(app):
    return [route.path for route in app.routes
            if isinstance(route, APIRoute) and route.path]


def _client(app):
    return TestClient(app, raise_server_exceptions=False)


def test_openapi_answers_200():
    app = create_app(dict(TEST_SETTINGS))
    resp = _client(app).get("/openapi.json")
    assert resp.status_code == 200, resp.text


def test_openapi_covers_every_mounted_route():
    app = create_app(dict(TEST_SETTINGS))
    client = _client(app)
    before = len(app.routes)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200, resp.text
    after = len(app.routes)
    assert after == before
    documented = set(resp.json().get("paths", {}).keys())
    for path in _mounted_api_paths(app):
        assert path in documented, path
    for path in REQUIRED_PATHS:
        assert path in documented, path


def test_runtime_import_still_works():
    app = create_app(dict(TEST_SETTINGS))
    assert set(_mounted_api_paths(app)) >= set(REQUIRED_PATHS)
