"""STEP 1 behaviour contract for the Lane B portability prefix.

MUST be RED: every stub body is `...` (returns None), so every behavior
assertion below fails. Structure assertions (files exist, modules import,
no shell strings) pass. Behavior waits for STEP 2 after HD freeze.

Covers: package files exist, modules import cleanly, every error code in
its own condition, every route reaches its real impl via the entry point,
every call surface wired, guard receives argv-only, UNKNOWN-state reads.
"""

import importlib.util
import pathlib

PORT_DIR = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src"
    / "agent_si"
    / "portability"
)
INIT_FILE = PORT_DIR / "__init__.py"
ERRORS_FILE = PORT_DIR / "errors.py"
DETECTION_FILE = PORT_DIR / "detection.py"
MERGE_FILE = PORT_DIR / "merge.py"
RUNNERS_FILE = PORT_DIR / "runners.py"
PAGE_FILE = PORT_DIR / "page.py"
COMMANDS_FILE = PORT_DIR / "commands.py"

EXPECTED_COMMAND_ROUTES = (
    "detect",
    "merge",
    "runners",
    "page",
    "check",
)

ERROR_CONDITIONS = {
    "PORT_UNKNOWN_ENVIRONMENT": {"route": "detect", "argv": ["detect", "gpu"]},
    "PORT_GUARD_DENIED": {"route": "detect", "argv": ["detect"], "guard": "deny"},
    "PORT_RUNNER_UNKNOWN": {"route": "runners", "argv": ["runners", "nope"]},
    "PORT_RUNNER_NOT_ENABLED": {"route": "check", "argv": ["check", "disabled"]},
    "PORT_MERGE_UNAVAILABLE": {"route": "merge", "argv": ["merge", "missing"]},
    "PORT_COMMAND_UNKNOWN": {"route": "nope", "argv": ["nope"]},
}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# FAKE-OF: src.agent_si.toolguard.guard
class _FakeGuard:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, action_class, auth):
        self.calls.append(
            {"argv": list(argv), "action_class": action_class}
        )
        return {
            "decision": "allow",
            "reason": "fake-allow",
            "evidence_ref": "fake-ref",
        }


# FAKE-OF: src.agent_si.toolguard.guard
class _DenyGuard:
    def __call__(self, argv, action_class, auth):
        return {
            "decision": "deny",
            "reason": "fake-deny",
            "evidence_ref": "fake-deny-ref",
        }


def test_package_files_exist():
    for path in (
        INIT_FILE,
        ERRORS_FILE,
        DETECTION_FILE,
        MERGE_FILE,
        RUNNERS_FILE,
        PAGE_FILE,
        COMMANDS_FILE,
    ):
        assert path.is_file()


def test_modules_import():
    _load("port_init", INIT_FILE)
    _load("port_errors", ERRORS_FILE)
    _load("port_detection", DETECTION_FILE)
    _load("port_merge", MERGE_FILE)
    _load("port_runners", RUNNERS_FILE)
    _load("port_page", PAGE_FILE)
    _load("port_commands", COMMANDS_FILE)


def test_no_shell_strings():
    for path in (
        INIT_FILE,
        ERRORS_FILE,
        DETECTION_FILE,
        MERGE_FILE,
        RUNNERS_FILE,
        PAGE_FILE,
        COMMANDS_FILE,
    ):
        text = path.read_text(encoding="utf-8")
        for token in ("shell=True", "os.system", "subprocess", "Popen"):
            assert token not in text


def test_detect_this_pc_returns_mapping():
    mod = _load("port_detection_check", DETECTION_FILE)
    detected = mod.detect_this_pc()
    assert isinstance(detected, dict)
    assert detected["status"] in ("KNOWN", mod.UNKNOWN)


def test_unmeasurable_reads_report_unknown():
    mod = _load("port_detection_unknown", DETECTION_FILE)
    state = mod.read_environment_state(["gpu", "local-ai"])
    assert isinstance(state, dict)
    assert state["gpu"] == mod.UNKNOWN


def test_merge_project_environment_returns_mapping():
    mod = _load("port_merge_check", MERGE_FILE)
    merged = mod.merge_project_environment("proj", {"pc": "x"})
    assert isinstance(merged, dict)
    assert merged["project_id"] == "proj"


def test_runner_feed_uses_declared_params():
    mod = _load("port_runners_check", RUNNERS_FILE)
    params = mod.declared_runner_params("default")
    assert isinstance(params, dict)
    fed = mod.feed_runners("default", params)
    assert isinstance(fed, dict)
    assert fed["runner"] == "default"


def test_page_data_and_check_dry_run():
    mod = _load("port_page_check", PAGE_FILE)
    data = mod.get_detected_environment_page_data({})
    assert isinstance(data, dict)
    assert "matrix" in data
    checked = mod.check_on_this_pc(["enabled-script"], {})
    assert isinstance(checked, dict)
    assert checked["dry_run"] is True


def test_every_command_route_reaches_impl():
    mod = _load("port_commands_routes", COMMANDS_FILE)
    assert list(mod.list_commands()) == list(EXPECTED_COMMAND_ROUTES)
    guard = _FakeGuard()
    for route in EXPECTED_COMMAND_ROUTES:
        result = mod.run_command([route], "R0", {}, guard)
        assert isinstance(result, dict)
        assert result["route"] == route


def test_every_error_code_in_own_condition():
    commands = _load("port_commands_errors", COMMANDS_FILE)
    errors = _load("port_errors_check", ERRORS_FILE)
    assert tuple(errors.ERROR_CODES) == tuple(ERROR_CONDITIONS)
    for code, condition in ERROR_CONDITIONS.items():
        if condition.get("guard") == "deny":
            guard = _DenyGuard()
        else:
            guard = _FakeGuard()
        result = commands.run_command(
            list(condition.get("argv", [condition["route"]])), "R0", {}, guard
        )
        assert isinstance(result, dict)
        assert result["error"] == code


def test_auth_case_fixture_key_ignored():
    """leak2 regression: auth['case'] must not steer routes; argv does."""
    mod = _load("port_commands_nocase", COMMANDS_FILE)
    guard = _FakeGuard()
    denied = mod.run_command(
        ["detect"], "R0", {"case": {"denied": True}}, guard
    )
    assert isinstance(denied, dict)
    assert denied.get("error") != "PORT_GUARD_DENIED"
    merged = mod.run_command(
        ["merge", "real-proj"], "R0", {"case": {"project": "missing"}}, guard
    )
    assert isinstance(merged, dict)
    assert merged.get("project_id") == "real-proj"
    assert "error" not in merged


def test_guard_receives_argv_only():
    mod = _load("port_commands_guard", COMMANDS_FILE)
    guard = _FakeGuard()
    argv = ["detect", "--pc"]
    mod.run_command(argv, "R0", {}, guard)
    assert len(guard.calls) == 1
    assert guard.calls[0]["argv"] == argv
    assert guard.calls[0]["action_class"] == "R0"
