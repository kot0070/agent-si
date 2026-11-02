"""FXOPEN O1: frozen catalog child uses the sidecar --qa-runner flag.

RED-first: with sys.frozen faked, catalog_v2.run_code_test must spawn
[sys.executable, --qa-runner, runner] (never [exe, host.py, runner],
which would start a second full app: window + instance lock + folder
picker). The flag path through sidecar.main() is served end to end:
no window, no lock, no folder picker.
"""
from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

_WS = Path(__file__).resolve().parents[1]
_SRC = _WS / "src"
for _entry in (str(_WS), str(_SRC)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from agent_si import sidecar  # noqa: E402
from agent_si.qa_catalog import catalog_v2  # noqa: E402

HOST_SRC = _SRC / "agent_si" / "qa_catalog" / "runners" / "host.py"


class _FakeStdin:
    def write(self, data):
        pass

    def close(self):
        pass


class _FakeProc:
    def __init__(self, argv):
        self.argv = argv
        self.stdin = _FakeStdin()
        self.pid = 424242
        self.returncode = 0

    def poll(self):
        return 0

    def communicate(self, timeout=None):
        envelope = {
            "test_id": "REQ-002",
            "runner_id": "static_lint",
            "status": "PASS",
            "reason": "frozen argv probe",
            "assertions": 1,
            "evidence": [],
        }
        return (json.dumps(envelope).encode("utf-8"), b"")

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


def _freeze(monkeypatch, meipass):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)


def test_fxopen_frozen_argv_uses_qa_runner_flag(monkeypatch, tmp_path):
    """Frozen: child argv is [exe, --qa-runner, runner], flag pinned."""
    meipass = tmp_path / "meipass"
    (meipass / "qa_catalog" / "runners").mkdir(parents=True)
    (meipass / "qa_catalog" / "runners" / "host.py").write_text(
        HOST_SRC.read_text(encoding="utf-8"), encoding="utf-8")
    _freeze(monkeypatch, meipass)
    captured = {}

    def _fake_popen(argv, **kwargs):
        captured["argv"] = list(argv)
        return _FakeProc(argv)

    monkeypatch.setattr(catalog_v2.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(
        catalog_v2, "resolve",
        lambda row, profile: {"status": "SUPPORTED", "params": {}})
    outcome = catalog_v2.run_code_test(
        "REQ-002", str(tmp_path), str(tmp_path / "ev"))
    assert captured["argv"][0] == sys.executable
    assert captured["argv"][1] == "--qa-runner"
    assert captured["argv"][1] == sidecar._QA_RUNNER_FLAG
    assert captured["argv"][2] == "static_lint"
    assert len(captured["argv"]) == 3
    assert outcome["status"] == "PASS"
    assert outcome["reason"] == "frozen argv probe"


def test_fxopen_unfrozen_argv_uses_host_script(monkeypatch, tmp_path):
    """Unfrozen: child argv stays [python, host.py, runner]."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    captured = {}

    def _fake_popen(argv, **kwargs):
        captured["argv"] = list(argv)
        return _FakeProc(argv)

    monkeypatch.setattr(catalog_v2.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(
        catalog_v2, "resolve",
        lambda row, profile: {"status": "SUPPORTED", "params": {}})
    catalog_v2.run_code_test("REQ-002", str(tmp_path), str(tmp_path / "ev"))
    assert captured["argv"] == [
        sys.executable, catalog_v2._host_path(), "static_lint"]


def test_fxopen_flag_path_served_no_window_no_lock_no_picker(
        monkeypatch, tmp_path, capsys):
    """Served: main([--qa-runner, policy_gate]) runs the runner only.

    No single-instance gate (no lock, no second-instance exit), no
    data dir, no app build, no window: touching any of them fails.
    """
    touched = []

    def _boom(name):
        def _inner(*args, **kwargs):
            touched.append(name)
            raise AssertionError("flag path touched %s" % name)
        return _inner

    monkeypatch.setattr(
        sidecar, "_single_instance_gate", _boom("_single_instance_gate"))
    monkeypatch.setattr(
        sidecar, "_sidecar_data_dir", _boom("_sidecar_data_dir"))
    monkeypatch.setattr(
        sidecar, "_lock_file_path", _boom("_lock_file_path"))
    monkeypatch.setattr(sidecar, "build_app", _boom("build_app"))
    project = tmp_path / "proj"
    project.mkdir()
    (project / "hello.sh").write_text(
        "#!/bin/sh\necho hi\n", encoding="utf-8")
    evidence = tmp_path / "ev"
    request = {
        "project_root": str(project),
        "test_id": "REQ-UX-1",
        "params": {},
        "budgets": {"timeout_s": 30.0, "evidence_dir": str(evidence)},
    }
    payload = json.dumps(request).encode("utf-8")
    monkeypatch.setattr(
        sys, "stdin", io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8"),
        raising=False)
    code = sidecar.main(["--qa-runner", "policy_gate"])
    out = capsys.readouterr().out
    assert touched == []
    assert code == 0
    answer = json.loads(out.strip().splitlines()[-1])
    assert answer["runner_id"] == "policy_gate"
    assert answer["status"] == "PASS"
    assert answer["assertions"] >= 1


def test_fxopen_sys_executable_use_audit():
    """Every sys.executable use in src/agent_si is known-safe.

    catalog_v2.py: frozen --qa-runner branch only; host.py: the same
    frozen dispatch; code_executor.py: frozen_python never returns the
    exe; actions.py: comment text only; sidecar.py: frozen-only
    Zone.Identifier strip (no-op unless sys.frozen).
    """
    allowed = {
        "catalog_v2.py": ("--qa-runner",),
        "host.py": ("--qa-runner",),
        "code_executor.py": ("frozen_python", "sys.executable"),
        "actions.py": ("never sys.executable",),
        "suite_invoke.py": ("never sys.executable",),
        # sidecar.py: frozen-only Zone.Identifier cleanup (returns 0
        # unless sys.frozen, src/agent_si/sidecar.py:284-290) -- same
        # frozen-only class as the --qa-runner branch above.
        "sidecar.py": ("frozen-only Zone-strip", "sys.executable"),
    }
    hits = []
    for path in (_SRC / "agent_si").rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if "sys.executable" in line:
                hits.append((path.name, lineno, line.strip()))
    assert hits, "audit found no sys.executable uses at all"
    for name, lineno, line in hits:
        assert name in allowed, (
            "new sys.executable use %s:%d: %s" % (name, lineno, line))
