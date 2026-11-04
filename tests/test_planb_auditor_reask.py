"""PLANB: a malformed auditor reply is re-asked once; two bad replies stay FAIL."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_si.runtime.devrun import audit, roles  # noqa: E402

BAD = '{"result": "PASS", "reasons": ["the "test" ran"]}'
GOOD = '{"result": "PASS", "reasons": ["tests green"]}'


class _Coordinator:
    def record_auditor_verdict(self, **kwargs):
        self.kwargs = kwargs
        return {"audit_id": "a1", "audit_session": "s1"}


def _judge(monkeypatch, replies):
    calls = []

    def fake_invoke_owned(app, adapter, resolution, messages, **kwargs):
        calls.append(list(messages))
        return SimpleNamespace(output_text=replies[len(calls) - 1]), False, {}

    monkeypatch.setattr(roles, "invoke_owned", fake_invoke_owned)
    coordinator = _Coordinator()
    entry = audit.judge(
        None, coordinator, object(), {"role": "auditor"}, record={},
        project_id="p", run_id="r", task_id="t", part_id="p1", attempt=1,
        producer_ref="w", auditor_ref="a", contract_hash="h", goal="g",
        files_diff="", checks=[], artifact_refs=[])
    return entry, calls, coordinator


def test_second_reply_valid_gives_the_verdict(monkeypatch):
    entry, calls, coordinator = _judge(monkeypatch, [BAD, GOOD])
    assert len(calls) == 2
    assert "not valid JSON" in calls[1][-1]["content"]
    assert entry["result"] == "PASS" and entry["reasons"] == ["tests green"]
    assert coordinator.kwargs["result"] == "PASS"


def test_two_bad_replies_stay_fail(monkeypatch):
    entry, calls, _ = _judge(monkeypatch, [BAD, BAD])
    assert len(calls) == 2
    assert entry["result"] == "FAIL"
    assert entry["reasons"][0].startswith("auditor output malformed")


def test_valid_first_reply_asks_once(monkeypatch):
    entry, calls, _ = _judge(monkeypatch, [GOOD])
    assert len(calls) == 1 and entry["result"] == "PASS"
