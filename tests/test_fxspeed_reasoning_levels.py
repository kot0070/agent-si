"""FXRUNSPEED S1: reasoning level per role, muse wire models only.

Through the real stack (create_app memory store + configured budget
gate + real OpenAICompatAdapter + real gateway transport) with the
only fake at urlopen, which captures the wire body: director low,
manager low, worker max, auditor low, solo (part 'solo') low on a
muse-spark wire model; an openai model sends no reasoning field and
no max_tokens is added. The level is recorded on the ledger row.
"""
import json
import os
import sys
import urllib.request as _urlreq

_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.dirname(_HERE)
_SRC = os.path.join(_WS, "src")
for _p in (_SRC, _WS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend import chat_stream as _cs  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from agent_si.providers.adapters.base import AdapterConfig  # noqa: E402
from agent_si.providers.adapters.openai_compat import (  # noqa: E402
    OpenAICompatAdapter)
from agent_si.runtime.devrun import records as _records  # noqa: E402
from agent_si.runtime.devrun import roles as _roles  # noqa: E402

APP_TOKEN = "fxs1-app-token"
HEADERS = {"x-actor": "fxs1", "x-ui-session-token": APP_TOKEN}
PROJECT = "proj-fxs1"


def _settings(tmp_path):
    return {"store_dir": str(tmp_path / "appdata"),
            "ui_session_token": APP_TOKEN,
            "secret_store": "memory"}


def _make_client(tmp_path):
    _steplimits._reset_state()
    app = create_app(_settings(tmp_path))
    gate = app.state.k04_ctx.budget_state
    gate.configure_project(PROJECT, "USD", "100.00", "100.00", "100.00")
    return app


class _FakeStore:
    def get_secret(self, _sid):
        return "FXS1-FAKE-SECRET-not-a-real-key"


class _FakeResponse:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _canned():
    return {"choices": [{"message": {"content": "ok"},
                         "finish_reason": "stop"}],
            "usage": {"input_tokens": 3, "output_tokens": 5}}


def _secret_ref(provider_id):
    return {"secret_id": "fxs1-sid", "provider_id": provider_id,
            "type": "api-key", "scope": "providers", "source": "test",
            "created_at": "t", "last_rotated_at": "t"}


def _run_role(app, monkeypatch, captured, provider_id, model, role,
              part=None):
    def _fake_urlopen(http_request, timeout=None):
        captured["body"] = json.loads(http_request.data.decode("utf-8"))
        return _FakeResponse(_canned())

    monkeypatch.setattr(_urlreq, "urlopen", _fake_urlopen)
    ref = _secret_ref(provider_id)
    transport = _cs._gateway_transport("https://api.meta.ai/v1",
                                       _FakeStore(), ref)
    config = AdapterConfig(provider_id=provider_id, model=model,
                           secret_ref=ref,
                           base_url="https://api.meta.ai/v1")
    adapter = OpenAICompatAdapter(config, transport)
    record = {"task": "s1", "ledger": []}
    resolution = {"role": role, "provider": provider_id, "model": model}
    response, _over = _roles.invoke(
        app, adapter, resolution, [{"role": "user", "content": "hi"}],
        record=record, project_id=PROJECT, run_id="fxs1-run",
        part=part, attempt=1)
    assert response.output_text == "ok"
    row = record["ledger"][-1]
    return captured["body"], row


def test_director_sends_low_and_records_it(tmp_path, monkeypatch):
    app = _make_client(tmp_path)
    captured: dict = {}
    body, row = _run_role(app, monkeypatch, captured, "meta",
                          "muse-spark-1.3-contributor", "director")
    assert body.get("reasoning_effort") == "low", body
    assert "max_tokens" not in body, body
    assert row["reasoning_effort"] == "low", row


def test_worker_sends_max(tmp_path, monkeypatch):
    app = _make_client(tmp_path)
    captured: dict = {}
    body, row = _run_role(app, monkeypatch, captured, "meta",
                          "muse-spark-1.3-contributor", "worker",
                          part="p1")
    assert body.get("reasoning_effort") == "max", body
    assert row["reasoning_effort"] == "max", row


def test_manager_and_auditor_send_low(tmp_path, monkeypatch):
    app = _make_client(tmp_path)
    for role in ("manager", "auditor"):
        captured = {}
        body, row = _run_role(app, monkeypatch, captured, "meta",
                              "muse-spark-1.3-contributor", role)
        assert body.get("reasoning_effort") == "low", (role, body)
        assert row["reasoning_effort"] == "low", (role, row)


def test_solo_part_sends_low_on_worker_role(tmp_path, monkeypatch):
    app = _make_client(tmp_path)
    captured: dict = {}
    body, row = _run_role(app, monkeypatch, captured, "meta",
                          "muse-spark-1.3-contributor", "worker",
                          part="solo")
    assert body.get("reasoning_effort") == "low", body
    assert row["reasoning_effort"] == "low", row


def test_openai_model_sends_no_reasoning_and_no_max_tokens(
        tmp_path, monkeypatch):
    app = _make_client(tmp_path)
    captured: dict = {}
    body, row = _run_role(app, monkeypatch, captured, "openai",
                          "openai/gpt-4o", "worker", part="p1")
    assert "reasoning_effort" not in body, body
    assert "max_tokens" not in body, body
    assert row["reasoning_effort"] is None, row


def test_one_arg_fakes_keep_working_without_params():
    seen: dict = {}

    class _OneArg:
        def invoke(self, messages):
            seen["n"] = len(messages)

            class _R:
                usage = {}
            return _R()

    out = _roles.invoke_timed(_OneArg(),
                              [{"role": "user", "content": "hi"}])
    assert out is not None
    assert seen["n"] == 1
