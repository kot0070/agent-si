"""FXHIGH item 2: automation resume fails closed on the budget guard.

RED: with no budget hook bound, resume() of a paused over-budget
automation currently succeeds (fail-open). Expected: AUTOMATION_PAUSED,
like admit_budget_call with a missing gate; hook present + refusing
also raises; the served resume route wires the real gate-backed check.
"""
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
_WS = os.path.dirname(_TESTS_DIR)
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest  # noqa: E402

import agent_si.automation.interface as auto_iface  # noqa: E402
from agent_si.automation import runner  # noqa: E402
from agent_si.automation.interface import AutomationError  # noqa: E402
from agent_si.backend import automation_routes  # noqa: E402
from agent_si.budget.gate import BudgetGate  # noqa: E402
from agent_si.runtime import manager as _manager  # noqa: E402

_PROJ = "fxhigh-budget-proj"
_TPL = "tpl-fxhigh-budget"


@pytest.fixture()
def _paused_run():
    prev_hook = runner._budget
    prev_gate = getattr(_manager, "_BUDGET_GATE", None)
    runner.reset_state()
    runner.set_budget_hook(None)
    _manager.set_budget_gate(None)
    runner.register_template(_TPL, _PROJ, "fxhigh budget")
    started = runner.start_run(_PROJ, _TPL, now=2000.0)
    runner.cancel_run(_PROJ, started.run_id, reason="restart")
    yield started.run_id
    runner.reset_state()
    runner.set_budget_hook(prev_hook)
    _manager.set_budget_gate(prev_gate)


def _code(excinfo):
    return getattr(excinfo.value, "code", "")


def test_hook_present_blocks_over_budget(_paused_run):
    runner.set_budget_hook(lambda project_id: False)
    with pytest.raises(AutomationError) as excinfo:
        runner.resume(_PROJ, _paused_run, now=2060.0)
    assert _code(excinfo) == "AUTOMATION_PAUSED"
    assert "budget" in (excinfo.value.detail or "")


def test_hook_missing_raises(_paused_run):
    runner.set_budget_hook(None)
    with pytest.raises(AutomationError) as excinfo:
        runner.resume(_PROJ, _paused_run, now=2060.0)
    assert _code(excinfo) == "AUTOMATION_PAUSED"
    assert "budget" in (excinfo.value.detail or "")


def test_hook_allows_within_budget(_paused_run):
    runner.set_budget_hook(lambda project_id: True)
    resumed = runner.resume(_PROJ, _paused_run, now=2060.0)
    assert resumed.state == "RUNNING"


def _gate(*projects, hard="1000.00"):
    gate = BudgetGate()
    for project in projects:
        gate.configure_project(project, "USD", "1000.00", "900.00", hard)
    return gate


def test_real_check_refuses_without_gate():
    _manager.set_budget_gate(None)
    assert automation_routes.real_budget_check(_PROJ) is False


def test_real_check_refuses_unknown_project():
    _manager.set_budget_gate(_gate("other-proj"))
    try:
        assert automation_routes.real_budget_check(_PROJ) is False
    finally:
        _manager.set_budget_gate(None)


def test_real_check_allows_configured_project():
    _manager.set_budget_gate(_gate(_PROJ))
    try:
        assert automation_routes.real_budget_check(_PROJ) is True
    finally:
        _manager.set_budget_gate(None)


def test_real_check_refuses_zero_hard_limit():
    _manager.set_budget_gate(_gate(_PROJ, hard="0.00"))
    try:
        assert automation_routes.real_budget_check(_PROJ) is False
    finally:
        _manager.set_budget_gate(None)


def test_configure_installs_budget_hook(_paused_run):
    automation_routes.configure(
        lambda token: True, None, None,
        budget_hook=lambda project_id: False)
    try:
        with pytest.raises(AutomationError) as excinfo:
            runner.resume(_PROJ, _paused_run, now=2060.0)
        assert _code(excinfo) == "AUTOMATION_PAUSED"
    finally:
        automation_routes.configure(lambda token: True, None, None,
                                    budget_hook=None)
        runner.set_budget_hook(None)
