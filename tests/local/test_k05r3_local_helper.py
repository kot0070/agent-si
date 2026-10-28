"""K05R3 helper tests: on-demand local helper via the gateway (B0B-BP03-47).

Busy/idle outcomes are driven only by the documented env seams
(AGENT_SI_BENCH_RUN_ID / AGENT_SI_TEST_RUN_ID). Test isolation resets the
frozen one-shot serial grant with importlib.reload of the gateway module
object (stdlib mechanism, no private names); the helper keeps pointing at
the same module object, so it sees the reset. No product patching.
"""
from __future__ import annotations

import importlib
import inspect
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from agent_si.local import gateway  # noqa: E402
from agent_si.local import k05r3_helper as helper  # noqa: E402

_BENCH_ENV = "AGENT_SI_BENCH_RUN_ID"
_TEST_ENV = "AGENT_SI_TEST_RUN_ID"


@pytest.fixture(autouse=True)
def _serial_machine(monkeypatch):
    """Isolation: clear env seams and reset the serial grant before each test."""
    monkeypatch.delenv(_BENCH_ENV, raising=False)
    monkeypatch.delenv(_TEST_ENV, raising=False)
    importlib.reload(gateway)
    yield
    monkeypatch.delenv(_BENCH_ENV, raising=False)
    monkeypatch.delenv(_TEST_ENV, raising=False)
    importlib.reload(gateway)


def _make_idle(monkeypatch):
    """Restore an idle machine between lifecycle phases inside one test."""
    monkeypatch.delenv(_BENCH_ENV, raising=False)
    monkeypatch.delenv(_TEST_ENV, raising=False)
    importlib.reload(gateway)


def test_attach_idle_allowed():
    got = helper.attach_helper("assignment-1")
    assert got.assignment_ref == "assignment-1"
    assert got.helper_id.startswith("k05r3-helper-")
    assert got.gateway_reason == gateway.GATEWAY_IDLE_REASON
    assert got.started is False


def test_attach_busy_bench_refused(monkeypatch):
    monkeypatch.setenv(_BENCH_ENV, "user-bench-1")
    with pytest.raises(helper.HelperError) as excinfo:
        helper.attach_helper("assignment-1")
    assert excinfo.value.code == helper.K05R3_HELPER_GATEWAY_BUSY
    assert "USER_BENCH_RUNNING" in str(excinfo.value)
    _make_idle(monkeypatch)
    assert helper.attach_helper("assignment-1").started is False


def test_attach_busy_test_refused(monkeypatch):
    monkeypatch.setenv(_TEST_ENV, "user-test-1")
    with pytest.raises(helper.HelperError) as excinfo:
        helper.attach_helper("assignment-1")
    assert excinfo.value.code == helper.K05R3_HELPER_GATEWAY_BUSY
    assert "USER_TEST_RUNNING" in str(excinfo.value)


@pytest.mark.parametrize("bad", ["", None, 42])
def test_attach_bad_ref_refused(bad):
    with pytest.raises(helper.HelperError) as excinfo:
        helper.attach_helper(bad)
    assert excinfo.value.code == helper.K05R3_HELPER_BAD_REF


def test_start_reverifies_idle(monkeypatch):
    attached = helper.attach_helper("assignment-1")
    _make_idle(monkeypatch)
    started = helper.start_helper(attached)
    assert started.helper_id == attached.helper_id
    assert started.started is True
    assert started.gateway_reason == gateway.GATEWAY_IDLE_REASON


def test_start_busy_never_forces(monkeypatch):
    attached = helper.attach_helper("assignment-1")
    monkeypatch.setenv(_BENCH_ENV, "user-bench-1")
    with pytest.raises(helper.HelperError) as excinfo:
        helper.start_helper(attached)
    assert excinfo.value.code == helper.K05R3_HELPER_GATEWAY_BUSY
    _make_idle(monkeypatch)
    assert helper.start_helper(attached).started is True


def test_start_unknown_and_double_start_refused(monkeypatch):
    with pytest.raises(helper.HelperError) as excinfo:
        helper.start_helper("not-an-attachment")
    assert excinfo.value.code == helper.K05R3_HELPER_STATE_REFUSED
    attached = helper.attach_helper("assignment-1")
    _make_idle(monkeypatch)
    started = helper.start_helper(attached)
    with pytest.raises(helper.HelperError) as excinfo:
        helper.start_helper(started)
    assert excinfo.value.code == helper.K05R3_HELPER_STATE_REFUSED


def test_release_full_cycle_records_gateway(monkeypatch):
    attached = helper.attach_helper("assignment-1")
    _make_idle(monkeypatch)
    started = helper.start_helper(attached)
    _make_idle(monkeypatch)
    released = helper.release_helper(started)
    assert released.helper_id == attached.helper_id
    assert released.started is True
    assert released.gateway_reason == gateway.GATEWAY_IDLE_REASON


def test_release_completes_under_busy_gateway(monkeypatch):
    attached = helper.attach_helper("assignment-1")
    monkeypatch.setenv(_TEST_ENV, "user-test-1")
    released = helper.release_helper(attached)
    assert released.started is False
    assert released.gateway_reason == "USER_TEST_RUNNING"
    with pytest.raises(helper.HelperError) as excinfo:
        helper.release_helper(released)
    assert excinfo.value.code == helper.K05R3_HELPER_STATE_REFUSED


def test_gateway_entry_point_has_no_force():
    assert "force" not in inspect.signature(gateway.passive_check).parameters
    assert os.environ.get(_BENCH_ENV) is None
    assert os.environ.get(_TEST_ENV) is None


def test_error_codes_new_module_only():
    assert tuple(helper.ERROR_CODES_K05R3_HELPER) == (
        "K05R3_HELPER_GATEWAY_BUSY",
        "K05R3_HELPER_STATE_REFUSED",
        "K05R3_HELPER_BAD_REF",
    )
    for code in helper.ERROR_CODES_K05R3_HELPER:
        assert code not in gateway.GATEWAY_SKIP_REASONS
