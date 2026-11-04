"""PLANB: a local model (a few tokens per second) is never cut at 300 s."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_si.backend import chat_stream  # noqa: E402
from agent_si.runtime.devrun import roles  # noqa: E402


class _Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _seen_timeout(monkeypatch, base_url):
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["timeout"] = timeout
        body = {"choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {}}
        return _Reply(json.dumps(body).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    transport = chat_stream._gateway_transport(
        base_url, None, {"secret_id": "", "provider_id": "ollama"})
    transport({"model": "ollama/m", "messages": [
        {"role": "user", "content": "hi"}], "chat_path": "/v1/chat/completions"})
    return seen["timeout"]


def test_loopback_transport_waits_at_least_an_hour(monkeypatch):
    assert _seen_timeout(monkeypatch, "http://localhost:11434") >= 3600


def test_cloud_transport_keeps_its_short_bound(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["timeout"] = timeout
        raise OSError("stop here")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    transport = chat_stream._gateway_transport(
        "https://example.invalid", SimpleNamespace(), {"secret_id": ""})
    try:
        transport({"model": "x", "messages": []})
    except Exception:
        pass
    assert "timeout" not in seen or seen["timeout"] == 300


def test_call_bound_allows_an_hour_and_local_role_defaults_to_it(monkeypatch):
    assert roles._clamp_timeout(3600) == 3600.0
    assert roles._clamp_timeout(None) == roles._CALL_TIMEOUT_S == 300.0
    captured = []

    def fake_invoke_timed(adapter, messages, **kwargs):
        captured.append(kwargs.get("timeout_s"))
        return SimpleNamespace(content="ok", usage={})

    monkeypatch.setattr(roles, "invoke_timed", fake_invoke_timed)
    monkeypatch.setattr(roles, "admit_role_call", lambda *a, **k: None)
    monkeypatch.setattr(roles, "_cap_block", lambda *a, **k: None)
    app = SimpleNamespace(state=SimpleNamespace())
    for provider in ("ollama", "openai"):
        try:
            roles.invoke_owned(
                app, object(), {"role": "worker", "provider": provider,
                                "model": "m"}, [], record={},
                project_id="p", run_id="r")
        except Exception:
            pass
    assert captured[0] >= 3600
    assert captured[1] is None


def _sent_body(monkeypatch, model):
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return _Reply(json.dumps({"message": {"role": "assistant", "content": "ok"}}).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    transport = chat_stream._gateway_transport(
        "http://localhost:11434", None, {"secret_id": "", "provider_id": "ollama"})
    transport({"model": model, "messages": [{"role": "user", "content": "hi"}],
               "chat_path": "/api/chat"})
    return seen["body"]


def test_muse_glimmer_gets_thinking_off_and_8k_window(monkeypatch):
    body = _sent_body(monkeypatch, "ollama/muse-glimmer:30b")
    assert body["think"] is False
    assert body["options"]["num_ctx"] == 8192
    assert body["model"] == "muse-glimmer:30b"


def test_other_local_models_get_no_think_field(monkeypatch):
    body = _sent_body(monkeypatch, "ollama/qwen3:8b")
    assert "think" not in body and "options" not in body
