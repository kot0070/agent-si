import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import ast
import inspect
import pathlib

import pytest

from agent_si.providers.registry.contracts import SecretRef
from agent_si.providers.registry.presets import get_preset
from agent_si.providers.registry.provider_api import (
    CONFIRM_REQUIRED,
    CREDENTIAL_ENTRY_MISSING,
    LEFTOVER_RULES,
    LIVE_LINKED,
    NON_DEFAULT_EXAMPLE,
    NOT_FOUND,
    NOT_OWN_PREFIX,
    PROVIDER_UNEVIDENCED,
    TOKEN_REQUIRED,
    ProviderAPI,
    ProviderContracts,
    list_leftover_keys,
    request_delete_entry,
)
from agent_si.providers.registry.registry import ProviderRegistry

LOOPBACK = "http://127.0.0.1:9/v1"


# FAKE-OF: provisioning-gateway secret store (port: agent_si.providers.registry.provider_api.ProviderAPI)
class FakeCredentialStore:
    """In-repo fake store: has/delete only on the product path."""

    def __init__(self):
        self._entries = {}

    def seed(self, secret_id, payload="fake-entry"):
        self._entries[secret_id] = payload

    def has(self, secret_id):
        return secret_id in self._entries

    def delete(self, secret_id):
        if secret_id not in self._entries:
            raise KeyError(secret_id)
        del self._entries[secret_id]


# FAKE-OF: audit backend (port: agent_si.providers.registry.provider_api.ProviderAPI)
class FakeAuditSink:
    """In-repo fake audit sink: records appended dicts."""

    def __init__(self):
        self.records = []

    def append(self, record):
        self.records.append(dict(record))


def _ref(provider="openai", secret="s-1"):
    return SecretRef(secret_id=secret, provider_id=provider)


def _descriptor(provider="openai", ptype=None, base_url=LOOPBACK, **kw):
    desc = {
        "provider_id": provider,
        "type": ptype or provider,
        "base_url": base_url,
    }
    desc.update(kw)
    return desc


def _api(usage_probe=None):
    reg = ProviderRegistry()
    store = FakeCredentialStore()
    sink = FakeAuditSink()
    return ProviderAPI(reg, store, sink, usage_probe=usage_probe), store, sink, reg


def test_register_get_roundtrip():
    api, store, sink, reg = _api()
    view = api.register_provider(
        _descriptor(), _ref(), model="gpt-fake-1")
    assert isinstance(view, ProviderContracts)
    assert view.provider_id == "openai"
    assert view.type == "openai"
    assert view.base_url == LOOPBACK
    assert view.secret_ref.secret_id == "s-1"
    assert view.evidenced is False
    back = api.get_provider("openai")
    assert back is not None and back.provider_id == "openai"


def test_register_accepts_object_and_mapping_descriptor():
    api, store, sink, reg = _api()
    obj = ProviderContracts(
        provider_id="mistral", type="mistral",
        base_url=LOOPBACK, secret_ref=_ref("mistral", "s-m"))
    view = api.register_provider(obj, model="m-1")
    assert view.secret_ref.secret_id == "s-m"
    assert api.get_provider("mistral") is not None


def test_register_validates_nonempty_fields():
    api, store, sink, reg = _api()
    for field in ("provider_id", "type", "base_url"):
        bad = _descriptor()
        bad[field] = ""
        with pytest.raises(ValueError):
            api.register_provider(bad, _ref(), model="m-1")


def test_register_resolves_ref_from_descriptor():
    api, store, sink, reg = _api()
    desc = _descriptor(secret_ref=_ref("openai", "s-9"))
    view = api.register_provider(desc, model="m-1")
    assert view.secret_ref.secret_id == "s-9"


def test_register_rejects_inline_key_material():
    api, store, sink, reg = _api()
    bad = _descriptor(api_key="sk-fake-1")
    with pytest.raises(ValueError) as excinfo:
        api.register_provider(bad, _ref(), model="m-1")
    assert "api_key" in str(excinfo.value)
    nested = _descriptor(
        secret_ref={"secret_id": "s-2", "provider_id": "openai",
                    "api_key": "sk-fake-2"})
    with pytest.raises(ValueError) as excinfo:
        api.register_provider(nested, model="m-1")
    assert "api_key" in str(excinfo.value)


def test_get_provider_exact_match_no_casefold():
    api, store, sink, reg = _api()
    api.register_provider(_descriptor(), _ref(), model="gpt-fake-1")
    assert api.get_provider("openai") is not None
    assert api.get_provider("OPENAI") is None
    assert api.get_provider("OpenAI") is None
    assert reg.lookup("openai", "GPT-FAKE-1") is None


def test_list_providers_stable_sorted_and_evidenced_filter():
    api, store, sink, reg = _api()
    for pid in ("mistral", "openai", "anthropic"):
        api.register_provider(
            _descriptor(pid, base_url=LOOPBACK), _ref(pid, "s-" + pid),
            model="m-" + pid)
    ids = [v.provider_id for v in api.list_providers()]
    assert ids == ["anthropic", "mistral", "openai"]
    assert api.list_providers(only_evidenced=True) == []
    api2, store2, sink2, reg2 = _api()
    api2.register_provider(
        _descriptor("openai"), _ref(), model="m-1", evidence_ref="ev-1")
    api2.register_provider(
        _descriptor("mistral"), _ref("mistral", "s-m"), model="m-2")
    assert [v.provider_id for v in api2.list_providers(True)] == ["openai"]
    assert api2.is_evidenced("openai") is True
    assert api2.is_evidenced("mistral") is False
    assert api2.is_evidenced("nope") is False


def test_b04_unevidenced_view_surfaces_frozen_code():
    api, store, sink, reg = _api()
    view = api.register_provider(
        _descriptor(), _ref(), model="m-b04")
    assert view.evidenced is False
    assert api.is_evidenced("openai") is False
    assert PROVIDER_UNEVIDENCED in repr(view)
    assert view.describe()["evidenced"] is False
    api2, store2, sink2, reg2 = _api()
    proved = api2.register_provider(
        _descriptor(), _ref(), model="m-b04", evidence_ref="ev-b04")
    assert proved.evidenced is True
    assert api2.is_evidenced("openai") is True
    assert PROVIDER_UNEVIDENCED not in repr(proved)


def test_evidence_gates_routing_eligibility():
    api, store, sink, reg = _api()
    api.register_provider(_descriptor(), _ref(), model="gpt-fake-1")
    api.record_health("openai", "default", "ONLINE")
    assert reg.is_routing_eligible("openai", "gpt-fake-1") is False
    api2, store2, sink2, reg2 = _api()
    api2.register_provider(
        _descriptor(), _ref(), model="gpt-fake-1", evidence_ref="ev-1")
    api2.record_health("openai", "default", "ONLINE")
    assert reg2.is_routing_eligible("openai", "gpt-fake-1") is True
    rows = {r["provider"]: r for r in reg2.matrix()}
    assert rows["openai"]["credential"] == "MEASURED"


def test_record_health_latest_wins_per_instance():
    api, store, sink, reg = _api()
    api.register_provider(_descriptor(), _ref(), model="m-1")
    api.record_health("openai", "default", "ONLINE")
    api.record_health("openai", "default", "OFFLINE")
    view = api.record_health("openai", "default", "ONLINE")
    assert view.health == "ONLINE"
    assert reg.provider_status("openai", "default") == "ONLINE"
    view2 = api.record_health("openai", None, "DEGRADED")
    assert view2.health == "DEGRADED"
    with pytest.raises(ValueError):
        api.record_health("openai", "default", "SLEEPING")


def test_provider_online_is_not_model_ready():
    api, store, sink, reg = _api()
    api.register_provider(_descriptor(), _ref(), model="gpt-fake-1")
    api.record_health("openai", "default", "ONLINE")
    assert reg.model_status("openai", "gpt-fake-1") == "UNKNOWN"
    reg.record_model_health("openai", "gpt-fake-1", "READY")
    assert reg.model_status("openai", "gpt-fake-1") == "READY"


def test_remove_provider_deletes_store_entry():
    api, store, sink, reg = _api()
    store.seed("s-1")
    api.register_provider(_descriptor(), _ref(), model="m-1")
    assert api.remove_provider("openai") is None
    assert api.get_provider("openai") is None
    assert api.list_providers() == []
    assert store.has("s-1") is False
    assert reg.instances() == []
    assert reg.lookup("openai", "m-1") is None


def test_remove_provider_missing_store_entry():
    api, store, sink, reg = _api()
    api.register_provider(_descriptor(), _ref(), model="m-1")
    with pytest.raises(ValueError) as excinfo:
        api.remove_provider("openai")
    assert CREDENTIAL_ENTRY_MISSING in str(excinfo.value)
    assert api.get_provider("openai") is not None


def test_secret_ref_only_in_repr_and_views():
    api, store, sink, reg = _api()
    view = api.register_provider(
        _descriptor(secret_ref=_ref("openai", "s-1")), model="m-1")
    blob = repr(view) + str(view.describe())
    assert "s-1" in blob
    assert "sk-fake" not in blob
    assert "value" not in view.describe()["secret_ref"]
    assert not hasattr(view.secret_ref, "value")


def test_exact_model_ids_verbatim():
    api, store, sink, reg = _api()
    api.register_provider(_descriptor(), _ref(), model="Exact-Model_Id-7")
    contract = reg.lookup("openai", "Exact-Model_Id-7")
    assert contract is not None
    assert contract.models == ("Exact-Model_Id-7",)
    assert reg.lookup("openai", "exact-model_id-7") is None


def test_dev_id_never_a_default():
    assert NON_DEFAULT_EXAMPLE == "meta/muse-spark-1.3-contributor"
    for _, obj in inspect.getmembers(ProviderAPI, predicate=inspect.isfunction):
        for param in inspect.signature(obj).parameters.values():
            if param.default is not inspect.Parameter.empty:
                assert "muse-spark" not in str(param.default)
    api, store, sink, reg = _api()
    assert api.list_providers() == []
    assert reg.lookup("meta", NON_DEFAULT_EXAMPLE) is None


def test_usage_probe_partial_and_streaming_separate():
    from agent_si.providers.adapters.usage_probe import probe_adapter
    api, store, sink, reg = _api(usage_probe=probe_adapter)
    api.register_provider(_descriptor(), _ref(), model="m-1")

    # FAKE-OF: agent_si.providers.adapters.usage_probe (usage transport port)
    def base_transport(request):
        return {"usage": {"input_tokens": 5},
                "raw": {"input_tokens": 5}, "raw_safe": True}

    result = api.probe_usage("openai", "default", usage_transport=base_transport)
    assert result["state"] == "PARTIAL"
    assert result["input_tokens"] == 5
    assert result["output_tokens"] == "UNAVAILABLE"
    assert result["stream_usage"] == "UNAVAILABLE"

    # FAKE-OF: agent_si.providers.adapters.usage_probe (usage transport port) (stream)
    def stream_transport(request):
        return {"usage": {"input_tokens": 5, "output_tokens": 3,
                          "cached_tokens": 0, "reasoning_tokens": 0}}

    both = api.probe_usage("openai", "default",
                           usage_transport=base_transport,
                           stream_transport=stream_transport)
    assert both["stream_usage"] != "UNAVAILABLE"
    assert both["stream_usage"]["input_tokens"] == 5
    assert both["output_tokens"] == "UNAVAILABLE"


def test_mock_flag_marks_traffic():
    api, store, sink, reg = _api()
    store.seed("s-mock")
    view = api.register_provider(
        _descriptor("mocky", base_url=LOOPBACK), _ref("mocky", "s-mock"),
        model="Mock-Model-1", mock=True)
    assert view.mock is True
    assert reg.downstream_mark("mocky", "default")["mock"] is True
    from agent_si.providers.adapters.base import AdapterConfig, make_secret_ref
    from agent_si.providers.adapters.mock_provider import MockProviderAdapter
    config = AdapterConfig(provider_id="mock", model="Mock-Model-1",
                           secret_ref=make_secret_ref("s-9", "mock"))
    adapter = MockProviderAdapter(config)
    response = adapter.invoke([{"role": "user", "content": "hi"}])
    assert response.mock is True
    assert response.to_record()["mock"] is True


def test_preset_connect_fills_id_type_base_url_from_key():
    api, store, sink, reg = _api()
    preset = get_preset("openai")
    view = api.connect_via_preset("openai", _ref("openai"), model="m-9")
    assert view.provider_id == preset["provider_id"]
    assert view.type == preset["provider_type"]
    assert view.base_url == preset["base_url"]
    assert api.get_provider("openai") is not None
    with pytest.raises(KeyError):
        api.connect_via_preset("OPENAI", _ref("openai"), model="m-9")
    with pytest.raises(KeyError):
        api.connect_via_preset("no-such-preset", _ref("x"), model="m-9")


def test_leftover_144_lists_own_prefix_only():
    store_view = {
        "app:one": {"last_used_at": "2026-10-20", "extra": "x"},
        "app:two": {"last_used_at": "2026-10-21"},
        "other:key": {"last_used_at": "2026-10-22"},
    }
    result = list_leftover_keys(store_view, "app:")
    assert [e["name"] for e in result["entries"]] == ["app:one", "app:two"]
    assert set(result["entries"][0]) == {"name", "last_used_at"}
    outcome = request_delete_entry(
        dict(store_view), FakeAuditSink(), name="other:key", app_prefix="app:",
        confirmed=True, session_token="tok", live_provider_ids=set(),
        reason="cleanup")
    assert outcome["removed"] is False
    assert outcome["reason"] == NOT_OWN_PREFIX
    assert outcome["rule"] == "M-P4-144"


def test_leftover_145_names_dates_only_missing_not_found():
    store_view = {
        "app:one": {"last_used_at": "2026-10-20", "token": "must-strip"},
    }
    result = list_leftover_keys(store_view, "app:")
    assert result == {"entries": [{"name": "app:one",
                                   "last_used_at": "2026-10-20"}]}
    store = dict(store_view)
    sink = FakeAuditSink()
    outcome = request_delete_entry(
        store, sink, name="app:gone", app_prefix="app:",
        confirmed=True, session_token="tok", live_provider_ids=set(),
        reason="cleanup")
    assert outcome["removed"] is False
    assert outcome["reason"] == NOT_FOUND
    assert outcome["rule"] == "M-P4-145"
    assert store == store_view
    assert sink.records == []


def test_leftover_146_live_linked_never_deletable():
    store = {"app:openai": {"last_used_at": "2026-10-20"}}
    sink = FakeAuditSink()
    outcome = request_delete_entry(
        store, sink, name="app:openai", app_prefix="app:",
        confirmed=True, session_token="tok",
        live_provider_ids={"app:openai"}, reason="cleanup")
    assert outcome["removed"] is False
    assert outcome["reason"] == LIVE_LINKED
    assert outcome["rule"] == "M-P4-146"
    assert "app:openai" in store
    assert sink.records == []


def test_leftover_147_confirm_and_token_required():
    store = {"app:one": {"last_used_at": "2026-10-20"}}
    sink = FakeAuditSink()
    refused = request_delete_entry(
        store, sink, name="app:one", app_prefix="app:",
        confirmed=False, session_token="tok", live_provider_ids=set(),
        reason="cleanup")
    assert refused["removed"] is False
    assert refused["reason"] == CONFIRM_REQUIRED
    assert refused["rule"] == "M-P4-147"
    refused2 = request_delete_entry(
        store, sink, name="app:one", app_prefix="app:",
        confirmed=True, session_token="", live_provider_ids=set(),
        reason="cleanup")
    assert refused2["removed"] is False
    assert refused2["reason"] == TOKEN_REQUIRED
    assert "app:one" in store
    assert sink.records == []


def test_leftover_148_audit_logged_by_entry_name():
    store = {"app:one": {"last_used_at": "2026-10-20"}}
    sink = FakeAuditSink()
    outcome = request_delete_entry(
        store, sink, name="app:one", app_prefix="app:",
        confirmed=True, session_token="tok-1", live_provider_ids=set(),
        reason="user-confirmed-cleanup")
    assert outcome == {"removed": True, "entry": "app:one"}
    assert "app:one" not in store
    assert len(sink.records) == 1
    record = sink.records[0]
    assert record["entry"] == "app:one"
    assert record["reason"] == "user-confirmed-cleanup"
    assert record["at"]


def test_leftover_149_fakes_only_and_rule_map_verbatim():
    for rule in ("M-P4-144", "M-P4-145", "M-P4-146",
                 "M-P4-147", "M-P4-148", "M-P4-149"):
        assert rule in LEFTOVER_RULES
    store = FakeCredentialStore()
    assert isinstance(store, FakeCredentialStore)
    assert "gateway" in LEFTOVER_RULES["M-P4-149"]


def test_product_hygiene_no_banned_imports_or_paths():
    path = pathlib.Path(_SRC, "agent_si", "providers",
                        "registry", "provider_api.py")
    text = path.read_text(encoding="utf-8")
    assert "C:\\" not in text
    assert "C:/" not in text
    assert "/home/" not in text
    assert "/Users/" not in text
    tree = ast.parse(text)
    banned = {"litellm", "openai", "anthropic", "httpx", "requests",
              "pydantic", "boto3", "google", "mistralai", "groq", "ollama"}
    allowed = set(sys.stdlib_module_names) | {"agent_si", "__future__"}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                assert top in allowed, alias.name
                assert top not in banned, alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            top = (node.module or "").split(".")[0]
            assert top in allowed, node.module
            assert top not in banned, node.module
    assert "adapters" not in text or "never import" in text.lower()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = ""
            if isinstance(node, ast.Import):
                names = " ".join(a.name for a in node.names)
            else:
                names = node.module or ""
            assert "adapters" not in names
    assert text.count("meta/muse-spark-1.3-contributor") == 1

# --- K04-A1FIXC D10/D11/D12/D9 facade tests (strict lane K04-A1) ---
# New thin-real-facade surface: module-level frozen signatures delegating
# to ProviderAPI (D10), adapter transport registry + probing (D11), server
# bindings + leg mapping (D12), provider HTTP routes (D9).

import inspect as _inspect

from agent_si.routing import interface as _IF
from agent_si.providers.registry import facades as _reg_facades
from agent_si.providers.adapters import facades as _adp_facades
from agent_si.providers.registry import provider_routes as _routes
from agent_si.providers.adapters import legs as _legs
from agent_si.providers.adapters import usage_probe as _uprobes


def _stub_params(_name):
    return [
        _p.name
        for _p in _inspect.signature(getattr(_IF, _name)).parameters.values()
        if _p.kind
        in (
            _p.POSITIONAL_ONLY,
            _p.POSITIONAL_OR_KEYWORD,
            _p.KEYWORD_ONLY,
        )
    ]


def _fn_params(_fn):
    return [
        _p.name
        for _p in _inspect.signature(_fn).parameters.values()
        if _p.kind
        in (
            _p.POSITIONAL_ONLY,
            _p.POSITIONAL_OR_KEYWORD,
            _p.KEYWORD_ONLY,
        )
    ]


def _fn_defaults(_fn):
    return [
        _p.default
        for _p in _inspect.signature(_fn).parameters.values()
        if _p.kind
        in (
            _p.POSITIONAL_ONLY,
            _p.POSITIONAL_OR_KEYWORD,
            _p.KEYWORD_ONLY,
        )
    ]


# D10-part: module-level frozen signatures over ProviderAPI.


def test_d10_facade_signatures_exact_vs_stub():
    assert _fn_params(_reg_facades.register_provider) == [
        "descriptor",
        "secret_ref",
    ]
    assert _fn_params(_reg_facades.get_provider) == ["provider_id"]
    assert _fn_params(_reg_facades.list_providers) == ["only_evidenced"]
    assert _fn_params(_reg_facades.record_health) == [
        "provider_id",
        "provider_instance",
        "health",
    ]
    assert _fn_params(_reg_facades.remove_provider) == ["provider_id"]
    for _name in (
        "register_provider",
        "get_provider",
        "list_providers",
        "record_health",
        "remove_provider",
    ):
        assert _fn_params(getattr(_reg_facades, _name)) == _stub_params(_name)
        assert all(
            _d is _inspect.Parameter.empty
            for _d in _fn_defaults(getattr(_reg_facades, _name))
        )


def test_d10_facade_functions_are_module_level():
    for _name in (
        "register_provider",
        "get_provider",
        "list_providers",
        "record_health",
        "remove_provider",
    ):
        assert "." not in getattr(_reg_facades, _name).__qualname__, _name


def _configured_api():
    _reg_facades.configure(None)
    _reg = ProviderRegistry()
    _store = FakeCredentialStore()
    _sink = FakeAuditSink()
    _api = ProviderAPI(_reg, _store, _sink)
    _reg_facades.configure(_api)
    return _api, _store, _reg


def test_d10_facade_delegates_register_get_list():
    _api, _store, _reg = _configured_api()
    try:
        _view = _reg_facades.register_provider(
            dict(_descriptor(), model="m-1"), _ref()
        )
        assert isinstance(_view, ProviderContracts)
        assert _view.provider_id == "openai"
        assert _reg_facades.get_provider("openai") is not None
        assert _reg_facades.get_provider("OPENAI") is None
        assert [
            _v.provider_id for _v in _reg_facades.list_providers(False)
        ] == ["openai"]
        assert _reg_facades.list_providers(True) == []
    finally:
        _reg_facades.configure(None)


def test_d10_facade_health_and_remove_roundtrip():
    _api, _store, _reg = _configured_api()
    try:
        _store.seed("s-1")
        _reg_facades.register_provider(
            dict(_descriptor(), model="m-1"), _ref()
        )
        _view = _reg_facades.record_health("openai", "default", "ONLINE")
        assert _view.health == "ONLINE"
        assert _reg_facades.remove_provider("openai") is None
        assert _reg_facades.get_provider("openai") is None
    finally:
        _reg_facades.configure(None)


def test_d10_facade_lazy_default_backing():
    _reg_facades.configure(None)
    try:
        assert _reg_facades.get_provider("no-such-provider") is None
        assert _reg_facades.list_providers(False) == []
    finally:
        _reg_facades.configure(None)


# D11-part: frozen probe_usage(adapter_id, provider_id, streaming).


def test_d11_probe_signature_exact_vs_stub():
    assert _fn_params(_adp_facades.probe_usage) == [
        "adapter_id",
        "provider_id",
        "streaming",
    ]
    assert _fn_params(_adp_facades.probe_usage) == _stub_params("probe_usage")
    assert all(
        _d is _inspect.Parameter.empty
        for _d in _fn_defaults(_adp_facades.probe_usage)
    )


def _full_usage_reply(_request):
    # FAKE-OF: agent_si.providers.adapters.usage_probe (usage transport port)
    return {
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "cached_tokens": 2,
            "reasoning_tokens": 0,
        },
        "raw": {
            "input_tokens": 10,
            "output_tokens": 5,
            "cached_tokens": 2,
            "reasoning_tokens": 0,
        },
        "raw_safe": True,
    }


def _register_openai_pair(_stream=True):
    _adp_facades.register_adapter_transports(
        "openai",
        _full_usage_reply,
        _full_usage_reply if _stream else None,
    )


def test_d11_probe_non_streaming_keys_exact_order():
    _register_openai_pair()
    try:
        _cap = _adp_facades.probe_usage("openai", "openai", False)
        assert tuple(_cap.keys()) == tuple(_uprobes.USAGE_CAPABILITY_FIELDS)
        assert _cap["state"] == "VERIFIED"
        assert _cap["input_tokens"] == 10
        assert _cap["stream_usage"] == "UNAVAILABLE"
    finally:
        _adp_facades.clear_adapter_transports()


def test_d11_probe_streaming_genuinely_probed():
    _register_openai_pair()
    try:
        _both = _adp_facades.probe_usage("openai", "openai", True)
        assert _both["state"] == "VERIFIED"
        assert _both["stream_usage"] != "UNAVAILABLE"
        assert _both["stream_usage"]["output_tokens"] == 5
    finally:
        _adp_facades.clear_adapter_transports()


def test_d11_probe_fail_closed():
    _register_openai_pair(_stream=False)
    try:
        with pytest.raises(ValueError):
            _adp_facades.probe_usage("no-such-adapter", "openai", False)
        with pytest.raises(ValueError):
            _adp_facades.probe_usage("openai", "openai", True)
    finally:
        _adp_facades.clear_adapter_transports()


# D12-part: frozen resolve_model(provider_id, model).


def test_d12_resolve_signature_exact_vs_stub():
    assert _fn_params(_adp_facades.resolve_model) == ["provider_id", "model"]
    assert _fn_params(_adp_facades.resolve_model) == _stub_params(
        "resolve_model"
    )


def test_d12_resolve_unbound_raises():
    _adp_facades.clear_provider_bindings()
    with pytest.raises(ValueError):
        _adp_facades.resolve_model("openai", "m-1")


def test_d12_resolve_bound_verbatim_with_leg_fields():
    _adp_facades.clear_provider_bindings()
    try:
        _ref = {
            "secret_id": "s-1",
            "provider_id": "openai",
            "type": "api_key",
            "scope": "provider",
            "source": "secret_store",
        }
        _adp_facades.bind_provider(
            "openai", _ref, _full_usage_reply, "https://api.example/v1"
        )
        _row = _adp_facades.resolve_model("openai", "MiXeD-CaSe_Model-9")
        assert set(_row) == {"provider_id", "model_id", "fields"}
        assert _row["provider_id"] == "openai"
        assert _row["model_id"] == "MiXeD-CaSe_Model-9"
        _leg = _legs.leg_descriptor("openai")
        assert _row["fields"]["chat_path"] == _leg["chat_path"]
        assert _row["fields"]["route_params"] == _leg["route_params"]
        assert _row["fields"]["capabilities"] == _leg["capabilities"]
        assert _row["fields"]["endpoint"] == "https://api.example/v1"
        assert _row["fields"]["secret_id"] == "s-1"
        assert _row["fields"]["evidence_ref"]
        assert _row["fields"]["source"]
        assert _row["fields"]["retrieved_at"]
    finally:
        _adp_facades.clear_provider_bindings()


def test_d12_resolve_rejects_unknown_and_recased_ids():
    _adp_facades.clear_provider_bindings()
    with pytest.raises(ValueError):
        _adp_facades.resolve_model("no-such-provider", "m-1")
    with pytest.raises(ValueError):
        _adp_facades.bind_provider(
            "OPENAI",
            {"secret_id": "s-1", "provider_id": "OPENAI"},
            None,
            "https://api.example/v1",
        )


# D9-part: provider HTTP routes over the D10 facade.


def _provider_ctx():
    _api, _store, _reg = _configured_api()
    _ctx = _routes.ProviderCtx(
        facade=_reg_facades, models={"openai": ["gpt-fake-1"]}
    )
    return _ctx, _store


def test_d9_routes_exact_frozen_pairs():
    # Frozen five plus the HD-ruling-4 DELTA-1 addition (exact set of 6).
    assert {
        (_method.lower(), _path) for _method, _path, _name, _fn in _routes.ROUTES
    } == {
        ("get", "/api/v1/providers"),
        ("post", "/api/v1/providers/connect"),
        ("post", "/api/v1/providers/{id}/disconnect"),
        ("get", "/api/v1/providers/{id}/models"),
        ("get", "/api/v1/chat/models"),
        ("get", "/api/v1/providers/leftover-keys"),
    }
    assert all(
        isinstance(_method, str) and _method == _method.lower()
        for _method, _path, _name, _fn in _routes.ROUTES
    )


def test_d9_connect_lists_ids_only_and_refuses_raw_secrets():
    _ctx, _store = _provider_ctx()
    try:
        _store.seed("s-conn")
        _status, _payload = _ctx_connect(_ctx)
        assert _status == 200
        assert _payload["provider"]["secret_ref"]["secret_id"] == "s-conn"
        assert "value" not in str(_payload)
        _status, _payload = _routes.list_providers(
            _ctx, {"project_id": "p1"}, None
        )
        assert _status == 200
        assert _payload["providers"][0]["provider_id"] == "openai"
        assert set(_payload["providers"][0]) == {
            "provider_id",
            "type",
            "base_url",
            "health",
            "evidenced",
        }
        _status, _payload = _routes.connect_provider(
            _ctx,
            {},
            {
                "preset_id": "openai",
                "model": "m-1",
                "key_ref": {"secret_id": "s-conn", "api_key": "sk-fake-9"},
            },
        )
        assert _status == 400
    finally:
        _reg_facades.configure(None)


def _ctx_connect(_ctx):
    return _routes.connect_provider(
        _ctx,
        {},
        {
            "preset_id": "openai",
            "model": "gpt-fake-1",
            "key_ref": {
                "secret_id": "s-conn",
                "provider_id": "openai",
                "type": "api_key",
                "scope": "provider",
                "source": "secret_store",
            },
        },
    )


def test_d9_disconnect_models_chatmodels_and_mount():
    _ctx, _store = _provider_ctx()
    try:
        _store.seed("s-conn")
        assert _ctx_connect(_ctx)[0] == 200
        _status, _payload = _routes.provider_models(
            _ctx, {"id": "openai"}, None
        )
        assert _status == 200
        assert _payload["models"][0]["model"] == "gpt-fake-1"
        assert set(_payload["models"][0]) == {
            "model",
            "enabled",
            "in_base",
            "kb",
        }
        _status, _payload = _routes.provider_models(
            _ctx, {"id": "nope"}, None
        )
        assert _status == 404
        _status, _payload = _routes.chat_models(
            _ctx, {"project_id": "p1"}, None
        )
        assert _status == 200
        assert _payload["models"] == []
        _status, _payload = _routes.disconnect_provider(
            _ctx, {"id": "openai"}, {}
        )
        assert _status == 200
        assert _payload == {"removed": True, "provider_id": "openai"}
        assert _store.has("s-conn") is False
        _status, _payload = _routes.disconnect_provider(
            _ctx, {"id": "openai"}, {}
        )
        assert _status == 404

        class _FakeApp:
            # FAKE-OF: pools_routes mount host (port: agent_si.backend.pools_routes.mount)

            def __init__(self):
                self.paths = {}

            def get(self, _path):
                def _reg(_fn):
                    self.paths[("get", _path)] = _fn
                    return _fn

                return _reg

            def post(self, _path):
                def _reg(_fn):
                    self.paths[("post", _path)] = _fn
                    return _fn

                return _reg

        _app = _FakeApp()
        assert _routes.mount(_app, _ctx) is _app
        # Frozen five plus the HD-ruling-4 DELTA-1 addition (exact set of 6).
        assert len(_app.paths) == 6
        assert ("get", "/api/v1/providers/leftover-keys") in _app.paths
        _status, _payload = _app.paths[("get", "/api/v1/providers")](
            {"project_id": "p1"}, None
        )
        assert _status == 200
    finally:
        _reg_facades.configure(None)
