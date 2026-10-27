"""Lane A STEP2 probes (252 chain / 254 install-record / B-011 / no-install / scope-diff).

Runs against the real worker_tools registry + guarded dispatcher.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_si.worker_tools import ToolRegistry, guarded_dispatch  # noqa: E402
from agent_si.worker_tools.registry import ToolNotFoundError  # noqa: E402


def _real_echo_impl(argv, action_class, auth):
    return {
        "ok": True,
        "argv": list(argv),
        "action_class": action_class,
        "pid": 4242,
        "output": {"words": list(argv)},
    }


class _EchoEntryPoint:
    name = "echo"
    action_class = "R1"

    def load(self):
        return _real_echo_impl


def _fresh_echo_registry():
    registry = ToolRegistry()
    registry.register(_EchoEntryPoint())
    return registry


def _allow_double(monkeypatch, record=None):
    def _evaluate(argv, action_class, auth):
        if record is not None:
            record.append((argv, action_class, auth))
        return {"decision": "allow", "reason": "probe", "evidence_ref": "ev-allow"}

    module = types.ModuleType("agent_si.toolguard")
    module.evaluate = _evaluate
    monkeypatch.setitem(sys.modules, "agent_si.toolguard", module)
    return _evaluate


def _deny_double(monkeypatch):
    def _evaluate(argv, action_class, auth):
        return {"decision": "deny", "reason": "generated class", "evidence_ref": "ev-deny"}

    module = types.ModuleType("agent_si.toolguard")
    module.evaluate = _evaluate
    monkeypatch.setitem(sys.modules, "agent_si.toolguard", module)
    return _evaluate


def test_252_chain_demo_ok():
    registry = _fresh_echo_registry()
    argv = ["echo", "hello"]
    result = guarded_dispatch(
        argv, "R1",
        {"subject": "worker", "scopes": ["tools:exec"], "contract": "contract-1"},
        tool="echo", registry=registry,
    )
    assert result["ok"] is True
    assert result["argv"] == argv
    assert result["action_class"] == "R1"
    assert isinstance(result["pid"], int) and result["pid"] > 0
    assert result["output"] == {"words": ["echo", "hello"]}


def test_252_generated_auth_end_to_end_deny(monkeypatch):
    _deny_double(monkeypatch)
    with pytest.raises(PermissionError):
        guarded_dispatch(
            ["echo", "hello"], "R1", {"subject": "worker"},
            tool="echo", registry=_fresh_echo_registry(),
        )


def test_254_install_record_view_unknown_names_tool():
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError) as excinfo:
        guarded_dispatch(
            ["nope"], "R2",
            {
                "subject": "worker",
                "contract": "contract-1",
                "director_record": "director-1",
            },
            tool="nope", registry=registry,
        )
    assert "nope" in str(excinfo.value)
    registry.register(_EchoEntryPoint())
    assert "echo" in registry.names()


def test_b011_active_content_round_trips_inert():
    registry = _fresh_echo_registry()
    payload = "<script>alert('x')</script><b>markup</b>"
    argv = ["echo", payload]
    result = guarded_dispatch(
        argv, "R1",
        {"subject": "worker", "scopes": ["tools:exec"], "contract": "contract-1"},
        tool="echo", registry=registry,
    )
    assert result["output"] == {"words": ["echo", payload]}
    assert result["output"]["words"][1] == payload
    assert isinstance(result["output"]["words"][1], str)


def test_auto_install_disabled_unknown_raises_before_load(monkeypatch):
    _allow_double(monkeypatch)
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError) as excinfo:
        guarded_dispatch(
            ["nope", "x"], "R2", {"subject": "worker"},
            tool="nope", registry=registry,
        )
    assert "nope" in str(excinfo.value)
    assert registry.names() == []


def test_scope_diff_declared_only(monkeypatch):
    seen = {}

    def _capturing_impl(argv, action_class, auth):
        seen.update(dict(auth))
        return {
            "ok": True,
            "argv": list(argv),
            "action_class": action_class,
            "pid": 4242,
            "output": {"words": list(argv)},
        }

    class _CapEntryPoint:
        name = "cap"
        action_class = "R1"

        def load(self):
            return _capturing_impl

    calls = []
    _allow_double(monkeypatch, record=calls)
    registry = ToolRegistry()
    registry.register(_CapEntryPoint())
    result = guarded_dispatch(
        ["cap", "run"], "R1",
        {"subject": "worker", "scopes": ["tools:exec", "admin"]},
        tool="cap", registry=registry,
    )
    assert result["ok"] is True
    assert seen.get("scopes") == ["tools:exec", "admin"]
    assert calls and calls[0][2] == {"subject": "worker", "scopes": ["tools:exec", "admin"]}
