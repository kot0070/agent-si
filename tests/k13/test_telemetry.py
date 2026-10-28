"""Lane T telemetry tests: TelemetryEvent envelope (Manifest §55) + secrets (§20A).

Probes owned by lane T (fake-secret fixtures only, isolated memory store):
  B-002  fake-secret record refused-or-redacted
  B-005  private-content export holds the §59 allowlist only
  B-006  wrapped fake secret redacted everywhere
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from agent_si.telemetry import metrics, telemetry
from iface.frozen_manifest import manifest

FAKE_SECRET = "FAKE-SECRET-T-PROBE-7f3a9c2e"


@pytest.fixture(autouse=True)
def isolated_secret_store(monkeypatch):
    """Probes run against an isolated in-memory store; no real secrets."""
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    assert os.environ["AGENT_SI_SECRET_STORE"] == "memory"
    return {"probe-key": FAKE_SECRET}


def _event(**overrides):
    base = dict(
        event_id="evt-1",
        project_id="P1",
        timestamp="2026-10-26T00:00:00Z",
        task_id="T1",
        event_type="TASK_CREATED",
    )
    base.update(overrides)
    return telemetry.TelemetryEvent(**base)


def test_manifest_verified():
    assert manifest.MANIFEST_SHA256 == "f256bab4d31be3cd9e86c22a1bdcef90b08ad62500a8eca2051705cc0a9b0690"
    assert manifest.verify_manifest(ROOT / "iface" / "frozen_manifest" / "K13_MANIFEST.md") is True


def test_project_id_required():
    with pytest.raises(telemetry.MissingProjectIdError):
        _event(project_id="")


def test_unknown_event_type_rejected():
    with pytest.raises(telemetry.UnknownEventTypeError):
        _event(event_type="NO_SUCH_TYPE")


def test_event_type_sets_required_identity_fields():
    with pytest.raises(telemetry.MissingIdentityFieldError):
        _event(event_type="RUN_STARTED", run_id=None)
    with pytest.raises(telemetry.MissingIdentityFieldError):
        _event(event_type="ATTEMPT_STARTED", task_id="T1", run_id="R1", attempt_id=None)
    ok = _event(event_type="ATTEMPT_STARTED", run_id="R1", attempt_id="A1")
    assert ok.run_id == "R1"


def test_duplicate_event_id_returns_stored():
    log = telemetry.TelemetryEventLog()
    first = log.append(_event())
    second = log.append(_event(state="changed"))
    assert second is first
    assert len(log) == 1


def test_envelopes_append_only():
    log = telemetry.TelemetryEventLog()
    stored = log.append(_event())
    with pytest.raises(Exception):
        stored.state = "mutated"  # frozen dataclass: no rewrite
    assert log.load("evt-1") is stored


def test_b002_fake_secret_record_refused(isolated_secret_store):
    log = telemetry.TelemetryEventLog()
    leaked = _event(event_type="TASK_CREATED", route=FAKE_SECRET)
    with pytest.raises(telemetry.SecretLeakRefusedError):
        log.append(leaked, known_secrets=[FAKE_SECRET])
    assert log.load("evt-1") is None
    clean = telemetry.redact({"route": FAKE_SECRET}, [FAKE_SECRET])
    assert FAKE_SECRET not in repr(clean)


def test_b006_wrapped_fake_secret_redacted_everywhere(isolated_secret_store):
    wrapped = {
        "prompt": ["discuss", {"token": FAKE_SECRET}],
        "refs": (FAKE_SECRET,),
        "nested": {"deep": [{"deeper": "prefix-" + FAKE_SECRET + "-suffix"}]},
        "safe": "untouched value",
    }
    out = telemetry.redact(wrapped, [FAKE_SECRET])
    assert FAKE_SECRET not in repr(out)
    assert out["safe"] == "untouched value"
    assert out["refs"][0] == telemetry.REDACTED


def test_secret_ref_shape():
    ref = telemetry.SecretRef(
        secret_id="sec-1",
        provider_id="prov-a",
        type="api_key",
        scope="project:P1",
        source="os-store",
        created_at="2026-10-26T00:00:00Z",
        last_rotated_at="2026-10-26T00:00:00Z",
    )
    assert ref.secret_id == "sec-1"
    assert telemetry.redact(ref, [FAKE_SECRET]) is ref  # refs carry no raw values


def test_b005_export_holds_allowlist_only():
    dataset = {
        "PROJECT": {"project_id": "P1"},
        "TASKS": [{"task_id": "T1"}],
        "PROMPT_TEXT": "private prompt content",
        "RAW_SECRET": FAKE_SECRET,
        "FILE_CONTENT": "private file bytes",
    }
    exported = telemetry.filter_export_dataset(dataset)
    assert set(exported) == {"PROJECT", "TASKS"}
    assert FAKE_SECRET not in repr(exported)
    for key in telemetry.EXPORT_ALLOWLIST:
        assert isinstance(key, str)


def test_metric_record_requires_value_unit_state_source():
    with pytest.raises(Exception):
        metrics.MetricRecord(
            metric_id="m-1",
            project_id="P1",
            metric_name="input_tokens",
            value=10.0,
            unit="tokens",
            state=metrics.MetricState.MEASURED,
            source="",
        )
    rec = metrics.MetricRecord(
        metric_id="m-1",
        project_id="P1",
        metric_name="input_tokens",
        value=10.0,
        unit="tokens",
        state=metrics.MetricState.MEASURED,
        source="provider-usage-api",
    )
    assert rec.source == "provider-usage-api"


def test_cost_unavailable_without_snapshot():
    usage = metrics.TokenUsage(input_tokens=100, output_tokens=50)
    rec = metrics.CostCalculator.calculate(
        usage, None, metric_id="c-1", project_id="P1"
    )
    assert rec.state == metrics.MetricState.UNAVAILABLE


def test_active_wall_time_interval_union():
    assert metrics.active_wall_time([]) == 0.0
    assert metrics.active_wall_time([(0.0, 10.0), (5.0, 15.0)]) == 15.0
    assert metrics.active_wall_time([(0.0, 5.0), (10.0, 12.0)]) == 7.0
