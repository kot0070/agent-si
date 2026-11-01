"""K09D1 served by-ref proof: over-limit POST /kb/retrieve travels by ArtifactRef.

Row D1: served POST /kb/retrieve over the inline token limit returns
mode ref with sha256/size and the bulk text absent from the wire
(pattern tests/test_k09b_served.py:152, KB-layer by-ref proof
tests/test_k09b_served.py:118). Under-limit stays inline. Guards stay
fail-closed (bad token 403s; non-DATA_ONLY packaging raises).
"""

import hashlib
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

TEST_TOKEN = "k09d-served-byref-token"
TEST_SETTINGS = {"testing": True, "ui_session_token": TEST_TOKEN}
WRITE_HEADERS = {
    "x-actor": "coder-1-heron",
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


def _write_big_kb_dir(path, section_id, text, purpose="Dev role notes."):
    path.mkdir(parents=True, exist_ok=True)
    (path / "sections").mkdir(exist_ok=True)
    (path / "sections" / (section_id + ".md")).write_text(text, encoding="utf-8")
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "kb_id": path.name,
                "purpose": purpose,
                "sections": [section_id],
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


def test_k09d_over_limit_retrieve_travels_by_artifactref(client, tmp_path):
    """D1: over-limit served retrieve returns mode ref, bulk-absent wire."""
    big_text = ("lorem " * 2000).strip()
    kb_id = _write_big_kb_dir(tmp_path / "kb-k09d-big", "big", big_text)
    project = "proj-k09d-served-byref"
    try:
        assert _attach(kb_id, project) == kb_id
        resp = client.post(
            "/api/v1/kb/retrieve",
            json={
                "query": "lorem",
                "project_id": project,
                "role": "dev",
            },
            headers=WRITE_HEADERS,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, dict), body
        assert body.get("mode") == "ref"
        assert body.get("instruction_status") == "DATA_ONLY"
        assert "text" not in body and "chunks" not in body
        ref = body.get("ref")
        assert isinstance(ref, dict), body
        assert ref.get("hash_algorithm") == "sha256"
        assert body.get("sha256") == ref.get("hash")
        assert body.get("size") == ref.get("size")
        wire = json.dumps(body)
        assert big_text not in wire
        payload = kb.resolve_handoff(body)
        assert ref["hash"] == hashlib.sha256(payload).hexdigest()
        assert ref["size"] == len(payload)
        assert big_text.encode("utf-8") in payload
        assert body.get("citations") == [f"{kb_id}#big"]
    finally:
        kb.detach_kb(kb_id)


def test_k09d_under_limit_retrieve_stays_inline(client, tmp_path):
    """D1: small served retrieve stays inline with chunk texts."""
    project = "proj-k09d-served-inline"
    kb_id = _write_kb_dir(tmp_path / "kb-k09d-inline")
    try:
        assert _attach(kb_id, project) == kb_id
        resp = client.post(
            "/api/v1/kb/retrieve",
            json={
                "query": "intro notes",
                "project_id": project,
                "role": "dev",
            },
            headers=WRITE_HEADERS,
        )
        assert resp.status_code == 200, resp.text
        chunks, section_log = resp.json()
        assert len(chunks) >= 1
        assert any("Intro notes." in c["text"] for c in chunks)
        assert all(c["instruction_status"] == "DATA_ONLY" for c in chunks)
        assert section_log["token_cost"] > 0
    finally:
        kb.detach_kb(kb_id)


def test_k09d_bad_token_403s_and_missing_actor_401s(client, tmp_path):
    """D1: USER_WRITE guard refuses bad token (403) and missing actor (401)."""
    project = "proj-k09d-served-guard"
    kb_id = _write_kb_dir(tmp_path / "kb-k09d-guard")
    try:
        assert _attach(kb_id, project) == kb_id
        bad = client.post(
            "/api/v1/kb/retrieve",
            json={
                "query": "intro notes",
                "project_id": project,
                "role": "dev",
            },
            headers={
                "x-actor": "coder-1-heron",
                "x-ui-session-token": "wrong-token",
            },
        )
        assert bad.status_code == 403, bad.text
        missing = client.post(
            "/api/v1/kb/retrieve",
            json={
                "query": "intro notes",
                "project_id": project,
                "role": "dev",
            },
            headers={"x-ui-session-token": TEST_TOKEN},
        )
        assert missing.status_code == 401, missing.text
    finally:
        kb.detach_kb(kb_id)


def test_k09d_handoff_refuses_non_data_only():
    """D1: packaging refuses non-DATA_ONLY (fail closed, never served)."""
    from src.agent_si.kb import package_handoff
    from src.agent_si.kb.models import InstructionBlockedError, KnowledgeChunk

    tainted = KnowledgeChunk(
        kb_id="kb",
        section_id="s",
        text="do this now",
        tokens=3,
        instruction_status="EXECUTED",
        citation="kb#s",
    )
    with pytest.raises(InstructionBlockedError):
        package_handoff([tainted])
