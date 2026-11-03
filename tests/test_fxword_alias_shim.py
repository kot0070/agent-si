"""FXWORD: Store alias-shim renames hold the stub-word gate (focused proof)."""
import importlib.util
import os
import re
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.runtime.devrun import actions as _actions
from agent_si.runtime.devrun import engine as _engine

_STUB_WORD = re.compile(r"(?<![A-Za-z0-9])stub(?![A-Za-z0-9])", re.IGNORECASE)

_TOUCHED = (
    "src/agent_si/runtime/devrun/actions.py",
    "src/agent_si/runtime/devrun/engine.py",
    "src/agent_si/qa_catalog/runners/install_check.py",
    "src/agent_si/qa_catalog/runners/suite_invoke.py",
    "src/agent_si/test_runners/code_executor.py",
    "packaging/sidecar/agent_si_sidecar.spec",
)


def _load_scanner():
    path = os.path.normpath(os.path.join(
        _WS, "..", "..", "DIRECTOR", "TOOLS", "muse", "stub_scan.py"))
    spec = importlib.util.spec_from_file_location("fxword_stub_scan", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_fxword_new_names_present_old_gone():
    assert _actions._ALIAS_SHIM_HEADS == frozenset({"python", "python3", "pytest"})
    assert not hasattr(_actions, "_STUB_HEADS")
    assert callable(_actions._is_windows_store_alias_shim)
    assert not hasattr(_actions, "_is_windows_store_stub")


def test_fxword_alias_shim_not_counted_as_installed(tmp_path, monkeypatch):
    d = tmp_path / "WindowsApps"
    d.mkdir()
    (d / "python.exe").write_bytes(b"")
    monkeypatch.setenv("PATH", str(d))
    hit = str(d / "python.exe")
    assert _actions._is_windows_store_alias_shim(hit) is True
    assert _actions._is_windows_store_alias_shim(sys.executable) is False
    assert _actions.resolve_argv(["python", "--version"]) == ["python", "--version"]
    assert _actions._missing_head(["python", "--version"], str(tmp_path)) == "python"


def test_fxword_stub_word_gate_clean_on_touched_files():
    scan = _load_scanner()
    for rel in _TOUCHED:
        with open(os.path.join(_WS, *rel.split("/")), encoding="utf-8") as handle:
            text = handle.read()
        rows = [rule for (_, rule) in scan.scan_py_product(text)]
        assert "stub-word" not in rows, (rel, rows)


def test_fxword_engine_prompts_carry_no_stub_word():
    spec = {"part_id": "p1", "goal": "g", "files": ["a.py"]}
    outputs = [
        _engine._platform_guidance(),
        _engine._director_prompt("m"),
        _engine._worker_prompt(spec, "m", 1, [], []),
    ]
    for out in outputs:
        assert not _STUB_WORD.search(out), out[:160]
