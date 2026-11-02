"""FXLOC C1: local config persists JSON under the app data dir.

Save writes an atomic JSON snapshot; a fresh load (evicted memory, and
a brand-new process) returns the saved config; the seeded proj-a
default is kept when no snapshot exists. No Ollama, no network.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from agent_si.local import config as _config  # noqa: E402

_KEY = "fxloc-c1-proj"


@pytest.fixture()
def _isolated(monkeypatch, tmp_path):
    """Data dir at tmp; snapshot/restore process-global store state."""
    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(tmp_path))
    saved_store = dict(_config._STORE)
    saved_loaded = _config._LOADED
    _config._STORE.pop(_KEY, None)
    _config._LOADED = False
    yield tmp_path
    _config._STORE.clear()
    _config._STORE.update(saved_store)
    _config._LOADED = saved_loaded


def _decision(project_key):
    return _config.record_decision(
        project_key, "fxloc-c1", "persist cover", "fxloc-coder")


def _saved():
    return _config.LocalAIConfig(
        project_key=_KEY,
        endpoint_url="http://127.0.0.1:11434",
        model_id="fxloc-c1-model",
        permission_scope="local-contact-allowed",
    )


def test_save_writes_atomic_json_snapshot(_isolated, tmp_path):
    _config.save_config(_saved(), _decision(_KEY))
    path = tmp_path / _config._CONFIG_FILE_NAME
    assert path.is_file(), list(tmp_path.iterdir())
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc[_KEY]["model_id"] == "fxloc-c1-model"
    assert not any(str(name).startswith(".local-ai-config-")
                   for name in os.listdir(tmp_path)), "tmp file left behind"


def test_fresh_load_returns_saved_config(_isolated):
    _config.save_config(_saved(), _decision(_KEY))
    _config._STORE.pop(_KEY, None)
    _config._LOADED = False
    loaded = _config.load_config(_KEY, _KEY)
    assert loaded == _saved()


def test_fresh_process_loads_snapshot(_isolated, tmp_path):
    _config.save_config(_saved(), _decision(_KEY))
    probe = (
        "import sys; sys.path.insert(0, %r); "
        "from agent_si.local import config as c; "
        "got = c.load_config(%r, %r); "
        "assert got.model_id == 'fxloc-c1-model', got; "
        "print('FXLOC-C1-NEW-PROCESS-OK')"
        % (str(pathlib.Path(_config.__file__).resolve().parents[2]),
           _KEY, _KEY)
    )
    env = dict(os.environ, AGENT_SI_DATA_DIR=str(tmp_path))
    done = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True,
        env=env, timeout=120)
    assert done.returncode == 0, done.stderr[-1500:]
    assert "FXLOC-C1-NEW-PROCESS-OK" in done.stdout


def test_seeded_default_kept_without_snapshot(_isolated, tmp_path):
    _config._LOADED = False
    default = _config.load_config("proj-a", "proj-a")
    assert default.endpoint_url == "http://127.0.0.1:11434"
    assert default.model_id == "llama3.1:8b"
    assert not (tmp_path / _config._CONFIG_FILE_NAME).exists()
