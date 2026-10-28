import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import ast
import pathlib

import pytest

from agent_si.providers.registry import (
    META_CATALOGUE,
    PRESET_KEYS,
    LocalProbeNotPermitted,
    ProviderRegistry,
    SecretRef,
    TransportDescriptor,
    build_config,
    get_preset,
)

ROWS_COVERAGE = {
    "[42]": "src/agent_si/providers/registry/registry.py",
    "[M-R-ANY-API]": "src/agent_si/providers/registry/presets.py",
    "[HD-PROVIDERS]": "src/agent_si/providers/registry/presets.py",
    "[B0B-UNCOVERED_BP05-14]": "src/agent_si/providers/registry/contracts.py",
    "[B0B-SDK-123/124]": "src/agent_si/providers/registry/",
    "[ARCH-303]": "src/agent_si/providers/registry/registry.py",
    "[ARCH-452]": "src/agent_si/providers/registry/usage.py",
    "[MVP_ACCEPT-219]": "src/agent_si/providers/registry/registry.py",
    "[SPEC 33]": "src/agent_si/providers/registry/registry.py",
    "[SPEC 33A]": "src/agent_si/providers/registry/usage.py",
    "[SPEC 35]": "src/agent_si/providers/registry/health.py",
    "[SPEC 20A]": "src/agent_si/providers/registry/contracts.py",
}

EXPECTED_PRESETS = (
    "meta",
    "openai",
    "anthropic",
    "any-openai-compatible",
    "ollama",
    "lm-studio",
    "claude",
    "gemini",
    "mistral",
    "groq",
    "openrouter",
    "deepseek",
    "xai",
)

LOOPBACK = "http://127.0.0.1:9/v1"


def _ref(provider="openai", secret="ref-1"):
    return SecretRef(
        secret_id=secret,
        provider_id=provider,
        type="api_key",
        scope="models",
        source="fake-store",
    )


def _config(provider="openai", model="gpt-fake-1", **kw):
    cfg = {
        "provider": provider,
        "model": model,
        "base_url": LOOPBACK,
        "credential_ref": _ref(provider),
    }
    cfg.update(kw)
    return cfg


def test_fresh_install_blocks_with_reason():
    """[42] empty registry reports BLOCKED with reason, never a baked-in model."""
    reg = ProviderRegistry()
    assert reg.instances() == []
    status = reg.status()
    assert status["status"] == "BLOCKED"
    assert status["reason"]
    assert reg.lookup("meta", "meta/muse-spark-1.3-contributor") is None


def test_no_default_instances_after_init():
    """[HD-PROVIDERS] presets never self-register: nothing configured, none default."""
    reg = ProviderRegistry()
    assert reg.status()["status"] == "BLOCKED"
    assert reg.matrix() == []
    assert len(PRESET_KEYS) == len(EXPECTED_PRESETS)
    assert reg.instances() == []


def test_all_presets_present_by_config():
    """[HD-PROVIDERS] every named preset builds a config; nothing registers itself."""
    for key in EXPECTED_PRESETS:
        assert key in PRESET_KEYS
        preset = get_preset(key)
        assert preset["provider_id"]
        assert preset["transport"] in (
            "openai_compatible",
            "litellm_backed",
            "local",
        )
    with pytest.raises(KeyError):
        get_preset("no-such-preset")


def test_any_api_preset_config_part():
    """[M-R-ANY-API] generic OpenAI-compatible preset takes a caller base_url."""
    cfg = build_config(
        "any-openai-compatible",
        model="fake-model-1",
        credential_ref=_ref("any-openai-compatible"),
        base_url="http://127.0.0.1:9/custom",
    )
    assert cfg["base_url"] == "http://127.0.0.1:9/custom"
    assert cfg["transport"] == "openai_compatible"
    reg = ProviderRegistry()
    reg.register_instance(cfg)
    assert reg.lookup("any-openai-compatible", "fake-model-1") is not None


def test_build_config_requires_model_and_ref():
    """[M-R-ANY-API] presets never bake in a model; ref is mandatory."""
    with pytest.raises(ValueError):
        build_config("openai", model="", credential_ref=_ref())
    with pytest.raises(ValueError):
        build_config("openai", model="gpt-fake-1", credential_ref=None)


def test_register_and_lookup_roundtrip():
    """[SPEC 33] instance registers by config and reads back by identity pair."""
    reg = ProviderRegistry()
    reg.register_instance(_config())
    contract = reg.lookup("openai", "gpt-fake-1")
    assert contract is not None
    assert contract.provider_id == "openai"
    assert contract.instance_id == "default"
    assert contract.transport.base_url == LOOPBACK
    assert contract.credential_ref.secret_id == "ref-1"


def test_identity_pairs_same_model_name_distinct():
    """[SPEC 33] same model name on two providers are different entities."""
    reg = ProviderRegistry()
    reg.register_instance(_config(provider="openai", model="shared-name"))
    reg.register_instance(_config(provider="mistral", model="shared-name"))
    left = reg.lookup("openai", "shared-name")
    right = reg.lookup("mistral", "shared-name")
    assert left is not None and right is not None
    assert left.provider_id != right.provider_id
    assert left is not right


def test_register_rejects_raw_secret_material():
    """[SPEC 20A] configs carry refs; inline key fields are rejected."""
    reg = ProviderRegistry()
    bad = _config()
    bad["api_key"] = "sk-fake-inline-1"
    with pytest.raises(ValueError):
        reg.register_instance(bad)
    nested = _config()
    nested["credential_ref"] = {"secret_id": "ref-9", "api_key": "sk-fake-2"}
    with pytest.raises(ValueError):
        reg.register_instance(nested)


def test_refs_never_raw_in_repr_and_views():
    """[SPEC 20A] no key material in repr, summaries, or health views."""
    reg = ProviderRegistry()
    reg.register_instance(_config())
    contract = reg.lookup("openai", "gpt-fake-1")
    blob = repr(contract) + repr(contract.credential_ref)
    blob += str(contract.safe_summary()) + str(reg.health_view())
    assert "sk-fake" not in blob
    assert not hasattr(contract.credential_ref, "value")
    assert contract.auth_mode == "secret_ref"


def test_health_latest_wins():
    """[SPEC 35] repeated checks overwrite; the newest status reads back."""
    reg = ProviderRegistry()
    reg.register_instance(_config())
    reg.record_health("openai", "default", "ONLINE")
    reg.record_health("openai", "default", "DEGRADED", error="fake-slow")
    reg.record_health("openai", "default", "OFFLINE", error="fake-down")
    assert reg.provider_status("openai", "default") == "OFFLINE"
    reg.record_health("openai", "default", "ONLINE")
    assert reg.provider_status("openai", "default") == "ONLINE"


def test_provider_online_is_not_model_ready():
    """[SPEC 35] provider ONLINE never implies model READY without a probe."""
    reg = ProviderRegistry()
    reg.register_instance(_config())
    reg.record_health("openai", "default", "ONLINE")
    assert reg.model_status("openai", "gpt-fake-1") == "UNKNOWN"
    reg.record_model_health("openai", "gpt-fake-1", "READY")
    assert reg.model_status("openai", "gpt-fake-1") == "READY"
    reg.record_model_health("openai", "gpt-fake-1", "ERROR")
    assert reg.model_status("openai", "gpt-fake-1") == "ERROR"


def test_unknown_transport_and_status_rejected():
    """[B0B-UNCOVERED_BP05-14] bad transport/status values fail loudly."""
    with pytest.raises(ValueError):
        TransportDescriptor(transport="pigeon", base_url=LOOPBACK)
    reg = ProviderRegistry()
    reg.register_instance(_config())
    with pytest.raises(ValueError):
        reg.record_health("openai", "default", "SLEEPING")
    with pytest.raises(ValueError):
        reg.record_model_health("openai", "gpt-fake-1", "SLEEPING")
    with pytest.raises(ValueError):
        reg.register_instance(_config())
    with pytest.raises(ValueError):
        reg.record_health("openai", "missing", "ONLINE")


def test_probed_limits_and_route_params_recorded():
    """[B0B-UNCOVERED_BP05-14] probed limits/route params land on the descriptor."""
    reg = ProviderRegistry()
    reg.register_instance(_config(transport="litellm_backed"))
    contract = reg.lookup("openai", "gpt-fake-1")
    contract.transport.record_probe(
        limits={"max_context": 8000}, route_params={"route": "litellm"}
    )
    assert contract.transport.limits == {"max_context": 8000}
    assert contract.transport.route_params == {"route": "litellm"}


def _product_files():
    root = pathlib.Path(_SRC, "agent_si", "providers", "registry")
    return sorted(root.glob("*.py"))


def test_no_third_party_sdk_imports_at_top_level():
    """[B0B-SDK-123/124] product modules import no third-party SDK at top level."""
    banned = {
        "litellm",
        "openai",
        "anthropic",
        "httpx",
        "requests",
        "pydantic",
        "boto3",
        "google",
        "mistralai",
        "groq",
        "ollama",
    }
    files = _product_files()
    assert files, "registry product files must exist"
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        top = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                top.update(a.name.split(".")[0] for a in node.names)
            elif (
                isinstance(node, ast.ImportFrom)
                and node.level == 0
                and node.module
            ):
                top.add(node.module.split(".")[0])
        assert not (top & banned), (path.name, top & banned)


def test_imports_are_stdlib_or_local_only():
    """[B0B-SDK-123/124] every import is stdlib, local, or future."""
    allowed = set(sys.stdlib_module_names) | {"agent_si", "__future__"}
    for path in _product_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] in allowed, alias.name
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                assert (node.module or "").split(".")[0] in allowed, node.module


def test_no_machine_paths_in_product_code():
    """Portable APIs only: no machine paths baked into product modules."""
    for path in _product_files():
        text = path.read_text(encoding="utf-8")
        assert "C:\\" not in text
        assert "C:/" not in text
        assert "/home/" not in text
        assert "/Users/" not in text


def test_unevidenced_credential_ineligible():
    """[ARCH-303] an instance without ref evidence never routes."""
    reg = ProviderRegistry()
    reg.register_instance(_config())
    reg.record_health("openai", "default", "ONLINE")
    assert reg.credential_evidenced("openai", "default") is False
    assert reg.is_routing_eligible("openai", "gpt-fake-1") is False


def test_evidenced_credential_eligible_when_online():
    """[ARCH-303] ref evidence plus ONLINE health reads eligible."""
    reg = ProviderRegistry()
    reg.register_instance(_config())
    reg.record_credential_evidence("openai", "default", "fake-probe-1")
    assert reg.credential_evidenced("openai", "default") is True
    assert reg.is_routing_eligible("openai", "gpt-fake-1") is False
    reg.record_health("openai", "default", "ONLINE")
    assert reg.is_routing_eligible("openai", "gpt-fake-1") is True
    assert reg.is_routing_eligible("openai", "unknown-model") is False


def test_unpermitted_local_probe_refused():
    """[ARCH-452] local usage probing without permission is refused, not run."""
    reg = ProviderRegistry()
    reg.register_local_identity("fake-local-tag")
    with pytest.raises(LocalProbeNotPermitted):
        reg.probe_local_usage("fake-local-tag", permitted=False)
    assert reg.usage_state("local", "fake-local-tag") == "UNPERMITTED"


def test_permitted_local_probe_recorded():
    """[ARCH-452] an explicitly permitted local probe records evidence."""
    reg = ProviderRegistry()
    reg.register_local_identity("fake-local-tag")
    entry = reg.probe_local_usage(
        "fake-local-tag",
        permitted=True,
        capabilities={"input_tokens": True},
        evidence_ref="fake-local-probe-1",
    )
    assert entry.state == "PARTIAL"
    assert reg.usage_state("local", "fake-local-tag") == "PARTIAL"


def test_local_identity_is_presence_only():
    """Local tag presence is presence only, never capability evidence."""
    reg = ProviderRegistry()
    record = reg.register_local_identity("fake-local-tag")
    assert record["presence"] is True
    assert reg.local_capability_evidence("fake-local-tag") is None
    assert [r["tag"] for r in reg.local_identities()] == ["fake-local-tag"]


def test_matrix_only_evidenced():
    """[MVP_ACCEPT-219] the matrix marks unevidenced cells UNAVAILABLE."""
    reg = ProviderRegistry()
    reg.register_instance(_config())
    reg.register_instance(_config(provider="mistral", model="fake-model-m"))
    reg.record_credential_evidence("openai", "default", "fake-probe-1")
    reg.record_health("openai", "default", "ONLINE")
    reg.record_usage_probe(
        "openai", "default", capabilities={"input_tokens": True}
    )
    rows = {r["provider"]: r for r in reg.matrix()}
    assert rows["openai"]["credential"] == "MEASURED"
    assert rows["openai"]["usage"]["input_tokens"] == "MEASURED"
    assert rows["openai"]["usage"]["output_tokens"] == "UNAVAILABLE"
    assert rows["mistral"]["credential"] == "UNAVAILABLE"
    assert rows["mistral"]["health"] == "UNAVAILABLE"
    assert rows["mistral"]["model_ready"] == "UNKNOWN"


def test_partial_usage_missing_metrics_unavailable():
    """[SPEC 33A] partial probes leave missing metrics UNAVAILABLE."""
    reg = ProviderRegistry()
    reg.register_instance(_config())
    entry = reg.record_usage_probe(
        "openai",
        "default",
        capabilities={"input_tokens": True, "output_tokens": True},
        evidence_ref="fake-usage-1",
    )
    assert entry.state == "PARTIAL"
    assert entry.metric_state("input_tokens") == "MEASURED"
    assert entry.metric_state("cached_tokens") == "UNAVAILABLE"
    assert reg.usage_state("openai", "default") == "PARTIAL"


def test_streaming_verified_separately():
    """[SPEC 33A] streaming support needs its own probe evidence."""
    reg = ProviderRegistry()
    reg.register_instance(_config())
    entry = reg.record_usage_probe(
        "openai",
        "default",
        capabilities={m: True for m in ("input_tokens", "output_tokens",
                                        "cached_tokens", "reasoning_tokens",
                                        "raw_usage", "request_level_usage",
                                        "cost_fields")},
    )
    assert entry.state == "VERIFIED"
    assert entry.metric_state("input_tokens", "stream") == "UNAVAILABLE"
    entry2 = reg.record_usage_probe(
        "openai",
        "default",
        capabilities={"input_tokens": True},
        stream_capabilities={"input_tokens": True},
    )
    assert entry2.metric_state("input_tokens", "stream") == "MEASURED"
    assert entry2.metric_state("output_tokens", "stream") == "UNAVAILABLE"


def test_mock_instances_marked_downstream():
    """Mock instances are allowed and flagged for downstream marking."""
    reg = ProviderRegistry()
    reg.register_instance(_config(mock=True))
    mark = reg.downstream_mark("openai", "default")
    assert mark["mock"] is True
    assert mark["models"] == ["gpt-fake-1"]
    reg.register_instance(_config(provider="mistral", model="m2"))
    assert reg.downstream_mark("mistral", "default")["mock"] is False


def test_meta_contract_endpoint_and_catalogue():
    """Meta records its endpoint plus model catalogue; access stays ref-based."""
    reg = ProviderRegistry()
    cfg = build_config(
        "meta",
        model="meta/muse-spark-1.3-contributor",
        credential_ref=_ref("meta", secret="ref-meta"),
    )
    reg.register_instance(cfg)
    contract = reg.lookup("meta", "meta/muse-spark-1.3-contributor")
    assert contract.endpoint == cfg["base_url"]
    assert "meta/muse-spark-1.3-contributor" in contract.catalogue
    assert contract.catalogue == tuple(META_CATALOGUE)
    assert isinstance(contract.credential_ref, SecretRef)


def test_policy_refs_hold_strings_only():
    """Registry holds policy_ref strings; shapes are never redefined here."""
    reg = ProviderRegistry()
    with pytest.raises(ValueError):
        reg.register_instance(_config(policy_refs={"routing": {"shape": 1}}))
    reg.register_instance(_config(policy_refs={"routing": "policy-ref-1"}))
    contract = reg.lookup("openai", "gpt-fake-1")
    assert contract.policy_refs == {"routing": "policy-ref-1"}


def test_health_view_is_read_only_copy():
    """Health views are derived copies: mutating them touches no state."""
    reg = ProviderRegistry()
    reg.register_instance(_config())
    reg.record_health("openai", "default", "ONLINE")
    view = reg.health_view()
    view["providers"]["openai/default"]["status"] = "EDITED"
    assert reg.provider_status("openai", "default") == "ONLINE"


def test_registry_owns_no_execution_or_routing():
    """Registries own lookup plus health views, never execution or routing."""
    reg = ProviderRegistry()
    for name in ("execute", "run", "route", "dispatch", "choose_model"):
        assert not hasattr(reg, name), name
    assert not hasattr(reg, "secret_values")
    assert not hasattr(ProviderRegistry, "secret_values")

