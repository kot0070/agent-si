"""FXR1A served suite: model-JSON tolerance, brief+gate, audits, install evidence.

Served path with the fake model at the provider boundary only
(_FakeFactory adapters); everything else is the real product: real
engine, real guard, real npm/node/pytest, real files.
"""

from __future__ import annotations

import json
import os
import sys
import types

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
_WS = os.path.dirname(_TESTS_DIR)
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import test_fxdevrun_served as fx  # noqa: E402
from agent_si.runtime.devrun import engine as _engine  # noqa: E402
from agent_si.runtime.devrun import protocol as _protocol  # noqa: E402
from agent_si.runtime.devrun import records as _records  # noqa: E402
from agent_si.toolguard import permissions as _permissions  # noqa: E402


def _chat(app, project, folder, message="do it"):
    folder.mkdir(parents=True, exist_ok=True)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/v1/chat/stream",
        json={"project": project, "folder": str(folder),
              "task": "task-%s" % project, "message": message},
        headers=fx._auth())
    assert resp.status_code == 200, resp.text
    return fx._all_text(fx._parse_sse(resp.text))


_DONE = json.dumps({"actions": [], "done": True})


# -- 5 reply shapes through all 3 parsers -------------------------------

_DIRECTOR = ('{"parts": [{"part_id": "p1", "goal": "g", '
             '"files": ["a.txt"], "check_commands": [], '
             '"depends_on": []}]}')
_AGENT = '{"actions": [], "done": true}'
_AUDIT = '{"result": "PASS", "reasons": ["ok"]}'

_SHAPES = {
    "plain": lambda s: s,
    "fence": lambda s: "```json\n" + s + "\n```",
    "sentence": lambda s: "Here is the plan:\n" + s + "\nDone.",
    "empty": lambda s: "   \n  ",
    "garbage": lambda s: "thinking out loud, no object here",
}


@pytest.mark.parametrize("shape", ["plain", "fence", "sentence"])
@pytest.mark.parametrize("name,fn,good", [
    ("director", _protocol.parse_director_reply, _DIRECTOR),
    ("agent", _protocol.parse_agent_reply, _AGENT),
    ("auditor", _protocol.parse_auditor_reply, _AUDIT),
])
def test_shapes_parse(name, fn, good, shape):
    fn(_SHAPES[shape](good))


@pytest.mark.parametrize("name,fn,good", [
    ("director", _protocol.parse_director_reply, _DIRECTOR),
    ("agent", _protocol.parse_agent_reply, _AGENT),
    ("auditor", _protocol.parse_auditor_reply, _AUDIT),
])
def test_shapes_reject_plainly(name, fn, good):
    with pytest.raises(ValueError, match="empty reply"):
        fn(_SHAPES["empty"](good))
    with pytest.raises(ValueError, match="no JSON object in reply"):
        fn(_SHAPES["garbage"](good))


# -- empty-reply retry without burning the attempt ---------------------

def test_empty_reply_retried_served(tmp_path):
    plan = [{"part_id": "p1", "goal": "write a.txt", "files": ["a.txt"],
             "check_commands": [], "why": "needed", "depends_on": []}]

    def _worker(n_calls, messages):
        if n_calls < 2:
            return ""
        return json.dumps({"actions": [{
            "action": "write_file", "path": "a.txt", "content": "hi"}],
            "done": True})

    factory = fx._FakeFactory({
        "director": [json.dumps({"parts": plan})],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": _worker,
        "auditor": [fx._audit_pass]})
    app = fx._served_app(tmp_path, "fxr1a-empty", factory)
    folder = tmp_path / "proj-empty"
    _chat(app, "fxr1a-empty", folder)
    record = fx._run_record(app, "fxr1a-empty")
    assert record["parts"][0]["verdict"] == "PASS", record["parts"]
    assert record["parts"][0]["attempts"] == 1, record["parts"]
    log = folder / ".devrun" / "agent" / "p1-a1.jsonl"
    assert log.is_file(), "reply-tail log kept"
    assert len(log.read_text(encoding="utf-8").strip().splitlines()) >= 3


# -- history block: manifests + test files, empty says new project -----

def test_history_block_lists_project_facts(tmp_path):
    folder = tmp_path / "proj-hist"
    folder.mkdir()
    (folder / "test_app.py").write_text("def test_a(): pass\n",
                                        encoding="utf-8")
    (folder / "package.json").write_text(
        '{"scripts": {"test": "pytest test_app.py"}}', encoding="utf-8")
    app = types.SimpleNamespace(
        state=types.SimpleNamespace(devrun_runs={}))
    block = _engine._director_history_block(app, "p", str(folder), "r1")
    assert "Test files now:" in block and "test_app.py" in block
    assert "--- package.json ---" in block
    assert "pytest test_app.py" in block
    assert block.find("package.json") < block.find("workspace files:")
    empty = _engine._director_history_block(
        app, "p", str(tmp_path / "nope"), "r2")
    assert "new project" in empty


def test_prompt_has_rules_no_pytest_example():
    prompt = _engine._director_prompt("build it", "HISTORY")
    assert '"check_commands": [[argv words]]' in prompt
    assert '"check_commands": [["python", "-m", "pytest"' not in prompt
    assert "own test command" in prompt
    assert "HISTORY" in prompt


# -- missing targets: one re-ask quoting paths, then plain end ---------

_BAD = [{"part_id": "p1", "goal": "v", "files": [],
         "check_commands": [["python", "-m", "pytest",
                             "tests/plan/check_x.py"]],
         "depends_on": []}]
_GOOD = [{"part_id": "p1", "goal": "v", "files": [],
          "check_commands": [["python", "--version"]],
          "depends_on": []}]


def test_missing_target_reasks_once_served(tmp_path):
    factory = fx._FakeFactory({
        "director": [json.dumps({"parts": _BAD}),
                     json.dumps({"parts": _GOOD})],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": [_DONE],
        "auditor": [fx._audit_pass]})
    app = fx._served_app(tmp_path, "fxr1a-reask", factory)
    _chat(app, "fxr1a-reask", tmp_path / "proj-reask")
    directors = [e for e in factory.spy if e.get("role") == "director"]
    assert len(directors) == 2, "exactly one re-ask"
    assert "tests/plan/check_x.py" in json.dumps(directors[1]["messages"])
    record = fx._run_record(app, "fxr1a-reask")
    assert record.get("success") is True, record.get("summary")


def test_missing_target_twice_is_plain_end_served(tmp_path):
    factory = fx._FakeFactory({
        "director": [json.dumps({"parts": _BAD}),
                     json.dumps({"parts": _BAD})],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": [_DONE],
        "auditor": [fx._audit_pass]})
    app = fx._served_app(tmp_path, "fxr1a-term", factory)
    text = _chat(app, "fxr1a-term", tmp_path / "proj-term")
    assert "tests/plan/check_x.py" in text
    assert "exit None" not in text
    record = fx._run_record(app, "fxr1a-term")
    assert record.get("success") is False, record.get("summary")


def test_missing_targets_unit(tmp_path):
    folder = tmp_path / "gate"
    (folder / "tests").mkdir(parents=True)
    (folder / "tests" / "a.py").write_text("x=1\n", encoding="utf-8")
    ok = [{"part_id": "p1", "files": [],
           "check_commands": [["pytest", "tests/a.py::test_b"]]}]
    assert _protocol.missing_check_targets(ok, str(folder)) == []
    inline = [{"part_id": "p1", "files": [],
               "check_commands": [["python", "-c", "print(1)"]]}]
    assert _protocol.missing_check_targets(inline, str(folder)) == []
    bad = [{"part_id": "p1", "files": [],
            "check_commands": [["python", "-m", "pytest",
                                "tests/plan/check_x.py"]]}]
    missing = _protocol.missing_check_targets(bad, str(folder))
    assert missing and "tests/plan/check_x.py" in missing[0][1]


# -- sibling files stay out of the audit agreement ---------------------

def test_sibling_files_not_in_audit(tmp_path, monkeypatch):
    monkeypatch.setattr(_engine, "_MAX_PART_WORKERS", 2)
    import threading

    barrier = threading.Barrier(2)
    parts = [{
        "part_id": "p%d" % n,
        "goal": "Write test_q%d.py with one passing test" % n,
        "files": ["test_q%d.py" % n],
        "check_commands": [["python", "-m", "pytest", "test_q%d.py" % n,
                            "-q", "-p", "no:cacheprovider"]],
        "depends_on": []} for n in (1, 2)]

    def _worker(n_calls, messages):
        text = " ".join(str(p.get("content", ""))
                         for p in messages if isinstance(p, dict))
        n = 2 if "part p2" in text else 1
        if n_calls % 2 == 0:
            barrier.wait(timeout=15)
            return json.dumps({"actions": [{
                "action": "write_file", "path": "test_q%d.py" % n,
                "content": "def test_q%d():\n    assert %d + %d == %d\n"
                           % (n, n, n, 2 * n)}], "done": False})
        return json.dumps({"actions": [], "done": True})

    factory = fx._FakeFactory({
        "director": [json.dumps({"parts": parts})],
        "manager": [json.dumps({"order": ["p1", "p2"]})],
        "worker": _worker,
        "auditor": [fx._audit_pass]})
    app = fx._served_app(tmp_path, "fxr1a-sib", factory)
    _chat(app, "fxr1a-sib", tmp_path / "proj-sib", message="build it")
    record = fx._run_record(app, "fxr1a-sib")
    assert record.get("success") is True, record.get("summary")
    audits = [e for e in factory.spy if e.get("role") == "auditor"]
    assert len(audits) == 2
    assert len({e["adapter_id"] for e in audits}) == 2
    by_goal = {}
    for entry in audits:
        text = json.dumps(entry["messages"])
        by_goal["q2" if "test_q2" in text and "test_q1" not in text
                else "q1"] = text
    assert set(by_goal) == {"q1", "q2"}, "audits split by part"
    assert "test_q2" not in by_goal["q1"], "no sibling leak into q1 audit"
    assert "test_q1" not in by_goal["q2"], "no sibling leak into q2 audit"


# -- install evidence: real installer, real record ---------------------

def test_install_evidence_served(tmp_path):
    project = "fxr1a-install"
    folder = tmp_path / "proj-install"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "package.json").write_text(
        json.dumps({"name": "fxr1a-probe", "version": "0.0.0"}),
        encoding="utf-8")
    plan = [{"part_id": "p1", "goal": "install deps",
             "files": ["package-lock.json"],
             "check_commands": [["findstr", "name",
                                 "package-lock.json"]],
             "depends_on": []}]

    def _worker(n_calls, messages):
        return json.dumps({
            "actions": [{"action": "run", "argv": ["npm", "install"]}],
            "done": True})

    factory = fx._FakeFactory({
        "director": [json.dumps({"parts": plan})],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": _worker,
        "auditor": [fx._audit_pass]})
    app = fx._served_app(tmp_path, project, factory)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        _permissions.PERMISSIONS_DECIDE_ROUTE,
        json={"tool_id": "install:%s:npm" % project, "decision": "allow",
              "project_id": project},
        headers=fx._auth())
    assert resp.status_code == 200, resp.text
    _chat(app, project, folder)
    record = fx._run_record(app, project)
    assert record["parts"][0]["verdict"] == "PASS", record["parts"]
    assert (folder / "package-lock.json").is_file(), "real install ran"
    assert bool(_records.combined_evidence(record)), "install on record"


# -- spent allow: second run asks again, check path and action path -

def _types(sse_text):
    return [e.get("type") for e in fx._parse_sse(sse_text)]


def _chat_raw(app, project, folder, message="do it"):
    folder.mkdir(parents=True, exist_ok=True)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/v1/chat/stream",
        json={"project": project, "folder": str(folder),
              "task": "task-%s" % project, "message": message},
        headers=fx._auth())
    assert resp.status_code == 200, resp.text
    return resp.text

def _allow_npm(app, project):
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        _permissions.PERMISSIONS_DECIDE_ROUTE,
        json={"tool_id": "install:%s:npm" % project, "decision": "allow",
              "project_id": project},
        headers=fx._auth())
    assert resp.status_code == 200, resp.text


def test_spent_allow_check_path_asks_again_served(tmp_path):
    project = "fxr1a-spent-check"
    folder = tmp_path / "proj-spent-check"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "package.json").write_text(
        json.dumps({"name": "fxr1a-probe", "version": "0.0.0"}),
        encoding="utf-8")
    first = [{"part_id": "p1", "goal": "install deps",
              "files": ["package-lock.json"],
              "check_commands": [["findstr", "name",
                                  "package-lock.json"]],
              "depends_on": []}]

    def _worker(n_calls, messages):
        return json.dumps({
            "actions": [{"action": "run", "argv": ["npm", "install"]}],
            "done": True})

    factory = fx._FakeFactory({
        "director": [json.dumps({"parts": first})],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": _worker,
        "auditor": [fx._audit_pass]})
    app = fx._served_app(tmp_path, project, factory)
    _allow_npm(app, project)
    _chat(app, project, folder)
    record = fx._run_record(app, project)
    assert record["parts"][0]["verdict"] == "PASS", record["parts"]
    # Second run: the once-allow is spent, the CHECK asks again.
    plan2 = [{"part_id": "p1", "goal": "install deps again", "files": [],
              "check_commands": [["npm", "install"]],
              "depends_on": []}]
    factory2 = fx._FakeFactory({
        "director": [json.dumps({"parts": plan2})],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": [json.dumps({"actions": [], "done": True})],
        "auditor": [fx._audit_pass]})
    app2 = fx._served_app(tmp_path, project + "-2", factory2)
    raw = _chat_raw(app2, project + "-2", folder)
    assert "approval" in _types(raw), raw[:500]
    assert "refused" not in raw.lower(), raw[:500]
    record2 = fx._run_record(app2, project + "-2")
    assert record2.get("held") is True, record2.get("summary")
    for row in record2.get("parts", []):
        for check in row.get("checks", []):
            assert not check.get("refused"), check


def test_spent_allow_action_path_asks_again_served(tmp_path):
    project = "fxr1a-spent-action"
    folder = tmp_path / "proj-spent-action"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "package.json").write_text(
        json.dumps({"name": "fxr1a-probe", "version": "0.0.0"}),
        encoding="utf-8")
    plan = [{"part_id": "p1", "goal": "install deps", "files": [],
             "check_commands": [], "why": "needed", "depends_on": []}]

    def _worker(n_calls, messages):
        return json.dumps({
            "actions": [{"action": "run", "argv": ["npm", "install"]}],
            "done": True})

    factory = fx._FakeFactory({
        "director": [json.dumps({"parts": plan})],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": _worker,
        "auditor": [fx._audit_pass]})
    app = fx._served_app(tmp_path, project, factory)
    raw = _chat_raw(app, project, folder)
    assert "approval" in _types(raw), raw[:800]
    assert "refused" not in raw.lower(), raw[:800]
    record = fx._run_record(app, project)
    assert record.get("held") is True, record.get("summary")


def test_g4_extractor_units():
    uk = "Запусти node tests/git/verify.mjs та node tests/code-audit/verify.mjs"
    en = "Run node tests/git/verify.mjs, and node tests/code-audit/verify.mjs"
    want = ["node tests/git/verify.mjs",
            "node tests/code-audit/verify.mjs"]
    assert _engine.goal_check_commands(uk) == want
    assert _engine.goal_check_commands(en) == want
    assert _engine.goal_check_commands("Please write clean code.") == []
    assert _engine.goal_check_commands(
        'Run `python -c "print(1)"` to verify') == ['python -c "print(1)"']
    parts = [
        {"part_id": "p1", "goal": "x", "files": ["tests/git/verify.mjs"],
         "check_commands": [["python", "--version"]], "depends_on": []},
        {"part_id": "p2", "goal": "y", "files": ["tests/code-audit/verify.mjs"],
         "check_commands": [["python", "--version"]], "depends_on": ["p1"]},
    ]
    assert _engine.plan_missing_checks(parts, uk) == want
    assert _engine._command_fits_part(
        ["tests/git/verify.mjs"], "node tests/git/verify.mjs") == 3
    assert _engine._command_fits_part(
        ["tests/git/verify.mjs"], "node tests/code-audit/verify.mjs") == 2
    assert _engine.goal_check_commands("do it") == []
    assert _engine.goal_check_commands("go") == []
    # Install-evidence lines are never commands, even naming a runner.
    assert _engine.goal_check_commands("$ npm install -> exit 0") == []
    assert _engine.goal_check_commands(
        "Installed already for this project:\n$ npm install -> exit 0"
    ) == []


def test_g4_named_check_served(tmp_path):
    uk = "Запусти node tests/git/verify.mjs"
    parts = [{"part_id": "p1", "goal": "verify git tooling",
              "files": ["tests/git/verify.mjs"],
              "check_commands": [["python", "--version"]],
              "depends_on": []}]
    factory = fx._FakeFactory({
        "director": [json.dumps({"parts": parts})],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": [json.dumps({"actions": [], "done": True})],
        "auditor": [fx._audit_pass]})
    app = fx._served_app(tmp_path, "fxr1a-g4", factory)
    folder = tmp_path / "proj-g4"
    target = folder / "tests" / "git" / "verify.mjs"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("console.log('ok');\n", encoding="utf-8")
    text = _chat(app, "fxr1a-g4", folder, message=uk)
    assert "Added named check" in text
    record = fx._run_record(app, "fxr1a-g4")
    assert record.get("success") is True, record.get("summary")
    joined = [" ".join(c["argv"])
              for r in record["parts"] for c in r["checks"]]
    assert any("tests/git/verify.mjs" in a for a in joined), joined


# -- gate on empty work: verify-only and declared-missing both FAIL ----

def test_gate_empty_work_served(tmp_path):
    plan = [
        {"part_id": "p1", "goal": "verify the build", "files": [],
         "check_commands": [], "why": "looked", "depends_on": []},
        {"part_id": "p2", "goal": "write it",
         "files": ["ghost-xyz-123.txt"],
         "check_commands": [["python", "--version"]],
         "depends_on": []},
    ]
    factory = fx._FakeFactory({
        "director": [json.dumps({"parts": plan})],
        "manager": [json.dumps({"order": ["p1", "p2"]})],
        "worker": [json.dumps({"actions": [], "done": True})],
        "auditor": [fx._audit_pass]})
    app = fx._served_app(tmp_path, "fxr1a-gate", factory)
    _chat(app, "fxr1a-gate", tmp_path / "proj-gate")
    record = fx._run_record(app, "fxr1a-gate")
    rows = {r["part_id"]: r for r in record["parts"]}
    assert rows["p1"]["verdict"] == "FAIL", rows["p1"]
    assert "verify-only part ran no green check" in str(
        rows["p1"].get("reason")), rows["p1"]
    assert rows["p2"]["verdict"] == "FAIL", rows["p2"]
    assert "ghost-xyz-123.txt" in str(rows["p2"].get("reason")), rows["p2"]
