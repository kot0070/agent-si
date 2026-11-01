# CODER-1 Flint FXEXEUI served tests (H1/H2 lane gate, RED-first).
# Served = the sidecar build_app() endpoints over the real product app
# (agent_si.backend.app.create_app, untouched): web-tree index.html on /,
# built asset bytes, index.html on non-API extensionless paths (the UI
# router owns those), JSON 404 on unknown /api/*, the previous root JSON
# on /api/v1/sidecar/about, and clear 503 text on an empty tree. No
# network beyond the loopback TestClient transport.
import json
import os
import sys

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

INDEX_HTML = (
    "<!doctype html><html><head><title>Agent SI</title></head>"
    "<body>product-ui</body></html>"
)
ASSET_JS = "console.log('ui');"

ABOUT_JSON = {
    "service": "agent-si-sidecar",
    "version": "0.1.0",
    "status": "ok",
    "copyright": "Copyright (c) 2026 Ivan Soprun",
    "license": "MIT",
    "license_file": "LICENSE",
    "notices": "docs/third_party_notices/NOTICES.md",
}


@pytest.fixture()
def web_tree(tmp_path, monkeypatch):
    """Staged web tree served through the sidecar resolver hook."""
    monkeypatch.delenv("AGENT_SI_DATA_DIR", raising=False)
    tree = tmp_path / "web"
    (tree / "assets").mkdir(parents=True)
    (tree / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (tree / "assets" / "app.js").write_bytes(ASSET_JS.encode("utf-8"))
    monkeypatch.setattr(sidecar, "_resolve_web_dir", lambda: str(tree))
    return tree


@pytest.fixture()
def client(web_tree):
    return TestClient(sidecar.build_app())


def test_uvicorn_config_builds_with_none_streams(web_tree, monkeypatch):
    """H1 GREEN: Config builds while stdout/stderr are None."""
    app = sidecar.build_app()
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    config = sidecar._make_config(app, 1)
    assert config.host == sidecar.HOST
    assert config.log_config is None


def test_build_app_safe_with_none_streams(web_tree, monkeypatch):
    """H1 GREEN: build_app() itself tolerates None streams."""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    app = sidecar.build_app()
    assert getattr(app.state, "ui_session_token", "") != ""


def test_root_serves_index_html(client):
    """H2 GREEN: GET / answers the web-tree index.html."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert resp.text == INDEX_HTML


def test_projects_route_serves_index_html(client):
    """H2 GREEN: UI router paths answer index.html (browser fallback)."""
    for path in ("/projects", "/projects/p-1/overview"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert "text/html" in resp.headers["content-type"], path
        assert resp.text == INDEX_HTML, path


def test_built_asset_bytes(client):
    """H2 GREEN: built assets are served byte-for-byte."""
    resp = client.get("/assets/app.js")
    assert resp.status_code == 200
    assert resp.content == ASSET_JS.encode("utf-8")


def test_unknown_api_stays_json_404(client):
    """Unknown /api/* stays a JSON 404 (never the web tree)."""
    resp = client.get("/api/v1/no-such-route")
    assert resp.status_code == 404
    assert "application/json" in resp.headers["content-type"]
    assert resp.json()["detail"] == "Not Found"


def test_about_serves_old_json(client):
    """The previous root JSON moved to /api/v1/sidecar/about verbatim."""
    resp = client.get("/api/v1/sidecar/about")
    assert resp.status_code == 200
    assert resp.json() == ABOUT_JSON


def test_empty_tree_answers_503_text(tmp_path, monkeypatch):
    """Empty tree: clear 503 text on / and UI paths, never the JSON."""
    monkeypatch.delenv("AGENT_SI_DATA_DIR", raising=False)
    empty = tmp_path / "empty-web"
    empty.mkdir()
    monkeypatch.setattr(sidecar, "_resolve_web_dir", lambda: str(empty))
    app_client = TestClient(sidecar.build_app())
    for path in ("/", "/projects"):
        resp = app_client.get(path)
        assert resp.status_code == 503, path
        assert "application/json" not in resp.headers["content-type"], path
        assert "index.html" in resp.text, path
        with pytest.raises(json.JSONDecodeError):
            json.loads(resp.text)
