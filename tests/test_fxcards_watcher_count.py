"""FXCARDS C4 RED: a decision row names a model only for a counted call.

Answered watcher-model call: the row carries model= AND stats count it,
so status names the model. Unanswered (transport failure): the row names
no model and stats stay 0. A legacy row naming model= with no counted
call reads "Rules only": the card can never say a model beside 0 calls.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from agent_si.watcher import journal as _journal
from agent_si.watcher import rules as _rules
from agent_si.watcher import stats as _stats
from agent_si.watcher import status as _status


@pytest.fixture(autouse=True)
def _lane():
    _journal.reset_state()
    _rules.reset_state()
    _stats.reset_state()
    yield
    _journal.reset_state()
    _rules.reset_state()
    _stats.reset_state()


_FXCARDS_GATE_PROJECTS = (
    "fxcards-c4-answered",
    "fxcards-c4-unanswered",
    "fxcards-c4-legacy",
)


@pytest.fixture(autouse=True)
def _real_budget_gate():
    from agent_si.budget.gate import BudgetGate
    from agent_si.runtime import manager as _manager

    prev = _manager._BUDGET_GATE
    gate = BudgetGate()
    for project in _FXCARDS_GATE_PROJECTS:
        gate.configure_project(
            project, "USD", "1000000.00", "900000.00", "1000000.00")
    _manager.set_budget_gate(gate)
    yield
    _manager.set_budget_gate(prev)


class _AnsweringTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, model, rule_id, allowed):
        self.calls.append(model)
        script, params = allowed[0]
        return {"script": script, "params": list(params),
                "usage": {"input_tokens": 10, "output_tokens": 5}}


class _FailingTransport:
    def __call__(self, model, rule_id, allowed):
        raise ConnectionError("watcher model down")


def test_answered_call_counted_and_named():
    pid = "fxcards-c4-answered"
    _rules.configure_watcher_model(
        transport=_AnsweringTransport(), local_model="fx-local-1",
        local_connected=True, cloud_model="", cloud_connected=False,
        cloud_fallback=False)
    _journal.append_event(pid, "agent-x", "TAMPER_ATTEMPT",
                          "edited log", ("ref-1",))
    _rules.evaluate(pid, "rule-tamper")
    rows = list(_journal.stored_rows(pid, "WATCH_DECISION"))
    assert len(rows) == 1
    assert "model=fx-local-1" in rows[0].summary, rows[0].summary
    assert _stats.get_stats(pid)["watcher_calls"] == 1
    assert _status.get(pid).watcher_model == "fx-local-1"


def test_unanswered_row_names_no_model_and_counts_zero():
    pid = "fxcards-c4-unanswered"
    _rules.configure_watcher_model(
        transport=_FailingTransport(), local_model="fx-local-1",
        local_connected=True, cloud_model="", cloud_connected=False,
        cloud_fallback=False)
    _journal.append_event(pid, "agent-x", "TAMPER_ATTEMPT",
                          "edited log", ("ref-1",))
    _rules.evaluate(pid, "rule-tamper")
    rows = list(_journal.stored_rows(pid, "WATCH_DECISION"))
    assert len(rows) == 1
    assert "model=" not in rows[0].summary, rows[0].summary
    assert _stats.get_stats(pid)["watcher_calls"] == 0
    assert _status.get(pid).watcher_model == "Rules only"


def test_legacy_model_row_without_count_reads_rules_only():
    pid = "fxcards-c4-legacy"
    _journal.append_event(
        pid, "watcher", "WATCH_DECISION",
        "rule-tamper BLOCK model=API action=signal-higher-level",
        ("rule-tamper",))
    assert _stats.get_stats(pid)["watcher_calls"] == 0
    assert _status.get(pid).watcher_model == "Rules only"
