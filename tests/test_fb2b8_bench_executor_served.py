"""FB2B8 F10 local-bench background executor, served proof.

RED before the bench_runner background executor lands (start_run returns
at once with zero rows and done_cases stays 0: completion, pause-resume
and stop assertions fail); GREEN after. The FAKE loopback runtime lives
only at the network boundary (a real HTTP server on 127.0.0.1 emulating
the runtime endpoint, pointed at by AGENT_SI_BENCH_CHAT_ENDPOINT); the
test otherwise drives product paths only (served POST /runs plus runner
reads). Fixtures live in this file only. The fake answers some Quick
cases right and some wrong against the frozen prompts, so the proof shows
scores derive from replies (right -> 1.0, wrong -> 0.0); endpoint tests
drive the POST body / last-check / env chain with the env deleted.
"""
from __future__ import annotations

import json
import pathlib
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from agent_si.backend import localbench_routes as _routes
from agent_si.capability_store import store as _cap_store  # noqa: E402
from agent_si.local import bench_cases as _cases
from agent_si.local import bench_runner as _runner  # noqa: E402
from agent_si.local.bench_protocol import BenchLevel

_TOKEN = "tok-fb2b8-exec-1"
_ACTOR = "fb2b8-user"
_HEADERS = {"x-actor": _ACTOR, "x-ui-session-token": _TOKEN}
_MODEL = "FB2B8-LOOPBACK-MODEL"
_ENDPOINT_ENV = "AGENT_SI_BENCH_CHAT_ENDPOINT"
_CASE_DELAY_S = 0.3

#: Fake-runtime answer plan per Quick case: some right, some wrong, so the
#: served proof shows scores derive from replies (right -> 1.0, wrong -> 0.0).
_RIGHT_CASES = ("q01", "q03", "q05")


def _prompt_to_case() -> dict[str, str]:
    """Frozen prompt text -> Quick case id (product constants only)."""
    table = {}
    for case in _cases.list_cases(BenchLevel.Quick):
        table[_cases.quick_case_spec(case.case_id).prompt] = case.case_id
    return table


class _FakeLoopbackRuntimeHandler(BaseHTTPRequestHandler):
    """Fake runtime endpoint: deterministic JSON reply per POST prompt."""

    delay_s = _CASE_DELAY_S

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body.decode("utf-8"))
        except ValueError:
            payload = {}
        prompt = payload.get("prompt", "") if isinstance(payload, dict) else ""
        time.sleep(type(self).delay_s)
        case_id = _prompt_to_case().get(prompt, "")
        if case_id and case_id in _RIGHT_CASES:
            text = _cases.quick_case_spec(case_id).expected
        else:
            text = f"fake-reply-for:{prompt}"
        reply = json.dumps(
            {"response": text, "model": "fake-loopback"}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, *args):  # noqa: ANN001, ANN002, ANN202
        return


@pytest.fixture()
def fake_runtime(monkeypatch):
    """Real loopback HTTP server emulating the runtime endpoint (tests only)."""
    server = HTTPServer(("127.0.0.1", 0), _FakeLoopbackRuntimeHandler)
    port = server.server_address[1]
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    monkeypatch.setenv(_ENDPOINT_ENV, f"http://127.0.0.1:{port}/api/chat")
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=10)


@pytest.fixture()
def exec_state():
    """Snapshot-restore every global the executor proofs touch."""
    runner_dicts = {}
    for _name in (
        "_RUNS",
        "_PROGRESS",
        "_RUN_ROWS",
        "_RUN_HARDWARE",
        "_RUN_ADMISSION",
        "_RUN_THREADS",
    ):
        _saved = getattr(_runner, _name, None)
        runner_dicts[_name] = dict(_saved) if _saved is not None else None
    runner_active = _runner._ACTIVE_RUN_ID
    routes_had_memory = hasattr(_routes, "_LAST_CHECK_ENDPOINT")
    saved_check_endpoint = getattr(_routes, "_LAST_CHECK_ENDPOINT", None)
    store_records = dict(_cap_store._RECORDS)
    store_by_ref = dict(_cap_store._RECORDS_BY_REF)
    yield
    try:
        if _runner._ACTIVE_RUN_ID is not None:
            _runner.stop_run(_runner._ACTIVE_RUN_ID)
    except (KeyError, Exception):
        pass
    for _thread in list(getattr(_runner, "_RUN_THREADS", {}).values()):
        try:
            _thread.join(timeout=10)
        except (RuntimeError, Exception):
            pass
    threads = getattr(_runner, "_RUN_THREADS", None)
    if threads is not None:
        threads.clear()
        _saved_threads = runner_dicts.get("_RUN_THREADS")
        if _saved_threads:
            threads.update(_saved_threads)
    for _name, _saved in runner_dicts.items():
        if _name == "_RUN_THREADS" or _saved is None:
            continue
        _target = getattr(_runner, _name)
        _target.clear()
        _target.update(_saved)
    _runner._ACTIVE_RUN_ID = runner_active
    if routes_had_memory:
        _routes._LAST_CHECK_ENDPOINT = saved_check_endpoint
    _cap_store._RECORDS.clear()
    _cap_store._RECORDS.update(store_records)
    _cap_store._RECORDS_BY_REF.clear()
    _cap_store._RECORDS_BY_REF.update(store_by_ref)


def _served_client():
    """create_app + TestClient on the real served localbench entry."""
    from agent_si.backend.app import create_app
    from fastapi.testclient import TestClient

    app = create_app({"env": "test", "ui_session_token": _TOKEN})
    return TestClient(app)


def _wait_for(predicate, timeout_s, desc):
    deadline = time.monotonic() + timeout_s
    while True:
        if predicate():
            return
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {desc}")
        time.sleep(0.05)


def _start_quick(client, model_id, endpoint=None):
    payload = {"model_id": model_id, "level": "Quick"}
    if endpoint is not None:
        payload["endpoint"] = endpoint
    started = client.post(
        "/api/v1/local/bench/runs",
        json=payload,
        headers=_HEADERS,
    )
    assert started.status_code == 200, started.text
    return started.json()["run_id"]


def test_fb2b8_executor_completes_quick_served(exec_state, fake_runtime) -> None:
    """F10: served Quick run executes all 6 cases and writes MEASURED."""
    client = _served_client()
    run_id = _start_quick(client, _MODEL)
    assert _runner.run_progress(run_id).done_cases < 6
    _wait_for(
        lambda: _runner.run_progress(run_id).done_cases == 6,
        30.0,
        "done_cases==6",
    )
    rows = _runner.run_result_rows(run_id)
    assert [row.case_id for row in rows] == ["q01", "q02", "q03", "q04", "q05", "q06"]
    assert all(row.kind.value == "MEASURED" for row in rows)
    assert all(row.model_id == _MODEL for row in rows)
    scores = [row.score for row in rows]
    assert all(isinstance(score, float) and 0.0 <= score <= 1.0 for score in scores)
    by_case = {row.case_id: row for row in rows}
    for case_id in ("q01", "q03", "q05"):
        assert by_case[case_id].score == 1.0
    for case_id in ("q02", "q04", "q06"):
        assert by_case[case_id].score == 0.0
    assert len(set(scores)) > 1
    for row in rows:
        spec = _cases.quick_case_spec(row.case_id)
        assert row.expected_rule == spec.rule
        if row.case_id in _RIGHT_CASES:
            assert row.reply_excerpt == spec.expected
        else:
            assert row.reply_excerpt == f"fake-reply-for:{spec.prompt}"
    measured = _cap_store.get_evidence(_MODEL, "localbench:Quick")
    assert measured is not None
    assert measured.tier == _cap_store.EvidenceTier.MEASURED
    assert measured.sample_count == 6
    assert measured.score == pytest.approx(sum(scores) / len(scores))
    assert _cap_store.require_current(measured.evidence_ref).model_id == _MODEL
    second_id = _start_quick(client, _MODEL)
    _wait_for(
        lambda: _runner.run_progress(second_id).done_cases == 6,
        30.0,
        "second run done_cases==6",
    )
    second_scores = [row.score for row in _runner.run_result_rows(second_id)]
    assert second_scores == scores
    status = client.get("/api/v1/local/status")
    assert status.status_code == 200, status.text
    assert status.json()["status"] == "NOT_CONFIGURED"


def test_fb2b8_executor_pause_resume_served(exec_state, fake_runtime) -> None:
    """F10: the executor waits while paused and finishes after resume."""
    client = _served_client()
    run_id = _start_quick(client, _MODEL + "-pause")
    paused = client.post(
        "/api/v1/local/bench/runs/pause", json={"run_id": run_id}, headers=_HEADERS
    )
    assert paused.status_code == 200, paused.text
    assert _runner.run_progress(run_id).paused is True
    time.sleep(_CASE_DELAY_S * 2 + 0.4)
    frozen = _runner.run_progress(run_id).done_cases
    assert frozen < 6
    time.sleep(_CASE_DELAY_S * 2)
    assert _runner.run_progress(run_id).done_cases == frozen
    resumed = client.post(
        "/api/v1/local/bench/runs/resume", json={"run_id": run_id}, headers=_HEADERS
    )
    assert resumed.status_code == 200, resumed.text
    assert _runner.run_progress(run_id).paused is False
    _wait_for(
        lambda: _runner.run_progress(run_id).done_cases == 6,
        30.0,
        "resumed done_cases==6",
    )
    assert len(_runner.run_result_rows(run_id)) == 6


def test_fb2b8_executor_stop_aborts_and_frees_slot(
    exec_state, fake_runtime
) -> None:
    """F10: stop aborts at once and frees the serial slot for a fresh run."""
    client = _served_client()
    run_id = _start_quick(client, _MODEL + "-stop")
    _wait_for(
        lambda: _runner.run_progress(run_id).done_cases >= 1,
        30.0,
        "first case done",
    )
    stopped = client.post(
        "/api/v1/local/bench/runs/stop", json={"run_id": run_id}, headers=_HEADERS
    )
    assert stopped.status_code == 200, stopped.text
    assert _runner.run_progress(run_id).stopped is True
    time.sleep(_CASE_DELAY_S * 8)
    assert _runner.run_progress(run_id).done_cases < 6
    assert len(_runner.run_result_rows(run_id)) < 6
    fresh_id = _start_quick(client, _MODEL + "-stop-next")
    _wait_for(
        lambda: _runner.run_progress(fresh_id).done_cases == 6,
        30.0,
        "fresh run done_cases==6",
    )
    assert len(_runner.run_result_rows(fresh_id)) == 6


def test_fb2b8_unknown_run_is_keyerror(exec_state) -> None:
    """F10: unknown run ids stay KeyError (served stop maps to 404)."""
    with pytest.raises(KeyError):
        _runner.run_progress("run-fb2b8-unknown")
    client = _served_client()
    resp = client.post(
        "/api/v1/local/bench/runs/stop",
        json={"run_id": "run-fb2b8-unknown"},
        headers=_HEADERS,
    )
    assert resp.status_code == 404, resp.text


def test_fb2b8_executor_body_endpoint_serves_run(
    exec_state, fake_runtime, monkeypatch
) -> None:
    """F10: POST body endpoint routes the background executor (env unset)."""
    monkeypatch.delenv(_ENDPOINT_ENV, raising=False)
    client = _served_client()
    run_id = _start_quick(client, _MODEL + "-body", endpoint=fake_runtime)
    _wait_for(
        lambda: _runner.run_progress(run_id).done_cases == 6,
        30.0,
        "body-endpoint done_cases==6",
    )
    assert len(_runner.run_result_rows(run_id)) == 6


def test_fb2b8_executor_check_endpoint_fallback(
    exec_state, fake_runtime, monkeypatch
) -> None:
    """F10: last check endpoint routes the run when the body has none."""
    monkeypatch.delenv(_ENDPOINT_ENV, raising=False)
    client = _served_client()
    checked = client.get(f"/api/v1/local/bench/check?endpoint={fake_runtime}")
    assert checked.status_code == 200, checked.text
    run_id = _start_quick(client, _MODEL + "-check")
    _wait_for(
        lambda: _runner.run_progress(run_id).done_cases == 6,
        30.0,
        "check-fallback done_cases==6",
    )
    assert len(_runner.run_result_rows(run_id)) == 6


def test_fb2b8_executor_body_endpoint_wins_over_check(
    exec_state, fake_runtime, monkeypatch
) -> None:
    """F10: POST body endpoint wins over the remembered check endpoint."""
    monkeypatch.delenv(_ENDPOINT_ENV, raising=False)
    client = _served_client()
    dead = "http://127.0.0.1:1/api/chat"
    checked = client.get(f"/api/v1/local/bench/check?endpoint={dead}")
    assert checked.status_code == 200, checked.text
    run_id = _start_quick(client, _MODEL + "-wins", endpoint=fake_runtime)
    _wait_for(
        lambda: _runner.run_progress(run_id).done_cases == 6,
        30.0,
        "body-wins done_cases==6",
    )
    assert len(_runner.run_result_rows(run_id)) == 6
