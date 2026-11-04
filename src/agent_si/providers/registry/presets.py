"""Named provider config presets.

DATA only: a preset fills id/type/base_url from its key at connect time
for the caller. Nothing here registers an instance, so a fresh install
stays empty (and therefore BLOCKED with reason) until configured.
"""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import (
    TRANSPORT_LITELLM_BACKED,
    TRANSPORT_LOCAL,
    TRANSPORT_OPENAI_COMPATIBLE,
    SecretRef,
    coerce_secret_ref,
)

META_CATALOGUE = ("meta/muse-spark-1.3-contributor",)

PRESETS: dict[str, dict[str, Any]] = {
    "meta": {
        "provider_id": "meta",
        "label": "Meta",
        "provider_type": "meta",
        "transport": TRANSPORT_OPENAI_COMPATIBLE,
        "base_url": "https://api.meta.ai/v1",
        "adapter": None,
        "catalogue": META_CATALOGUE,
    },
    "openai": {
        "provider_id": "openai",
        "label": "OpenAI",
        "provider_type": "openai",
        "transport": TRANSPORT_OPENAI_COMPATIBLE,
        "base_url": "https://api.openai.com/v1",
        "adapter": None,
        "catalogue": (),
    },
    "anthropic": {
        "provider_id": "anthropic",
        "label": "Anthropic",
        "provider_type": "anthropic",
        "transport": TRANSPORT_LITELLM_BACKED,
        "base_url": "https://api.anthropic.com",
        "adapter": "litellm",
        "catalogue": (),
    },
    "any-openai-compatible": {
        "provider_id": "any-openai-compatible",
        "label": "OpenAI-compatible",
        "provider_type": "openai_compatible",
        "transport": TRANSPORT_OPENAI_COMPATIBLE,
        "base_url": "",
        "adapter": None,
        "catalogue": (),
    },
    "ollama": {
        "provider_id": "ollama",
        "label": "Ollama",
        "provider_type": "ollama",
        "transport": TRANSPORT_LOCAL,
        "base_url": "http://localhost:11434",
        "adapter": None,
        "catalogue": (),
    },
    "lm-studio": {
        "provider_id": "lm-studio",
        "label": "LM Studio",
        "provider_type": "lm_studio",
        "transport": TRANSPORT_LOCAL,
        "base_url": "http://localhost:1234/v1",
        "adapter": None,
        "catalogue": (),
    },
    "claude": {
        "provider_id": "claude",
        "label": "Claude",
        "provider_type": "claude",
        "transport": TRANSPORT_LITELLM_BACKED,
        "base_url": "https://api.anthropic.com",
        "adapter": "litellm",
        "catalogue": (),
    },
    "gemini": {
        "provider_id": "gemini",
        "label": "Gemini",
        "provider_type": "gemini",
        "transport": TRANSPORT_OPENAI_COMPATIBLE,
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "adapter": None,
        "catalogue": (),
    },
    "mistral": {
        "provider_id": "mistral",
        "label": "Mistral",
        "provider_type": "mistral",
        "transport": TRANSPORT_OPENAI_COMPATIBLE,
        "base_url": "https://api.mistral.ai/v1",
        "adapter": None,
        "catalogue": (),
    },
    "groq": {
        "provider_id": "groq",
        "label": "Groq",
        "provider_type": "groq",
        "transport": TRANSPORT_OPENAI_COMPATIBLE,
        "base_url": "https://api.groq.com/openai/v1",
        "adapter": None,
        "catalogue": (),
    },
    "openrouter": {
        "provider_id": "openrouter",
        "label": "OpenRouter",
        "provider_type": "openrouter",
        "transport": TRANSPORT_OPENAI_COMPATIBLE,
        "base_url": "https://openrouter.ai/api/v1",
        "adapter": None,
        "catalogue": (),
    },
    "deepseek": {
        "provider_id": "deepseek",
        "label": "DeepSeek",
        "provider_type": "deepseek",
        "transport": TRANSPORT_OPENAI_COMPATIBLE,
        "base_url": "https://api.deepseek.com/v1",
        "adapter": None,
        "catalogue": (),
    },
    "xai": {
        "provider_id": "xai",
        "label": "xAI",
        "provider_type": "xai",
        "transport": TRANSPORT_OPENAI_COMPATIBLE,
        "base_url": "https://api.x.ai/v1",
        "adapter": None,
        "catalogue": (),
    },
}

PRESET_KEYS = tuple(PRESETS)


def get_preset(key: str) -> dict[str, Any]:
    try:
        preset = PRESETS[key]
    except KeyError:
        raise KeyError("unknown provider preset: %r" % (key,)) from None
    return {
        "key": key,
        "provider_id": preset["provider_id"],
        "label": preset.get("label", preset["provider_id"]),
        "provider_type": preset["provider_type"],
        "transport": preset["transport"],
        "base_url": preset["base_url"],
        "adapter": preset["adapter"],
        "catalogue": tuple(preset["catalogue"]),
    }


def build_config(
    key: str,
    *,
    model: str,
    credential_ref: SecretRef | Mapping[str, Any],
    base_url: str | None = None,
    instance_id: str | None = None,
    adapter: str | None = None,
    mock: bool = False,
    policy_refs: Mapping[str, str] | None = None,
    transport: str | None = None,
) -> dict[str, Any]:
    preset = get_preset(key)
    if not model:
        raise ValueError("model is required: presets never bake one in")
    ref = coerce_secret_ref(credential_ref)
    resolved_base = preset["base_url"] if base_url is None else base_url
    if not resolved_base:
        raise ValueError("base_url is required for preset %r" % (key,))
    return {
        "provider": preset["provider_id"],
        "provider_type": preset["provider_type"],
        "model": model,
        "base_url": resolved_base,
        "credential_ref": ref,
        "transport": transport or preset["transport"],
        "instance_id": instance_id or "default",
        "adapter": preset["adapter"] if adapter is None else adapter,
        "mock": mock,
        "policy_refs": dict(policy_refs or {}),
    }
