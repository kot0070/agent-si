# H6 RED: POST /api/v1/sidecar/open-folder opens a project folder
# natively. Guarded exactly like pick-folder (401 without x-actor, 403
# with a bad token); 404 when the path names no directory; 409 with a
# stable machine code when no native open runs; {"ok": true} when the
# opener runs. No network beyond the loopback TestClient transport.
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agent_si import sidecar
from fastapi.testclient import TestClient

ACTOR = "fxopenfolder-tester"
OPEN_PATH = "/api/v1/sidecar/open-folder"
OPEN_CODE = "NATIVE_OPEN_UNAVAILABLE"


def _app_client():
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


def test_open_folder_needs_actor():
    _app, client = _app_client()
    assert client.post(OPEN_PATH, json={"path": "x"}).status_code == 401


def test_open_folder_refuses_bad_token(tmp_path):
    app, client = _app_client()
    resp = client.post(
        OPEN_PATH, json={"path": str(tmp_path)},
        headers=_auth(app, token="wrong"),
    )
    assert resp.status_code == 403


def test_open_folder_missing_dir_is_404(tmp_path):
    app, client = _app_client()
    resp = client.post(
        OPEN_PATH, json={"path": str(tmp_path / "nope")},
        headers=_auth(app),
    )
    assert resp.status_code == 404


def test_open_folder_unavailable_is_409(tmp_path, monkeypatch):
    app, client = _app_client()

    def _boom(path):
        raise OSError("no native open")

    monkeypatch.setattr(sidecar, "_open_native_folder", _boom)
    resp = client.post(
        OPEN_PATH, json={"path": str(tmp_path)},
        headers=_auth(app),
    )
    assert resp.status_code == 409
    assert resp.json().get("code") == OPEN_CODE


def test_open_folder_opens(tmp_path, monkeypatch):
    app, client = _app_client()
    seen = []
    monkeypatch.setattr(
        sidecar, "_open_native_folder", lambda path: seen.append(path))
    resp = client.post(
        OPEN_PATH, json={"path": str(tmp_path)},
        headers=_auth(app),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "path": str(tmp_path)}
    assert seen == [str(tmp_path)]
