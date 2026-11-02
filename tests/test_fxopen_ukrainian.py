"""FXOPEN O3 (SG-01..04): Ukrainian task end to end on the real path.

SG-01: child bytes decode without crash; Python children are forced
to UTF-8 at spawn so console output stays readable.
SG-02: a Cyrillic part_id returns a decomposition record (no crash),
the id rides the part_id field, the gated reason stays ASCII.
SG-03: a Cyrillic settings key refuses cleanly naming the key rule
(never a falsified `-----` row); ASCII keys record verbatim.
SG-04: acceptance probes decode as UTF-8 regardless of locale.
"""
from __future__ import annotations

import ast
import locale
import os
import subprocess
import sys
from pathlib import Path

import pytest

_WS = Path(__file__).resolve().parents[1]
_SRC = _WS / "src"
for _entry in (str(_WS), str(_SRC)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from agent_si.runtime.devrun import actions as _actions  # noqa: E402
from agent_si.backend.orchestration import hierarchy as _hierarchy  # noqa: E402
from agent_si.backend.orchestration import split as _split  # noqa: E402
from agent_si.backend.orchestration import teamcard as _teamcard  # noqa: E402

GOAL = "Проаналізуй вимоги та підготуй звіт"
FILENAME = "звіт-аналіз.txt"


def _hostile_cp866(monkeypatch):
    """Pretend the parent console speaks cp866 (Ukrainian OEM box)."""
    monkeypatch.setenv("PYTHONIOENCODING", "cp866")
    monkeypatch.delenv("PYTHONUTF8", raising=False)


def test_fxopen_sg01_served_ukrainian_child_readable(monkeypatch, tmp_path):
    """Real Python child under a hostile cp866 console stays readable."""
    _hostile_cp866(monkeypatch)
    project = tmp_path / "проєкт"
    project.mkdir()
    (project / FILENAME).write_text(GOAL + "\n", encoding="utf-8")
    env = _actions.scrub_env()
    log_path = project / "run.log"
    code = (
        "import sys; "
        "print('Привіт, ' + sys.argv[1]); "
        "print('файл: ' + sys.argv[2])"
    )
    with open(log_path, "ab") as handle:
        proc = subprocess.run(
            [sys.executable, "-c", code, GOAL, FILENAME],
            cwd=str(project), stdin=subprocess.DEVNULL,
            stdout=handle, stderr=subprocess.STDOUT, env=env,
            timeout=60,
        )
    assert proc.returncode == 0
    tail = _actions.finalize_log(str(log_path))
    assert "Привіт" in tail
    assert GOAL in tail
    assert FILENAME in tail


def test_fxopen_sg01_decode_never_crashes():
    """Legacy console bytes never crash; UTF-8 always round-trips."""
    blob_utf8 = "Привіт, світ!".encode("utf-8")
    assert "Привіт" in _actions._decode_console_text(blob_utf8)
    samples = {
        "cp866": "Привет",
        "cp1251": "Привіт",
        "cp1252": "Grüße",
    }
    for encoding, sample in samples.items():
        text = _actions._decode_console_text(sample.encode(encoding))
        assert isinstance(text, str) and text.strip()


def test_fxopen_sg02_cyrillic_part_id_returns_record():
    """Cyrillic part_id: record returned, id kept, reason ASCII."""
    for mod in (_split, _teamcard):
        rec = mod.record_decomposition("аналіз-вимог", 3)
        assert rec.part_id == "аналіз-вимог"
        assert rec.reason and all(ord(ch) < 128 for ch in rec.reason)


def test_fxopen_sg02_served_facts_keep_cyrillic_id():
    """R-301 served row keeps a Cyrillic part_id with an ASCII reason."""
    answer = _teamcard.serve_decomposition_facts({
        "part_id": "аналіз-вимог",
        "size_units": 3,
        "provider": "p",
        "model_kb_facts": {"k": "v"},
        "budget_left": {"n": 1},
        "limits": {"m": 2},
    })
    assert answer["record"]["part_id"] == "аналіз-вимог"
    reason = answer["record"]["reason"]
    assert reason and all(ord(ch) < 128 for ch in reason)


def test_fxopen_sg02_ascii_ids_keep_exact_reason():
    """ASCII ids keep the exact historical reason wording."""
    rec = _split.record_decomposition("p-c4", 2)
    assert "p-c4" in rec.reason


def test_fxopen_sg03_cyrillic_settings_key_refuses_cleanly():
    """Cyrillic settings key: SplitRefused naming the key rule."""
    with pytest.raises(_hierarchy.SplitRefused) as exc:
        _hierarchy.split({
            "project_id": "p",
            "parts": [{"id": "a", "kind": "k"}],
            "settings": {"режим": "x"},
        })
    assert "режим" in str(exc.value)


def test_fxopen_sg03_ascii_settings_key_records_verbatim():
    """ASCII settings keys record verbatim, one decision row."""
    _hierarchy._reset_state()
    try:
        served = _hierarchy.split({
            "project_id": "p",
            "parts": [{"id": "a", "kind": "k"}],
            "settings": {"mode": "x"},
        })
        assert "mode" in served["decision"]["statement"]
        assert "-----" not in served["decision"]["statement"]
    finally:
        _hierarchy._reset_state()


def test_fxopen_sg04_probes_decode_utf8_regardless_of_locale(monkeypatch):
    """k10_accept run() calls pin encoding=utf-8; a UTF-8 child keeps
    Cyrillic even when the preferred encoding claims cp1251."""
    import agent_si.k10_accept as _accept

    source = Path(_accept.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    runs = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
    ]
    assert len(runs) >= 2
    for node in runs:
        keywords = {}
        for kw in node.keywords:
            try:
                keywords[kw.arg] = ast.literal_eval(kw.value)
            except (ValueError, TypeError, SyntaxError):
                continue
        assert keywords.get("encoding") == "utf-8"
        assert keywords.get("errors") == "replace"
    monkeypatch.setattr(
        locale, "getpreferredencoding", lambda *args, **kwargs: "cp1251")
    proc = subprocess.run(
        [sys.executable, "-c", "print('Підсумок: PASS')"],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
    )
    assert proc.returncode == 0
    assert "Підсумок" in proc.stdout
