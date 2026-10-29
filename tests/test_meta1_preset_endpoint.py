"""META1: meta preset endpoint + bare wire model (MR-04).

Fake only at urlopen; no network.
"""

import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_SRC = _os.path.abspath(_os.path.join(_HERE, "..", "src"))
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)

import json as _json
import urllib.request as _urlrequest

from agent_si.backend.chat_stream import _gateway_transport
from agent_si.providers.registry.presets import META_CATALOGUE, get_preset


def test_preset_meta_base_host():
    preset = get_preset("meta")
    assert preset["base_url"] == "https://api.meta.ai/v1"
    assert "api.meta.ai" in preset["base_url"]
    assert "api.llama.com" not in preset["base_url"]


def test_catalogue_keeps_prefixed_id():
    assert "meta/muse-spark-1.3-contributor" in tuple(META_CATALOGUE)


def _capture_transport(monkeypatch, base_url, model):
    captured = {}

    class _FakeStore:
        def get_secret(self, _sid):
            return "test-secret-value"

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return _json.dumps({
                "choices": [{"message": {"content": "ok"},
                             "finish_reason": "stop"}],
                "usage": {},
            }).encode("utf-8")

    def _fake_urlopen(http_request, timeout=None):
        captured["url"] = http_request.full_url
        captured["body"] = _json.loads(
            http_request.data.decode("utf-8"))
        captured["auth"] = http_request.get_header("Authorization")
        return _FakeResponse()

    monkeypatch.setattr(_urlrequest, "urlopen", _fake_urlopen)
    transport = _gateway_transport(
        base_url,
        _FakeStore(),
        {"secret_id": "sid", "provider_id": "meta"},
    )
    reply = transport({
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "chat_path": "/chat/completions",
    })
    assert reply["output_text"] == "ok"
    return captured


def test_gateway_sends_bare_model_to_meta_endpoint(monkeypatch):
    preset = get_preset("meta")
    captured = _capture_transport(
        monkeypatch, preset["base_url"],
        "meta/muse-spark-1.3-contributor")
    assert captured["url"] == "https://api.meta.ai/v1/chat/completions"
    assert captured["body"]["model"] == "muse-spark-1.3-contributor"
    assert captured["auth"] == "Bearer test-secret-value"


def test_gateway_keeps_bare_model(monkeypatch):
    preset = get_preset("meta")
    captured = _capture_transport(
        monkeypatch, preset["base_url"],
        "muse-spark-1.3-contributor")
    assert captured["body"]["model"] == "muse-spark-1.3-contributor"
    assert captured["url"] == "https://api.meta.ai/v1/chat/completions"
