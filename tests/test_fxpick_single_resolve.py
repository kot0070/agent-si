"""FXPICK item 1: exactly one model pick per attempt.

The worker adapter and the billed spec come from the same resolve, so
under AUTO the model that did the work matches ledger rows + live
panel. RED-first: _agent_loop took no worker_spec and _run_part
resolved twice per attempt.
"""

import inspect
import os
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.runtime.devrun import audit as _audit  # noqa: E402
from agent_si.runtime.devrun import engine as _engine  # noqa: E402
from agent_si.runtime.devrun import records as _records  # noqa: E402
from agent_si.runtime.devrun import roles as _roles  # noqa: E402


def test_agent_loop_requires_worker_spec():
    params = inspect.signature(_engine._agent_loop).parameters
    assert "worker_spec" in params
    assert params["worker_spec"].default is inspect.Parameter.empty


def test_single_resolve_per_attempt(tmp_path, monkeypatch):
    calls: list = []
    models = iter(["mock-first", "mock-second"])

    def fake_resolve(app, project):
        model = next(models)
        calls.append(model)
        return {"role": "worker", "mode": "AUTO",
                "provider": "mock", "model": model, "why": {}}

    seen: dict = {}

    def fake_build(app, spec):
        seen["adapter_model"] = spec["model"]
        return ("ADAPTER", spec["model"])

    def fake_loop(*, worker_spec, adapter, **kw):
        seen["spec"] = worker_spec
        seen["adapter"] = adapter
        return (int(kw.get("turn", 0)) + 1, True, None)

    def fake_checks(**kw):
        rows = [{"argv": ["python", "--version"], "exit_code": 0,
                 "output_tail": "Python 3.13.15", "output_file": "f"}]
        return (int(kw.get("turn", 0)), rows, True)

    def fake_judge(*a, **kw):
        return {"producer_ref": "pr", "audit_ref": "ar",
                "audit_id": "a", "audit_session": "s",
                "result": "PASS", "reasons": ["ok"],
                "over_cap": False}

    monkeypatch.setattr(_engine, "_resolve_worker", fake_resolve)
    monkeypatch.setattr(_roles, "build_adapter", fake_build)
    monkeypatch.setattr(_engine, "_agent_loop", fake_loop)
    monkeypatch.setattr(_engine, "_run_checks", fake_checks)
    monkeypatch.setattr(_audit, "judge", fake_judge)

    record: dict = {"ledger": [], "parts": [], "artifacts": []}
    row = _records.part_add(record, part_id="p1", goal="g")
    spec = {"part_id": "p1", "goal": "g", "files": [],
            "check_commands": [["python", "--version"]], "depends_on": []}
    gen = _engine._run_part(
        record=record, app=object(), spec=spec, row=row,
        auditor_spec={}, auditor_adapter=None, folder=str(tmp_path),
        project="p", task_id="t", run_id="r", turn=0, turn_cap=3,
        state={}, attached=set(), procs=[], message="тест",
        contract_hash="h", publish=lambda: None,
        check_stop=lambda: None, stop_seen=lambda: False,
        live=lambda *a, **k: None, call=lambda *a, **k: None,
        lock=None, abort=None)
    verdict, _turn = _drain(gen)
    assert verdict == "PASS"
    assert calls == ["mock-first"]
    assert seen["spec"]["model"] == "mock-first"
    assert seen["adapter_model"] == seen["spec"]["model"]
    assert seen["adapter"] == ("ADAPTER", "mock-first")


def _drain(gen):
    try:
        while True:
            next(gen)
    except StopIteration as done:
        return done.value
