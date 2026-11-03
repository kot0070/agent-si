"""FXROLEPICK R2 (backend): provider model routes answer for local ids.

GET/PUT /api/v1/providers/{ollama,lm-studio,any-openai-compatible}/models
serve the attached runtime's real names (possibly zero rows), never a
placeholder and never a cloud fetch. Nothing attached keeps the legacy
404. Role/chat saves accept served real names through the normal
allow checks.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from agent_si.providers.registry import provider_model_lists as _ml
from agent_si.providers.registry import provider_routes as _pr


class _Facade:
    def get_provider(self, provider_id):
        return None

    def list_providers(self, only=False):
        return []


def _ctx(tmp_path, names):
    return _pr.ProviderCtx(
        facade=_Facade(),
        models={},
        model_state_dir=str(tmp_path),
        local_models=(lambda pid: list(names) if pid == "ollama" else None),
    )


def test_local_models_get_serves_real_names(tmp_path):
    ctx = _ctx(tmp_path, ["llama3.2", "mistral:7b"])
    status, payload = _pr.provider_models(ctx, {"id": "ollama"}, None)
    assert status == 200
    assert payload["source"] == "local"
    assert [m["id"] for m in payload["models"]] == [
        "ollama/llama3.2", "ollama/mistral:7b"]
    assert [m["name"] for m in payload["models"]] == [
        "llama3.2", "mistral:7b"]
    assert all(m["kb_known"] is False for m in payload["models"])
    assert payload["enabled"] == []


def test_local_models_get_empty_runtime_answers_empty(tmp_path):
    ctx = _ctx(tmp_path, [])
    status, payload = _pr.provider_models(ctx, {"id": "ollama"}, None)
    assert status == 200
    assert payload["models"] == []


def test_local_models_get_unattached_keeps_404(tmp_path):
    ctx = _pr.ProviderCtx(facade=_Facade(), models={},
                          model_state_dir=str(tmp_path))
    status, _ = _pr.provider_models(ctx, {"id": "ollama"}, None)
    assert status == 404


def test_local_models_put_round_trip(tmp_path):
    ctx = _ctx(tmp_path, ["llama3.2"])
    status, payload = _pr.put_provider_models(
        ctx, {"id": "ollama"}, {"ids": ["llama3.2"]})
    assert status == 200
    assert payload["enabled"] == ["ollama/llama3.2"]
    status, payload = _pr.provider_models(ctx, {"id": "ollama"}, None)
    assert payload["enabled"] == ["ollama/llama3.2"]


def test_local_models_put_unknown_model_400(tmp_path):
    ctx = _ctx(tmp_path, ["llama3.2"])
    status, payload = _pr.put_provider_models(
        ctx, {"id": "ollama"}, {"ids": ["nope"]})
    assert status == 400
    assert "unknown model" in payload["error"]


def test_fetch_local_models_keyless_parses_openai_shape():
    body = {"data": [{"id": "b"}, {"id": "a"}, {"id": "a"}]}
    got = _ml.fetch_local_models(
        "http://localhost:11434", provider_id="ollama",
        http_get=lambda url, headers, timeout: body)
    assert got == ["a", "b"]


headers_seen = []


def _recording_get(url, headers, timeout):
    headers_seen.append(dict(headers))
    return {"data": [{"id": "x"}]}


def test_fetch_local_models_sends_no_auth_header():
    headers_seen.clear()
    _ml.fetch_local_models(
        "http://127.0.0.1:11434", provider_id="ollama",
        http_get=_recording_get)
    assert headers_seen and "Authorization" not in headers_seen[0]


def test_fetch_local_models_refuses_non_loopback():
    with pytest.raises(_ml.LiveModelsError):
        _ml.fetch_local_models(
            "https://api.example.com/v1", provider_id="ollama",
            http_get=lambda u, h, t: {"data": [{"id": "x"}]})


def test_fetch_local_models_refuses_bad_shape():
    with pytest.raises(_ml.LiveModelsError):
        _ml.fetch_local_models(
            "http://localhost:11434", provider_id="ollama",
            http_get=lambda u, h, t: {"models": []})


def _allow_ctx(tmp_path):
    from agent_si.backend import pools_routes as _prr
    from agent_si.routing import roles as _rl
    from agent_si.routing import store as _st
    store = _st.RoutingStore(str(tmp_path / "data"))
    ctx = _prr.RoutingCtx(store=store, role_table=_rl.RoleTable(store),
                          kb=None)
    ctx.model_state_dir = str(tmp_path)
    return ctx, _prr


def test_enabled_allows_served_local_name(monkeypatch, tmp_path):
    ctx, prr = _allow_ctx(tmp_path)
    monkeypatch.setattr(prr, "_local_model_names",
                        lambda pid: ["llama3.2"] if pid == "ollama"
                        else None)
    assert prr._enabled_allows(ctx, "ollama", "ollama/llama3.2") is None
    assert prr._enabled_allows(ctx, "ollama", "llama3.2") is None
    denied = prr._enabled_allows(ctx, "ollama", "ollama/bogus")
    assert denied is not None and "attached local runtime" in denied


def test_enabled_allows_unattached_local_stays_legacy(monkeypatch, tmp_path):
    ctx, prr = _allow_ctx(tmp_path)
    monkeypatch.setattr(prr, "_local_model_names", lambda pid: None)
    assert prr._enabled_allows(ctx, "ollama", "ollama/anything") is None


def test_chat_model_allows_served_local_name(monkeypatch, tmp_path):
    ctx, prr = _allow_ctx(tmp_path)
    monkeypatch.setattr(prr, "_local_model_names",
                        lambda pid: ["llama3.2"] if pid == "ollama"
                        else None)
    assert prr._chat_model_allowed(ctx, "ollama/llama3.2") is None
    denied = prr._chat_model_allowed(ctx, "ollama/bogus")
    assert denied is not None and "not enabled" in denied
