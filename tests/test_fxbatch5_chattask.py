"""FXBATCH5 B2 chat rows + B3 attach auth (served proof).

Drives the real seam app (create_app + TestClient,
raise_server_exceptions=False) over a real tmp store dir on the real
fs. Only the provider boundary uses the sanctioned K04
MockProviderAdapter (no network, no keys, no token in URL).

  B2: every accepted chat message stores ONE task row; a repeat of the
    same stripped text stores none; a named chat_task that exists
    stores none; a store failure still leaves the stream whole.
  B3: POST /api/v1/kb/attach via the product route attaches (200, not
    401) when the caller carries the frozen USER_WRITE credentials.
"""

import json
import os
import sys

from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import chat_stream as _chat  # noqa: E402
from agent_si.backend import read_routes as _reads  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from agent_si.providers.adapters.base import (  # noqa: E402
    AdapterConfig,
    make_secret_ref,
)
from agent_si.providers.adapters.mock_provider import (  # noqa: E402
    MockProviderAdapter,
)

try:  # same dual-harness import the seam app uses (agent_si.* first)
    from agent_si.kb import registry as _registry
    from agent_si.kb import retriever as _kb
except ImportError:
    from src.agent_si.kb import registry as _registry
    from src.agent_si.kb import retriever as _kb

TEST_TOKEN = "fxbatch5-chattask-token"
ACTOR = "coder-1-gull"
CANNED = ("Canned service reply.",)
MSG_A = "gull field note: map the north fence line"
MSG_B = "gull follow-up: check the south gate pump"

TASKS_SNAPSHOT = "k02r3_tasks.jsonl"


def _auth(token=TEST_TOKEN, actor=ACTOR):
    return {"x-actor": actor, "x-ui-session-token": token}


def _settings(store_dir=None):
    settings = {"testing": True, "ui_session_token": TEST_TOKEN}
    if store_dir is not None:
        settings["store_dir"] = str(store_dir)
    return settings


def _mock_adapter(canned=CANNED):
    config = AdapterConfig(
        provider_id="mock",
        instance_id="fxbatch5-behavior",
        model="mock-canned",
        secret_ref=make_secret_ref(
            secret_id="mock-secret", provider_id="mock"),
    )
    return MockProviderAdapter(config, transport=None, canned=canned)


def _apply_chat_limits(project_id):
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": project_id,
        "authority": "fxbatch5-test",
        "reason": "configure test project limits for chat behavior",
        "task_max_steps": 10,
        "chat_max_steps": 10,
    })
    assert outcome.applied, outcome.reason


def setup_function(_func):
    _steplimits._reset_state()


def teardown_function(_func):
    _steplimits._reset_state()


def _served_client(tmp_path, monkeypatch):
    """Real app with the orchestration path forced (manager loaders off)."""
    monkeypatch.setattr(
        _chat, "_load_manager_run_task_streamed", lambda: None)
    monkeypatch.setattr(
        _chat, "_load_manager_bound_provider", lambda: None)
    app = create_app(_settings(tmp_path))
    app.state.chat_provider_adapter = _mock_adapter()
    return TestClient(app, raise_server_exceptions=False), app


def _create_project(client):
    resp = client.post(
        "/api/v1/projects",
        json={"name": "fxbatch5", "folder_ref": "dock-fxbatch5"},
        headers=_auth(),
    )
    assert resp.status_code == 200, resp.text
    pid = resp.json()["project"]["project_id"]
    assert pid, resp.text
    return pid


def _parse_sse(text):
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


def _snapshot_rows(tmp_path):
    path = os.path.join(str(tmp_path), TASKS_SNAPSHOT)
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle.read().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _listed_tasks(client, project_id):
    resp = client.get(
        "/api/v1/tasks", params={"project_id": project_id})
    assert resp.status_code == 200, resp.text
    return resp.json()["tasks"]


def _post_chat(client, message, project=None, task=""):
    body = {"message": message}
    if project is not None:
        body["project"] = project
    if task:
        body["task"] = task
    return client.post("/api/v1/chat/stream", json=body, headers=_auth())


# -- B2: two different accepted messages store two rows ---------------------


def test_two_different_messages_store_two_rows(tmp_path, monkeypatch):
    client, _app = _served_client(tmp_path, monkeypatch)
    pid = _create_project(client)
    _apply_chat_limits(pid)
    first = _post_chat(client, MSG_A, project=pid)
    assert first.status_code == 200, first.text
    second = _post_chat(client, MSG_B, project=pid)
    assert second.status_code == 200, second.text
    listed = _listed_tasks(client, pid)
    assert len(listed) == 2, listed
    titles = sorted(row["title"] for row in listed)
    assert titles == sorted([MSG_A, MSG_B]), listed
    rows = _snapshot_rows(tmp_path)
    mine = [row for row in rows if row.get("project_id") == pid]
    assert len(mine) == 2, rows


# -- B2: same stripped text twice stores one row ----------------------------


def test_same_stripped_text_twice_stores_one_row(tmp_path, monkeypatch):
    client, _app = _served_client(tmp_path, monkeypatch)
    pid = _create_project(client)
    _apply_chat_limits(pid)
    first = _post_chat(client, MSG_A, project=pid)
    assert first.status_code == 200, first.text
    second = _post_chat(client, "  " + MSG_A + "  ", project=pid)
    assert second.status_code == 200, second.text
    listed = _listed_tasks(client, pid)
    assert len(listed) == 1, listed
    assert listed[0]["title"] == MSG_A, listed[0]
    rows = _snapshot_rows(tmp_path)
    mine = [row for row in rows if row.get("project_id") == pid]
    assert len(mine) == 1, rows


# -- B2: store failure never breaks the stream -------------------------------


def test_task_write_failure_leaves_stream_whole(tmp_path, monkeypatch):
    client, app = _served_client(tmp_path, monkeypatch)
    pid = _create_project(client)
    _apply_chat_limits(pid)
    _projects, tasks = _reads.repos_for(app)

    def _boom(_record):
        raise RuntimeError("fxbatch5 probe write failure")

    monkeypatch.setattr(tasks, "append", _boom)
    resp = _post_chat(client, MSG_A, project=pid)
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    kinds = [event.get("type") for event in events]
    assert kinds[0] == "start", kinds
    assert kinds.count("start") == 1, kinds
    assert kinds[-1] in ("done", "error"), kinds
    rows = _snapshot_rows(tmp_path)
    mine = [row for row in rows if row.get("project_id") == pid]
    assert mine == [], rows


# -- B3: served attach carries auth -> attached, not 401 ---------------------


def _write_kb_dir(path, sections=None, purpose="Dev role notes."):
    sections = sections or {"intro": "Intro notes.", "setup": "Setup notes."}
    path.mkdir(parents=True, exist_ok=True)
    (path / "sections").mkdir(exist_ok=True)
    for name, text in sections.items():
        (path / "sections" / (name + ".md")).write_text(text, encoding="utf-8")
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "kb_id": path.name,
                "purpose": purpose,
                "sections": sorted(sections),
            }
        ),
        encoding="utf-8",
    )
    (path / "purpose.txt").write_text(purpose, encoding="utf-8")
    return str(path)


def test_served_attach_with_write_auth_attaches(tmp_path):
    from agent_si.backend.app import create_app as _create

    app = _create(dict(_settings()))
    client = TestClient(app, raise_server_exceptions=False)
    project = "proj-fxbatch5-attach"
    kb_id = _write_kb_dir(tmp_path / "kb-fxbatch5-attach")
    try:
        resp = client.post(
            "/api/v1/kb/attach",
            json={"source": {
                "kb_id": kb_id,
                "kind": "DEV_ROLE",
                "project_id": project,
                "role": "dev",
                "purpose": "Dev role notes.",
            }},
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.status_code != 401, resp.text
        assert resp.json() == kb_id
        assert _registry.is_attached(kb_id) is True
    finally:
        _kb.detach_kb(kb_id)
