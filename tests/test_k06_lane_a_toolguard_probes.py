"""Lane A STEP2 toolguard probes (B-007/B-008/B-009/B-010, 252 chain,
backslash-exact, SecretRef redaction, DATA-never-instructions).

Runs against the real toolguard modules and the real
worker_tools guarded dispatch path (read-only use). The echo
route below is a probe-local double carrying a FAKE-OF mark.
"""

# FAKE-OF: tests/toolguard-probe-echo (probe-local echo route double)
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_si.toolguard import ask, guard, secrets  # noqa: E402
from agent_si.worker_tools import ToolRegistry, guarded_dispatch  # noqa: E402
from agent_si.worker_tools.registry import ToolNotFoundError  # noqa: E402

OUTSIDE_PATH = "C:\\Windows\\Temp\\k06_lane_a_outside.txt"

B008_VARIANTS = (
    "c:/windows/temp/k06_lane_a_outside.txt",
    "C:\\Windows\\Temp\\..\\Temp\\k06_lane_a_outside.txt",
    "C:/Windows\\Temp/./k06_lane_a_outside.txt",
)

B009_CASES = (
    ("fetch", "http://127.0.0.1:8080/x", "127.0.0.1"),
    ("fetch", "http://localhost:3000/", "localhost"),
    ("fetch", "http://169.254.169.254/latest", "169.254.169.254"),
    ("fetch", "http://10.0.0.5/", "10.0.0.5"),
    ("fetch", "http://[::1]/", "::1"),
)

B010_FLAGS = ("--allow-all", "--privileged", "--bypass", "--no-sandbox")

TASK_AUTH = {"task": "t1"}
CONTRACT_AUTH = {"contract": "c1"}
CHAIN_AUTH = {"subject": "worker", "scopes": ["tools:exec"], "contract": "c1"}


# FAKE-OF: tests/toolguard-probe-echo (probe-local echo route double)
def _probe_echo_impl(argv, action_class, auth):
    return {
        "ok": True,
        "argv": list(argv),
        "action_class": action_class,
        "output": {"words": list(argv)},
    }


# FAKE-OF: tests/toolguard-probe-echo (probe-local echo entry point double)
class _ProbeEchoEntryPoint:
    name = "echo"
    action_class = "R1"

    def load(self):
        return _probe_echo_impl


def _echo_registry():
    registry = ToolRegistry()
    registry.register(_ProbeEchoEntryPoint())
    return registry


def test_b007_write_outside_root_refused_naming_path():
    verdict = guard.evaluate(
        ["write", OUTSIDE_PATH], "R0", dict(TASK_AUTH),
    )
    assert verdict["decision"] == "deny"
    assert OUTSIDE_PATH in verdict["reason"]
    inside = os.path.join(os.getcwd(), "k06_lane_a_inside.txt")
    allowed = guard.evaluate(["write", inside], "R0", dict(TASK_AUTH))
    assert allowed["decision"] == "allow"


def test_b008_alternate_spelling_replay_refused():
    for variant in B008_VARIANTS:
        verdict = guard.evaluate(["write", variant], "R0", dict(TASK_AUTH))
        assert verdict["decision"] == "deny"
        assert variant in verdict["reason"]


def test_b009_internal_address_fetch_refused_naming_host():
    for tool, target, host in B009_CASES:
        verdict = guard.evaluate([tool, target], "R1", dict(CONTRACT_AUTH))
        assert verdict["decision"] == "deny"
        assert host in verdict["reason"]
    external = guard.evaluate(
        ["fetch", "https://example.com/x"], "R1", dict(CONTRACT_AUTH),
    )
    assert external["decision"] == "allow"


def test_b010_widened_flag_refused_naming_flag():
    for flag in B010_FLAGS:
        verdict = guard.evaluate(["echo", flag], "R1", dict(CONTRACT_AUTH))
        assert verdict["decision"] == "deny"
        assert flag in verdict["reason"]
    plain = guard.evaluate(["echo", "--color=always"], "R1", dict(CONTRACT_AUTH))
    assert plain["decision"] == "allow"


def test_str_argv_denied_naming_it():
    verdict = guard.evaluate("echo hi", "R0", dict(TASK_AUTH))
    assert verdict["decision"] == "deny"
    assert "echo hi" in verdict["reason"]


def test_252_chain_demo_via_real_guard_evaluate():
    argv = ["echo", "hello"]
    result = guarded_dispatch(
        argv, "R1", dict(CHAIN_AUTH), tool="echo", registry=_echo_registry(),
    )
    assert result["ok"] is True
    assert result["argv"] == argv
    assert result["action_class"] == "R1"
    assert result["pid"] == os.getpid()
    assert isinstance(result["pid"], int) and result["pid"] > 0
    assert result["output"] == {"words": ["echo", "hello"]}


def test_auto_install_disabled_unknown_tool_never_fetches():
    with pytest.raises(PermissionError) as excinfo:
        guarded_dispatch(
            ["pip", "install", "requests"], "R1", dict(CHAIN_AUTH),
            tool="pip", registry=ToolRegistry(),
        )
    assert "pip" in str(excinfo.value)
    with pytest.raises(ToolNotFoundError) as excinfo:
        guarded_dispatch(
            ["nope"], "R1", dict(CHAIN_AUTH), tool="nope", registry=ToolRegistry(),
        )
    assert "nope" in str(excinfo.value)


def test_backslash_exact_write_path_preserved():
    verdict = guard.evaluate(["write", OUTSIDE_PATH], "R0", dict(TASK_AUTH))
    assert verdict["decision"] == "deny"
    assert "C:\\Windows\\Temp\\k06_lane_a_outside.txt" in verdict["reason"]
    assert "/" not in verdict["reason"].split(OUTSIDE_PATH)[0].split(":")[-1]
    relative = "some\\nested\\file.txt"
    result = guarded_dispatch(
        ["echo", relative], "R1", dict(CHAIN_AUTH),
        tool="echo", registry=_echo_registry(),
    )
    assert result["output"] == {"words": ["echo", relative]}
    assert "\\" in result["output"]["words"][1]
    assert result["output"]["words"][1] == relative


def test_secret_ref_redaction_raw_absent():
    raw = "vault://prod/api-key-SECRET123"
    ref = secrets.make_secret_ref(ref=raw)
    assert isinstance(ref, str)
    assert secrets.is_secret_ref(ref) is True
    assert raw not in ref
    assert "SECRET123" not in ref
    assert secrets.is_secret_ref(raw) is False
    assert secrets.is_secret_ref("") is False
    assert secrets.is_secret_ref(None) is False
    card = ask.build_ask_card(
        ask_id="q1",
        kind="approve",
        summary="Allow this action?",
        options=["yes", "no"],
        resume_token=ref,
    )
    assert raw not in repr(card)


def test_data_never_instructions_active_content_inert():
    payload = "<script>alert('x')</script><b>markup</b>"
    result = guarded_dispatch(
        ["echo", payload], "R1", dict(CHAIN_AUTH),
        tool="echo", registry=_echo_registry(),
    )
    assert result["output"] == {"words": ["echo", payload]}
    assert result["output"]["words"][1] == payload
    assert isinstance(result["output"]["words"][1], str)
