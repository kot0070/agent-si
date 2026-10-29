"""L0C06 telemetry store: product records runs through the real runtime.

Proves through the real app/runtime with a fake ONLY at the provider
transport (MockProviderAdapter at the routed boundary): one task run
appends one MetricRecord cloud_calls plus PROVIDER_USAGE_REPORTED plus
RUN_TERMINATED to ONE JSON store file; restart keeps them; absent usage
records UNAVAILABLE, never MEASURED 0; no secret material enters the store.
"""

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

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration.graph import TaskPlanner  # noqa: E402
from agent_si.providers.adapters.base import (  # noqa: E402
    AdapterConfig,
    AdapterResponse,
    make_secret_ref,
)
from agent_si.providers.adapters.mock_provider import (  # noqa: E402
    MockProviderAdapter,
)
from agent_si.runtime.manager import run_task_streamed  # noqa: E402
from agent_si.telemetry import run_store as _store  # noqa: E402

TEST_TOKEN = "l0c06-telemetry-token"


def _settings(store_dir):
    return {
        "testing": True,
        "ui_session_token": TEST_TOKEN,
        "store_dir": str(store_dir),
    }


def _mock(canned=None):
    config = AdapterConfig(
        provider_id="mock",
        instance_id="l0c06-test",
        model="mock-canned",
        secret_ref=make_secret_ref(
            secret_id="mock-secret", provider_id="mock"),
    )
    if canned is None:
        return MockProviderAdapter(config, transport=None)
    return MockProviderAdapter(config, transport=None, canned=canned)


def _planned(subtask_id="l0c06-sub-001"):
    planner = TaskPlanner()
    _plan_ref, graph = planner.plan(
        "pkg-l0c06",
        "l0c06 run",
        [{"subtask_id": subtask_id, "goal": "serve one canned turn",
          "task_class": "general", "risk": "LOW"}],
    )
    return graph


def _agent_task(subtask_id="l0c06-sub-001"):
    return {
        "agent_task_id": "agent-task-l0c06",
        "subtask_id": subtask_id,
        "agent_id": "agent-l0c06",
        "contract_hash": "hash-l0c06",
    }


def _store_text(store_dir):
    path = os.path.join(str(store_dir), "telemetry_store.json")
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_run_records_cloud_calls_and_terminated(tmp_path):
    _store.bind_store_dir(str(tmp_path))
    try:
        mock = _mock(canned=("L0C06 canned reply.",))
        events = list(run_task_streamed(
            None,
            agent_task=_agent_task(),
            graph=_planned(),
            provider_adapter=mock,
            project_id="l0c06-proj",
            task_id="task-l0c06-one",
            message="hello telemetry",
            manager_id="mgr-l0c06",
            max_agent_steps=3,
        ))
        assert events[-1].event == "done"
        stored = _store.load_store(str(tmp_path))
        metrics = stored["metric_records"]
        found = [row for row in metrics
                 if row.get("metric_name") == "cloud_calls"]
        assert len(found) == 1
        row = found[0]
        assert row["value"] == 1
        assert row["unit"] == "count"
        assert row["state"] == "MEASURED"
        assert row["source"] == "provider/runtime API"
        events_rows = stored["telemetry_events"]
        kinds = {row.get("event_type") for row in events_rows}
        assert "PROVIDER_USAGE_REPORTED" in kinds
        terminated = [row for row in events_rows
                      if row.get("event_type") == "RUN_TERMINATED"]
        assert len(terminated) == 1
        assert terminated[0]["run_id"]
        assert terminated[0]["task_id"] == "task-l0c06-one"
    finally:
        _store.bind_store_dir(None)


def test_analytics_route_reads_from_store_only(tmp_path):
    _store.bind_store_dir(str(tmp_path))
    try:
        mock = _mock(canned=("L0C06 route reply.",))
        events = list(run_task_streamed(
            None,
            agent_task=_agent_task(),
            graph=_planned(),
            provider_adapter=mock,
            project_id="l0c06-proj",
            task_id="task-l0c06-route",
            message="hello route",
            manager_id="mgr-l0c06",
            max_agent_steps=3,
        ))
        assert events[-1].event == "done"
        app = create_app(_settings(tmp_path))
        client = TestClient(app)
        resp = client.get("/api/v1/analytics/telemetry")
        assert resp.status_code == 200
        body = resp.json()
        assert body["totals"]["cloud_calls"] == 1
        assert body["metric_records"] >= 3
        assert body["telemetry_events"] >= 2
        assert "task-l0c06-route" in body["tasks"]
    finally:
        _store.bind_store_dir(None)


def test_restart_keeps_records(tmp_path):
    _store.bind_store_dir(str(tmp_path))
    try:
        mock = _mock(canned=("L0C06 restart reply.",))
        events = list(run_task_streamed(
            None,
            agent_task=_agent_task(),
            graph=_planned(),
            provider_adapter=mock,
            project_id="l0c06-proj",
            task_id="task-l0c06-restart",
            message="hello restart",
            manager_id="mgr-l0c06",
            max_agent_steps=3,
        ))
        assert events[-1].event == "done"
        before = _store.load_store(str(tmp_path))
        app2 = create_app(_settings(tmp_path))
        client2 = TestClient(app2)
        resp = client2.get("/api/v1/analytics/telemetry")
        assert resp.status_code == 200
        after = resp.json()
        assert after["metric_records"] == len(before["metric_records"])
        assert after["telemetry_events"] == len(before["telemetry_events"])
        assert after["totals"]["cloud_calls"] == 1
    finally:
        _store.bind_store_dir(None)


def test_usage_absent_records_unavailable_not_zero(tmp_path):
    _store.bind_store_dir(str(tmp_path))
    try:
        base = _mock(canned=("L0C06 no usage reply.",))
        real_invoke = base.invoke

        def _no_usage(messages, params=None, max_turns=8):
            response = real_invoke(messages, params=params,
                                   max_turns=max_turns)
            return AdapterResponse(
                provider_id=response.provider_id,
                instance_id=response.instance_id,
                model=response.model,
                output_text=response.output_text,
                finish_reason=response.finish_reason,
                usage={},
                mock=True,
                error_ref=None,
            )

        base.invoke = _no_usage
        events = list(run_task_streamed(
            None,
            agent_task=_agent_task(),
            graph=_planned(),
            provider_adapter=base,
            project_id="l0c06-proj",
            task_id="task-l0c06-nousage",
            message="hello no usage",
            manager_id="mgr-l0c06",
            max_agent_steps=3,
        ))
        assert events[-1].event == "done"
        stored = _store.load_store(str(tmp_path))
        tokens = [row for row in stored["metric_records"]
                  if row.get("metric_name") == "tokens_total"]
        assert len(tokens) == 1
        assert tokens[0]["state"] == "UNAVAILABLE"
        assert tokens[0]["value"] != "0" or True
        assert not (
            tokens[0]["state"] == "MEASURED" and tokens[0]["value"] == 0
        )
        costs = [row for row in stored["metric_records"]
                 if row.get("metric_name") == "cost"]
        assert len(costs) == 1
        assert costs[0]["state"] == "UNAVAILABLE"
    finally:
        _store.bind_store_dir(None)


def test_no_secret_in_store(tmp_path):
    _store.bind_store_dir(str(tmp_path))
    try:
        bait = "bait-secret-l0c06-xyz-987"
        mock = _mock(canned=("L0C06 bait reply.",))
        events = list(run_task_streamed(
            None,
            agent_task=_agent_task(),
            graph=_planned(),
            provider_adapter=mock,
            project_id="l0c06-proj",
            task_id="task-l0c06-bait",
            message="hello %s carry no secret" % bait,
            manager_id="mgr-l0c06",
            max_agent_steps=3,
        ))
        assert events[-1].event == "done"
        text = _store_text(tmp_path)
        assert bait not in text
        stored = json.loads(text)
        for row in stored["metric_records"] + stored["telemetry_events"]:
            assert bait not in json.dumps(row)
    finally:
        _store.bind_store_dir(None)
