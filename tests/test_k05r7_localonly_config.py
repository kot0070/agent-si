"""K05R7 local-only config gates: B0B-UNCOVERED_BP06-44 + B0B-UNCOVERED_BP06-48.

Behaviour tests over real LocalAIConfig / record_decision / save_config /
load_config flows. No fakes, no fixtures, no canned payloads: every config
is a constructed LocalAIConfig, every stored row goes through save_config
with a real record_decision, and the no-mutation checks compare the real
_STORE before and after the gate.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from agent_si.local import config as cfg  # noqa: E402


def _local_only_config(project_key):
    """Real stored-shape config with local_only_mode set."""
    return cfg.LocalAIConfig(
        project_key=project_key,
        endpoint_url="http://127.0.0.1:11434",
        model_id="llama3.1:8b",
        permission_scope="local-contact-allowed",
        local_only_mode=True,
    )


def _seed(project_key, local_only=True):
    """Persist one config through the real decision-record flow."""
    base = _local_only_config(project_key)
    if not local_only:
        base = cfg.LocalAIConfig(
            project_key=base.project_key,
            endpoint_url=base.endpoint_url,
            model_id=base.model_id,
            permission_scope=base.permission_scope,
            local_only_mode=False,
        )
    decision = cfg.record_decision(
        project_key, "k05r7 seed", "behaviour test", "test")
    return cfg.save_config(base, decision)


# --- B0B-UNCOVERED_BP06-44: local_ai_allowed at every used level ---

def test_bp06_44_all_allowed_levels_pass():
    config = _local_only_config("k05r7-pure-1")
    levels = [
        {"level": "director", "local_ai_allowed": True},
        {"level": "manager", "local_ai_allowed": True,
         "resource_cap": {"max_models": 2}},
    ]
    assert cfg.require_local_ai_allowed_at_used_levels(
        config, levels) == ["director", "manager"]


def test_bp06_44_disallowed_level_raises():
    config = _local_only_config("k05r7-pure-2")
    levels = [
        {"level": "director", "local_ai_allowed": True},
        {"level": "cloud-verify", "local_ai_allowed": False},
    ]
    with pytest.raises(cfg.LocalAISettingsError) as exc:
        cfg.require_local_ai_allowed_at_used_levels(config, levels)
    assert exc.value.code == cfg.LOCAL_AI_LOCAL_ONLY_VIOLATION


def test_bp06_44_missing_flag_denies():
    config = _local_only_config("k05r7-pure-3")
    with pytest.raises(cfg.LocalAISettingsError) as exc:
        cfg.require_local_ai_allowed_at_used_levels(
            config, [{"level": "manager"}])
    assert exc.value.code == cfg.LOCAL_AI_LOCAL_ONLY_VIOLATION


def test_bp06_44_empty_levels_deny():
    config = _local_only_config("k05r7-pure-4")
    with pytest.raises(cfg.LocalAISettingsError) as exc:
        cfg.require_local_ai_allowed_at_used_levels(config, [])
    assert exc.value.code == cfg.LOCAL_AI_LOCAL_ONLY_VIOLATION
    with pytest.raises(cfg.LocalAISettingsError) as exc2:
        cfg.require_local_ai_allowed_at_used_levels(config, None)
    assert exc2.value.code == cfg.LOCAL_AI_LOCAL_ONLY_VIOLATION


def test_bp06_44_mode_off_passes_through():
    config = cfg.LocalAIConfig(
        project_key="k05r7-pure-5",
        endpoint_url="http://127.0.0.1:11434",
        model_id="llama3.1:8b",
        permission_scope="local-contact-allowed",
        local_only_mode=False,
    )
    levels = [{"level": "cloud-verify", "local_ai_allowed": False}]
    assert cfg.require_local_ai_allowed_at_used_levels(
        config, levels) == ["cloud-verify"]


def test_bp06_44_bad_config_identity_raises():
    config = cfg.LocalAIConfig(
        project_key="k05r7-pure-6",
        endpoint_url="ftp://not-http/evil",
        model_id="llama3.1:8b",
        permission_scope="local-contact-allowed",
        local_only_mode=True,
    )
    with pytest.raises(cfg.LocalAISettingsError) as exc:
        cfg.require_local_ai_allowed_at_used_levels(
            config, [{"level": "director", "local_ai_allowed": True}])
    assert exc.value.code == cfg.LOCAL_AI_INVALID_ENDPOINT


def test_bp06_44_bad_level_identity_raises():
    config = _local_only_config("k05r7-pure-7")
    levels = [{"level": "director", "local_ai_allowed": True,
               "endpoint_url": "notaurl"}]
    with pytest.raises(cfg.LocalAISettingsError) as exc:
        cfg.require_local_ai_allowed_at_used_levels(config, levels)
    assert exc.value.code == cfg.LOCAL_AI_INVALID_ENDPOINT


def test_bp06_44_nonpositive_resource_cap_raises():
    config = _local_only_config("k05r7-pure-8")
    bad_caps = [{"max_models": 0}, {"max_models": -1},
                {"max_models": True}, {}]
    for bad in bad_caps:
        levels = [{"level": "director", "local_ai_allowed": True,
                   "resource_cap": bad}]
        with pytest.raises(cfg.LocalAISettingsError) as exc:
            cfg.require_local_ai_allowed_at_used_levels(config, levels)
        assert exc.value.code == cfg.LOCAL_AI_LOCAL_ONLY_VIOLATION


# --- B0B-UNCOVERED_BP06-48: block activation, never mutate stored config ---

def test_bp06_48_allowed_activation_true_without_mutation():
    key = "k05r7-act-ok"
    try:
        seeded = _seed(key, local_only=True)
        before = dict(cfg._STORE)
        levels = [{"level": "director", "local_ai_allowed": True}]
        assert cfg.check_local_only_activation(key, levels) is True
        assert dict(cfg._STORE) == before
        assert cfg.load_config(key, key) == seeded
    finally:
        cfg._STORE.pop(key, None)


def test_bp06_48_blocked_activation_raises_without_mutation():
    key = "k05r7-act-block"
    try:
        seeded = _seed(key, local_only=True)
        before = dict(cfg._STORE)
        levels = [{"level": "cloud-verify", "local_ai_allowed": False}]
        with pytest.raises(cfg.LocalAISettingsError) as exc:
            cfg.check_local_only_activation(key, levels)
        assert exc.value.code == cfg.LOCAL_AI_LOCAL_ONLY_VIOLATION
        assert dict(cfg._STORE) == before
        assert cfg.load_config(key, key) == seeded
    finally:
        cfg._STORE.pop(key, None)


def test_bp06_48_mode_off_passes_without_mutation():
    key = "k05r7-act-off"
    try:
        seeded = _seed(key, local_only=False)
        before = dict(cfg._STORE)
        levels = [{"level": "cloud-verify", "local_ai_allowed": False}]
        assert cfg.check_local_only_activation(key, levels) is True
        assert dict(cfg._STORE) == before
        assert cfg.load_config(key, key) == seeded
    finally:
        cfg._STORE.pop(key, None)
