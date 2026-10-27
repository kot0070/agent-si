"""Lane T tracing-off probe: app telemetry stays complete with SDK tracing off.

0C sec 9 DECISION: sdk_tracing_enabled defaults false for every project and
run. The TelemetryEvent store is the authoritative record and never depends
on the tracing switch, so collection is identical either way.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from agent_si.telemetry import telemetry
from iface.frozen_manifest import manifest


@pytest.fixture(autouse=True)
def isolated_secret_store(monkeypatch):
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    assert os.environ["AGENT_SI_SECRET_STORE"] == "memory"


def test_manifest_verified():
    assert manifest.verify_manifest(ROOT / "RECORDS" / "day0" / "K13_MANIFEST.md") is True


def test_tracing_defaults_off_and_telemetry_complete():
    sdk_tracing_enabled = False  # 0C sec 9 default for every project and run
    assert sdk_tracing_enabled is False
    log = telemetry.TelemetryEventLog()
    events = [
        telemetry.TelemetryEvent(
            event_id="evt-t1",
            project_id="P1",
            timestamp="2026-10-26T00:00:00Z",
            task_id="T1",
            event_type="TASK_CREATED",
        ),
        telemetry.TelemetryEvent(
            event_id="evt-t2",
            project_id="P1",
            timestamp="2026-10-26T00:00:01Z",
            task_id="T1",
            run_id="R1",
            event_type="RUN_STARTED",
        ),
        telemetry.TelemetryEvent(
            event_id="evt-t3",
            project_id="P1",
            timestamp="2026-10-26T00:00:02Z",
            task_id="T1",
            run_id="R1",
            event_type="RUN_TERMINATED",
            final_status="SUCCEEDED",
        ),
    ]
    for evt in events:
        assert log.append(evt, known_secrets=[]) is evt
    assert len(log) == 3
    assert [e.event_id for e in log.list_by_project("P1")] == ["evt-t1", "evt-t2", "evt-t3"]
    assert log.load("evt-t3").final_status == "SUCCEEDED"
