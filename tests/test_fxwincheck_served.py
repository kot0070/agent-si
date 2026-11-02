"""FXWINCHECK: Windows check commands + missing-exe handling + chat lines.

W1: director/worker prompts state sys.platform; on Windows they steer
  to executables present here (python -m pytest, findstr), never POSIX
  shell tools, and inline code stays refused.
W2: a check whose executable is missing is could-not-start (never a red
  check); auditor PASS with no check able to start still FAILS after
  the retry budget (a part whose check never ran is never PASS);
  auditor FAIL stays FAIL; real red checks still fail.
W3: green check status lines read "-> exit 0"; the auditor's long ref
  stays in the journal, never in chat.
"""

import json
import os
import re
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import agents_live  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from agent_si.runtime.devrun import engine as _engine  # noqa: E402
from agent_si.watcher import journal as _journal  # noqa: E402
from test_fxdevrun_served import (  # noqa: E402
    _PASS_TEST,
    _all_text,
    _audit_pass,
    _FakeFactory,
    _one_part_plan,
    _parse_sse,
    _project_dir,
    _post_chat,
    _run_record,
    _served_app,
)

_MISSING_TOOL = "fxdevrun-no-such-tool-xyz"


def setup_function(_func):
    agents_live.clear_live_rows()
    _steplimits._reset_state()


def teardown_function(_func):
    agents_live.clear_live_rows()
    _steplimits._reset_state()


# -- W1: platform-aware prompts --------------------------------------------

_POSIX_WORDS = re.compile(r"\b(grep|sed|bash|cat|ls)\b", re.IGNORECASE)


def _worker_spec():
    return {"part_id": "p1", "goal": "g", "files": ["test_p1.py"]}


def test_w1_director_prompt_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    prompt = _engine._director_prompt("build it")
    assert "win32" in prompt, prompt
    assert "pytest" in prompt, prompt
    assert "findstr" in prompt, prompt
    assert not _POSIX_WORDS.search(prompt), prompt
    assert "nline" in prompt and "refus" in prompt.lower(), prompt


def test_w1_worker_prompt_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    prompt = _engine._worker_prompt(_worker_spec(), "build it", 1, [], [])
    assert "win32" in prompt, prompt
    assert "pytest" in prompt, prompt
    assert "findstr" in prompt, prompt
    assert not _POSIX_WORDS.search(prompt), prompt


def test_w1_prompt_states_platform_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert "linux" in _engine._director_prompt("build it")
    assert "linux" in _engine._worker_prompt(
        _worker_spec(), "build it", 1, [], [])


# -- W2: missing executable is could-not-start ------------------------------

_MISSING_PLAN = [
    {"part_id": "p1", "goal": "Write test_p1.py with one passing test",
     "files": ["test_p1.py"],
     "check_commands": [[_MISSING_TOOL, "test_p1.py"]],
     "depends_on": []},
]


def _worker_write_pass(n_calls, messages):
    if n_calls % 2 == 0:
        return json.dumps({
            "actions": [{"action": "write_file", "path": "test_p1.py",
                         "content": _PASS_TEST}],
            "done": False})
    return json.dumps({"actions": [], "done": True})


def _plan_missing():
    return json.dumps({"parts": _MISSING_PLAN})


def _part_row(record, part_id="p1"):
    parts = {part["part_id"]: part for part in record.get("parts", [])}
    return parts[part_id]


def test_w2_missing_exe_auditor_pass_still_fails(tmp_path):
    project = "fxdr-w2pass"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [_plan_missing()],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": [_worker_write_pass],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    text = _all_text(_parse_sse(resp.text))
    assert ("could not start: %s is not installed"
            % (_MISSING_TOOL,)) in text, text
    assert "exit None" not in text, text
    assert "auditor only" not in text, text
    record = _run_record(app, project)
    assert record is not None
    assert record.get("success") is False, record.get("summary")
    row = _part_row(record)
    assert row["verdict"] == "FAIL", row
    assert row["attempts"] == 3, row
    assert row["checks"][0].get("could_not_start") is True, row["checks"]


def test_w2_missing_exe_auditor_fail_stays_fail(tmp_path):
    project = "fxdr-w2fail"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [_plan_missing()],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": [_worker_write_pass],
        "auditor": [json.dumps({"result": "FAIL",
                                "reasons": ["fxdevrun no-start reason"]})],
    })
    app = _served_app(tmp_path, project, factory)
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    text = _all_text(_parse_sse(resp.text))
    assert ("could not start: %s is not installed"
            % (_MISSING_TOOL,)) in text, text
    assert "exit None" not in text, text
    assert "auditor only" not in text, text
    record = _run_record(app, project)
    assert record is not None
    row = _part_row(record)
    assert row["verdict"] == "FAIL", row
    assert row["attempts"] == 1, row
    assert record.get("success") is not True, record.get("summary")


def test_w2_real_red_check_still_fails(tmp_path):
    from test_fxdevrun_served import _FAIL_TEST
    project = "fxdr-w2red"
    folder = _project_dir(tmp_path, project)

    def _worker_red(n_calls, messages):
        if n_calls % 2 == 0:
            return json.dumps({
                "actions": [{"action": "write_file", "path": "test_p1.py",
                             "content": _FAIL_TEST}],
                "done": False})
        return json.dumps({"actions": [], "done": True})

    factory = _FakeFactory({
        "director": [json.dumps({"parts": _one_part_plan()})],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": [_worker_red],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    record = _run_record(app, project)
    assert record is not None
    assert _part_row(record)["verdict"] == "FAIL", record.get("summary")
    assert record.get("success") is not True, record.get("summary")


# -- W3: status line format, auditor ref off chat ----------------------------

def test_w3_exit_line_and_no_auditor_ref_in_chat(tmp_path):
    project = "fxdr-w3"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [json.dumps({"parts": _one_part_plan()})],
        "manager": [json.dumps({"order": ["p1"]})],
        "worker": [_worker_write_pass],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    text = _all_text(events)
    assert "-> exit 0" in text, text
    assert not re.search(r"auditor-[0-9a-f]{6,}", text), text
    assert "Auditor for p1: PASS" in text, text
    record = _run_record(app, project)
    assert record is not None
    assert record.get("audits"), "auditor refs retained off chat"
    journal_text = " ".join(
        str(row.summary) for row in
        _journal.stored_rows(project, "DEVRUN_AUDIT"))
    assert re.search(r"auditor-[0-9a-f]+-p1", journal_text), (
        "auditor long ref lives in the journal")
