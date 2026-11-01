# CODER-1 Holt FXFOLDER served tests (RED-first).
# Drives POST /api/v1/sidecar/pick-folder through sidecar.build_app()
# over the real product app (agent_si.backend.app.create_app, untouched):
# the write guard answers 401 with no actor and 403 with a bad token;
# with no native window (headless or browser) the route answers 409 with
# a JSON body carrying the stable machine code; a stubbed window choosing
# a folder answers {"path": "<chosen>"} and a cancelled dialog answers
# {"path": null}. No network beyond the loopback TestClient transport.
import os
import sys
import types

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from agent_si import sidecar
from fastapi.testclient import TestClient

ACTOR = "fxfolder-tester"
PICK_PATH = "/api/v1/sidecar/pick-folder"
PICK_CODE = "NATIVE_DIALOG_UNAVAILABLE"


@pytest.fixture()
def picked_app():
    app = sidecar.build_app()
    return app, TestClient(app)


def _auth(app, actor=ACTOR, token=None):
    headers = {}
    if actor is not None:
        headers["x-actor"] = actor
    value = app.state.ui_session_token if token is None else token
    if value is not None:
        headers["x-ui-session-token"] = value
    return headers


class _FakeWindow:
    """Stub native window recording the dialog kind it was asked for."""

    def __init__(self, answer):
        self.answer = answer
        self.seen = []

    def create_file_dialog(self, dialog_type):
        self.seen.append(dialog_type)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def _stub_webview(monkeypatch, answer):
    window = _FakeWindow(answer)
    stub = types.SimpleNamespace(
        FOLDER_DIALOG="fxfolder-dialog-kind",
        windows=[window],
    )
    monkeypatch.setitem(sys.modules, "webview", stub)
    return window, stub


def test_pick_folder_needs_actor(picked_app):
    app, client = picked_app
    assert client.post(PICK_PATH).status_code == 401
    assert client.post(
        PICK_PATH, headers={"x-ui-session-token": "whatever"}
    ).status_code == 401


def test_pick_folder_refuses_bad_token(picked_app):
    app, client = picked_app
    resp = client.post(PICK_PATH, headers=_auth(app, token="wrong-token"))
    assert resp.status_code == 403


def test_pick_folder_headless_answers_409_with_code(picked_app):
    app, client = picked_app
    resp = client.post(PICK_PATH, headers=_auth(app))
    assert resp.status_code == 409
    body = resp.json()
    assert isinstance(body.get("code"), str) and body["code"]
    assert body["code"] == PICK_CODE


def test_pick_folder_choice_answers_path(picked_app, monkeypatch):
    app, client = picked_app
    window, stub = _stub_webview(monkeypatch, ("/chosen/dir",))
    resp = client.post(PICK_PATH, headers=_auth(app))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"path": "/chosen/dir"}
    assert window.seen == [stub.FOLDER_DIALOG]


def test_pick_folder_cancel_answers_null_path(picked_app, monkeypatch):
    app, client = picked_app
    _stub_webview(monkeypatch, None)
    resp = client.post(PICK_PATH, headers=_auth(app))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"path": None}


def test_pick_folder_empty_answer_is_null_path(picked_app, monkeypatch):
    app, client = picked_app
    _stub_webview(monkeypatch, ())
    resp = client.post(PICK_PATH, headers=_auth(app))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"path": None}


def test_pick_folder_dialog_error_answers_409(picked_app, monkeypatch):
    app, client = picked_app
    _stub_webview(monkeypatch, RuntimeError("dialog closed"))
    resp = client.post(PICK_PATH, headers=_auth(app))
    assert resp.status_code == 409
    assert resp.json()["code"] == PICK_CODE
