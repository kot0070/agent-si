"""FXR2E-KB: staged proposal apply is one-shot and idempotent (RED-first).

First approved POST applies (200 applied true). A repeated POST of the
same proposal id answers 200 applied false "already applied" — never
an error, never the fallback code. A never-staged id 404s with an
explicit code, never the fallback code.
"""
import os
import sys

from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agent_si.backend import modelkb as _modelkb  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.model_kb import kb as _kb  # noqa: E402

TOKEN = "fxr2e-kbapply-token"
HEADERS = {"x-actor": "fxr2e-kb", "x-ui-session-token": TOKEN}


def _client(tmp_path):
    app = create_app({"store_dir": str(tmp_path / "appdata"),
                      "testing": True, "ui_session_token": TOKEN})
    return TestClient(app, raise_server_exceptions=False)


def test_double_apply_is_idempotent(tmp_path):
    """Same staged id twice: applied true, then applied false + reason."""
    import copy as _copy
    import json as _json

    from agent_si.model_kb import kb as _kb

    saved = _copy.deepcopy(_kb.bound_catalog())
    client = _client(tmp_path)
    fetched = _json.dumps({"models": [
        {"provider_id": "openai", "model_id": "gpt-4o",
         "fields": {"purpose": "serves chat"}}]})
    proposal = _modelkb.trigger_update(
        _kb.bound_catalog(), "https://platform.openai.com/docs/w01",
        lambda _url: fetched, "2026-10-26T00:00:00Z")
    assert proposal["changes"], proposal
    staged = _modelkb.stage_proposal(proposal)
    try:
        first = client.post(
            "/api/v1/kb/proposals/apply",
            json={"proposal_id": staged, "approved_by_user": True},
            headers=HEADERS)
        assert first.status_code == 200, first.text
        assert first.json()["applied"] is True, first.text
        second = client.post(
            "/api/v1/kb/proposals/apply",
            json={"proposal_id": staged, "approved_by_user": True},
            headers=HEADERS)
        assert second.status_code == 200, second.text
        body = second.json()
        assert body["applied"] is False, body
        assert body["reason"] == "already applied", body
    finally:
        _kb.bind_catalog(saved)


def test_unknown_proposal_id_carries_code(tmp_path):
    """Never-staged id: 404 with an explicit code, not the fallback."""
    client = _client(tmp_path)
    resp = client.post(
        "/api/v1/kb/proposals/apply",
        json={"proposal_id": "kb-prop-nope-fxr2e",
              "approved_by_user": True},
        headers=HEADERS)
    assert resp.status_code == 404, resp.text
    assert resp.json().get("code") not in (
        None, "CONTEXT_WRONG_CONTRACT_VERSION"), resp.text
