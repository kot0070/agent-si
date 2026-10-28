"""K05 M2 STEP1-NOT-DONE cover: validate_config validates every field.

Smallest new surface only: validate_config RED coverage. No fakes.
"""

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from agent_si.local.config import (  # noqa: E402
    LOCAL_AI_INVALID_ENDPOINT,
    LOCAL_AI_INVALID_MODEL,
    LOCAL_AI_INVALID_PERMISSION,
    LocalAIConfig,
    LocalAISettingsError,
    validate_config,
)


def _config(**over: Any) -> LocalAIConfig:
    base: dict[str, Any] = {
        "project_key": "proj-a",
        "endpoint_url": "http://127.0.0.1:11434",
        "model_id": "llama3.1:8b",
        "permission_scope": "local-contact-allowed",
    }
    base.update(over)
    return LocalAIConfig(**base)


def test_validate_config_accepts_valid() -> None:
    validate_config(_config())


def test_validate_config_rejects_bad_endpoint() -> None:
    with pytest.raises(LocalAISettingsError) as exc:
        validate_config(_config(endpoint_url="not-a-url"))
    assert exc.value.code == LOCAL_AI_INVALID_ENDPOINT


def test_validate_config_rejects_bad_model() -> None:
    with pytest.raises(LocalAISettingsError) as exc:
        validate_config(_config(model_id="   "))
    assert exc.value.code == LOCAL_AI_INVALID_MODEL


def test_validate_config_rejects_bad_permission() -> None:
    with pytest.raises(LocalAISettingsError) as exc:
        validate_config(_config(permission_scope="unpermitted-contact"))
    assert exc.value.code == LOCAL_AI_INVALID_PERMISSION
