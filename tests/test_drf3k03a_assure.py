"""DRF3K03A rows 9-13 + R-304: fresh assurance + runner contract, served.

Drives POST /api/v1/assurance/fresh_assurance (new audit id per call,
per audit and per re-audit) and POST /api/v1/assurance/runner_contract
(judges the real files read and written) through the real seam app
(create_app) with TestClient over a real temp dir on the real fs.
Unique ids (drf3k03a-assure-*) keep the global audit store isolated
from every other test file. No network anywhere; no FakeAuditor: the
served path runs the real assurance backend modules.
"""

import os
import sys
import tempfile

from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import agent_si.backend.app as app_module
from agent_si.backend.app import create_app

TESTID = "drf3k03a-assure"
TEST_TOKEN = "drf3k03a-assure-token"


def _settings():
    return dict({"testing": True, "ui_session_token": TEST_TOKEN})


def _client():
    app = create_app(_settings())
    return app, TestClient(app)


def _turn_body(tag):
    return {
        "turn_ref": "turn-%s-%s" % (TESTID, tag),
        "project_id": "proj-%s" % TESTID,
        "task_id": "task-%s" % TESTID,
        "run_id": "run-%s-%s" % (TESTID, tag),
        "work_refs": ["work-%s-%s" % (TESTID, tag)],
        "artifact_refs": [],
        "evidence_refs": [],
        "producer_session_refs": [],
        "contract_hash": "contract-%s" % TESTID,
    }


def test_production_symbols_on_served_path():
    """fresh_assurance + runner_contract_verdict live on the backend mount."""
    assert callable(getattr(app_module, "fresh_assurance", None))
    assert callable(getattr(app_module, "runner_contract_verdict", None))


def test_served_fresh_assurance_mints_new_audit_id_per_call():
    """Two audits plus one re-audit mint three distinct audit ids."""
    _, client = _client()
    first = client.post(
        "/api/v1/assurance/fresh_assurance", json=_turn_body("one"))
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/v1/assurance/fresh_assurance", json=_turn_body("one"))
    assert second.status_code == 200, second.text
    id_one = first.json()["audit_id"]
    id_two = second.json()["audit_id"]
    assert id_one and id_two and id_one != id_two
    body = _turn_body("one")
    body["reaudit_of"] = id_one
    third = client.post("/api/v1/assurance/fresh_assurance", json=body)
    assert third.status_code == 200, third.text
    id_three = third.json()["audit_id"]
    assert id_three and id_three not in (id_one, id_two)


def test_served_fresh_assurance_refuses_empty_work():
    """Empty work fails on the fresh path too (row 7 holds)."""
    _, client = _client()
    body = _turn_body("empty")
    body["work_refs"] = []
    resp = client.post("/api/v1/assurance/fresh_assurance", json=body)
    assert resp.status_code == 400, resp.text


def _write_real_files(project_dir):
    with open(os.path.join(project_dir, "input.txt"),
              "w", encoding="utf-8") as handle:
        handle.write("real read input\n")
    with open(os.path.join(project_dir, "output.txt"),
              "w", encoding="utf-8") as handle:
        handle.write("real written output\n")


def _contract_body(project_dir, files_read, files_written):
    rows = ([{"tool": "runner", "evidence_ref": ref, "ok": True}
             for ref in list(files_read) + list(files_written)])
    return {
        "project_dir": project_dir,
        "tool_rows": rows,
        "files_read": list(files_read),
        "files_written": list(files_written),
    }


def test_served_runner_contract_judges_real_files():
    """PASS on real files read+written; FAIL when a written file is missing."""
    _, client = _client()
    project_dir = tempfile.mkdtemp(prefix="%s-" % TESTID)
    _write_real_files(project_dir)
    good = client.post(
        "/api/v1/assurance/runner_contract",
        json=_contract_body(
            project_dir, ["input.txt"], ["output.txt"]))
    assert good.status_code == 200, good.text
    assert good.json()["verdict"] == "PASS"
    bad = client.post(
        "/api/v1/assurance/runner_contract",
        json=_contract_body(
            project_dir, ["input.txt"], ["output-missing.txt"]))
    assert bad.status_code == 200, bad.text
    assert bad.json()["verdict"] == "FAIL"
    assert "output-missing.txt" in bad.json()["missing"]


def test_served_runner_contract_fails_closed():
    """Unknown dir and empty contract never PASS (no false PASS)."""
    _, client = _client()
    nosuch = os.path.join(
        tempfile.gettempdir(), "nosuch-%s-dir" % TESTID)
    resp = client.post(
        "/api/v1/assurance/runner_contract",
        json=_contract_body(nosuch, ["input.txt"], ["output.txt"]))
    assert resp.status_code == 200, resp.text
    assert resp.json()["verdict"] == "FAIL"
    project_dir = tempfile.mkdtemp(prefix="%s-empty-" % TESTID)
    _write_real_files(project_dir)
    empty = client.post(
        "/api/v1/assurance/runner_contract",
        json=_contract_body(project_dir, [], []))
    assert empty.status_code == 200, empty.text
    assert empty.json()["verdict"] == "FAIL"
