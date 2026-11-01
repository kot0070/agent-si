"""FXFROZEN RED->GREEN gate: frozen-exe breaks R1-R10 (FROZENSCAN_0101).

Proves, with ``sys.frozen`` faked True plus a fake ``sys._MEIPASS``:
- code_executor helper never returns the exe (R6-R8),
- k07next locale resolves inside _MEIPASS (R9),
- sidecar spec text names every report module (R1-R5),
- k09rows imports agent_si.kb with no sys.path hack (R3/R10).

R11 (registry-facades default path) is NOT-DONE: unowned file, untouched.
Helper/locale names are picked once here and in product code together:
``frozen_python`` (code_executor) and ``frozen_locale_dir`` (k07next).
"""

import json
import os
import shutil
import sys
from pathlib import Path

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest  # noqa: E402

from agent_si.test_runners import code_executor  # noqa: E402
from agent_si.http import k07next  # noqa: E402

SPEC_PATH = os.path.join(
    _WS, "packaging", "sidecar", "agent_si_sidecar.spec")
K09ROWS_PATH = os.path.join(
    _WS, "src", "agent_si", "backend", "k09rows.py")

FAKE_EXE = os.path.join("C:" + os.sep, "bundle", "AgentSI.exe")


def _freeze(monkeypatch, meipass=None):
    """Fake a frozen bundle: sys.frozen True, sys.executable the exe."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", FAKE_EXE, raising=False)
    if meipass is not None:
        monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    else:
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)


def test_helper_present_and_source_mode_returns_executable():
    """Helper exists; unfrozen it returns sys.executable."""
    helper = getattr(code_executor, "frozen_python", None)
    assert callable(helper), "code_executor.frozen_python missing (R6-R8)"
    assert helper() == sys.executable
    assert isinstance(helper(), str)


def test_helper_frozen_env_override_wins(monkeypatch, tmp_path):
    """Frozen: AGENT_SI_PYTHON (set, existing, != exe) is returned."""
    _freeze(monkeypatch)
    python = tmp_path / "python-signal"
    python.write_text("x", encoding="utf-8")
    monkeypatch.setenv("AGENT_SI_PYTHON", str(python))
    assert code_executor.frozen_python() == str(python)


def test_helper_frozen_ignores_exe_and_missing_env(monkeypatch, tmp_path):
    """Frozen: env pointing at the exe (or nowhere) is never returned."""
    _freeze(monkeypatch)
    monkeypatch.setenv("AGENT_SI_PYTHON", FAKE_EXE)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError):
        code_executor.frozen_python()
    monkeypatch.setenv(
        "AGENT_SI_PYTHON",
        str(tmp_path / "no-such-python"))
    with pytest.raises(RuntimeError):
        code_executor.frozen_python()


def test_helper_frozen_skips_which_hits_equal_exe(monkeypatch, tmp_path):
    """Frozen: PATH hits equal to the exe are skipped; else first hit."""
    _freeze(monkeypatch)
    monkeypatch.delenv("AGENT_SI_PYTHON", raising=False)
    real = tmp_path / "bin" / "python3"
    real.parent.mkdir(parents=True)
    real.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        shutil, "which",
        lambda name: FAKE_EXE if name == "python" else str(real))
    assert code_executor.frozen_python() == str(real)
    monkeypatch.setattr(shutil, "which", lambda _name: FAKE_EXE)
    with pytest.raises(RuntimeError):
        code_executor.frozen_python()


def test_resolve_and_default_argv_use_helper_frozen(monkeypatch, tmp_path):
    """Frozen: resolve + execute default argv start with helper, not exe."""
    _freeze(monkeypatch)
    python = tmp_path / "mypython"
    python.write_text("x", encoding="utf-8")
    monkeypatch.setenv("AGENT_SI_PYTHON", str(python))
    project = tmp_path / "proj"
    project.mkdir()
    (project / "test_probe.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8")
    argv, reason = code_executor.resolve_code_command(
        project_dir=str(project), test_id="probe")
    assert reason is None
    assert argv[0] == str(python)
    assert argv[0] != FAKE_EXE
    seen = {}

    class _Done:
        returncode = 0
        stdout = b"ok"
        stderr = b""

    def _fake_run(argv2, **_kw):
        seen["argv"] = list(argv2)
        return _Done()

    monkeypatch.setattr(code_executor.subprocess, "run", _fake_run)
    data_root = tmp_path / "data"
    data_root.mkdir()
    outcome = code_executor.execute_code_test(
        data_root=str(data_root), project_id="p1", test_id="probe")
    assert outcome.status == "PASS"
    assert seen["argv"][0] == str(python)
    assert seen["argv"][0] != FAKE_EXE


def test_locale_frozen_inside_meipass(monkeypatch, tmp_path):
    """Frozen: locale dir is Path(_MEIPASS)/locale; tables load from it."""
    meipass = tmp_path / "meipass"
    locale = meipass / "locale"
    locale.mkdir(parents=True)
    doc = {"section": {"title": "Title"}}
    (locale / "en.json").write_text(json.dumps(doc), encoding="utf-8")
    (locale / "uk.json").write_text(json.dumps(doc), encoding="utf-8")
    _freeze(monkeypatch, meipass=meipass)
    helper = getattr(k07next, "frozen_locale_dir", None)
    assert callable(helper), "k07next.frozen_locale_dir missing (R9)"
    assert helper() == Path(str(meipass)) / "locale"
    coverage = k07next.locale_coverage()
    assert coverage["parity"] is True
    assert coverage["en_leaves"] == coverage["uk_leaves"] == 1


def test_locale_source_mode_keeps_parents_expression():
    """Unfrozen: helper keeps the current parents[3] source expression."""
    assert getattr(sys, "frozen", False) is False
    expected = (Path(k07next.__file__).resolve().parents[3]
                / "frontend" / "src" / "locale")
    assert k07next.frozen_locale_dir() == expected
    coverage = k07next.locale_coverage()
    assert isinstance(coverage["en_leaves"], int)
    assert isinstance(coverage["uk_leaves"], int)


def test_spec_names_every_report_module():
    """Spec keeps 4 hiddenimports + covers all 5 report modules (R1-R5)."""
    with open(SPEC_PATH, encoding="utf-8") as handle:
        text = handle.read()
    for kept in ("iface.frozen_manifest.manifest",
                 "agent_si.watcher.interface",
                 "agent_si.automation.interface",
                 "agent_si.context_keeper.interface"):
        assert kept in text, "spec lost existing hiddenimport " + kept
    for covered in ("agent_si.backend.runtime_manager",
                    "agent_si.toolguard.ask",
                    "agent_si.services.channel_eval"):
        assert covered in text, "spec misses report module " + covered
    assert "kb_validator" in text, "spec misses tools/kb_validator cover"
    assert "frontend/src/locale" in text
    assert '"locale"' in text


def test_k09rows_uses_agent_si_kb_imports_without_sys_path():
    """k09rows imports agent_si.kb submodules; sys.path hack gone (R10)."""
    with open(K09ROWS_PATH, encoding="utf-8") as handle:
        text = handle.read()
    assert "from agent_si.kb import" in text
    assert "from src.agent_si.kb import" not in text
    assert "sys.path" not in text
    router = k09rows_router()
    paths = sorted(
        route.path for route in router.routes
        if getattr(route, "path", "").startswith("/api/v1/kb/"))
    assert paths == ["/api/v1/kb/live", "/api/v1/kb/savings",
                     "/api/v1/kb/telemetry", "/api/v1/kb/validate"]


def k09rows_router():
    """Import the fixed module late so the import itself is the proof."""
    from agent_si.backend import k09rows as module
    return module.k09b_router
