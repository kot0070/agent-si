"""K10AN analytics served: one proving test per open row.

Rows (all OPEN):
-158 project counts served through GET /api/v1/analytics/telemetry?project_id=.
-160 per-model/per-provider calls+tokens+cost (or UNAVAILABLE) served.
-161 values read only from the authoritative telemetry store file, never
from chat text or live rows; product path holds no recorded seams.
Loopback TEST data only; no network, no installs. Fixtures live only here.
"""

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.telemetry import run_store as store  # noqa: E402

PRODUCT_FILES = [
    ROOT / "src" / "agent_si" / "telemetry" / "run_store.py",
    ROOT / "src" / "agent_si" / "backend" / "read_routes.py",
    ROOT / "frontend" / "src" / "k07next2" / "TelemetrySummary.tsx",
]

RECORDED_SEAMS = [
    "k10_compet",
    "project_analytics_record",
    "model_provider_analytics_record",
    "analytics_authoritative_record",
]


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


def _seed_k10an(store_dir):
    store.record_provider_usage(
        project_id="k10an-proj",
        task_id="task-k10an-1",
        run_id="run-k10an-1",
        provider="k10an-provider-a",
        model="k10an-model-a",
        usage={"input_tokens": 100, "output_tokens": 50},
        store_dir=str(store_dir),
    )
    store.record_provider_usage(
        project_id="k10an-proj",
        task_id="task-k10an-2",
        run_id="run-k10an-2",
        provider="k10an-provider-a",
        model="k10an-model-b",
        usage={},
        store_dir=str(store_dir),
    )
    store.append_records(
        [],
        [
            {
                "event_id": "e-k10an-audit-1",
                "project_id": "k10an-proj",
                "timestamp": "2026-11-01T00:00:00+00:00",
                "task_id": "task-k10an-1",
                "run_id": "run-k10an-1",
                "event_type": "AUDIT_COMPLETED",
                "metric_refs": [],
            }
        ],
        store_dir=str(store_dir),
    )


def _number_or_unavailable(value):
    assert value == "UNAVAILABLE" or (
        isinstance(value, (int, float)) and not isinstance(value, bool)
    ), value


def test_158_project_counts_served(tmp_path, monkeypatch):
    """Row -158 served: project task/audit counts from the live route."""
    store_dir = tmp_path / "store158"
    store_dir.mkdir()
    _seed_k10an(store_dir)
    client = _client_with_store(tmp_path, monkeypatch, "k10an-158", store_dir)
    first = client.get("/api/v1/analytics/telemetry?project_id=k10an-proj")
    assert first.status_code == 200, first.text
    second = client.get("/api/v1/analytics/telemetry?project_id=k10an-proj")
    assert second.status_code == 200, second.text
    assert first.json() == second.json(), (first.json(), second.json())
    body = first.json()
    assert body["project"] == {"tasks": 2, "audits": 1}, body
    assert body["source"] == "telemetry_store", body
    for key in ("metric_records", "telemetry_events", "totals", "tasks",
                "models", "providers", "unavailable"):
        assert key in body, body
    assert body["tasks"] == ["task-k10an-1", "task-k10an-2"], body
    missing = client.get("/api/v1/analytics/telemetry?project_id=k10an-absent")
    assert missing.status_code == 200, missing.text
    assert missing.json()["project"] == {"tasks": None, "audits": None}, missing.json()
    assert missing.json()["project"]["tasks"] is None
    assert missing.json()["project"]["audits"] is None
    assert "project.tasks" in missing.json()["unavailable"], missing.json()
    assert "project.audits" in missing.json()["unavailable"], missing.json()


def test_160_model_provider_served(tmp_path, monkeypatch):
    """Row -160 served: per-model/per-provider calls+tokens+cost or UNAVAILABLE."""
    store_dir = tmp_path / "store160"
    store_dir.mkdir()
    _seed_k10an(store_dir)
    client = _client_with_store(tmp_path, monkeypatch, "k10an-160", store_dir)
    resp = client.get("/api/v1/analytics/telemetry?project_id=k10an-proj")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    models = {row["model"]: row for row in body["models"]}
    assert [row["model"] for row in body["models"]] == sorted(models), body
    assert set(models) == {"k10an-model-a", "k10an-model-b"}, body
    assert models["k10an-model-a"]["calls"] == 1, body
    assert models["k10an-model-a"]["tokens"] == 150, body
    assert models["k10an-model-b"]["calls"] == 1, body
    assert models["k10an-model-b"]["tokens"] == "UNAVAILABLE", body
    providers = {row["provider"]: row for row in body["providers"]}
    assert [row["provider"] for row in body["providers"]] == sorted(providers), body
    assert providers["k10an-provider-a"]["calls"] == 2, body
    assert providers["k10an-provider-a"]["tokens"] == 150, body
    for row in body["models"] + body["providers"]:
        assert isinstance(row["calls"], int) and not isinstance(row["calls"], bool), row
        assert row["calls"] >= 1, row
        _number_or_unavailable(row["tokens"])
        _number_or_unavailable(row["cost"])
        assert row["tokens"] != 0 or isinstance(row["tokens"], str), row
    assert "models.k10an-model-b.tokens" in body["unavailable"], body


def test_161_store_only(tmp_path, monkeypatch):
    """Row -161 served: route reads the live store file; no recorded seams."""
    store_dir = tmp_path / "store161"
    store_dir.mkdir()
    _seed_k10an(store_dir)
    client = _client_with_store(tmp_path, monkeypatch, "k10an-161", store_dir)
    before = client.get("/api/v1/analytics/telemetry?project_id=k10an-proj")
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
    assert before.json()["source"] == "telemetry_store", before.json()
    (tmp_path / "chat.txt").write_text(
        "chat claims cloud_calls 999999 tokens_total 999999\n",
        encoding="utf-8",
    )
    live_rows = [{"metric_name": "cloud_calls", "value": 999999}]
    assert live_rows[0]["value"] == 999999
    after = client.get("/api/v1/analytics/telemetry?project_id=k10an-proj")
    assert after.status_code == 200, after.text
    assert after.json() == before.json()
    for path in PRODUCT_FILES:
        text = path.read_text(encoding="utf-8")
        for seam in RECORDED_SEAMS:
            assert seam not in text, (str(path), seam)
    for path in PRODUCT_FILES[:2]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not any("k10_compet" in name for name in imported), (str(path), imported)
    ui = PRODUCT_FILES[2].read_text(encoding="utf-8")
    assert "/api/v1/analytics/telemetry" in ui, ui
    assert "UNAVAILABLE" in ui, ui
    assert "k10an-project" in ui and "k10an-models" in ui, ui
    assert "k10an-providers" in ui, ui
