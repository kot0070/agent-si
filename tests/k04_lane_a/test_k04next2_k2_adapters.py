"""K04NEXT2 K2 (CODER-2 Osprey) adapter unit tests: in-lane slices of
[M-R-ANY-API] and [HD-PROVIDERS].

RED-first: every test below drives NEW adapter API
(legs.build_any_api_adapter, facades.bound_provider_ids), so the whole
file fails before the product fix and passes after. Fixture transports
live only in this file (repo-wide FakeTransport pattern); stdlib +
pytest only; no network, no keys (id-only SecretRefs).

Row-definition sources (quoted, read-only search mode:regex):
- tests/k04_lane_a/test_adapters.py:4: generic OpenAI-compatible adapter
  plus one leg per provider.
- tests/k04_lane_a/test_adapters.py:356: LiteLLM-backed path part.
- tests/k04_lane_a/test_registry.py:27,115,130 [M-R-ANY-API]: generic
  OpenAI-compatible preset takes a caller base_url; ref mandatory.
- tests/k04_lane_a/test_registry.py:28,91,100 [HD-PROVIDERS]: presets
  never self-register, nothing default. The registry module itself
  (src/agent_si/providers/registry/) sits outside this lane's globs, so
  this file proves only the in-lane adapters slice: importing and
  calling the adapter layer binds nothing and defaults nothing.
- M-D-D26 / M-D-D28: no in-tree definition found workspace-wide
  (search mode:regex `M-D-D26|M-D-D28` over tests/ plus src/ matched no
  files); marked NOT-DONE waits-for-definition in RETURN_K2.md, never
  invented here, so no test claims them.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from agent_si.providers.adapters import facades as facades_mod
from agent_si.providers.adapters import legs as legs_mod
from agent_si.providers.adapters.base import (
    AdapterConfigError,
    make_secret_ref,
)
from agent_si.providers.adapters.openai_compat import OpenAICompatAdapter


@pytest.fixture(autouse=True)
def _clean_lane_state():
    facades_mod.clear_provider_bindings()
    facades_mod.clear_adapter_transports()
    yield
    facades_mod.clear_provider_bindings()
    facades_mod.clear_adapter_transports()


def _secret(provider_id="openai_compatible"):
    return make_secret_ref(
        secret_id="k2-secret-1",
        provider_id=provider_id,
        type="api_key",
        scope="provider",
        source="secret_store",
    )


class _FakeTransport:
    def __init__(self):
        self.requests = []

    def __call__(self, request):
        self.requests.append(dict(request))
        return {
            "output_text": "k2 canned",
            "finish": "stop",
            "usage": {"input_tokens": 4, "output_tokens": 2},
        }


# [M-R-ANY-API]-part: generic any-API adapter serves the caller base_url.
def test_k2_any_api_serves_caller_base_url_verbatim():
    transport = _FakeTransport()
    adapter = legs_mod.build_any_api_adapter(
        "Exact-Model_K2-7", _secret(), "https://caller.example/v1",
        transport)
    assert isinstance(adapter, OpenAICompatAdapter)
    assert adapter.openai_compat is True
    assert adapter.config.provider_id == "openai_compatible"
    assert adapter.config.model == "Exact-Model_K2-7"
    response = adapter.invoke([{"role": "user", "content": "hi"}])
    assert response.mock is False
    assert response.model == "Exact-Model_K2-7"
    assert response.usage["input_tokens"] == 4
    assert transport.requests[0]["base_url"] == "https://caller.example/v1"
    assert transport.requests[0]["model"] == "Exact-Model_K2-7"
    descriptor = adapter.transport_descriptor()
    assert descriptor["endpoint"] == "https://caller.example/v1"
    assert descriptor["openai_compat"] is True


# [M-R-ANY-API]-part: caller base_url is mandatory at build time.
def test_k2_any_api_refuses_empty_base_url_at_build():
    with pytest.raises(AdapterConfigError):
        legs_mod.build_any_api_adapter(
            "m", _secret(), "", _FakeTransport())
    with pytest.raises(AdapterConfigError):
        legs_mod.build_any_api_adapter(
            "m", _secret(), None, _FakeTransport())


# [M-R-ANY-API]-part: model and ref are mandatory, never baked in.
def test_k2_any_api_refuses_empty_model_and_bad_secret():
    with pytest.raises(AdapterConfigError):
        legs_mod.build_any_api_adapter(
            "", _secret(), "https://caller.example/v1",
            _FakeTransport())
    raw = dict(_secret())
    del raw["secret_id"]
    with pytest.raises(AdapterConfigError):
        legs_mod.build_any_api_adapter(
            "m", raw, "https://caller.example/v1", _FakeTransport())
    leaky = dict(_secret())
    leaky["value"] = "SHOULD-NEVER-BE-STORED"
    with pytest.raises(AdapterConfigError):
        legs_mod.build_any_api_adapter(
            "m", leaky, "https://caller.example/v1", _FakeTransport())


# Negative probe by design: unknown providers stay rejected.
def test_k2_unknown_provider_rejected_by_design():
    with pytest.raises(AdapterConfigError):
        legs_mod.build_leg("not-a-provider", "m", _secret("openai"),
                           transport=_FakeTransport())
    with pytest.raises(AdapterConfigError):
        legs_mod.build_leg("OpenAI_Compatible", "m", _secret("openai"),
                           transport=_FakeTransport())
    with pytest.raises(AdapterConfigError):
        legs_mod.leg_descriptor("no-such-leg")


# [HD-PROVIDERS]-part: nothing configured, none default, through a
# public route (ids only, never secret material).
def test_k2_bound_ids_empty_when_nothing_configured():
    assert facades_mod.bound_provider_ids() == []


# [HD-PROVIDERS]-part: explicit binds list verbatim; clear restores none.
def test_k2_bound_ids_lists_binds_without_secret_material():
    facades_mod.bind_provider(
        "groq", _secret("groq"), _FakeTransport(),
        "https://loopback.example/v1")
    facades_mod.bind_provider(
        "mistral", _secret("mistral"), _FakeTransport(),
        "https://loopback.example/v1", instance_id="i2")
    assert facades_mod.bound_provider_ids() == [
        {"provider_id": "groq", "instance_id": "default"},
        {"provider_id": "mistral", "instance_id": "i2"},
    ]
    for entry in facades_mod.bound_provider_ids():
        assert set(entry) == {"provider_id", "instance_id"}
    facades_mod.disconnect_provider("groq")
    assert facades_mod.bound_provider_ids() == [
        {"provider_id": "mistral", "instance_id": "i2"}]
    facades_mod.clear_provider_bindings()
    assert facades_mod.bound_provider_ids() == []