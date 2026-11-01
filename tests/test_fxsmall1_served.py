"""FXSMALL1: GET /api/v1/kb/list needs project_id (400 without, 200 with).

Drives the real seam app (create_app + TestClient,
raise_server_exceptions=False). Unique project ids (proj-fxsmall1-*)
keep the global KB registry isolated from every other test file.
Fixtures (KB dirs) live in this file only.

  test_list_without_project_id_is_400: GET /api/v1/kb/list answers 400
    with a KB_* code when project_id is missing.
  test_list_with_empty_project_id_is_400: same 400 for an empty value.
  test_list_with_project_id_is_200: GET with project_id answers 200 and
    serves the attached KB.
  test_retrieve_without_project_id_is_400: the same guard on the other
    project_id route (POST /api/v1/kb/retrieve).
"""

import json
import os
import sys

from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from src.agent_si.kb import retriever as kb

EXPECTED_CODE = "KB_MISSING_PROJECT_ID"

TEST_TOKEN = "fxsmall1-kbpeak-token"
TEST_SETTINGS = {"testing": True, "ui_session_token": TEST_TOKEN}
WRITE_HEADERS = {
    "x-actor": "coder-1-kbpeak",
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


def _client():
    from agent_si.backend.app import create_app

    app = create_app(dict(TEST_SETTINGS))
    return TestClient(app, raise_server_exceptions=False)


def test_list_without_project_id_is_400():
    """GET /api/v1/kb/list without project_id answers 400 with a code."""
    resp = _client().get("/api/v1/kb/list")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == EXPECTED_CODE


def test_list_with_empty_project_id_is_400():
    """GET /api/v1/kb/list with an empty project_id answers 400."""
    resp = _client().get("/api/v1/kb/list", params={"project_id": ""})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == EXPECTED_CODE


def test_list_with_project_id_is_200(tmp_path):
    """GET /api/v1/kb/list with project_id answers 200 with the KB."""
    project = "proj-fxsmall1-list"
    kb_id = _write_kb_dir(tmp_path / "kb-fxsmall1-list")
    try:
        assert _attach(kb_id, project) == kb_id
        resp = _client().get(
            "/api/v1/kb/list", params={"project_id": project, "role": "dev"}
        )
        assert resp.status_code == 200
        assert kb_id in [s["kb_id"] for s in resp.json()]
    finally:
        kb.detach_kb(kb_id)


def test_retrieve_without_project_id_is_400():
    """POST /api/v1/kb/retrieve without project_id answers 400."""
    resp = _client().post(
        "/api/v1/kb/retrieve",
        json={"query": "intro notes", "role": "dev"},
        headers=WRITE_HEADERS,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == EXPECTED_CODE
