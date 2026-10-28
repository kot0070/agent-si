"""R-315 RED->GREEN proof: plain chat writes via offered tools.

Pre-change this module FAILS (``chat_adapter`` does not exist);
post-change it PASSES. Every fake below lives only in this test
file; product code routes through the real services belt caller,
the real guard and the real guarded dispatcher.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import agent_si.backend.chat_adapter as chat_adapter  # noqa: E402
import agent_si.worker_tools.dispatcher as belt_dispatcher  # noqa: E402
from agent_si.worker_tools.registry import ToolRegistry  # noqa: E402


def _real_status_impl_factory(calls):
    """Build the real tool impl behind the test entry point."""

    def _real_status_impl(argv, action_class, auth):
        calls.append((list(argv), action_class, dict(auth)))
        return {
            "ok": True,
            "argv": list(argv),
            "action_class": action_class,
            "pid": 4242,
            "output": {"written": ["note.txt"], "bytes": 13},
        }

    return _real_status_impl


class _StatusEntryPoint:  # FAKE-OF: real declared-service entry point
    name = "status"
    action_class = "R0"

    def __init__(self, impl):
        self._impl = impl

    def load(self):
        return self._impl


def _registry_with_status(calls) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(_StatusEntryPoint(_real_status_impl_factory(calls)))
    return registry


def _auth() -> dict:
    return {"subject": "tester", "task": "task-1", "contract": "contract-1"}


def test_offered_tool_routed_via_belt_through_guard(monkeypatch) -> None:
    seen: dict = {}
    real_guarded = belt_dispatcher.guarded_dispatch

    def _spy(argv, action_class, auth, *, tool, registry=None):
        seen["argv"] = list(argv)
        seen["auth"] = dict(auth)
        seen["tool"] = tool
        seen["registry_given"] = registry is not None
        return real_guarded(
            argv, action_class, auth, tool=tool, registry=registry
        )

    monkeypatch.setattr(belt_dispatcher, "guarded_dispatch", _spy)
    calls: list = []
    result = chat_adapter.run_chat_tool(
        ["status"], "R0", _auth(), registry=_registry_with_status(calls)
    )
    assert seen.get("tool") == "status"
    assert seen.get("registry_given") is True
    assert seen.get("argv") == ["status"]
    assert result["output"] == {"written": ["note.txt"], "bytes": 13}
    assert isinstance(result["pid"], int) and result["pid"] > 0
    assert len(calls) == 1


def test_guard_deny_raises_and_performs_no_write() -> None:
    calls: list = []
    with pytest.raises(PermissionError):
        chat_adapter.run_chat_tool(
            ["pip", "install", "x"],
            "R0",
            _auth(),
            tool="status",
            registry=_registry_with_status(calls),
        )
    assert calls == []


def test_unknown_tool_returns_error_without_touching_belt(monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise AssertionError("belt must not run for unknown tools")

    monkeypatch.setattr(belt_dispatcher, "guarded_dispatch", _boom)
    calls: list = []
    assert chat_adapter.run_chat_tool(
        ["nope"], "R0", _auth(), registry=_registry_with_status(calls)
    ) == {"error": "E_UNKNOWN_SERVICE"}
    assert chat_adapter.run_chat_tool(
        ["status"], "R0", _auth(), tool="nope",
        registry=_registry_with_status(calls),
    ) == {"error": "E_UNKNOWN_SERVICE"}
    assert calls == []


def test_bad_argv_rejected_before_belt(monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise AssertionError("belt must not run for bad argv")

    monkeypatch.setattr(belt_dispatcher, "guarded_dispatch", _boom)
    calls: list = []
    assert chat_adapter.run_chat_tool(
        [], "R0", _auth(), registry=_registry_with_status(calls)
    ) == {"error": "E_BAD_ARGV"}
    assert chat_adapter.run_chat_tool(
        [""], "R0", _auth(), registry=_registry_with_status(calls)
    ) == {"error": "E_BAD_ARGV"}
    assert chat_adapter.run_chat_tool(
        "status", "R0", _auth(), registry=_registry_with_status(calls)
    ) == {"error": "E_BAD_ARGV"}
    assert chat_adapter.run_chat_tool(
        ["status", 7], "R0", _auth(), registry=_registry_with_status(calls)
    ) == {"error": "E_BAD_ARGV"}
    assert chat_adapter.run_chat_tool(
        ["status"], "R0", _auth(), tool="",
        registry=_registry_with_status(calls)
    ) == {"error": "E_BAD_ARGV"}
    assert calls == []


def test_bad_action_class_rejected_before_belt(monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise AssertionError("belt must not run for bad action class")

    monkeypatch.setattr(belt_dispatcher, "guarded_dispatch", _boom)
    calls: list = []
    assert chat_adapter.run_chat_tool(
        ["status"], "R9", _auth(), registry=_registry_with_status(calls)
    ) == {"error": "E_BAD_ACTION_CLASS"}
    assert chat_adapter.run_chat_tool(
        ["status"], "", _auth(), registry=_registry_with_status(calls)
    ) == {"error": "E_BAD_ACTION_CLASS"}
    assert calls == []


def test_bad_auth_rejected_before_belt(monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise AssertionError("belt must not run for bad auth")

    monkeypatch.setattr(belt_dispatcher, "guarded_dispatch", _boom)
    calls: list = []
    assert chat_adapter.run_chat_tool(
        ["status"], "R0", {}, registry=_registry_with_status(calls)
    ) == {"error": "E_BAD_AUTH"}
    assert chat_adapter.run_chat_tool(
        ["status"], "R0", "auth", registry=_registry_with_status(calls)
    ) == {"error": "E_BAD_AUTH"}
    assert calls == []


def test_auth_reaches_belt_without_added_privilege(monkeypatch) -> None:
    seen: dict = {}
    real_guarded = belt_dispatcher.guarded_dispatch

    def _spy(argv, action_class, auth, *, tool, registry=None):
        seen["auth"] = dict(auth)
        return real_guarded(
            argv, action_class, auth, tool=tool, registry=registry
        )

    monkeypatch.setattr(belt_dispatcher, "guarded_dispatch", _spy)
    calls: list = []
    sent = _auth()
    chat_adapter.run_chat_tool(
        ["status"], "R0", sent, registry=_registry_with_status(calls)
    )
    assert seen.get("auth") == sent
    assert "token" not in seen.get("auth", {})
    assert "scopes" not in seen.get("auth", {})
    assert "approvals" not in seen.get("auth", {})


def test_adapter_performs_no_filesystem_io() -> None:
    source = Path(chat_adapter.__file__).read_text(encoding="utf-8")
    assert len(source) > 0
    assert "run_declared_service_via_belt" in source
    for token in (
        "open(",
        "pathlib",
        "shutil",
        "import os",
        "from os",
        "os.write",
        "os.remove",
        "os.mkdir",
        "os.rename",
        "os.replace",
        "os.unlink",
        "os.makedirs",
        "os.open",
        "os.fdopen",
        "write_text",
        "write_bytes",
        "import io",
    ):
        assert token not in source, token


def test_adapter_adds_no_new_belt_call_site() -> None:
    source = Path(chat_adapter.__file__).read_text(encoding="utf-8")
    assert "run_declared_service_via_belt" in source
    for token in (
        "guarded_dispatch",
        "get_registry",
        "ToolRegistry",
        ".dispatch(",
    ):
        assert token not in source, token
