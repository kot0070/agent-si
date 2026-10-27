"""Lane A behaviour contract (STEP1 STUB -- all tests RED until STEP2).

Every route must reach its real implementation via a registered entry
point, and every call surface (argv list, action_class R0-R3, auth dict)
must be wired through the guarded dispatcher and ``toolguard.evaluate``.
Bodies in ``worker_tools/`` are ``...`` stubs, so each test below FAILS
for now.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_si.worker_tools import (  # noqa: E402
    ToolRegistry,
    get_registry,
    guarded_dispatch,
)
from agent_si.worker_tools.registry import ToolNotFoundError  # noqa: E402

ACTION_CLASSES = ("R0", "R1", "R2", "R3")


def _real_echo_impl(argv, action_class, auth):  # FAKE-OF: real echo tool impl
    return {
        "ok": True,
        "argv": list(argv),
        "action_class": action_class,
        "pid": 4242,
        "output": {"words": list(argv)},
    }


class _FakeEntryPoint:  # FAKE-OF: real tool entry point behind the registry
    name = "echo"
    action_class = "R1"

    def load(self):
        return _real_echo_impl


def _registry_with_echo():
    registry = ToolRegistry()
    registry.register(_FakeEntryPoint())
    return registry


def test_route_reaches_real_impl_via_entry_point():
    registry = _registry_with_echo()
    loaded = registry.load("echo")
    assert loaded is _real_echo_impl
    assert loaded(["hello"], "R1", {})["output"] == {"words": ["hello"]}


@pytest.mark.parametrize("action_class", ACTION_CLASSES)
def test_guarded_dispatch_wires_every_call_surface(action_class):
    registry = _registry_with_echo()
    argv = ["echo", "hello"]
    auth = {
        "subject": "worker",
        "scopes": ["tools:exec"],
        "task": "task-1",
        "contract": "contract-1",
        "director_record": "director-1",
        "user_record": "user-1",
    }
    result = guarded_dispatch(
        argv, action_class, auth, tool="echo", registry=registry
    )
    assert isinstance(result, dict)
    assert result["ok"] is True
    assert result["argv"] == argv
    assert result["action_class"] == action_class


def test_argv_only_guard_rejects_shell_string():
    with pytest.raises(TypeError):
        guarded_dispatch(
            "echo hello",  # type: ignore[arg-type]  # G1: never a shell string
            "R1",
            {},
            tool="echo",
            registry=_registry_with_echo(),
        )


def test_dispatch_calls_toolguard_evaluate(monkeypatch):
    # FAKE-OF: agent_si.toolguard.evaluate (read-only G2/G5 usage)
    calls = []

    def _spy(*args, **kwargs):
        calls.append((args, kwargs))
        return {"allow": True}

    module = types.ModuleType("agent_si.toolguard")
    module.evaluate = _spy
    monkeypatch.setitem(sys.modules, "agent_si.toolguard", module)
    guarded_dispatch(
        ["echo", "hello"], "R1", {"subject": "worker"}, tool="echo",
        registry=_registry_with_echo(),
    )
    assert calls, "guarded_dispatch never called toolguard.evaluate"


def test_unknown_tool_raises_instead_of_installing():
    with pytest.raises(ToolNotFoundError):
        guarded_dispatch(
            ["nope"], "R2",
            {
                "subject": "worker",
                "contract": "contract-1",
                "director_record": "director-1",
            },
            tool="nope", registry=ToolRegistry(),
        )


def test_result_carries_real_pid_and_data_output():
    result = guarded_dispatch(
        ["echo", "hello"], "R1", {"subject": "worker", "contract": "contract-1"},
        tool="echo", registry=_registry_with_echo(),
    )
    assert isinstance(result, dict)
    assert isinstance(result["pid"], int) and result["pid"] > 0
    assert result["output"] == {"words": ["echo", "hello"]}


def test_registry_none_resolves_to_real_registry():
    # HD rule: registry=None (5th param default) must resolve to the REAL
    # registry in product code, never a fake/empty default.
    real_registry = get_registry()  # FAKE-OF: process-wide real registry
    assert real_registry is not None
    real_registry.register(_FakeEntryPoint())
    argv = ["echo", "hello"]
    action_class = "R1"
    auth = {
        "subject": "worker",
        "scopes": ["tools:exec"],
        "contract": "contract-1",
    }
    result = guarded_dispatch(argv, action_class, auth, tool="echo")
    assert isinstance(result, dict)
    assert result["ok"] is True
    assert result["argv"] == argv
    assert result["action_class"] == action_class


def test_guarded_dispatch_no_token_refuses():
    with pytest.raises(PermissionError):
        guarded_dispatch(
            ["echo", "hello"], "R1", {}, tool="echo",
            registry=_registry_with_echo(),
        )


def test_guarded_dispatch_wrong_token_refuses():
    forged_auth = {"subject": "worker", "token": "forged-bad-token"}  # FAKE-OF: forged credential
    with pytest.raises(PermissionError):
        guarded_dispatch(
            ["echo", "hello"], "R1", forged_auth, tool="echo",
            registry=_registry_with_echo(),
        )


def test_registry_dispatch_no_token_refuses():
    registry = _registry_with_echo()
    with pytest.raises(PermissionError):
        registry.dispatch("echo", ["echo", "hello"], "R1", {})


def test_registry_dispatch_wrong_token_refuses():
    registry = _registry_with_echo()
    forged_auth = {"subject": "worker", "token": "forged-bad-token"}  # FAKE-OF: forged credential
    with pytest.raises(PermissionError):
        registry.dispatch("echo", ["echo", "hello"], "R1", forged_auth)


def test_ladder_r0_allow_with_task():
    result = guarded_dispatch(
        ["echo", "hello"], "R0",
        {"subject": "worker", "scopes": ["tools:exec"], "task": "task-1"},
        tool="echo", registry=_registry_with_echo(),
    )
    assert result["ok"] is True


def test_ladder_r0_deny_without_task():
    with pytest.raises(PermissionError) as excinfo:
        guarded_dispatch(
            ["echo", "hello"], "R0",
            {"subject": "worker", "scopes": ["tools:exec"]},
            tool="echo", registry=_registry_with_echo(),
        )
    assert "ERR_R0_NOT_TASK_AUTHORIZED" in str(excinfo.value)


def test_ladder_r1_allow_with_contract():
    result = guarded_dispatch(
        ["echo", "hello"], "R1",
        {"subject": "worker", "scopes": ["tools:exec"], "contract": "contract-1"},
        tool="echo", registry=_registry_with_echo(),
    )
    assert result["ok"] is True


def test_ladder_r1_deny_without_contract():
    with pytest.raises(PermissionError) as excinfo:
        guarded_dispatch(
            ["echo", "hello"], "R1",
            {"subject": "worker", "scopes": ["tools:exec"]},
            tool="echo", registry=_registry_with_echo(),
        )
    assert "ERR_R1_CONTRACT_REQUIRED" in str(excinfo.value)


def test_ladder_r2_allow_with_director_record():
    result = guarded_dispatch(
        ["echo", "hello"], "R2",
        {
            "subject": "worker",
            "scopes": ["tools:exec"],
            "contract": "contract-1",
            "director_record": "director-1",
        },
        tool="echo", registry=_registry_with_echo(),
    )
    assert result["ok"] is True


def test_ladder_r2_deny_without_director_record():
    with pytest.raises(PermissionError) as excinfo:
        guarded_dispatch(
            ["echo", "hello"], "R2",
            {"subject": "worker", "scopes": ["tools:exec"], "contract": "contract-1"},
            tool="echo", registry=_registry_with_echo(),
        )
    assert "ERR_R2_DIRECTOR_RECORD_REQUIRED" in str(excinfo.value)


def test_ladder_r3_allow_with_user_record():
    result = guarded_dispatch(
        ["echo", "hello"], "R3",
        {
            "subject": "worker",
            "scopes": ["tools:exec"],
            "contract": "contract-1",
            "user_record": "user-1",
        },
        tool="echo", registry=_registry_with_echo(),
    )
    assert result["ok"] is True


def test_ladder_r3_deny_without_user_record():
    with pytest.raises(PermissionError) as excinfo:
        guarded_dispatch(
            ["echo", "hello"], "R3",
            {"subject": "worker", "scopes": ["tools:exec"], "contract": "contract-1"},
            tool="echo", registry=_registry_with_echo(),
        )
    assert "ERR_R3_USER_RECORD_REQUIRED" in str(excinfo.value)
