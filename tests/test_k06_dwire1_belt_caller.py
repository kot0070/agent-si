"""DWIRE1 RED->GREEN proof: the services production caller uses the belt.

Pre-change this module FAILS (``commands`` exposes no belt caller);
post-change it PASSES. Every fake below lives only in this test file;
product code calls the real registry plus the real guarded dispatcher.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import agent_si.services.commands as commands  # noqa: E402
import agent_si.worker_tools.dispatcher as belt_dispatcher  # noqa: E402
from agent_si.worker_tools.registry import ToolRegistry  # noqa: E402


def _real_status_impl(argv, action_class, auth):  # FAKE-OF: real service impl
    return {
        "ok": True,
        "argv": list(argv),
        "action_class": action_class,
        "pid": 4242,
        "output": {"service": "status"},
    }


class _StatusEntryPoint:  # FAKE-OF: real declared-service entry point
    name = "status"
    action_class = "R0"

    def load(self):
        return _real_status_impl


def _registry_with_status() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(_StatusEntryPoint())
    return registry


def _auth() -> dict:
    return {"subject": "tester", "task": "task-1", "contract": "contract-1"}


def test_production_belt_caller_exists() -> None:
    assert callable(getattr(commands, "run_declared_service_via_belt", None))


def test_caller_executes_through_real_guarded_dispatch(monkeypatch) -> None:
    seen: dict = {}
    real_guarded = belt_dispatcher.guarded_dispatch

    def _spy(argv, action_class, auth, *, tool, registry=None):
        seen["argv"] = list(argv)
        seen["tool"] = tool
        seen["registry_given"] = registry is not None
        return real_guarded(
            argv, action_class, auth, tool=tool, registry=registry
        )

    monkeypatch.setattr(belt_dispatcher, "guarded_dispatch", _spy)
    result = commands.run_declared_service_via_belt(
        ["status"], "R0", _auth(), registry=_registry_with_status()
    )
    assert seen.get("tool") == "status"
    assert seen.get("registry_given") is True
    assert seen.get("argv") == ["status"]
    assert result["output"] == {"service": "status"}
    assert isinstance(result["pid"], int) and result["pid"] > 0


def test_caller_defaults_to_process_registry(monkeypatch) -> None:
    hits: list = []

    def _fake_get_registry():
        hits.append(True)
        return _registry_with_status()

    monkeypatch.setattr(
        belt_dispatcher, "get_registry", _fake_get_registry
    )
    result = commands.run_declared_service_via_belt(
        ["status"], "R0", _auth()
    )
    assert hits == [True]
    assert result["output"] == {"service": "status"}


def test_caller_rejects_unknown_service_before_belt(monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise AssertionError("belt must not run for unknown services")

    monkeypatch.setattr(belt_dispatcher, "guarded_dispatch", _boom)
    result = commands.run_declared_service_via_belt(
        ["nope"], "R0", _auth(), registry=_registry_with_status()
    )
    assert result == {"error": "E_UNKNOWN_SERVICE"}


def test_caller_rejects_bad_argv_before_belt(monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise AssertionError("belt must not run for bad argv")

    monkeypatch.setattr(belt_dispatcher, "guarded_dispatch", _boom)
    assert commands.run_declared_service_via_belt(
        [], "R0", _auth(), registry=_registry_with_status()
    ) == {"error": "E_BAD_ARGV"}
    assert commands.run_declared_service_via_belt(
        ["status"], "R9", _auth(), registry=_registry_with_status()
    ) == {"error": "E_BAD_ACTION_CLASS"}
    assert commands.run_declared_service_via_belt(
        ["status"], "R0", {}, registry=_registry_with_status()
    ) == {"error": "E_BAD_AUTH"}
