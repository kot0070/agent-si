"""K10D Heron served map: one proving test per open row.

Rows (all OPEN):
-158 analytics totals deterministic from stores.
-160 per-model/per-provider calls+tokens+cost or UNAVAILABLE.
-161 values read only from TelemetryEvent+MetricRecord stores.
-172 fixture rows labelled TEST FIXTURES with provenance, never measured.
-129 setup+demo+fixture command index (report + start seam).
Each row is listed by packaging/k10d_analytics.served_rows_k10d() and proven
here against the real backend route or the real store file (loopback TEST
data only; no network, no installs). Fixtures live only under tests/.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.telemetry import run_store as store  # noqa: E402
from agent_si.telemetry.metrics import MetricState  # noqa: E402

K10D_MOD_PATH = ROOT / "packaging" / "k10d_analytics.py"
START_PATH = ROOT / "tools" / "start.py"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "k10d_fixtures.json"
REPORT_PATH = ROOT / "docs" / "reports" / "K10D.md"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _k10d():
    return _load_module("k10d_analytics", K10D_MOD_PATH)


def _served():
    return {row["row"]: row for row in _k10d().served_rows_k10d()}


def _client_with_store(tmp_path, monkeypatch, token, store_dir):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(store_dir))
    app = create_app(
        {
            "ui_session_token": token,
            "secret_store": "memory",
            "testing": True,
        }
    )
    return fastapi.testclient.TestClient(app)


def _seed_two_usages(store_dir):
    store.record_provider_usage(
        project_id="k10d-proj",
        task_id="task-k10d-1",
        run_id="run-k10d-1",
        provider="k10d-provider-a",
        model="k10d-model-a",
        usage={"input_tokens": 100, "output_tokens": 50},
        store_dir=str(store_dir),
    )
    store.record_provider_usage(
        project_id="k10d-proj",
        task_id="task-k10d-1",
        run_id="run-k10d-1",
        provider="k10d-provider-b",
        model="k10d-model-b",
        usage={"input_tokens": 200, "output_tokens": 25},
        store_dir=str(store_dir),
    )
    store.record_run_terminated(
        project_id="k10d-proj",
        task_id="task-k10d-1",
        run_id="run-k10d-1",
        reason="done",
        store_dir=str(store_dir),
    )


def test_k10d_158_totals_deterministic(tmp_path, monkeypatch):
    """Row -158 served through GET /api/v1/analytics/telemetry totals."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-158"]
    assert entry["route"] == (
        "GET /api/v1/analytics/telemetry deterministic totals"
    ), entry
    assert entry["test"] == (
        "tests/test_k10d_served.py::test_k10d_158_totals_deterministic"
    ), entry
    store_dir = tmp_path / "store158"
    store_dir.mkdir()
    _seed_two_usages(store_dir)
    client = _client_with_store(tmp_path, monkeypatch, "k10d-158", store_dir)
    first = client.get("/api/v1/analytics/telemetry")
    assert first.status_code == 200, first.text
    second = client.get("/api/v1/analytics/telemetry")
    assert second.status_code == 200, second.text
    assert first.json() == second.json(), (first.json(), second.json())
    body = first.json()
    assert body["metric_records"] == 6, body
    assert body["telemetry_events"] == 3, body
    assert body["totals"]["cloud_calls"] == 2, body
    assert body["totals"]["tokens_total"] == 375, body
    assert body["tasks"] == ["task-k10d-1"], body


def test_k10d_160_per_model_provider(tmp_path, monkeypatch):
    """Row -160 served through the packaging by_model_provider seam."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-160"]
    assert entry["route"] == (
        "packaging/k10d_analytics.py by_model_provider seam"
    ), entry
    assert entry["test"] == (
        "tests/test_k10d_served.py::test_k10d_160_per_model_provider"
    ), entry
    store_dir = tmp_path / "store160"
    store_dir.mkdir()
    store.record_provider_usage(
        project_id="k10d-proj",
        task_id="task-k10d-2",
        run_id="run-k10d-2",
        provider="k10d-provider-a",
        model="k10d-model-a",
        usage={"input_tokens": 10, "output_tokens": 5},
        store_dir=str(store_dir),
    )
    store.record_provider_usage(
        project_id="k10d-proj",
        task_id="task-k10d-2",
        run_id="run-k10d-2",
        provider="k10d-provider-a",
        model="k10d-model-b",
        usage={},
        store_dir=str(store_dir),
    )
    _ = _client_with_store(tmp_path, monkeypatch, "k10d-160", store_dir)
    snapshot = store.load_store(store_dir=str(store_dir))
    view = _k10d().by_model_provider(snapshot)
    by_model = {(r["provider"], r["model"]): r for r in view["per_model"]}
    assert set(by_model) == {
        ("k10d-provider-a", "k10d-model-a"),
        ("k10d-provider-a", "k10d-model-b"),
    }, view
    for row in view["per_model"]:
        assert isinstance(row["calls"], int) and row["calls"] >= 1, row
        assert ("tokens" in row) and ("cost" in row), row
        for key in ("tokens", "cost"):
            value = row[key]
            assert value == "UNAVAILABLE" or isinstance(value, (int, float)), row
            if isinstance(value, bool):
                raise AssertionError(row)
    assert by_model[("k10d-provider-a", "k10d-model-a")]["tokens"] == 15, view
    assert by_model[("k10d-provider-a", "k10d-model-b")]["tokens"] == (
        "UNAVAILABLE"
    ), view
    by_provider = {r["provider"]: r for r in view["per_provider"]}
    assert by_provider["k10d-provider-a"]["calls"] == 2, view
    assert by_provider["k10d-provider-a"]["tokens"] == 15, view


def test_k10d_161_authoritative_only(tmp_path, monkeypatch):
    """Row -161 served through the authoritative-stores analytics route."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-161"]
    assert entry["route"] == (
        "GET /api/v1/analytics/telemetry authoritative stores"
    ), entry
    assert entry["test"] == (
        "tests/test_k10d_served.py::test_k10d_161_authoritative_only"
    ), entry
    origins = _k10d().authoritative_origins()
    assert origins["allowed"] == [
        "metric-records-store",
        "telemetry-events-store",
    ], origins
    assert origins["refused"] == ["chat-text", "live-rows"], origins
    store_dir = tmp_path / "store161"
    store_dir.mkdir()
    _seed_two_usages(store_dir)
    client = _client_with_store(tmp_path, monkeypatch, "k10d-161", store_dir)
    before = client.get("/api/v1/analytics/telemetry")
    assert before.status_code == 200, before.text
    with open(store_dir / "telemetry_store.json", encoding="utf-8") as handle:
        saved = json.load(handle)
    totals = {}
    for row in saved["metric_records"]:
        value = row.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        totals[row["metric_name"]] = totals.get(row["metric_name"], 0) + value
    assert before.json()["totals"] == totals, (before.json(), totals)
    assert before.json()["metric_records"] == len(saved["metric_records"])
    assert before.json()["telemetry_events"] == len(saved["telemetry_events"])
    (tmp_path / "chat.txt").write_text(
        "chat claims cloud_calls 999999 tokens_total 999999\n",
        encoding="utf-8",
    )
    live_rows = [{"metric_name": "cloud_calls", "value": 999999}]
    assert live_rows[0]["value"] == 999999
    after = client.get("/api/v1/analytics/telemetry")
    assert after.status_code == 200, after.text
    assert after.json() == before.json()


def test_k10d_172_fixture_rows_labelled(tmp_path, monkeypatch):
    """Row -172 served through the TEST FIXTURES fixture seam."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-172"]
    assert entry["route"] == (
        "tests/fixtures/k10d_fixtures.json TEST FIXTURES seam"
    ), entry
    assert entry["test"] == (
        "tests/test_k10d_served.py::test_k10d_172_fixture_rows_labelled"
    ), entry
    rows = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    _k10d().validate_fixture_rows(rows)
    assert [row["fixture"] for row in rows] == [
        "demo-fixture",
        "command-fixture",
    ], rows
    for row in rows:
        assert row["label"] == "TEST FIXTURES", row
        assert row["provenance"], row
        assert "never measured evidence" in row["provenance"], row
    store_dir = tmp_path / "store172"
    store_dir.mkdir()
    _seed_two_usages(store_dir)
    snapshot = store.load_store(store_dir=str(store_dir))
    measured_ids = {
        row.get("metric_id")
        for row in snapshot["metric_records"]
        if isinstance(row, dict)
        and row.get("state") == MetricState.MEASURED.value
    }
    for row in rows:
        assert row["fixture_id"] not in measured_ids, row


def test_k10d_129_command_index(tmp_path):
    """Row -129 served through the report command index + start seam."""
    entry = _served()["B0B-UNCOVERED_MVP_ACCEPT-129"]
    assert entry["route"] == (
        "docs/reports/K10D.md command index + "
        "tools/start.py k10d_command_index seam"
    ), entry
    assert entry["test"] == (
        "tests/test_k10d_served.py::test_k10d_129_command_index"
    ), entry
    start_mod = _load_module("k10d_start_index", START_PATH)
    index = start_mod.k10d_command_index()
    assert set(index) == {"setup", "demo", "fixture"}, index
    for section in ("setup", "demo", "fixture"):
        assert len(index[section]) >= 1, index
        for command in index[section]:
            assert isinstance(command, str) and command.strip(), index
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "## Command index" in report, report
    for section in ("setup", "demo", "fixture"):
        for command in index[section]:
            assert command in report, (section, command)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "start.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "--smoke" in proc.stdout, proc.stdout
    assert "tools/start.py --smoke" in report, report


def test_k10d_negative_fabricated_evidence_rejected(tmp_path):
    """Negative: invented totals that are not in the store are rejected."""
    store_dir = tmp_path / "store-neg"
    store_dir.mkdir()
    _seed_two_usages(store_dir)
    snapshot = store.load_store(store_dir=str(store_dir))
    fabricated = {"cloud_calls": 999999, "tokens_total": 999999}
    with pytest.raises(ValueError):
        _k10d().verify_totals_against_store(fabricated, snapshot)
    honest = dict(store.aggregates(store_dir=str(store_dir))["totals"])
    _k10d().verify_totals_against_store(honest, snapshot)


def test_k10d_negative_unlabelled_fixture_rejected():
    """Negative: a fixture row without TEST FIXTURES labelling fails."""
    with pytest.raises(ValueError):
        _k10d().validate_fixture_rows(
            [
                {
                    "fixture": "demo-fixture",
                    "label": "measured",
                    "provenance": "",
                }
            ]
        )
    with pytest.raises(ValueError):
        _k10d().validate_fixture_rows(
            [
                {
                    "fixture": "demo-fixture",
                    "label": "TEST FIXTURES",
                    "provenance": "",
                }
            ]
        )
