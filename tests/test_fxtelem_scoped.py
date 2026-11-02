"""FXTELEM: project-scoped telemetry aggregates (RED first).

Two runs in one project record 5142 + 13938 tokens; a second project
records 99999 tokens. The ?project_id= route must serve only the
requested project's per-model/per-provider aggregates, so the rail's
per-model rows add up to this project's total (19080), never a global
sum across projects.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.telemetry import run_store as store  # noqa: E402


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


def _seed(tmp_path):
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    store.record_provider_usage(
        project_id="fxtelem-proj",
        task_id="task-1",
        run_id="run-1",
        provider="meta",
        model="muse-spark-1.3-contributor",
        usage={"input_tokens": 1442, "output_tokens": 3700},
        store_dir=str(store_dir),
    )
    store.record_provider_usage(
        project_id="fxtelem-proj",
        task_id="task-2",
        run_id="run-2",
        provider="meta",
        model="muse-spark-1.3-contributor",
        usage={"input_tokens": 3938, "output_tokens": 10000},
        store_dir=str(store_dir),
    )
    store.record_provider_usage(
        project_id="other-proj",
        task_id="task-9",
        run_id="run-9",
        provider="meta",
        model="muse-spark-1.3-contributor",
        usage={"input_tokens": 99999},
        store_dir=str(store_dir),
    )
    return store_dir


def test_models_scoped_to_project(tmp_path, monkeypatch):
    store_dir = _seed(tmp_path)
    rows = store.get_model_aggregates(
        store_dir=str(store_dir), project_id="fxtelem-proj")
    assert len(rows) == 1, rows
    assert rows[0]["tokens"] == 5142 + 13938, rows


def test_route_models_scoped_to_project(tmp_path, monkeypatch):
    store_dir = _seed(tmp_path)
    client = _client_with_store(tmp_path, monkeypatch, "fxtelem-1", store_dir)
    resp = client.get("/api/v1/analytics/telemetry?project_id=fxtelem-proj")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    model_tokens = sum(
        row["tokens"] for row in body["models"]
        if isinstance(row.get("tokens"), (int, float)))
    assert model_tokens == 5142 + 13938, body


def _seed_roles(tmp_path):
    store_dir = tmp_path / "storeroles"
    store_dir.mkdir()
    store.record_provider_usage(
        project_id="fxtelem-roles",
        task_id="task-1",
        run_id="run-1",
        provider="meta",
        model="muse-spark-1.3-contributor",
        usage={"input_tokens": 1000, "output_tokens": 4000},
        store_dir=str(store_dir),
        role="worker",
    )
    store.record_provider_usage(
        project_id="fxtelem-roles",
        task_id="task-1",
        run_id="run-1",
        provider="meta",
        model="muse-spark-1.3-contributor",
        usage={"input_tokens": 2000, "output_tokens": 2000},
        store_dir=str(store_dir),
        role="manager",
    )
    store.record_provider_usage(
        project_id="fxtelem-roles",
        task_id="task-1",
        run_id="run-1",
        provider="meta",
        model="muse-spark-1.3-contributor",
        usage={"input_tokens": 10},
        store_dir=str(store_dir),
    )
    return store_dir


def test_role_aggregates_group_tokens_by_role(tmp_path, monkeypatch):
    store_dir = _seed_roles(tmp_path)
    rows = store.get_role_aggregates(
        store_dir=str(store_dir), project_id="fxtelem-roles")
    by_role = {row["role"]: row for row in rows}
    assert by_role["worker"]["tokens"] == 5000, rows
    assert by_role["manager"]["tokens"] == 4000, rows
    assert by_role[""]["tokens"] == 10, rows
    assert sum(
        row["tokens"] for row in rows
        if isinstance(row.get("tokens"), (int, float))) == 9010, rows


def test_route_roles_scoped_to_project(tmp_path, monkeypatch):
    store_dir = _seed_roles(tmp_path)
    client = _client_with_store(tmp_path, monkeypatch, "fxtelem-2", store_dir)
    resp = client.get("/api/v1/analytics/telemetry?project_id=fxtelem-roles")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "roles" in body, body
    role_tokens = sum(
        row["tokens"] for row in body["roles"]
        if isinstance(row.get("tokens"), (int, float)))
    assert role_tokens == 9010, body
