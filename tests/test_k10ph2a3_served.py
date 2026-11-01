"""K10PH2A3 served map: one proving test per open row.

Row M-P4-166 (combine): GET /api/v1/release/combine combines best plus KB
plus benchmark plus Watcher on DEFAULT.
Row M-R-COMPET (audit): GET /api/v1/release/compet/audit returns the
flow-by-flow claims each with a recorded source plus snippet.
Row B0B-UNCOVERED_MVP_ACCEPT-200: the recorded
report-export seam carries dataset rows per demo and fixture.
Row B0B-UNCOVERED_MVP_ACCEPT-130: the recorded seam
checks README plus setup instructions alongside demos and fixtures.
Row B0B-UNCOVERED_MVP_ACCEPT-132: the recorded
acceptance map links each checklist item to its design section.
Each row is listed by agent_si.k10_compet.served_rows() and proven here
through its serving seam on the real create_app app with real
state (temp data dir, memory secret store). Loopback TEST data only; no
network, no installs. A sixth candidate row has no seam and is not proven here.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import fastapi.testclient  # noqa: E402

from agent_si import k10_compet  # noqa: E402
from agent_si.backend.app import (  # noqa: E402
    create_app,
)

TAG = "tests/test_k10ph2a3_served.py"


def _served():
    return {row["row"]: row for row in k10_compet.served_rows()}


def _client_on_temp_dir(tmp_path, monkeypatch, token):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(data_dir))
    app = create_app(
        {"ui_session_token": token, "secret_store": "memory", "testing": True}
    )
    return fastapi.testclient.TestClient(app), data_dir


def test_k10ph2a3_mp166_combine_served(tmp_path, monkeypatch):
    """Row M-P4-166 served through GET /api/v1/release/combine.

    Already proven by tests/test_k10st4_accept_compet.py::
    test_k10st4_combine_default_served; cited here and re-exercised
    live through the same seam.
    """
    entry = _served()["M-P4-166"]
    assert entry["route"] == "GET /api/v1/release/combine", entry
    assert entry["test"] == (
        "tests/test_k10st4_accept_compet.py::"
        "test_k10st4_combine_default_served"
    ), entry
    client, _data_dir = _client_on_temp_dir(tmp_path, monkeypatch, "ph2a3-mp166")
    resp = client.get("/api/v1/release/combine", params={"package_id": "TEST-PKG-PH2A3"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == "k10st4-accept", body
    assert body["package_id"] == "TEST-PKG-PH2A3", body
    assert body["mode"] == "default", body
    for key in ("best", "kb", "benchmark", "watcher"):
        assert key in body, body


def test_k10ph2a3_mrcompet_audit_served(tmp_path, monkeypatch):
    """Row M-R-COMPET served through GET /api/v1/release/compet/audit.

    Already proven by tests/test_k10st4_accept_compet.py::
    test_k10st4_compet_audit_served; cited here and re-exercised
    live through the same seam.
    """
    entry = _served()["M-R-COMPET"]
    assert entry["route"] == "GET /api/v1/release/compet/audit", entry
    assert entry["test"] == (
        "tests/test_k10st4_accept_compet.py::"
        "test_k10st4_compet_audit_served"
    ), entry
    client, _data_dir = _client_on_temp_dir(tmp_path, monkeypatch, "ph2a3-mrcompet")
    resp = client.get("/api/v1/release/compet/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == "k10st4-accept", body
    flows = body["flows"]
    assert isinstance(flows, list) and len(flows) >= 3, body
    for row in flows:
        for key in ("flow", "claim", "source", "snippet"):
            assert row.get(key), row


def test_k10ph2a3_bison_report_export_rows():
    """Row B0B-UNCOVERED_MVP_ACCEPT-200 served through the recorded seam.

    Already proven by tests/test_k10wave_served.py::
    test_k10wave3_bison_report_export_rows; cited here and re-exercised
    live through the same seam.
    """
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-200"]
    assert entry["route"] == (
        "agent_si.k10_compet.report_export_rows recorded seam"
    ), entry
    assert entry["test"] == (
        "tests/test_k10wave_served.py::"
        "test_k10wave3_bison_report_export_rows"
    ), entry
    rows = k10_compet.report_export_rows()
    assert [row["dataset"] for row in rows] == ["demo", "fixture"], rows
    assert {row["kind"] for row in rows} == {"demo", "fixture"}, rows
    for row in rows:
        for key in ("dataset", "kind", "claim", "source", "snippet",
                    "artifact", "version"):
            assert row.get(key), row
        assert "route " in row["artifact"] and "tests/" in row["artifact"], row
        assert "recorded" in row["source"], row


def test_k10ph2a3_bison_readme_setup_checks():
    """Row B0B-UNCOVERED_MVP_ACCEPT-130 served through the recorded seam.

    Already proven by tests/test_k10wave_served.py::
    test_k10wave3_bison_readme_setup_checks; cited here and re-exercised
    live through the same seam.
    """
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-130"]
    assert entry["route"] == (
        "agent_si.k10_compet.readme_setup_checks recorded seam"
    ), entry
    assert entry["test"] == (
        "tests/test_k10wave_served.py::"
        "test_k10wave3_bison_readme_setup_checks"
    ), entry
    rows = k10_compet.readme_setup_checks()
    assert [row["check"] for row in rows] == [
        "readme", "setup-instructions", "demos", "fixtures",
    ], rows
    for row in rows:
        for key in ("check", "claim", "source", "snippet", "evidence"):
            assert row.get(key), row
        assert "README plus setup instructions" in row["snippet"], row


def test_k10ph2a3_bison_acceptance_map():
    """Row B0B-UNCOVERED_MVP_ACCEPT-132 served through the recorded seam.

    Already proven by tests/test_k10wave_served.py::
    test_k10wave3_bison_acceptance_map; cited here and re-exercised
    live through the same seam.
    """
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-132"]
    assert entry["route"] == (
        "agent_si.k10_compet.acceptance_map recorded seam"
    ), entry
    assert entry["test"] == (
        "tests/test_k10wave_served.py::"
        "test_k10wave3_bison_acceptance_map"
    ), entry
    rows = k10_compet.acceptance_map()
    assert [row["item"] for row in rows] == [
        "readme", "setup-instructions", "demos", "fixtures",
        "combine-default", "competitive-audit",
    ], rows
    for row in rows:
        for key in ("item", "claim", "source", "snippet",
                    "design_section", "evidence"):
            assert row.get(key), row
        assert "kit BUILD_PLAN" in row["design_section"], row
