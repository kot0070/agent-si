"""K09 LIVE0-06 stale KB copy refresh through the real route (TPL1-NEW).

Drives GET /api/v1/kb/refresh/proposal (open read) and POST
/api/v1/kb/refresh/apply (USER_WRITE) through the real seam app
(create_app) with TestClient over real tmp KB dirs on the real fs.
Unique project ids (proj-l06-*) keep the global KB registry isolated
from every other test file. No network anywhere: all sources are local
dirs, and the KB dir itself is never mutated by proposal or apply.
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

from src.agent_si.kb import retriever as _kb
from src.agent_si.kb.models import KnowledgeSource

TEST_TOKEN = "k09-refresh-live006-token"


def _settings():
    return dict({"testing": True, "ui_session_token": TEST_TOKEN})


@pytest.fixture
def app_client():
    from agent_si.backend.app import create_app
    app = create_app(_settings())
    return app, TestClient(app)


def _write_kb_dir(path, version="1.0.0", sections=None,
                   purpose="Capability notes."):
    """Real KB dir: manifest.json (+version) + purpose.txt + sections."""
    sections = dict(sections) if sections is not None else {
        "intro": "Intro notes.", "setup": "Setup notes."}
    path.mkdir(parents=True, exist_ok=True)
    (path / "sections").mkdir(exist_ok=True)
    for name, text in sections.items():
        (path / "sections" / ("%s.md" % name)).write_text(
            text, encoding="utf-8")
    manifest = {"kb_id": path.name, "purpose": purpose,
                "sections": sorted(sections)}
    if version is not None:
        manifest["version"] = version
    (path / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8")
    (path / "purpose.txt").write_text(purpose, encoding="utf-8")
    return str(path)


def _rewrite_manifest(path, version, sections):
    manifest = json.loads(
        (path / "manifest.json").read_text(encoding="utf-8"))
    manifest["version"] = version
    manifest["sections"] = sorted(sections)
    (path / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8")


def _attach(kb_id, project, role="dev"):
    return _kb.attach_kb(KnowledgeSource(
        kb_id=kb_id, kind="DEV_ROLE", project_id=project, role=role,
        purpose="Capability notes."))


def _write_headers(actor="dolphin-l06", token=TEST_TOKEN):
    headers = {"x-actor": actor}
    if token is not None:
        headers["x-ui-session-token"] = token
    return headers


def _dir_bytes(path):
    digest = hashlib.sha256()
    for child in sorted(path.rglob("*")):
        if child.is_file():
            digest.update(child.relative_to(path).as_posix().encode())
            digest.update(child.read_bytes())
    return digest.hexdigest()


def _proposal(client, kb_id):
    return client.get(
        "/api/v1/kb/refresh/proposal", params={"kb_id": kb_id})


def _apply(client, kb_id, **kwargs):
    return client.post(
        "/api/v1/kb/refresh/apply", json={"kb_id": kb_id}, **kwargs)


def test_proposal_records_then_detects_stale_after_version_bump(
        tmp_path, app_client):
    app, client = app_client
    kb_dir = tmp_path / "kb-l06-stale"
    kb_id = _write_kb_dir(kb_dir, version="1.0.0")
    _attach(kb_id, "proj-l06-stale")
    first = _proposal(client, kb_id)
    assert first.status_code == 200
    assert first.json() == {
        "kb_id": kb_id, "stale": False,
        "recorded_version": "1.0.0", "source_version": "1.0.0",
        "diff": {"added": [], "removed": [], "changed": [],
                 "version_from": "1.0.0", "version_to": "1.0.0"}}
    (kb_dir / "sections" / "models.md").write_text(
        "New model notes.", encoding="utf-8")
    _rewrite_manifest(kb_dir, "1.1.0",
                      {"intro": "Intro notes.", "setup": "Setup notes.",
                       "models": "New model notes."})
    second = _proposal(client, kb_id)
    assert second.status_code == 200
    stale = second.json()
    assert stale["stale"] is True
    assert stale["recorded_version"] == "1.0.0"
    assert stale["source_version"] == "1.1.0"
    assert stale["diff"]["added"] == ["models"]
    assert stale["diff"]["removed"] == []
    assert stale["diff"]["changed"] == []
    assert stale["diff"]["version_from"] == "1.0.0"
    assert stale["diff"]["version_to"] == "1.1.0"


def test_proposal_diff_lists_changed_and_removed(tmp_path, app_client):
    _, client = app_client
    kb_dir = tmp_path / "kb-l06-diff"
    kb_id = _write_kb_dir(kb_dir, version="2.0.0", sections={
        "a": "Alpha.", "b": "Beta.", "c": "Gamma."})
    _attach(kb_id, "proj-l06-diff")
    assert _proposal(client, kb_id).json()["stale"] is False
    (kb_dir / "sections" / "b.md").write_text(
        "Beta revised.", encoding="utf-8")
    (kb_dir / "sections" / "c.md").unlink()
    _rewrite_manifest(kb_dir, "2.0.0", {"a": "Alpha.",
                                        "b": "Beta revised."})
    resp = _proposal(client, kb_id)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stale"] is True
    assert body["recorded_version"] == "2.0.0"
    assert body["source_version"] == "2.0.0"
    assert body["diff"]["added"] == []
    assert body["diff"]["removed"] == ["c"]
    assert body["diff"]["changed"] == ["b"]


def test_apply_refusals_leave_implementation_untouched(tmp_path, app_client):
    app, client = app_client
    kb_dir = tmp_path / "kb-l06-refuse"
    kb_id = _write_kb_dir(kb_dir, version="1.0.0")
    _attach(kb_id, "proj-l06-refuse")
    assert _proposal(client, kb_id).json()["stale"] is False
    (kb_dir / "sections" / "models.md").write_text(
        "New model notes.", encoding="utf-8")
    _rewrite_manifest(kb_dir, "1.1.0",
                      {"intro": "Intro notes.", "setup": "Setup notes.",
                       "models": "New model notes."})
    before = _proposal(client, kb_id).json()
    assert before["stale"] is True
    assert _apply(client, kb_id).status_code == 401
    refused = _apply(client, kb_id, headers=_write_headers(token="wrong"))
    assert refused.status_code == 403
    assert app.state.kb_refresh_recorded[kb_id]["recorded_version"] == "1.0.0"
    no_token = _apply(
        client, kb_id, headers=_write_headers(token=None))
    assert no_token.status_code == 403
    assert _proposal(client, kb_id).json() == before
    assert app.state.kb_refresh_changelog == []


def test_apply_refreshes_records_version_and_changelog(tmp_path, app_client):
    app, client = app_client
    kb_dir = tmp_path / "kb-l06-apply"
    kb_id = _write_kb_dir(kb_dir, version="1.0.0")
    _attach(kb_id, "proj-l06-apply")
    assert _proposal(client, kb_id).json()["stale"] is False
    (kb_dir / "sections" / "models.md").write_text(
        "New model notes.", encoding="utf-8")
    _rewrite_manifest(kb_dir, "1.1.0",
                      {"intro": "Intro notes.", "setup": "Setup notes.",
                       "models": "New model notes."})
    assert _proposal(client, kb_id).json()["stale"] is True
    frozen = _dir_bytes(kb_dir)
    resp = _apply(client, kb_id, headers=_write_headers(actor="owner-l06"))
    assert resp.status_code == 200
    row = resp.json()
    assert row["applied"] is True
    assert row["kb_id"] == kb_id
    assert row["from"] == "1.0.0"
    assert row["to"] == "1.1.0"
    assert row["actor"] == "owner-l06"
    assert isinstance(row["at"], str) and row["at"]
    assert row["recorded_version"] == "1.1.0"
    assert row["source_version"] == "1.1.0"
    assert _dir_bytes(kb_dir) == frozen
    settled = _proposal(client, kb_id).json()
    assert settled["stale"] is False
    assert settled["recorded_version"] == "1.1.0"
    assert settled["source_version"] == "1.1.0"
    assert len(app.state.kb_refresh_changelog) == 1
    assert app.state.kb_refresh_changelog[0] == {
        key: row[key]
        for key in ("kb_id", "from", "to", "at", "actor")}


def test_apply_non_stale_is_noop(tmp_path, app_client):
    app, client = app_client
    kb_dir = tmp_path / "kb-l06-noop"
    kb_id = _write_kb_dir(kb_dir, version="3.0.0")
    _attach(kb_id, "proj-l06-noop")
    assert _proposal(client, kb_id).json()["stale"] is False
    first = _apply(client, kb_id, headers=_write_headers())
    assert first.status_code == 200
    assert first.json()["applied"] is False
    assert app.state.kb_refresh_changelog == []
    (kb_dir / "sections" / "models.md").write_text(
        "New model notes.", encoding="utf-8")
    _rewrite_manifest(kb_dir, "3.1.0",
                      {"intro": "Intro notes.", "setup": "Setup notes.",
                       "models": "New model notes."})
    applied = _apply(client, kb_id, headers=_write_headers())
    assert applied.json()["applied"] is True
    repeat = _apply(client, kb_id, headers=_write_headers())
    assert repeat.status_code == 200
    body = repeat.json()
    assert body["applied"] is False
    assert body["recorded_version"] == "3.1.0"
    assert body["source_version"] == "3.1.0"
    assert len(app.state.kb_refresh_changelog) == 1


@pytest.mark.parametrize("version", [None, 7], ids=["missing", "non-string"])
def test_unknown_version_never_counts_as_current_evidence(
        tmp_path, app_client, version):
    app, client = app_client
    kb_dir = tmp_path / ("kb-l06-unknown-%s" % (version,))
    kb_id = _write_kb_dir(kb_dir, version=version)
    _attach(kb_id, "proj-l06-unknown-%s" % (version,))
    resp = _proposal(client, kb_id)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stale"] is True
    assert body["source_version"] == "UNKNOWN"
    assert body["recorded_version"] == "UNKNOWN"
    refused = _apply(client, kb_id, headers=_write_headers())
    assert refused.status_code == 409
    assert app.state.kb_refresh_changelog == []
    assert _proposal(client, kb_id).json()["stale"] is True


def test_token_in_url_never_authorizes(tmp_path, app_client):
    app, client = app_client
    kb_dir = tmp_path / "kb-l06-urltoken"
    kb_id = _write_kb_dir(kb_dir, version="1.0.0")
    _attach(kb_id, "proj-l06-urltoken")
    assert _proposal(client, kb_id).json()["stale"] is False
    _rewrite_manifest(kb_dir, "1.1.0",
                      {"intro": "Intro notes.", "setup": "Setup notes."})
    assert _proposal(client, kb_id).json()["stale"] is True
    resp = client.post(
        "/api/v1/kb/refresh/apply",
        params={"x-ui-session-token": TEST_TOKEN, "kb_id": kb_id},
        json={"kb_id": kb_id},
        headers={"x-actor": "owner-l06"})
    assert resp.status_code == 403
    assert app.state.kb_refresh_changelog == []
    assert _proposal(client, kb_id).json()["stale"] is True


def test_records_are_per_app(tmp_path, app_client):
    from agent_si.backend.app import create_app
    _, client = app_client
    kb_dir = tmp_path / "kb-l06-perapp"
    kb_id = _write_kb_dir(kb_dir, version="1.0.0")
    _attach(kb_id, "proj-l06-perapp")
    assert _proposal(client, kb_id).json()["stale"] is False
    _rewrite_manifest(kb_dir, "1.1.0",
                      {"intro": "Intro notes.", "setup": "Setup notes."})
    assert _proposal(client, kb_id).json()["stale"] is True
    other = TestClient(create_app(_settings()))
    fresh = _proposal(other, kb_id).json()
    assert fresh["stale"] is False
    assert fresh["recorded_version"] == "1.1.0"
    assert fresh["source_version"] == "1.1.0"


def test_proposal_and_apply_unknown_kb_404(tmp_path, app_client):
    _, client = app_client
    missing = str(tmp_path / "kb-l06-missing")
    assert _proposal(client, missing).status_code == 404
    resp = _apply(client, missing, headers=_write_headers())
    assert resp.status_code == 404

