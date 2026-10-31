"""K05BATCH Beryl served-evidence tests (test_k05batchb_served).

One test per definable Beryl row, proven on the real stack: served HTTP
routes (create_app + TestClient) where a route fronts the behavior, else
the real module entry points (no fakes, no doubles, no skips). Rows whose
implementation lives in the sibling coder's files are proven by their
frozen lane tests (cited in RETURN, not re-driven here).
"""

from __future__ import annotations

import copy
import importlib
import pathlib
import socket
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from agent_si.local import bench_protocol as _proto
from agent_si.local import config as _config
from agent_si.local import gateway as _gateway
from agent_si.local import k05r3_backups as _backups
from agent_si.local import k05r3_discover as _discover
from agent_si.local import k05r3_helper as _helper
from agent_si.local import k05r7_probe_envs as _penvs
from agent_si.local.bench_protocol import BenchLevel

_TOKEN = "k05batchb-ui-session-token-1"
_HEADERS = {"x-actor": "k05batchb-user", "x-ui-session-token": _TOKEN}


def _served_client():
    from agent_si.backend.app import create_app

    app = create_app({"env": "test", "ui_session_token": _TOKEN})
    assert app.state.localbench_mounted is True
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture()
def _clean_gateway(monkeypatch):
    """Idle gateway, no grant held, helper handles restored after."""
    monkeypatch.delenv("AGENT_SI_BENCH_RUN_ID", raising=False)
    monkeypatch.delenv("AGENT_SI_TEST_RUN_ID", raising=False)
    importlib.reload(_gateway)
    handles_before = set(_helper._HANDLES)
    yield
    monkeypatch.delenv("AGENT_SI_BENCH_RUN_ID", raising=False)
    monkeypatch.delenv("AGENT_SI_TEST_RUN_ID", raising=False)
    importlib.reload(_gateway)
    for key in set(_helper._HANDLES) - handles_before:
        _helper._HANDLES.pop(key, None)


def _make_idle(monkeypatch):
    monkeypatch.delenv("AGENT_SI_BENCH_RUN_ID", raising=False)
    monkeypatch.delenv("AGENT_SI_TEST_RUN_ID", raising=False)
    importlib.reload(_gateway)


@pytest.fixture()
def _clean_store():
    """config._STORE snapshot-restore; tests use their own project key."""
    before = dict(_config._STORE)
    yield
    _config._STORE.clear()
    _config._STORE.update(before)


def test_batchb_probe_env_prefix_isolation(_clean_gateway) -> None:
    """M-D-D15: only AGENT_SI_PROBE_* feeds probe resolution."""
    env = {
        "AGENT_SI_PROBE_ENDPOINT": "http://127.0.0.1:11434",
        "AGENT_SI_PROBE_TIMEOUT_S": "0.2",
        "AGENT_SI_BENCH_JOURNAL": "/tmp/infra-journal",
        "AGENT_SI_OTHER_INFRA": "infra",
    }
    snap = _penvs.probe_env_snapshot(env)
    assert snap == {
        "AGENT_SI_PROBE_ENDPOINT": "http://127.0.0.1:11434",
        "AGENT_SI_PROBE_TIMEOUT_S": "0.2",
    }
    resolved = _penvs.resolve_probe_env(env)
    assert resolved.endpoint == "http://127.0.0.1:11434"
    assert resolved.timeout_s == 0.2


def test_batchb_probe_guard_served(_clean_gateway, monkeypatch) -> None:
    """M-D-D41: fail-closed host check before any contact, served too."""
    calls: list = []
    real = socket.create_connection

    def _recorder(address, timeout=None, *args, **kwargs):
        calls.append(address)
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError("external contact attempted: %r" % (address,))
        return real(address, timeout=timeout, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", _recorder)
    for endpoint in ("https://api.openai.com", "http://10.0.0.5/", "http://[::1"):
        with pytest.raises(_penvs.ProbeRefusedError):
            _penvs.guard_probe_endpoint(endpoint)
    assert calls == []
    client = _served_client()
    refused = client.get(
        "/api/v1/local/bench/check", params={"endpoint": "https://api.openai.com"}
    )
    assert refused.status_code == 200, refused.text
    assert refused.json()["reachable"] is False
    assert calls == []


def test_batchb_backups_owner_gate(_clean_store) -> None:
    """M-D-D16: versioned backups + owner gate close on matching record."""
    store = _backups.VersionedBackupStore()
    first = store.keep("kb-a", "copy-one")
    second = store.keep("kb-a", "copy-two")
    assert store.serve_current(second) == "copy-two"
    with pytest.raises(_backups.BackupError) as excinfo:
        store.serve_current(first)
    assert excinfo.value.code == _backups.K05R3_BACKUP_STALE_AS_CURRENT_REFUSED
    assert store.serve_backup(first) == "copy-one"
    book = _backups.OwnerGateBook()
    gate = book.open_gate("gate-1", "proj-batchb", "gate-1: proceed?")
    assert gate.state == _backups.GATE_OPEN
    decision = _config.record_decision(
        "proj-batchb", "gate-1: proceed? yes", "owner reason", "owner"
    )
    closed = book.close_gate("gate-1", decision)
    assert closed.state == _backups.GATE_CLOSED
    assert closed.decided_by == decision.decision_id
    foreign = _config.record_decision(
        "proj-other", "gate-1: proceed? yes", "owner reason", "owner"
    )
    with pytest.raises(_backups.OwnerGateError) as excinfo2:
        book.close_gate("gate-1", foreign)
    assert excinfo2.value.code in (
        _backups.K05R3_OWNER_GATE_STATE_REFUSED,
        _backups.K05R3_OWNER_GATE_DECISION_REFUSED,
    )


def test_batchb_discover_gate(tmp_path) -> None:
    """B0B-UNCOVERED_BP05-29: DISCOVER gate permission + stage + scan rule."""
    from agent_si.local import adapter as _adapter

    grant = _discover.enter_discover(_adapter.LifecycleStage.SCAN, "local-contact-allowed")
    assert grant.stage is _adapter.LifecycleStage.DISCOVER
    assert grant.identity_state == _discover.DISCOVER_IDENTITY_UNKNOWN
    with pytest.raises(_discover.DiscoverError) as excinfo:
        _discover.enter_discover(_adapter.LifecycleStage.SCAN, "wrong-scope")
    assert excinfo.value.code == _discover.K05R3_DISCOVER_PERMISSION_REFUSED
    with pytest.raises(_discover.DiscoverError) as excinfo2:
        _discover.enter_discover(_adapter.LifecycleStage.DISCOVER, "local-contact-allowed")
    assert excinfo2.value.code == _discover.K05R3_DISCOVER_STAGE_REFUSED
    target = tmp_path / "models"
    target.mkdir()
    (target / "m.gguf").write_text("weights", encoding="utf-8")
    assert _discover.scan_roots([str(tmp_path)], str(target)) == ["m.gguf"]
    creds = tmp_path / "secrets"
    creds.mkdir()
    with pytest.raises(_discover.DiscoverError):
        _discover.scan_roots([str(tmp_path)], str(creds))


def test_batchb_helper_idle_and_busy(_clean_gateway, monkeypatch) -> None:
    """B0B-BP03-47: helper behind the idle gateway; busy refuses, release lands."""
    attached = _helper.attach_helper("assign-batchb-1")
    assert attached.started is False
    assert attached.gateway_reason == _gateway.GATEWAY_IDLE_REASON
    _make_idle(monkeypatch)
    started = _helper.start_helper(attached)
    assert started.started is True
    _make_idle(monkeypatch)
    released = _helper.release_helper(started)
    assert released.started is True
    assert isinstance(released.gateway_reason, str) and released.gateway_reason
    monkeypatch.setenv("AGENT_SI_BENCH_RUN_ID", "user-bench-1")
    with pytest.raises(_helper.HelperError) as excinfo:
        _helper.attach_helper("assign-batchb-2")
    assert excinfo.value.code == _helper.K05R3_HELPER_GATEWAY_BUSY
    with pytest.raises(_helper.HelperError):
        _helper.attach_helper("")


def test_batchb_localonly_used_levels(_clean_store) -> None:
    """B0B-UNCOVERED_BP06-44: every used level carries local_ai_allowed."""
    decision = _config.record_decision("proj-batchb", "enable local-only", "r", "owner")
    _config.save_config(
        _config.LocalAIConfig(
            project_key="proj-batchb",
            endpoint_url="http://127.0.0.1:11434",
            model_id="llama3.1:8b",
            permission_scope="local-contact-allowed",
            local_only_mode=True,
        ),
        decision,
    )
    cfg = _config.load_config("proj-batchb", "proj-batchb")
    ok_levels = [
        {"level": "quick", "local_ai_allowed": True},
        {"level": "deep", "local_ai_allowed": True, "resource_cap": {"vram_gb": 8.0}},
    ]
    checked = _config.require_local_ai_allowed_at_used_levels(cfg, ok_levels)
    assert checked == ["quick", "deep"]
    with pytest.raises(_config.LocalAISettingsError) as excinfo:
        _config.require_local_ai_allowed_at_used_levels(
            cfg, [{"level": "quick"}]
        )
    assert excinfo.value.code == _config.LOCAL_AI_LOCAL_ONLY_VIOLATION
    with pytest.raises(_config.LocalAISettingsError):
        _config.require_local_ai_allowed_at_used_levels(
            cfg, [{"level": "x", "local_ai_allowed": True, "resource_cap": {}}]
        )
    permissive = _config.LocalAIConfig(
        project_key="proj-batchb",
        endpoint_url="http://127.0.0.1:11434",
        model_id="llama3.1:8b",
        permission_scope="local-contact-allowed",
    )
    assert _config.require_local_ai_allowed_at_used_levels(permissive, []) == []


def test_batchb_activation_gate_no_mutation(_clean_store) -> None:
    """B0B-UNCOVERED_BP06-48: block activation, never mutate stored config."""
    before = copy.deepcopy(_config._STORE.get("proj-a"))
    decision = _config.record_decision("proj-a", "local-only on", "r", "owner")
    _config.save_config(
        _config.LocalAIConfig(
            project_key="proj-a",
            endpoint_url="http://127.0.0.1:11434",
            model_id="llama3.1:8b",
            permission_scope="local-contact-allowed",
            local_only_mode=True,
        ),
        decision,
    )
    assert (
        _config.check_local_only_activation(
            "proj-a", [{"level": "q", "local_ai_allowed": True}]
        )
        is True
    )
    with pytest.raises(_config.LocalAISettingsError) as excinfo:
        _config.check_local_only_activation("proj-a", [{"level": "q"}])
    assert excinfo.value.code == _config.LOCAL_AI_LOCAL_ONLY_VIOLATION
    assert _config._STORE.get("proj-a") is not None
    assert before is None or _config._STORE["proj-a"].local_only_mode is True


def test_batchb_decision_record_and_scope(_clean_store) -> None:
    """111 + B0B-UNCOVERED_BP05-70: decision record required; scope guarded."""
    rec = _config.record_decision("proj-batchb", "stmt", "reason", "owner")
    assert rec.project_id == "proj-batchb"
    assert rec.decision_id.startswith("dec-")
    cfg = _config.LocalAIConfig(
        project_key="proj-batchb",
        endpoint_url="http://127.0.0.1:11434",
        model_id="m",
        permission_scope="local-contact-allowed",
    )
    with pytest.raises(_config.LocalAISettingsError) as excinfo:
        _config.save_config(cfg, None)
    assert excinfo.value.code == _config.LOCAL_AI_DECISION_RECORD_REQUIRED
    _config.save_config(cfg, rec)
    assert _config.load_config("proj-batchb", "proj-batchb") == cfg
    with pytest.raises(_config.LocalAISettingsError) as excinfo2:
        _config.load_config("proj-batchb", "proj-other")
    assert excinfo2.value.code == _config.LOCAL_AI_PROJECT_SCOPE_VIOLATION


def test_batchb_validators_and_explicit_patch(_clean_store) -> None:
    """B0B-UNCOVERED_MVP_ACCEPT-181: endpoint/model/permission + explicit patch."""
    with pytest.raises(_config.LocalAISettingsError) as excinfo:
        _config.validate_endpoint("no-scheme-here")
    assert excinfo.value.code == _config.LOCAL_AI_INVALID_ENDPOINT
    with pytest.raises(_config.LocalAISettingsError):
        _config.validate_model("")
    with pytest.raises(_config.LocalAISettingsError) as excinfo3:
        _config.validate_permission("wrong-scope")
    assert excinfo3.value.code == _config.LOCAL_AI_INVALID_PERMISSION
    rec = _config.record_decision("proj-a", "patch model", "r", "owner")
    updated = _config.update_config("proj-a", {"model_id": "m2"}, rec)
    assert updated.model_id == "m2"
    with pytest.raises(_config.LocalAISettingsError) as excinfo4:
        _config.update_config("proj-a", {"capability_evidence": "X"}, rec)
    assert excinfo4.value.code == _config.LOCAL_AI_AMBIGUOUS_FIELD


def test_batchb_served_estimate_check_scan(tmp_path) -> None:
    """Served bench surface over the real bench store (estimate/check/scan)."""
    client = _served_client()
    estimate = client.get(
        "/api/v1/local/bench/estimate",
        params={"model_id": "batchb-model", "level": "Deep"},
    )
    assert estimate.status_code == 200, estimate.text
    body = estimate.json()
    assert body["level"] == BenchLevel.Deep.value
    assert body["minutes_min"] >= 30.0
    assert body["minutes_max"] >= body["minutes_min"]
    refused = client.get(
        "/api/v1/local/bench/check", params={"endpoint": "https://api.openai.com"}
    )
    assert refused.status_code == 200, refused.text
    assert refused.json()["reachable"] is False
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "batchb-8b.gguf").write_text("fake-weights", encoding="utf-8")
    scanned = client.get(
        "/api/v1/local/bench/scan",
        params={"path": str(models_dir), "allowlist": str(tmp_path)},
    )
    assert scanned.status_code == 200, scanned.text
    assert scanned.json() == ["batchb-8b.gguf"]
    assert _proto.level_floor_minutes(BenchLevel.Quick, 8.0)[0] >= 5.0
