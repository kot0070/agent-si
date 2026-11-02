"""FXAUTODEV served proof: hierarchy run executes parts via run_task_streamed.

POST /api/v1/hierarchy/run routes every dispatched part through the real
manager run_task_streamed entry, so the hardcoded PASS is gone:

(a) the provider adapter call count equals the dispatched parts,
(b) GET /api/v1/agents/live shows rows for the run,
(c) an erroring adapter part yields FAIL and the parent is not PASS,
(d) a run with no bound provider answers an honest 409 NO_PROVIDER_BOUND.

The provider adapter is faked ONLY at the network boundary with canned
completions (MockProviderAdapter, transport None); the bind entry is the
only wiring seam the tests touch.
"""

import os
import sys
import threading
from unittest import mock

from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import agents_live  # noqa: E402
from agent_si.backend import chat_stream as _chat  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from agent_si.providers.adapters.base import (  # noqa: E402
    AdapterConfig,
    make_secret_ref,
)
from agent_si.providers.adapters.mock_provider import (  # noqa: E402
    MockProviderAdapter,
)
from agent_si.routing.types import RoleModelProfile  # noqa: E402

TEST_TOKEN = "fxautodev-served-token"
PROJECT = "fxad-proj"
PACKAGE = "fxad-pkg"
MODEL = "mock-canned"


def _refs(n):
    return [f"artifact://pkg-{i}/blob" for i in range(n)]


def _auth():
    return {"x-actor": "fxad-tester", "x-ui-session-token": TEST_TOKEN}


def _run_body(**overrides):
    body = {
        "package_id": PACKAGE,
        "goal": "prove hierarchy parts run through the manager",
        "context_refs": _refs(4),
        "max_parts": 2,
        "director_id": "director-fxad",
        "manager_id": "manager-fxad",
        "tool_agent_ids": ["tool-a", "tool-b"],
        "project_id": PROJECT,
    }
    body.update(overrides)
    return body


def _configure_limits():
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": PROJECT,
        "task_max_steps": 3,
        "chat_max_steps": 3,
        "authority": "fxautodev-test",
        "reason": "fxautodev served run needs a task budget",
    })
    assert outcome.applied, outcome.reason


def _pin_worker(app):
    table = app.state.k04_ctx.role_table
    table.set_profile(RoleModelProfile(
        role="worker", project_id=PROJECT, mode="PINNED",
        provider="mock", model=MODEL, binding="DEFAULT",
        version=1, hash="fxautodev-test"))
    return table


def _mock_config():
    return AdapterConfig(
        provider_id="mock",
        instance_id="fxautodev-served-test",
        model=MODEL,
        secret_ref=make_secret_ref(
            secret_id="mock-secret", provider_id="mock"),
    )


class _CountingMock(MockProviderAdapter):
    """Thread-safe canned adapter counting boundary calls."""

    def __init__(self, config, canned):
        super().__init__(config, transport=None, canned=canned)
        self._lock = threading.Lock()
        self.attempts = 0

    def invoke(self, messages, params=None, max_turns=8):
        with self._lock:
            self.attempts += 1
            return super().invoke(
                messages, params=params, max_turns=max_turns)


class _FailAfterFirstMock(_CountingMock):
    """Canned adapter whose second and later calls raise."""

    def invoke(self, messages, params=None, max_turns=8):
        with self._lock:
            self.attempts += 1
            if self.turns_served >= 1:
                raise RuntimeError("fxautodev induced part failure")
            return MockProviderAdapter.invoke(
                self, messages, params=params, max_turns=max_turns)


def _client(tmp_path, monkeypatch, adapter):
    agents_live.clear_live_rows()
    _steplimits._reset_state()
    _configure_limits()
    app = create_app({
        "testing": True,
        "ui_session_token": TEST_TOKEN,
        "store_dir": str(tmp_path),
    })
    _pin_worker(app)
    # FXLOC C5: fail-closed gate needs the project configured on the
    # app's real gate (generous limits; mirrors the served chat route).
    app.state.k04_ctx.budget_state.configure_project(
        PROJECT, "USD", "1000000.00", "900000.00", "1000000.00")
    monkeypatch.setattr(
        _chat, "bind_routed_provider_adapter",
        lambda app, project_id=None: adapter)
    return TestClient(app)


def setup_function(_func):
    agents_live.clear_live_rows()
    _steplimits._reset_state()


def teardown_function(_func):
    agents_live.clear_live_rows()
    _steplimits._reset_state()


def test_adapter_called_once_per_part(tmp_path, monkeypatch):
    adapter = _CountingMock(_mock_config(), ("Canned part reply.",))
    client = _client(tmp_path, monkeypatch, adapter)
    resp = client.post(
        "/api/v1/hierarchy/run", json=_run_body(), headers=_auth())
    assert resp.status_code == 200, resp.text
    assert adapter.turns_served == 2, (
        f"adapter call count equals parts, got {adapter.turns_served}")
    payload = resp.json()
    runs = payload.get("part_runs")
    assert runs is not None, "response carries per-part runs"
    assert len(runs) == 2, runs
    for run in runs:
        assert run["status"] == "PASS", run
        assert run["terminal_event"] == "done", run
        assert run["model"] == MODEL, run
        assert run["subtask_id"] and run["run_id"], run
    assert payload["integration"]["parent"] == "closed"


def test_live_rows_recorded_for_run(tmp_path, monkeypatch):
    adapter = _CountingMock(_mock_config(), ("Canned part reply.",))
    client = _client(tmp_path, monkeypatch, adapter)
    resp = client.post(
        "/api/v1/hierarchy/run", json=_run_body(), headers=_auth())
    assert resp.status_code == 200, resp.text
    live = client.get("/api/v1/agents/live")
    assert live.status_code == 200, live.text
    rows = live.json()["agents"]
    ours = [row for row in rows
            if f"{PACKAGE}:part-" in str(row.get("scope", ""))]
    assert ours, (
        f"agents/live shows rows for the run, got {len(rows)} rows")


def test_erroring_adapter_part_fails_parent_not_pass(tmp_path, monkeypatch):
    adapter = _FailAfterFirstMock(_mock_config(), ("Canned part reply.",))
    client = _client(tmp_path, monkeypatch, adapter)
    resp = client.post(
        "/api/v1/hierarchy/run", json=_run_body(), headers=_auth())
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    runs = detail["part_runs"]
    assert sorted(run["status"] for run in runs) == ["FAIL", "PASS"], runs
    failed = next(run for run in runs if run["status"] == "FAIL")
    assert failed["terminal_event"] == "error", failed
    assert "induced" in str(failed.get("reason", "")), failed
    assert "parts not PASS" in str(detail.get("reason", "")), detail
    assert adapter.attempts == 2, (
        f"both parts really ran, got {adapter.attempts} attempts")


def test_no_provider_answers_409(tmp_path):
    agents_live.clear_live_rows()
    app = create_app({
        "testing": True,
        "ui_session_token": TEST_TOKEN,
        "store_dir": str(tmp_path),
    })
    client = TestClient(app)
    resp = client.post(
        "/api/v1/hierarchy/run", json=_run_body(), headers=_auth())
    assert resp.status_code == 409, resp.text
    assert "NO_PROVIDER_BOUND" in resp.text, resp.text


CANNED_HIERARCHY_REPLY = ("Canned part reply.",)


def canned_hierarchy_adapter(canned=CANNED_HIERARCHY_REPLY):
    """Build a fresh canned network-boundary adapter (transport None).

    Canned completions only, no network, no keys. Every instance
    counts boundary calls. This is the one fixture other lanes reuse.
    """
    return _CountingMock(_mock_config(), canned)


def ensure_hierarchy_step_limits(project_id=None):
    """Apply the task/chat step budget one hierarchy run needs.

    project_id selects the per-project setting; None configures the
    lane sentinel so a None-project run reads the last project.
    Mirrors _client so other lanes run the identical budget path.
    """
    agents_live.clear_live_rows()
    _steplimits._reset_state()
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": project_id or PROJECT,
        "task_max_steps": 3,
        "chat_max_steps": 3,
        "authority": "fxautodev-test",
        "reason": "fxautodev served run needs a task budget",
    })
    assert outcome.applied, outcome.reason
    return outcome


_ACTIVE_CANNED_PATCH = None


def stop_canned_hierarchy_adapter():
    """Stop a started canned bind, if one is still active."""
    global _ACTIVE_CANNED_PATCH
    patcher, _ACTIVE_CANNED_PATCH = _ACTIVE_CANNED_PATCH, None
    if patcher is not None:
        patcher.stop()


def bind_canned_hierarchy_adapter(project_id=None):
    """Bind the canned adapter at the network boundary; return a stopper.

    Patches the bind_routed_provider_adapter entry, the only wiring
    seam tests touch, so every dispatched part runs on a fresh canned
    mock (transport None, no network, no keys). Callers stop the
    returned patcher right after POST. Heals a prior leak first.
    """
    stop_canned_hierarchy_adapter()
    ensure_hierarchy_step_limits(project_id)
    adapter = canned_hierarchy_adapter()
    patcher = mock.patch.object(
        _chat, "bind_routed_provider_adapter",
        lambda app, project_id=None: adapter)
    patcher.start()
    global _ACTIVE_CANNED_PATCH
    _ACTIVE_CANNED_PATCH = patcher
    return patcher
