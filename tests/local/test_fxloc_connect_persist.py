"""FXLOC C2: local runtime attachment persists as a JSON ref.

connect writes the runtime_ref JSON, disconnect deletes it, and a
startup restore re-attaches from it. Fake endpoint only: the ref is a
bare string, reachability is never faked (unconfigured refs stay
NOT_CONFIGURED).
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from agent_si.backend import local_connect  # noqa: E402

_TOKEN = "fxloc-c2-token"
_REF = "fxloc-c2-runtime-ref"


@pytest.fixture()
def _isolated(monkeypatch, tmp_path):
    """Clean globals + data dir at tmp; restore everything after."""
    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(tmp_path))
    saved_attached = local_connect._ATTACHED_RUNTIME
    saved_paired = local_connect._PAIRED_SESSION_TOKEN
    local_connect._ATTACHED_RUNTIME = None
    local_connect._PAIRED_SESSION_TOKEN = None
    yield tmp_path
    local_connect._ATTACHED_RUNTIME = saved_attached
    local_connect._PAIRED_SESSION_TOKEN = saved_paired


def _ref_file(tmp_path):
    return tmp_path / "local_runtime_ref.json"


def test_connect_writes_runtime_ref_json(_isolated, tmp_path):
    local_connect.connect(_REF, session_token=_TOKEN)
    path = _ref_file(tmp_path)
    assert path.is_file(), os.listdir(tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["runtime_ref"] == _REF


def test_reset_global_restore_still_attached(_isolated):
    local_connect.connect(_REF, session_token=_TOKEN)
    local_connect._ATTACHED_RUNTIME = None
    assert local_connect.restore_attached_runtime() == _REF
    assert local_connect._ATTACHED_RUNTIME == _REF


def test_disconnect_deletes_ref(_isolated, tmp_path):
    local_connect.connect(_REF, session_token=_TOKEN)
    assert _ref_file(tmp_path).is_file()
    local_connect.disconnect(session_token=_TOKEN)
    assert not _ref_file(tmp_path).exists()
    assert local_connect.restore_attached_runtime() is None
    assert local_connect._ATTACHED_RUNTIME is None


def test_refused_write_leaves_no_ref(_isolated, tmp_path):
    local_connect.connect(_REF, session_token=_TOKEN)
    with pytest.raises(Exception) as excinfo:
        local_connect.connect("fxloc-c2-evil-ref", session_token="wrong-token")
    assert "SESSION_TOKEN_REFUSED" in str(excinfo.value)
    assert json.loads(
        _ref_file(tmp_path).read_text(encoding="utf-8"))["runtime_ref"] == _REF
    with pytest.raises(Exception):
        local_connect.disconnect(session_token="wrong-token")
    assert json.loads(
        _ref_file(tmp_path).read_text(encoding="utf-8"))["runtime_ref"] == _REF


def test_startup_restore_attaches_in_fresh_process(_isolated, tmp_path):
    local_connect.connect(_REF, session_token=_TOKEN)
    probe = (
        "import sys; sys.path.insert(0, %r); "
        "from agent_si.backend import local_connect as lc; "
        "assert lc._ATTACHED_RUNTIME == %r, lc._ATTACHED_RUNTIME; "
        "print('FXLOC-C2-STARTUP-OK')"
        % (str(pathlib.Path(
            local_connect.__file__).resolve().parents[2]), _REF)
    )
    env = dict(os.environ, AGENT_SI_DATA_DIR=str(tmp_path))
    done = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True,
        env=env, timeout=120)
    assert done.returncode == 0, done.stderr[-1500:]
    assert "FXLOC-C2-STARTUP-OK" in done.stdout
