"""FXANSWER served proof: plain questions get visible answers fast (RED first).

Solo path (team off):
- visible prose with no JSON object and no action done yet = the answer,
  exactly ONE model call, success True + marker
  `run answered: plain answer, no parts`.
- {"answer": ...} from the worker ends the run the same way, 1 call.
- empty reply twice -> success False + `The model returned nothing. Try again.`
- loop exhausted with done never true -> success False +
  `Stopped after N steps: the task is not finished.` Never Done.
Team path:
- Director {"answer"} for a non-build-task message without "?" is a plain
  answer: success True + the same marker.
Fakes live ONLY at the provider network boundary (scripted per-role
adapter); real app, real fs, real engine.
"""

import json
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
_WS = os.path.dirname(_TESTS_DIR)
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import agents_live  # noqa: E402
from agent_si.backend import teammode_routes as _team  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from test_fxdevrun_served import (  # noqa: E402
    _all_text,
    _audit_pass,
    _FakeFactory,
    _parse_sse,
    _project_dir,
    _post_chat,
    _run_record,
    _served_app,
)

MARKER = "run answered: plain answer, no parts"


def setup_function(_func):
    agents_live.clear_live_rows()
    _steplimits._reset_state()
    _team._reset_state()


def teardown_function(_func):
    agents_live.clear_live_rows()
    _steplimits._reset_state()
    _team._reset_state()


def _solo_app(tmp_path, project, worker_script):
    factory = _FakeFactory({
        "director": [json.dumps({"answer": "unused"})],
        "manager": [json.dumps({"order": []})],
        "worker": worker_script,
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    _team._TEAM_MODE[project] = "off"
    return app, factory


def _worker_calls(factory):
    return [entry for entry in factory.spy if entry.get("role") == "worker"]


# -- solo: visible prose with no JSON object is the answer, 1 call ---------

def test_fxanswer_solo_prose_is_answer_one_call(tmp_path):
    project = "fxans-prose"
    folder = _project_dir(tmp_path, project)
    app, factory = _solo_app(tmp_path, project, ["Paris"])
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(
        client, project, folder, message="What is the capital of France?")
    assert resp.status_code == 200, resp.text
    calls = _worker_calls(factory)
    assert len(calls) == 1, "prose answer costs exactly one model call: %d" % (
        len(calls),)
    text = _all_text(_parse_sse(resp.text))
    assert "Paris" in text, text[:800]
    record = _run_record(app, project)
    assert record is not None
    assert record.get("success") is True, record.get("summary")
    assert MARKER in str(record.get("summary")), record.get("summary")


# -- solo: {"answer"} ends the run, 1 call ----------------------------------

def test_fxanswer_solo_answer_json_one_call(tmp_path):
    project = "fxans-json"
    folder = _project_dir(tmp_path, project)
    app, factory = _solo_app(
        tmp_path, project, [json.dumps({"answer": "pear"})])
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(
        client, project, folder,
        message="Reply with exactly this word: pear")
    assert resp.status_code == 200, resp.text
    calls = _worker_calls(factory)
    assert len(calls) == 1, "answer JSON costs exactly one model call: %d" % (
        len(calls),)
    text = _all_text(_parse_sse(resp.text))
    assert "pear" in text, text[:800]
    record = _run_record(app, project)
    assert record is not None
    assert record.get("success") is True, record.get("summary")
    assert MARKER in str(record.get("summary")), record.get("summary")


# -- solo: empty reply twice fails closed ------------------------------------

def test_fxanswer_solo_empty_twice_fails_closed(tmp_path):
    project = "fxans-empty"
    folder = _project_dir(tmp_path, project)
    app, factory = _solo_app(tmp_path, project, ["", ""])
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(
        client, project, folder, message="What is the capital of France?")
    assert resp.status_code == 200, resp.text
    calls = _worker_calls(factory)
    assert len(calls) == 2, "empty reply gets exactly one retry: %d" % (
        len(calls),)
    text = _all_text(_parse_sse(resp.text))
    assert "The model returned nothing. Try again." in text, text[:800]
    record = _run_record(app, project)
    assert record is not None
    assert record.get("success") is False, record.get("summary")
    assert "The model returned nothing. Try again." in str(
        record.get("summary")), record.get("summary")


# -- solo: loop exhausted with done never true is not Done -------------------

def test_fxanswer_solo_never_done_to_cap_not_done(tmp_path):
    project = "fxans-cap"
    folder = _project_dir(tmp_path, project)

    def _never_done(n_calls, messages):
        return json.dumps({"actions": [], "done": False})

    app, factory = _solo_app(tmp_path, project, [_never_done])
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(
        client, project, folder, message="What is the capital of France?")
    assert resp.status_code == 200, resp.text
    calls = _worker_calls(factory)
    assert len(calls) > 1, "the loop ran more than one turn: %d" % (
        len(calls),)
    text = _all_text(_parse_sse(resp.text))
    assert "Stopped after" in text and "not finished" in text, text[:800]
    assert "Done, not audited." not in text, text[:800]
    record = _run_record(app, project)
    assert record is not None
    assert record.get("success") is False, record.get("summary")
    assert "Done, not audited." not in str(record.get("summary")), (
        record.get("summary"))


# -- reconcile: leftover running chat turns become interrupted ------------

def test_fxanswer_reconcile_marks_running_turns_interrupted(tmp_path):
    project = "fxans-reconcile"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [json.dumps({"answer": "pear"})],
        "manager": [json.dumps({"order": []})],
        "worker": [json.dumps({"actions": [], "done": True})],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    from agent_si.backend import app as _app_mod
    from agent_si.backend import chat_history as _chathist
    _chathist.record_turn(
        app, project, "do it", "partial", status="running",
        run_id="run-leftover")
    page = _chathist.history_page(app, project)
    assert [turn["status"] for turn in page["turns"]] == ["running"]
    result = _app_mod._reconcile_running_to_interrupted(app)
    assert result.get("turns", 0) >= 1, result
    page = _chathist.history_page(app, project)
    assert [turn["status"] for turn in page["turns"]] == ["interrupted"]
    assert page["turns"][0]["run_end_reason"] != "", page["turns"][0]
    assert "restart reconcile" in page["turns"][0]["run_end_reason"], (
        page["turns"][0])


# -- team: answer without a question mark is a plain answer ------------------


# -- solo: file task names the real file in a [files:] marker --------------

def _worker_write_once(n_calls, messages):
    if n_calls == 0:
        return json.dumps({
            "actions": [{"action": "write_file", "path": "test.txt",
                         "content": "hello\n"}],
            "done": False})
    return json.dumps({"actions": [], "done": True})


def test_fxanswerb1_solo_file_task_marker_and_file(tmp_path):
    project = "fxans-file"
    folder = _project_dir(tmp_path, project)
    app, factory = _solo_app(tmp_path, project, [_worker_write_once])
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(
        client, project, folder,
        message="Create test.txt containing hello")
    assert resp.status_code == 200, resp.text
    assert (folder / "test.txt").is_file(), "the file is on disk"
    text = _all_text(_parse_sse(resp.text))
    assert "[files: test.txt]" in text, text[:800]
    assert "Done, not audited." in text, text[:800]
    assert "Nothing was built" not in text, text[:800]
    record = _run_record(app, project)
    assert record is not None
    assert record.get("success") is True, record.get("summary")

def test_fxanswer_team_answer_no_question_mark(tmp_path):
    project = "fxans-team"
    folder = _project_dir(tmp_path, project)
    factory = _FakeFactory({
        "director": [json.dumps({"answer": "pear"})],
        "manager": [json.dumps({"order": []})],
        "worker": [json.dumps({"actions": [], "done": True})],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(
        client, project, folder,
        message="Reply with exactly this word: pear")
    assert resp.status_code == 200, resp.text
    text = _all_text(_parse_sse(resp.text))
    assert "pear" in text, text[:800]
    assert "Nothing was built" not in text, text[:800]
    record = _run_record(app, project)
    assert record is not None
    assert record.get("success") is True, record.get("summary")
    assert MARKER in str(record.get("summary")), record.get("summary")
