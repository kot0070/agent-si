"""PLANB Z4 (DEFECT-39): Settings > Local benchmark on a connected Ollama.

Owner seen: POST /api/v1/local/bench/runs 200, then the UI error and no
result. Causes: (1) no endpoint reached the executor (UI sends none) so the
run idled forever with no reason; (2) the executor spoke a generic body to
Ollama's root path; (3) no way to read a run's end or its reason.
Contract: the connected local runtime is the endpoint fallback and is called
the Ollama way (/api/generate, stream false, bare model name); a status route
answers running / completed / aborted with the real reason. The fake is the
runtime at the network boundary only.
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

from agent_si.backend import local_connect as _lc  # noqa: E402
from agent_si.backend import localbench_routes as _routes  # noqa: E402
from agent_si.local import bench_cases as _cases  # noqa: E402
from agent_si.local import bench_runner as _runner  # noqa: E402
from agent_si.local.bench_protocol import BenchLevel  # noqa: E402

_TOKEN = "tok-planb-z4"
_HEADERS = {"x-actor": "z4-user", "x-ui-session-token": _TOKEN}
_ENV = "AGENT_SI_BENCH_CHAT_ENDPOINT"
SEEN: list[dict] = []


def _prompt_to_case() -> dict[str, str]:
    return {_cases.quick_case_spec(c.case_id).prompt: c.case_id
            for c in _cases.list_cases(BenchLevel.Quick)}


class _OllamaLike(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
        payload = json.loads(raw.decode("utf-8"))
        SEEN.append({"path": self.path, "payload": payload})
        ok = (self.path == "/api/generate" and payload.get("stream") is False
              and payload.get("model") == "z4-model:1b")
        if not ok:
            self.send_response(404)
            self.end_headers()
            return
        case_id = _prompt_to_case().get(payload.get("prompt", ""), "")
        text = _cases.quick_case_spec(case_id).expected if case_id else "x"
        body = json.dumps({"response": text, "done": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # noqa: ANN002
        return


@pytest.fixture()
def state(monkeypatch):
    saved = {n: dict(getattr(_runner, n)) for n in
             ("_RUNS", "_PROGRESS", "_RUN_ROWS", "_RUN_HARDWARE", "_RUN_ADMISSION")}
    active = _runner._ACTIVE_RUN_ID
    attached = _lc._ATTACHED_RUNTIME
    check = getattr(_routes, "_LAST_CHECK_ENDPOINT", None)
    monkeypatch.delenv(_ENV, raising=False)
    _routes._LAST_CHECK_ENDPOINT = None
    _runner._ACTIVE_RUN_ID = None
    SEEN.clear()
    yield
    try:
        if _runner._ACTIVE_RUN_ID is not None:
            _runner.stop_run(_runner._ACTIVE_RUN_ID)
    except Exception:
        pass
    for t in list(_runner._RUN_THREADS.values()):
        t.join(timeout=10)
    for n, v in saved.items():
        target = getattr(_runner, n)
        target.clear()
        target.update(v)
    _runner._ACTIVE_RUN_ID = active
    _lc._ATTACHED_RUNTIME = attached
    _routes._LAST_CHECK_ENDPOINT = check


@pytest.fixture()
def runtime():
    server = HTTPServer(("127.0.0.1", 0), _OllamaLike)
    thread = threading.Thread(target=server.serve_forever,
                              kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    yield "http://127.0.0.1:%d" % server.server_address[1]
    server.shutdown()
    server.server_close()
    thread.join(timeout=10)


def _client():
    from agent_si.backend.app import create_app
    from fastapi.testclient import TestClient
    return TestClient(create_app({"env": "test", "ui_session_token": _TOKEN}))


def _start(client, model):
    resp = client.post("/api/v1/local/bench/runs",
                       json={"model_id": model, "level": "Quick"},
                       headers=_HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()["run_id"]


def _until_ended(client, run_id, timeout=30.0):
    end = time.monotonic() + timeout
    body = {}
    while time.monotonic() < end:
        resp = client.get("/api/v1/local/bench/runs/status",
                          params={"run_id": run_id})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if body["state"] != "running":
            return body
        time.sleep(0.05)
    raise AssertionError("run did not end: %r" % (body,))


def test_z4_connected_ollama_is_called_the_ollama_way(state, runtime):
    _lc._ATTACHED_RUNTIME = runtime
    client = _client()
    run_id = _start(client, "ollama/z4-model:1b")
    done = _until_ended(client, run_id)
    assert done["state"] == "completed", done
    assert done["done_cases"] == done["total_cases"] == 6
    assert done["reason"] == ""
    rows = client.get("/api/v1/local/bench/results",
                      params={"run_id": run_id}).json()
    assert [r["case_id"] for r in rows] == ["q01", "q02", "q03", "q04", "q05", "q06"]
    assert all(r["kind"] == "MEASURED" for r in rows)
    assert {s["path"] for s in SEEN} == {"/api/generate"}


def test_z4_no_runtime_ends_with_a_clear_reason(state):
    _lc._ATTACHED_RUNTIME = None
    client = _client()
    run_id = _start(client, "ollama/z4-model:1b")
    done = _until_ended(client, run_id)
    assert done["state"] == "aborted", done
    assert "no local runtime" in done["reason"].lower(), done
    stopped = client.post("/api/v1/local/bench/runs/stop",
                          json={"run_id": run_id}, headers=_HEADERS)
    assert stopped.status_code == 200, stopped.text
    assert _runner._ACTIVE_RUN_ID is None


def test_z4_unreachable_runtime_reason_is_real(state):
    _lc._ATTACHED_RUNTIME = "http://127.0.0.1:9"
    client = _client()
    run_id = _start(client, "ollama/z4-model:1b")
    done = _until_ended(client, run_id)
    assert done["state"] == "aborted", done
    assert "unreachable" in done["reason"], done


def test_z4_status_of_unknown_run_is_404(state):
    resp = _client().get("/api/v1/local/bench/runs/status",
                         params={"run_id": "run-nope"})
    assert resp.status_code == 404
