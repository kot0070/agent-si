"""K05 M2 contract test: local-AI settings iface (RED on the STEP1 stub).

Each M2 error code gets its own test. Stub bodies are `...` (return
None), so every raises-check and value-check below FAILS until the real
lane lands. No fakes in this file.
"""

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from agent_si.local.config import (  # noqa: E402
    ERROR_CODES_M2,
    LOCAL_AI_AMBIGUOUS_FIELD,
    LOCAL_AI_CONFIG_NOT_FOUND,
    LOCAL_AI_DECISION_RECORD_REQUIRED,
    LOCAL_AI_INVALID_ENDPOINT,
    LOCAL_AI_INVALID_MODEL,
    LOCAL_AI_INVALID_PERMISSION,
    LOCAL_AI_LOCAL_ONLY_VIOLATION,
    LOCAL_AI_PROJECT_SCOPE_VIOLATION,
    DecisionRecord,
    LocalAIConfig,
    LocalAISettingsError,
    LocalAISettingsView,
    enforce_local_only,
    get_local_ai_view,
    load_config,
    local_only_warnings,
    record_decision,
    save_config,
    update_config,
    validate_endpoint,
    validate_model,
    validate_permission,
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


def _decision() -> DecisionRecord:
    return DecisionRecord(
        decision_id="dec-1",
        project_id="proj-a",
        statement="set endpoint",
        reason="row 111 per-change record",
        authority="user",
        created_at="2026-10-26T00:00:00Z",
    )


def test_cross_project_read_refused() -> None:
    with pytest.raises(LocalAISettingsError) as exc:
        load_config(project_key="proj-b", reader_project_key="proj-a")
    assert exc.value.code == LOCAL_AI_PROJECT_SCOPE_VIOLATION


def test_invalid_endpoint_rejected() -> None:
    with pytest.raises(LocalAISettingsError) as exc:
        validate_endpoint("not-a-url")
    assert exc.value.code == LOCAL_AI_INVALID_ENDPOINT


def test_invalid_model_rejected() -> None:
    with pytest.raises(LocalAISettingsError) as exc:
        validate_model("")
    assert exc.value.code == LOCAL_AI_INVALID_MODEL


def test_invalid_permission_rejected() -> None:
    with pytest.raises(LocalAISettingsError) as exc:
        validate_permission("unpermitted-contact")
    assert exc.value.code == LOCAL_AI_INVALID_PERMISSION


def test_ambiguous_field_rejected() -> None:
    with pytest.raises(LocalAISettingsError) as exc:
        update_config(
            project_key="proj-a",
            patch={"endpoint_or_path": "http://127.0.0.1:11434"},
            decision=_decision(),
        )
    assert exc.value.code == LOCAL_AI_AMBIGUOUS_FIELD


def test_local_only_cloud_call_refused() -> None:
    with pytest.raises(LocalAISettingsError) as exc:
        enforce_local_only(
            _config(local_only_mode=True), attempted_cloud_call=True
        )
    assert exc.value.code == LOCAL_AI_LOCAL_ONLY_VIOLATION


def test_mutation_without_decision_refused() -> None:
    with pytest.raises(LocalAISettingsError) as exc_update:
        update_config(
            project_key="proj-a", patch={"model_id": "m"}, decision=None
        )
    assert exc_update.value.code == LOCAL_AI_DECISION_RECORD_REQUIRED
    with pytest.raises(LocalAISettingsError) as exc_save:
        save_config(_config(), None)
    assert exc_save.value.code == LOCAL_AI_DECISION_RECORD_REQUIRED


def test_missing_config_not_found() -> None:
    with pytest.raises(LocalAISettingsError) as exc:
        load_config(project_key="proj-ghost", reader_project_key="proj-ghost")
    assert exc.value.code == LOCAL_AI_CONFIG_NOT_FOUND


def test_record_decision_returns_record() -> None:
    rec = record_decision(
        project_id="proj-a",
        statement="set endpoint",
        reason="row 111",
        authority="user",
    )
    assert isinstance(rec, DecisionRecord)
    assert rec.project_id == "proj-a"
    assert rec.statement == "set endpoint"


def test_view_serves_stored_config() -> None:
    view = get_local_ai_view(
        project_key="proj-a", reader_project_key="proj-a"
    )
    assert isinstance(view, LocalAISettingsView)
    assert view.project_key == "proj-a"
    assert isinstance(view.config, LocalAIConfig)
    assert view.config.project_key == "proj-a"


def test_local_only_weak_evidence_warns() -> None:
    warnings = local_only_warnings(
        _config(local_only_mode=True, capability_evidence="UNKNOWN")
    )
    assert isinstance(warnings, list)
    assert len(warnings) > 0


def test_m2_code_set_frozen() -> None:
    assert set(ERROR_CODES_M2) == {
        LOCAL_AI_PROJECT_SCOPE_VIOLATION,
        LOCAL_AI_INVALID_ENDPOINT,
        LOCAL_AI_INVALID_MODEL,
        LOCAL_AI_INVALID_PERMISSION,
        LOCAL_AI_AMBIGUOUS_FIELD,
        LOCAL_AI_LOCAL_ONLY_VIOLATION,
        LOCAL_AI_DECISION_RECORD_REQUIRED,
        LOCAL_AI_CONFIG_NOT_FOUND,
    }
