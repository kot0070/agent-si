"""FXROLEPICK R8 (backend): stop reason before any model call + local legs.

A run stopped before any model call ends with its reason as the
summary (code + fix link), never the no-parts verdict: no provider ->
"Connect a provider first" (NO_PROVIDER_BOUND); pinned provider with
no model -> "<Label> has no model chosen" (PROVIDER_NO_MODEL). A role
bound to a local model builds a keyless loopback leg that really
reaches the attached runtime (Ollama-native reply shapes parse).
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import json as _json
import urllib.request as _urlrequest

import pytest

from agent_si.backend import chat_stream as _chat
from agent_si.backend import local_connect as _lc
from agent_si.runtime.devrun import engine as _engine
from agent_si.runtime.devrun import roles as _roles


def test_stop_no_provider_keeps_plain_line():
    summary, code, href = _engine._stop_before_model_call(
        _roles.RoleUnbound("role 'w' has no provider: boom",
                           role="w", kind="no_provider"))
    assert summary == "Connect a provider first"
    assert code == "NO_PROVIDER_BOUND"
    assert href == "/providers"


def test_stop_no_model_names_provider():
    summary, code, href = _engine._stop_before_model_call(
        _roles.RoleUnbound("role 'w' has no provider: PINNED names no model",
                           role="w", provider="ollama", kind="no_model"))
    assert summary == "Ollama has no model chosen"
    assert code == "PROVIDER_NO_MODEL"
    assert href == "/settings/models"


def test_stop_no_model_without_provider_falls_back_to_connect():
    summary, code, _ = _engine._stop_before_model_call(
        _roles.RoleUnbound("x", role="w", kind="no_model"))
    assert (summary, code) == ("Connect a provider first",
                               "NO_PROVIDER_BOUND")


def _fake_app():
    class _Ctx:
        provider_facade = None
        credential_store = None

    class _State:
        k04_ctx = _Ctx()

    class _App:
        state = _State()

    return _App()


def test_build_adapter_local_reaches_attached_runtime(monkeypatch):
    monkeypatch.setattr(_lc, "_ATTACHED_RUNTIME",
                        "http://localhost:11434")
    adapter = _roles.build_adapter(
        _fake_app(),
        {"role": "worker", "provider": "ollama",
         "model": "ollama/llama3.2"})
    assert adapter.config.base_url == "http://localhost:11434"
    assert adapter.config.provider_id == "ollama"


def test_build_adapter_local_unattached_stays_no_provider(monkeypatch):
    monkeypatch.setattr(_lc, "_ATTACHED_RUNTIME", None)
    with pytest.raises(_roles.RoleUnbound) as caught:
        _roles.build_adapter(
            _fake_app(),
            {"role": "worker", "provider": "ollama",
             "model": "ollama/llama3.2"})
    assert caught.value.kind == "no_provider"
    assert caught.value.provider == "ollama"


def _capture(monkeypatch, body):
    captured = {}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return _json.dumps(body).encode("utf-8")

    def _fake_urlopen(http_request, timeout=None):
        captured["url"] = http_request.full_url
        captured["auth"] = http_request.get_header("Authorization")
        captured["body"] = _json.loads(
            http_request.data.decode("utf-8"))
        return _FakeResponse()

    monkeypatch.setattr(_urlrequest, "urlopen", _fake_urlopen)
    return captured


def test_transport_keyless_loopback_omits_auth(monkeypatch):
    captured = _capture(monkeypatch, {"choices": [
        {"message": {"content": "hi"}, "finish_reason": "stop"}]})
    transport = _chat._gateway_transport("http://127.0.0.1:11434", None,
                                         {})
    reply = transport({"model": "llama3.2", "messages": [],
                       "chat_path": "/api/chat"})
    assert reply["output_text"] == "hi"
    assert captured["auth"] is None
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["body"]["model"] == "llama3.2"


def test_transport_refuses_keyless_cloud(monkeypatch):
    _capture(monkeypatch, {})
    transport = _chat._gateway_transport("https://api.example.com/v1",
                                         None, {})
    with pytest.raises(Exception):
        transport({"model": "m", "messages": []})


def test_transport_parses_ollama_native_shapes(monkeypatch):
    captured = _capture(monkeypatch, {"message": {"content": "native"}})
    transport = _chat._gateway_transport("http://localhost:11434", None,
                                         {})
    assert transport({"model": "m", "messages": [],
                      "chat_path": "/api/chat"})["output_text"] == \
        "native"
    assert captured["auth"] is None
    _capture(monkeypatch, {"response": "gen"})
    assert transport({"model": "m", "messages": [],
                      "chat_path": "/api/generate"})["output_text"] == \
        "gen"
