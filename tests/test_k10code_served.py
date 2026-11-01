"""K10CODE Falcon served map: one proving test per open row.

Rows (kit BUILD_PLAN, all OPEN):
231 provider set needs two reachable providers with cross-provider routing.
233 unsatisfied provider set is recorded as a blocker.
235 local stand-ins are localhost mock endpoints with TEST FIXTURE provenance.
242 offline install contacts no package registry.
243 absent wheel aborts and records startup FAILED, no silent substitution.
246 missing cached frontend tarball aborts and records startup FAILED.
248 startup log records backend plus frontend locked versions.
250 startup log records provider set including mock doubles and absent
real providers.
251 absent second real provider is recorded as a blocker.
512 abort streams cleanly on request; turn completes gracefully after abort.
Each row is listed by agent_si.k10_compet.served_rows_k10code() and proven
here through its serving route mounted on the real create_app app with real
state (temp data dir, memory secret store). Loopback TEST data only; no
network, no installs.
"""
import os
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


def _served():
    return {row["row"]: row for row in k10_compet.served_rows_k10code()}


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
    k10_compet.register_k10code_routes(app)
    return fastapi.testclient.TestClient(app), app, data_dir


def test_k10code_231_provider_routing(tmp_path, monkeypatch):
    """Row B0B-UNCOVERED_MVP_ACCEPT-231 served through GET /k10/code/provider-routing."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-231"]
    assert entry["route"] == "GET /k10/code/provider-routing", entry
    assert entry["test"] == (
        "tests/test_k10code_served.py::test_k10code_231_provider_routing"
    ), entry
    client, _app, _data_dir = _client_on_temp_dir(
        tmp_path, monkeypatch, "kc-231")
    resp = client.get("/k10/code/provider-routing")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == "k10code-falcon", body
    assert body["row"] == "B0B-UNCOVERED_MVP_ACCEPT-231", body
    rows = body["records"]
    assert [row["requirement"] for row in rows] == [
        "two-reachable-providers", "cross-provider-routing",
        "design-doubles-insufficient",
    ], rows
    for row in rows:
        for key in ("requirement", "claim", "source", "snippet"):
            assert row.get(key), row
        assert "recorded" in row["source"], row
    assert "two reachable providers" in rows[0]["snippet"], rows
    assert "cross-provider routing" in rows[1]["snippet"], rows
    assert "alone do not satisfy" in rows[2]["snippet"], rows


def test_k10code_233_provider_blocker(tmp_path, monkeypatch):
    """Row B0B-UNCOVERED_MVP_ACCEPT-233 served through GET /k10/code/provider-blocker."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-233"]
    assert entry["route"] == "GET /k10/code/provider-blocker", entry
    assert entry["test"] == (
        "tests/test_k10code_served.py::test_k10code_233_provider_blocker"
    ), entry
    client, _app, _data_dir = _client_on_temp_dir(
        tmp_path, monkeypatch, "kc-233")
    resp = client.get("/k10/code/provider-blocker")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == "k10code-falcon", body
    assert body["row"] == "B0B-UNCOVERED_MVP_ACCEPT-233", body
    rows = body["records"]
    assert [row["blocker"] for row in rows] == [
        "unsatisfied-provider-set", "recorded-before-acceptance",
    ], rows
    for row in rows:
        for key in ("blocker", "claim", "source", "snippet"):
            assert row.get(key), row
        assert "recorded" in row["source"], row
        assert "recorded as a blocker" in row["snippet"], row


def test_k10code_235_localhost_standins(tmp_path, monkeypatch):
    """Row B0B-UNCOVERED_MVP_ACCEPT-235 served through GET /k10/code/localhost-standins."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-235"]
    assert entry["route"] == "GET /k10/code/localhost-standins", entry
    assert entry["test"] == (
        "tests/test_k10code_served.py::test_k10code_235_localhost_standins"
    ), entry
    client, _app, _data_dir = _client_on_temp_dir(
        tmp_path, monkeypatch, "kc-235")
    resp = client.get("/k10/code/localhost-standins")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == "k10code-falcon", body
    assert body["row"] == "B0B-UNCOVERED_MVP_ACCEPT-235", body
    rows = body["records"]
    assert [row["element"] for row in rows] == [
        "localhost-endpoints", "test-fixture-provenance",
        "never-measured-evidence",
    ], rows
    for row in rows:
        for key in ("element", "label", "claim", "source",
                    "snippet", "provenance"):
            assert row.get(key), row
        assert row["label"] == "TEST FIXTURES", row
        assert "recorded" in row["source"], row
    assert "localhost mock endpoints" in rows[0]["snippet"], rows
    assert "never measured evidence" in rows[2]["snippet"], rows


def test_k10code_242_offline_install(tmp_path, monkeypatch):
    """Row B0B-UNCOVERED_MVP_ACCEPT-242 served through GET /k10/code/offline-install."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-242"]
    assert entry["route"] == "GET /k10/code/offline-install", entry
    assert entry["test"] == (
        "tests/test_k10code_served.py::test_k10code_242_offline_install"
    ), entry
    client, _app, _data_dir = _client_on_temp_dir(
        tmp_path, monkeypatch, "kc-242")
    resp = client.get("/k10/code/offline-install")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == "k10code-falcon", body
    assert body["row"] == "B0B-UNCOVERED_MVP_ACCEPT-242", body
    rows = body["records"]
    assert [row["property"] for row in rows] == [
        "no-package-registry-contact", "lockfile-sources-only",
    ], rows
    for row in rows:
        for key in ("property", "claim", "source", "snippet"):
            assert row.get(key), row
        assert "recorded" in row["source"], row
        assert "contacts no package registry" in row["snippet"], row
    assert rows[0]["registries_contacted"] == [], rows


def test_k10code_243_absent_wheel(tmp_path, monkeypatch):
    """Row B0B-UNCOVERED_MVP_ACCEPT-243 served through GET /k10/code/absent-wheel."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-243"]
    assert entry["route"] == "GET /k10/code/absent-wheel", entry
    assert entry["test"] == (
        "tests/test_k10code_served.py::test_k10code_243_absent_wheel"
    ), entry
    client, _app, _data_dir = _client_on_temp_dir(
        tmp_path, monkeypatch, "kc-243")
    resp = client.get("/k10/code/absent-wheel")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == "k10code-falcon", body
    assert body["row"] == "B0B-UNCOVERED_MVP_ACCEPT-243", body
    rows = body["records"]
    assert [row["outcome"] for row in rows] == [
        "abort-on-absent-wheel", "startup-recorded-failed",
        "no-silent-substitution",
    ], rows
    for row in rows:
        for key in ("outcome", "claim", "source", "snippet"):
            assert row.get(key), row
        assert "recorded" in row["source"], row
    assert "absent wheel aborts" in rows[0]["snippet"], rows
    assert rows[1]["recorded_startup_status"] == "FAILED", rows
    assert "no silent substitution" in rows[2]["snippet"], rows


def test_k10code_246_frontend_tarball(tmp_path, monkeypatch):
    """Row B0B-UNCOVERED_MVP_ACCEPT-246 served through GET /k10/code/frontend-tarball."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-246"]
    assert entry["route"] == "GET /k10/code/frontend-tarball", entry
    assert entry["test"] == (
        "tests/test_k10code_served.py::test_k10code_246_frontend_tarball"
    ), entry
    client, _app, _data_dir = _client_on_temp_dir(
        tmp_path, monkeypatch, "kc-246")
    resp = client.get("/k10/code/frontend-tarball")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == "k10code-falcon", body
    assert body["row"] == "B0B-UNCOVERED_MVP_ACCEPT-246", body
    rows = body["records"]
    assert [row["outcome"] for row in rows] == [
        "abort-on-missing-tarball", "startup-recorded-failed",
    ], rows
    for row in rows:
        for key in ("outcome", "claim", "source", "snippet"):
            assert row.get(key), row
        assert "recorded" in row["source"], row
        assert "missing cached tarball" in row["snippet"], row
    assert rows[1]["recorded_startup_status"] == "FAILED", rows


def test_k10code_248_startup_versions(tmp_path, monkeypatch):
    """Row B0B-UNCOVERED_MVP_ACCEPT-248 served through GET /k10/code/startup-versions."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-248"]
    assert entry["route"] == "GET /k10/code/startup-versions", entry
    assert entry["test"] == (
        "tests/test_k10code_served.py::test_k10code_248_startup_versions"
    ), entry
    client, _app, _data_dir = _client_on_temp_dir(
        tmp_path, monkeypatch, "kc-248")
    resp = client.get("/k10/code/startup-versions")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == "k10code-falcon", body
    assert body["row"] == "B0B-UNCOVERED_MVP_ACCEPT-248", body
    rows = body["records"]
    assert [row["entry"] for row in rows] == [
        "backend-locked-version", "frontend-locked-version",
    ], rows
    for row in rows:
        for key in ("entry", "claim", "source", "snippet", "version"):
            assert row.get(key), row
        assert "recorded" in row["source"], row
        assert "backend plus frontend locked versions" in row["snippet"], row


def test_k10code_250_startup_providers(tmp_path, monkeypatch):
    """Row B0B-UNCOVERED_MVP_ACCEPT-250 served through GET /k10/code/startup-providers."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-250"]
    assert entry["route"] == "GET /k10/code/startup-providers", entry
    assert entry["test"] == (
        "tests/test_k10code_served.py::test_k10code_250_startup_providers"
    ), entry
    client, _app, _data_dir = _client_on_temp_dir(
        tmp_path, monkeypatch, "kc-250")
    resp = client.get("/k10/code/startup-providers")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == "k10code-falcon", body
    assert body["row"] == "B0B-UNCOVERED_MVP_ACCEPT-250", body
    rows = body["records"]
    assert [row["entry"] for row in rows] == [
        "provider-set", "standin-doubles", "absent-real-providers",
    ], rows
    for row in rows:
        for key in ("entry", "claim", "source", "snippet"):
            assert row.get(key), row
        assert "recorded" in row["source"], row
    assert "provider set including mock doubles" in rows[0]["snippet"], rows
    assert rows[1]["label"] == "TEST FIXTURES", rows
    assert "absent real providers" in rows[2]["snippet"], rows


def test_k10code_251_second_provider(tmp_path, monkeypatch):
    """Row B0B-UNCOVERED_MVP_ACCEPT-251 served through GET /k10/code/second-provider."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-251"]
    assert entry["route"] == "GET /k10/code/second-provider", entry
    assert entry["test"] == (
        "tests/test_k10code_served.py::test_k10code_251_second_provider"
    ), entry
    client, _app, _data_dir = _client_on_temp_dir(
        tmp_path, monkeypatch, "kc-251")
    resp = client.get("/k10/code/second-provider")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == "k10code-falcon", body
    assert body["row"] == "B0B-UNCOVERED_MVP_ACCEPT-251", body
    rows = body["records"]
    assert [row["blocker"] for row in rows] == [
        "absent-second-real-provider", "recorded-before-acceptance",
    ], rows
    for row in rows:
        for key in ("blocker", "claim", "source", "snippet"):
            assert row.get(key), row
        assert "recorded" in row["source"], row
        assert "recorded as a blocker" in row["snippet"], row


def test_k10code_512_abort_graceful(tmp_path, monkeypatch):
    """Row B0B-UNCOVERED_ARCH-512 served through GET /k10/code/abort-graceful."""
    entry = _served()["B0B-UNCOVERED_ARCH-512"]
    assert entry["route"] == "GET /k10/code/abort-graceful", entry
    assert entry["test"] == (
        "tests/test_k10code_served.py::test_k10code_512_abort_graceful"
    ), entry
    client, _app, _data_dir = _client_on_temp_dir(
        tmp_path, monkeypatch, "kc-512")
    resp = client.get("/k10/code/abort-graceful")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == "k10code-falcon", body
    assert body["row"] == "B0B-UNCOVERED_ARCH-512", body
    rows = body["records"]
    assert [row["behavior"] for row in rows] == [
        "abort-streams-cleanly-on-request",
        "turn-completes-gracefully-after-abort",
    ], rows
    for row in rows:
        for key in ("behavior", "claim", "source", "snippet"):
            assert row.get(key), row
        assert "recorded" in row["source"], row
    assert "cleanly on request" in rows[0]["snippet"], rows
    assert "complete the turn gracefully after abort" in rows[1]["snippet"], rows


def test_k10code_real_state(tmp_path, monkeypatch):
    """Served proof runs on the real create_app with real state."""
    client, app, data_dir = _client_on_temp_dir(
        tmp_path, monkeypatch, "kc-real")
    assert app.state.data_dir == os.path.abspath(str(data_dir))
    assert data_dir.is_dir(), data_dir
    resp = client.get("/k10/compet/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == "k10st4-accept", body
    assert isinstance(body["flows"], list) and len(body["flows"]) >= 3, body


def test_k10code_map_ten_rows():
    """Frozen map: served_rows_k10code holds exactly the 10 Falcon rows."""
    rows = k10_compet.served_rows_k10code()
    assert [row["row"] for row in rows] == [
        "B0B-UNCOVERED_MVP_ACCEPT-231", "B0B-UNCOVERED_MVP_ACCEPT-233",
        "B0B-UNCOVERED_MVP_ACCEPT-235", "B0B-UNCOVERED_MVP_ACCEPT-242",
        "B0B-UNCOVERED_MVP_ACCEPT-243", "B0B-UNCOVERED_MVP_ACCEPT-246",
        "B0B-UNCOVERED_MVP_ACCEPT-248", "B0B-UNCOVERED_MVP_ACCEPT-250",
        "B0B-UNCOVERED_MVP_ACCEPT-251", "B0B-UNCOVERED_ARCH-512",
    ], rows
    assert len(rows) == 10, rows


def test_k10code_frozen_served_rows_untouched():
    """Frozen interface: served_rows() keeps its WAVE entries in order.

    K10BMERGE extension: the total grows 34 to 40 with the 6 K10E rows
    appended; the first-10 pin below is byte-identical to round 1.
    """
    rows = k10_compet.served_rows()
    assert [row["row"] for row in rows[:10]] == [
        "R-328", "166", "R-343", "165", "167",
        "M-P3-89", "R-345", "M-P4-134", "M-P4-138", "M-P4-162",
    ], rows
    assert len(rows) == 40, rows
