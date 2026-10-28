# CODER-1 Harbor: K13 0C GuardedToolDispatcher dispatch tests; doubles live only in this file.
"""RED-to-GREEN tests for src/agent_si/sdk_adapter/tool_guard.py.

Every SDK tool call passes admission, limiter and sequence checks before it
runs; an install-class tool call parks the run as APPROVAL_WAITING; a refused
call never runs, returns an honest refusal, and is recorded.
"""

# CODER-1 Harbor: repo convention (contract test lines 28-32): tests put src/ on sys.path.
import os as _os
import sys as _sys

_SRC = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "src"))
if _SRC not in _sys.path:
    _sys.path.insert(0, _SRC)

from agent_si.sdk_adapter.tool_guard import (
    APPROVAL_WAITING,
    INSTALL_TOOL_CLASS,
    REFUSED,
    GuardedToolDispatcher,
    ToolCall,
)


def _allow(check_name):
    return lambda call: (True, check_name + " ok")


def _deny(reason):
    return lambda call: (False, reason)


def _call(tool_name="read_file", tool_class="exec"):
    return ToolCall(
        tool_name=tool_name,
        tool_class=tool_class,
        action_id="a-1",
        project_id="p-1",
        task_id="t-1",
        run_id="r-1",
        args_ref="args/1",
    )


def _allowed_dispatcher():
    return GuardedToolDispatcher(
        admission=_allow("admission"),
        limiter=_allow("limiter"),
        sequence=_allow("sequence"),
    )


def test_allowed_tool_call_runs_run_fn_once():
    dispatcher = _allowed_dispatcher()
    calls = []

    def run_fn(call):
        calls.append(call)
        return "result-1"

    outcome = dispatcher.guarded_call(_call(), run_fn)
    assert outcome.executed is True
    assert outcome.parked is False
    assert outcome.refusal == ""
    assert outcome.result == "result-1"
    assert len(calls) == 1
    assert calls[0].tool_name == "read_file"
    assert outcome.record.decision == "ALLOWED"


def test_admission_refusal_never_runs():
    dispatcher = GuardedToolDispatcher(
        admission=_deny("no admission row"),
        limiter=_allow("limiter"),
        sequence=_allow("sequence"),
    )
    calls = []
    outcome = dispatcher.guarded_call(
        _call(), lambda call: calls.append(call) or "must-not-run"
    )
    assert outcome.executed is False
    assert outcome.parked is False
    assert outcome.result is None
    assert "admission" in outcome.refusal
    assert "no admission row" in outcome.refusal
    assert calls == []
    assert outcome.record.decision == REFUSED


def test_limiter_refusal_never_runs():
    dispatcher = GuardedToolDispatcher(
        admission=_allow("admission"),
        limiter=_deny("over budget"),
        sequence=_allow("sequence"),
    )
    calls = []
    outcome = dispatcher.guarded_call(
        _call(), lambda call: calls.append(call) or "must-not-run"
    )
    assert outcome.executed is False
    assert outcome.parked is False
    assert outcome.result is None
    assert "limiter" in outcome.refusal
    assert "over budget" in outcome.refusal
    assert calls == []
    assert outcome.record.decision == REFUSED


def test_sequence_refusal_never_runs():
    dispatcher = GuardedToolDispatcher(
        admission=_allow("admission"),
        limiter=_allow("limiter"),
        sequence=_deny("out of order"),
    )
    calls = []
    outcome = dispatcher.guarded_call(
        _call(), lambda call: calls.append(call) or "must-not-run"
    )
    assert outcome.executed is False
    assert outcome.parked is False
    assert outcome.result is None
    assert "sequence" in outcome.refusal
    assert "out of order" in outcome.refusal
    assert calls == []
    assert outcome.record.decision == REFUSED


def test_install_class_parks_even_when_allowed():
    dispatcher = _allowed_dispatcher()
    calls = []
    outcome = dispatcher.guarded_call(
        _call(tool_class=INSTALL_TOOL_CLASS),
        lambda call: calls.append(call) or "must-not-run",
    )
    assert outcome.executed is False
    assert outcome.parked is True
    assert outcome.result is None
    assert calls == []
    assert outcome.record.decision == "PARKED"
    assert outcome.record.reason == APPROVAL_WAITING


def test_unbound_predicate_defaults_closed():
    dispatcher = GuardedToolDispatcher()
    calls = []
    outcome = dispatcher.guarded_call(
        _call(), lambda call: calls.append(call) or "must-not-run"
    )
    assert outcome.executed is False
    assert outcome.parked is False
    assert outcome.result is None
    assert "admission" in outcome.refusal
    assert calls == []
    assert outcome.record.decision == REFUSED


def test_refusals_and_parks_are_recorded():
    dispatcher = GuardedToolDispatcher(
        admission=lambda call: (
            (False, "blocked tool") if call.tool_name == "blocked" else (True, "ok")
        ),
        limiter=_allow("limiter"),
        sequence=_allow("sequence"),
    )
    ok = dispatcher.guarded_call(_call(tool_name="read"), lambda call: "read-ok")
    refused = dispatcher.guarded_call(
        _call(tool_name="blocked"), lambda call: "must-not-run"
    )
    parked = dispatcher.guarded_call(
        _call(tool_name="setup", tool_class=INSTALL_TOOL_CLASS),
        lambda call: "must-not-run",
    )
    assert ok.executed is True
    assert refused.executed is False
    assert parked.parked is True
    records = dispatcher.records
    assert isinstance(records, tuple)
    assert [record.decision for record in records] == ["ALLOWED", "REFUSED", "PARKED"]
    seqs = [record.seq for record in records]
    assert seqs == sorted(seqs) and len(set(seqs)) == 3
    assert records[0] is ok.record
    assert records[1] is refused.record
    assert records[2] is parked.record
