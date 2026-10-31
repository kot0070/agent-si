"""K09-A served proofs, phase 2 (frozen FREEZE-K09BATCH-v1).

One served test per frozen CODER-A row, driven through the real seam
app (create_app + TestClient, raise_server_exceptions=False):

  row 144  -> GET  /kb/list     (kb_list)
  row 145  -> POST /kb/attach   (kb_attach)
  row 146a -> POST /kb/detach   (kb_detach)
  row 146c -> POST /kb/retrieve (kb_retrieve)
  row 209  -> GET  /kb/manifest (kb_manifest)

Loopback TEST data only. All fixtures/fakes live in this file. KB
state is attached via src.agent_si.kb.retriever (the same module object
the served routes call), never via agent_si.kb.*.
"""

import json
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

from src.agent_si.kb import retriever as kb

TEST_TOKEN = "k09a-served-proof-token"
TEST_SETTINGS = {"testing": True, "ui_session_token": TEST_TOKEN}
WRITE_HEADERS = {
    "x-actor": "coder-a2",
    "x-ui-session-token": TEST_TOKEN,
}

GOOD_SECTIONS = {"intro": "Intro notes.", "setup": "Setup notes."}


def _write_kb_dir(path, sections=None, purpose="Dev role notes."):
    path.mkdir(parents=True, exist_ok=True)
    (path / "sections").mkdir(exist_ok=True)
    for name, text in (sections or GOOD_SECTIONS).items():
        (path / "sections" / f"{name}.md").write_text(text, encoding="utf-8")
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "kb_id": path.name,
                "purpose": purpose,
                "sections": sorted(sections or GOOD_SECTIONS),
            }
        ),
        encoding="utf-8",
    )
    (path / "purpose.txt").write_text(purpose, encoding="utf-8")
    return str(path)


def _attach(kb_id, project, role="dev"):
    return kb.attach_kb(
        kb.KnowledgeSource(
            kb_id=kb_id,
            kind="DEV_ROLE",
            project_id=project,
            role=role,
            purpose="Dev role notes.",
        )
    )


@pytest.fixture
def client():
    from agent_si.backend.app import create_app

    app = create_app(dict(TEST_SETTINGS))
    return TestClient(app, raise_server_exceptions=False)


def test_row144_list_serves_attached_kb(client, tmp_path):
    """Row 144: GET /kb/list serves the attached KB (kb_list)."""
    project = "proj-k09a-served-list"
    kb_id = _write_kb_dir(tmp_path / "kb-list")
    try:
        assert _attach(kb_id, project) == kb_id
        resp = client.get(
            "/kb/list", params={"project_id": project, "role": "dev"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert kb_id in [s["kb_id"] for s in body]
    finally:
        kb.detach_kb(kb_id)


def test_row145_attach_serves_kb_id(client, tmp_path):
    """Row 145: POST /kb/attach serves the kb_id (kb_attach)."""
    project = "proj-k09a-served-attach"
    kb_id = _write_kb_dir(tmp_path / "kb-attach")
    try:
        resp = client.post(
            "/kb/attach",
            json={
                "source": {
                    "kb_id": kb_id,
                    "kind": "DEV_ROLE",
                    "project_id": project,
                    "role": "dev",
                    "purpose": "Dev role notes.",
                }
            },
            headers=WRITE_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json() == kb_id
    finally:
        kb.detach_kb(kb_id)


def test_row146a_detach_serves_null_and_removes(client, tmp_path):
    """Row 146a: POST /kb/detach serves null and removes it (kb_detach)."""
    project = "proj-k09a-served-detach"
    kb_id = _write_kb_dir(tmp_path / "kb-detach")
    assert _attach(kb_id, project) == kb_id
    resp = client.post(
        "/kb/detach", json={"kb_id": kb_id}, headers=WRITE_HEADERS
    )
    assert resp.status_code == 200
    assert resp.json() is None
    listed = client.get(
        "/kb/list", params={"project_id": project, "role": "dev"}
    )
    assert listed.status_code == 200
    assert kb_id not in [s["kb_id"] for s in listed.json()]


def test_row146c_retrieve_serves_chunks_and_cost(client, tmp_path):
    """Row 146c: POST /kb/retrieve serves chunks + cost (kb_retrieve)."""
    project = "proj-k09a-served-retrieve"
    kb_id = _write_kb_dir(tmp_path / "kb-retrieve")
    try:
        assert _attach(kb_id, project) == kb_id
        resp = client.post(
            "/kb/retrieve",
            json={
                "query": "intro notes",
                "project_id": project,
                "role": "dev",
            },
            headers=WRITE_HEADERS,
        )
        assert resp.status_code == 200
        chunks, section_log = resp.json()
        assert len(chunks) >= 1
        assert all(
            c["instruction_status"] == "DATA_ONLY" and c["citation"]
            for c in chunks
        )
        assert section_log["touches"]
        assert section_log["token_cost"] > 0
    finally:
        kb.detach_kb(kb_id)


def test_row209_manifest_serves_section_names(client, tmp_path):
    """Row 209: GET /kb/manifest serves section names (kb_manifest)."""
    project = "proj-k09a-served-manifest"
    kb_id = _write_kb_dir(tmp_path / "kb-manifest")
    try:
        assert _attach(kb_id, project) == kb_id
        resp = client.get(
            "/kb/manifest", params={"kb_id": kb_id, "query": "intro"}
        )
        assert resp.status_code == 200
        assert "intro" in resp.json()
    finally:
        kb.detach_kb(kb_id)
