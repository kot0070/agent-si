"""STEP 1 behaviour contract for the Lane B services prefix (RED-until-impl).

Every behaviour assertion routes via the entry point
``run_command(..., guard_evaluate=...)`` with an injected fake guard, so
unimplemented ``...`` bodies (returning ``Ellipsis``) FAIL. STEP 2 must
implement ``list_commands``/``run_command`` to G1 for these to pass.

Error codes (defined here, frozen in RETURN.md round 2 NEW-NAMES):
E_BAD_ARGV, E_BAD_ACTION_CLASS, E_BAD_AUTH.
"""

import importlib.util
import inspect
import pathlib
from typing import Any

SERVICES_DIR = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src"
    / "agent_si"
    / "services"
)
INIT_FILE = SERVICES_DIR / "__init__.py"
COMMANDS_FILE = SERVICES_DIR / "commands.py"


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# FAKE-OF: src.agent_si.toolguard.guard
# Test-only fake of the G1 Lane A guard
# evaluate(argv, action_class, auth) -> decision/reason/evidence_ref.
# Never imported by src/; passed in as the guard_evaluate injection.
def fake_guard_evaluate(
    argv: list[str], action_class: str, auth: dict[str, Any]
) -> dict[str, Any]:
    calls: list[tuple[list[str], str, dict[str, Any]]] = getattr(
        fake_guard_evaluate, "calls", []
    )
    calls.append((list(argv), action_class, dict(auth)))
    fake_guard_evaluate.calls = calls  # type: ignore[attr-defined]
    return {
        "decision": "allow",
        "reason": "fake allow",
        "evidence_ref": "fake-evidence",
    }


def _reset_fake() -> None:
    fake_guard_evaluate.calls = []  # type: ignore[attr-defined]


def _fake_calls() -> list[tuple[list[str], str, dict[str, Any]]]:
    return list(getattr(fake_guard_evaluate, "calls", []))


def test_package_files_exist() -> None:
    assert INIT_FILE.is_file()
    assert COMMANDS_FILE.is_file()


def test_modules_import() -> None:
    _load("svc_init", INIT_FILE)
    _load("svc_commands", COMMANDS_FILE)


def test_stub_callables_exist() -> None:
    mod = _load("svc_commands_check", COMMANDS_FILE)
    assert callable(mod.list_commands)
    assert callable(mod.run_command)
    assert mod.ACTION_CLASSES == ("R0", "R1", "R2", "R3")


def test_no_shell_strings() -> None:
    text = COMMANDS_FILE.read_text(encoding="utf-8")
    for token in ("shell=True", "os.system", "subprocess", "Popen"):
        assert token not in text


def test_run_command_signature_wired() -> None:
    """The entry point must expose the injected guard_evaluate parameter.

    A rename of ``guard_evaluate`` breaks this test (mutation-sensitive).
    """
    mod = _load("svc_commands_sig", COMMANDS_FILE)
    params = inspect.signature(mod.run_command).parameters
    assert "guard_evaluate" in params
    assert list(params)[:4] == ["argv", "action_class", "auth", "guard_evaluate"]


def test_list_commands_returns_known_set() -> None:
    mod = _load("svc_commands_list", COMMANDS_FILE)
    cmds = mod.list_commands()
    assert isinstance(cmds, list)
    assert len(cmds) > 0
    assert all(isinstance(c, str) and c for c in cmds)


def test_run_command_happy_path_returns_guard_shape() -> None:
    mod = _load("svc_commands_happy", COMMANDS_FILE)
    _reset_fake()
    result = mod.run_command(
        ["status"],
        "R0",
        {"user": "tester"},
        guard_evaluate=fake_guard_evaluate,
    )
    assert isinstance(result, dict)
    assert result["decision"] in ("allow", "ask", "deny")
    assert isinstance(result["reason"], str) and result["reason"]
    assert isinstance(result["evidence_ref"], str) and result["evidence_ref"]
    routed = _fake_calls()
    assert len(routed) == 1
    assert routed[0][0] == ["status"]


def test_run_command_bad_argv_error_code() -> None:
    mod = _load("svc_commands_argv", COMMANDS_FILE)
    _reset_fake()
    result = mod.run_command(
        [],
        "R0",
        {"user": "tester"},
        guard_evaluate=fake_guard_evaluate,
    )
    assert isinstance(result, dict)
    assert result.get("error") == "E_BAD_ARGV"


def test_run_command_bad_action_class_error_code() -> None:
    mod = _load("svc_commands_cls", COMMANDS_FILE)
    _reset_fake()
    result = mod.run_command(
        ["status"],
        "R9",
        {"user": "tester"},
        guard_evaluate=fake_guard_evaluate,
    )
    assert isinstance(result, dict)
    assert result.get("error") == "E_BAD_ACTION_CLASS"


def test_run_command_bad_auth_error_code() -> None:
    mod = _load("svc_commands_auth", COMMANDS_FILE)
    _reset_fake()
    result = mod.run_command(
        ["status"],
        "R0",
        {},
        guard_evaluate=fake_guard_evaluate,
    )
    assert isinstance(result, dict)
    assert result.get("error") == "E_BAD_AUTH"
