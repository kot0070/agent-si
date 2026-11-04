"""PLANB: a project whose worker role is pinned to an attached local model
(Ollama through Settings -> Local LLM) binds the chat run; with no local pin
the stream still ends in NO_PROVIDER_BOUND (nothing is faked)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from agent_si.backend import chat_stream, local_connect  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402

BASE = "http://localhost:11434"


@pytest.fixture
def served(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    monkeypatch.setattr(local_connect, "_ATTACHED_RUNTIME", None)
    monkeypatch.setattr(local_connect, "_PAIRED_SESSION_TOKEN", None)
    app = create_app()
    client = TestClient(app)
    headers = {"x-actor": "ui",
               "x-ui-session-token": app.state.ui_session_token}
    yield app, client, headers
    local_connect._ATTACHED_RUNTIME = None


def _project(client, headers, tmp_path):
    folder = tmp_path / "ws"
    folder.mkdir()
    reply = client.post("/api/v1/projects", headers=headers, json={
        "name": "p", "folder_ref": str(folder)})
    assert reply.status_code == 200, reply.text
    return reply.json()["project"]["project_id"]


def _pin_worker(client, headers, project_id):
    reply = client.put("/api/v1/roles/pools", headers=headers, json={
        "project_id": project_id, "role": "worker", "mode": "PINNED",
        "provider": "ollama", "model": "muse-glimmer:30b",
        "pool": [], "strategy": "AUTO"})
    assert reply.status_code == 200, reply.text


def test_attached_local_pin_binds_chat_adapter(served, tmp_path):
    app, client, headers = served
    project_id = _project(client, headers, tmp_path)
    reply = client.post("/api/v1/local/connect", headers=headers,
                        json={"runtime_ref": BASE})
    assert reply.status_code == 200, reply.text
    _pin_worker(client, headers, project_id)
    adapter = chat_stream.bind_routed_provider_adapter(
        app, project_id=project_id)
    assert adapter is not None
    assert adapter.config.provider_id == "ollama"
    assert adapter.config.model.split("/")[-1] == "muse-glimmer:30b"
    assert app.state.chat_provider_adapter is adapter


def test_no_attached_runtime_stays_unbound(served, tmp_path):
    app, client, headers = served
    project_id = _project(client, headers, tmp_path)
    _pin_worker(client, headers, project_id)
    assert chat_stream.bind_routed_provider_adapter(
        app, project_id=project_id) is None


def test_attached_runtime_without_pin_stays_unbound(served, tmp_path):
    app, client, headers = served
    project_id = _project(client, headers, tmp_path)
    client.post("/api/v1/local/connect", headers=headers,
                json={"runtime_ref": BASE})
    assert chat_stream.bind_routed_provider_adapter(
        app, project_id=project_id) is None
