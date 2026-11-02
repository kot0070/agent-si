"""FXLOOP: long-task worker-loop fixes (RED first, then GREEN).

L1 history trim: 30 turns of 4KB run output stay under the cap, the
  first brief survives verbatim, old pairs fold into one deterministic
  summary line naming real files and exit codes.
L2 ContextOverflow: detect 400/413 length errors; worker shrinks to
  brief + last 2 turns and retries once; twice ends the attempt with
  the plain line in record + stream. Director/auditor show the same
  plain line, never "internal".
L3 audit snapshot per attempt plus the whole part diff for the
  auditor; the last attempt is always audited.
L5 AUTO double-resolve: dropped (see PAIR-RETURN; AUTO is
  deterministic, no RED under real AUTO code).
L6 attempt memory: attempt-2 brief lists earlier files + last failing
  command output.
L7 no-check + why: PASS only when the part changed files AND the
  auditor passes, else FAIL.
L8 Director {answer} on a build task: re-ask once for parts; second
  answer shows, success False, "Nothing was built.".
L9 provider's own timeout maps to ModelTimeout (existing retry paths);
  golden-10 analogue.
"""

import copy
import copy
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
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from agent_si.providers.adapters.base import ProviderTimeoutError  # noqa: E402
from agent_si.runtime.devrun import engine as _engine  # noqa: E402
from agent_si.runtime.devrun import roles as _roles  # noqa: E402
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

PLAIN = ("The task outgrew the model's context. "
         "Try smaller parts or a model with a larger window.")
NOTHING_BUILT = "Nothing was built."


def setup_function(_func):
    agents_live.clear_live_rows()
    _steplimits._reset_state()


def teardown_function(_func):
    agents_live.clear_live_rows()
    _steplimits._reset_state()


def _apply_limits_n(project_id, task=10, chat=10):
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": project_id,
        "authority": "fxloop-test",
        "reason": "fxloop needs its own step budgets",
        "task_max_steps": task,
        "chat_max_steps": chat,
    })
    assert outcome.applied, outcome.reason


def _manager_one(part_id="p1"):
    return json.dumps({"order": [part_id]})


def _seed(path, content):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


_GEN_PY = "import sys\nprint(\"x\" * 4000 + (sys.argv[1] if len(sys.argv) > 1 else \"\"))\n"


def _worker_msgs(factory, role="worker"):
    return [entry for entry in factory.spy if entry.get("role") == role]


# -- L1: history trim ----------------------------------------------------------

def test_l1_history_bounded_and_summarised(tmp_path):
    project = "fxloop-l1"
    folder = _project_dir(tmp_path, project)
    _seed(os.path.join(str(folder), "gen.py"), _GEN_PY)
    box = {"n": 0}

    def _worker(n_calls, messages):
        box["n"] += 1
        return json.dumps({
            "actions": [{"action": "run",
                         "argv": ["python", "gen.py", "t%d" % box["n"]]}],
            "done": False})

    plan = [{"part_id": "p1", "goal": "Run gen.py many times",
             "files": ["gen.py"],
             "check_commands": [["python", "gen.py", "check"]],
             "depends_on": []}]
    factory = _FakeFactory({
        "director": [json.dumps({"parts": plan})],
        "manager": [_manager_one()],
        "worker": [_worker],
        "auditor": [_audit_pass],
    })
    _apply_limits_n(project, task=40, chat=40)
    store = tmp_path / ("store-" + project)
    store.mkdir(parents=True, exist_ok=True)
    from agent_si.backend.app import create_app
    from test_fxdevrun_served import _settings, _pin_all, _bound_mock
    agents_live.clear_live_rows()
    _steplimits._reset_state()
    _apply_limits_n(project, task=40, chat=40)
    app = create_app(_settings(store))
    _pin_all(app, project)
    app.state.chat_provider_adapter = _bound_mock()
    app.state.devrun_adapter_factory = factory
    from fastapi.testclient import TestClient
    from test_fxdevrun_served import _auth
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/v1/chat/stream",
        json={"project": project, "folder": str(folder),
              "task": "task-%s" % project, "message": "build it"},
        headers=_auth())
    assert resp.status_code == 200, resp.text
    calls = _worker_msgs(factory)
    assert len(calls) >= 30, len(calls)
    sizes = [len(json.dumps(entry["messages"])) for entry in calls]
    assert max(sizes) < 120000, max(sizes)
    last = calls[-1]["messages"]
    assert "You are the worker for part p1 (attempt 1)" in last[0]["content"]
    summaries = [m.get("content", "") for entry in calls
                 for m in entry["messages"]
                 if m.get("role") == "user"
                 and "Earlier in this attempt:" in m.get("content", "")]
    assert summaries, "no summary line folded into history"
    assert "gen.py" in summaries[-1], summaries[-1][:500]
    assert "exit 0" in summaries[-1], summaries[-1][:500]


def test_l1_note_caps_unit():
    big_run = "o" * 8000
    capped = _engine._cap_run_tail(big_run)
    assert len(capped) < len(big_run), len(capped)
    assert capped.startswith("o" * 1000), capped[:1010]
    assert capped.endswith("o" * 4000), capped[-4010:]
    assert "...cut..." in capped
    assert _engine._cap_run_tail("o" * 4000) == "o" * 4000
    big_read = "r" * 30000
    capped_read = _engine._cap_read_note(big_read)
    assert len(capped_read) < len(big_read)
    assert "...file continues," in capped_read
    assert "more chars..." in capped_read
    assert _engine._cap_read_note("r" * 100) == "r" * 100


# -- L2: context overflow ------------------------------------------------------

def test_l2_overflow_markers_unit():
    from agent_si.providers.adapters.base import ProviderHttpError
    over = ProviderHttpError(
        "prompt is too long: context_length exceeded", "ref:http-400", 400)
    assert _roles._is_context_overflow(over) is True
    over413 = ProviderHttpError("request too large", "ref:http-413", 413)
    assert _roles._is_context_overflow(over413) is True
    assert _roles._is_context_overflow(
        _roles.ModelTimeout("slow")) is False
    assert _roles._is_context_overflow(RuntimeError("boom")) is False
    wrong_status = ProviderHttpError(
        "too many tokens? no, 500 server error", "ref:http-500", 500)
    assert _roles._is_context_overflow(wrong_status) is False
    no_marker = ProviderHttpError("bad request", "ref:http-400", 400)
    assert _roles._is_context_overflow(no_marker) is False


def test_l2_worker_overflow_shrink_then_plain(tmp_path):
    project = "fxloop-l2"
    folder = _project_dir(tmp_path, project)
    _seed(os.path.join(str(folder), "check_out.py"),
          "import sys\ntry:\n    data = open('out.txt').read()\n"
          "except Exception:\n    sys.exit(1)\n"
          "sys.exit(0 if data == 'done\\n' else 1)\n")
    box = {"n": 0}

    def _worker(n_calls, messages):
        box["n"] += 1
        if box["n"] == 5 or box["n"] == 6:
            box["m%d" % box["n"]] = copy.deepcopy(messages)
            raise _roles.ContextOverflow(
                "400 prompt is too long: context_length exceeded")
        if "attempt 1" in messages[0]["content"] and box["n"] < 7:
            return json.dumps({"actions": [], "done": False})
        if box["n"] == 7:
            return json.dumps({
                "actions": [{"action": "write_file", "path": "out.txt",
                             "content": "done\n"}],
                "done": False})
        return json.dumps({"actions": [], "done": True})

    plan = [{"part_id": "p1", "goal": "Write out.txt",
             "files": ["out.txt"],
             "check_commands": [["python", "check_out.py"]],
             "depends_on": []}]
    factory = _FakeFactory({
        "director": [json.dumps({"parts": plan})],
        "manager": [_manager_one()],
        "worker": [_worker],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    assert box["n"] == 8, box
    calls = _worker_msgs(factory)
    fifth = json.dumps(box["m5"])
    sixth = json.dumps(box["m6"])
    assert len(sixth) < len(fifth), (len(fifth), len(sixth))
    assert box["m6"][0] == box["m5"][0]
    assert len(box["m6"]) <= 5, len(box["m6"])
    text = _all_text(_parse_sse(resp.text))
    assert PLAIN in text, text[:800]
    record = _run_record(app, project)
    assert record is not None
    assert record.get("success") is True, record.get("summary")


# -- L9: provider timeout maps to ModelTimeout ----------------------------------

def test_l9_provider_timeout_retries(tmp_path):
    project = "fxloop-l9"
    folder = _project_dir(tmp_path, project)
    _seed(os.path.join(str(folder), "test_hello.py"),
          "def test_hello():\n    assert False, 'fxloop-l9 red'\n")
    seen = {"worker": 0, "auditor": 0}

    def _flaky(role):
        def _run(n_calls, messages):
            seen[role] += 1
            if seen[role] == 1:
                raise ProviderTimeoutError(
                    "golden simulated provider timeout",
                    "mock:fxloop:timeout")
            if role == "auditor":
                return _audit_pass(n_calls, messages)
            if seen["worker"] == 2:
                return json.dumps({
                    "actions": [{"action": "write_file",
                                 "path": "test_hello.py",
                                 "content": ("def test_hello():\n"
                                             "    assert True\n")}],
                    "done": False})
            return json.dumps({"actions": [], "done": True})
        return _run

    plan = [{"part_id": "p1", "goal": "Make test_hello.py pass",
             "files": ["test_hello.py"],
             "check_commands": [["python", "-m", "pytest", "test_hello.py",
                                  "-q", "-p", "no:cacheprovider"]],
             "depends_on": []}]
    factory = _FakeFactory({
        "director": [json.dumps({"parts": plan})],
        "manager": [_manager_one()],
        "worker": [_flaky("worker")],
        "auditor": [_flaky("auditor")],
    })
    app = _served_app(tmp_path, project, factory)
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    assert "internal" not in resp.text.lower(), resp.text[:500]
    events = _parse_sse(resp.text)
    assert [e.get("type") for e in events][-1] == "done", resp.text[:800]
    assert seen["worker"] == 4, seen
    assert seen["auditor"] == 2, seen
    record = _run_record(app, project)
    assert record is not None
    assert record.get("success") is True, record.get("summary")


# -- L3: per-attempt snapshot + whole part diff ---------------------------------

def test_l3_attempt_diff_and_cumulative(tmp_path):
    project = "fxloop-l3"
    folder = _project_dir(tmp_path, project)
    _seed(os.path.join(str(folder), "gen.py"), _GEN_PY)
    audits = {"n": 0}

    def _worker(n_calls, messages):
        text = messages[0]["content"]
        if "attempt 1" in text and n_calls == 0:
            return json.dumps({
                "actions": [{"action": "write_file", "path": "test_p1.py",
                             "content": "VALUE = 1\n"}],
                "done": False})
        return json.dumps({"actions": [], "done": True})

    def _auditor(n_calls, messages):
        audits["n"] += 1
        if audits["n"] < 3:
            return json.dumps({"result": "FAIL",
                               "reasons": ["not yet"]})
        return _audit_pass(n_calls, messages)

    plan = [{"part_id": "p1", "goal": "Write test_p1.py",
             "files": ["test_p1.py"],
             "check_commands": [["python", "gen.py", "check"]],
             "depends_on": []}]
    factory = _FakeFactory({
        "director": [json.dumps({"parts": plan})],
        "manager": [_manager_one()],
        "worker": [_worker],
        "auditor": [_auditor],
    })
    app = _served_app(tmp_path, project, factory)
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    audited = _worker_msgs(factory, role="auditor")
    assert len(audited) == 3, len(audited)
    second = audited[1]["messages"][0]["content"]
    assert "Files (diff vs attempt start):\n(no changes)" in second, (
        second[:800])
    assert "VALUE = 1" in second, second[:800]


# -- L6: attempt memory ---------------------------------------------------------

def test_l6_attempt_two_brief_memory(tmp_path):
    project = "fxloop-l6"
    folder = _project_dir(tmp_path, project)
    _seed(os.path.join(str(folder), "test_p1.py"),
          "def test_p1():\n    assert 1 == 2, 'fxloop red'\n")
    seen = {"auditor": 0}

    def _worker(n_calls, messages):
        text = messages[0]["content"]
        if "attempt 1" in text and n_calls == 0:
            return json.dumps({
                "actions": [{"action": "write_file", "path": "test_p1.py",
                             "content": ("def test_p1():\n"
                                         "    assert 2 == 3, 'still red'\n")}],
                "done": False})
        if "attempt 2" in text and n_calls == 0:
            return json.dumps({
                "actions": [{"action": "write_file", "path": "test_p1.py",
                             "content": ("def test_p1():\n"
                                         "    assert 1 + 1 == 2\n")}],
                "done": False})
        return json.dumps({"actions": [], "done": True})

    def _auditor(n_calls, messages):
        seen["auditor"] += 1
        if seen["auditor"] == 1:
            return json.dumps({"result": "FAIL",
                               "reasons": ["not green yet"]})
        return _audit_pass(n_calls, messages)

    plan = [{"part_id": "p1", "goal": "Make test_p1.py pass",
             "files": ["test_p1.py"],
             "check_commands": [["python", "-m", "pytest", "test_p1.py",
                                  "-q", "-p", "no:cacheprovider"]],
             "depends_on": []}]
    factory = _FakeFactory({
        "director": [json.dumps({"parts": plan})],
        "manager": [_manager_one()],
        "worker": [_worker],
        "auditor": [_auditor],
    })
    app = _served_app(tmp_path, project, factory)
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    calls = _worker_msgs(factory)
    second = [entry for entry in calls
              if "attempt 2" in entry["messages"][0]["content"]]
    assert second, "no attempt-2 worker call"
    brief = second[0]["messages"][0]["content"]
    assert "test_p1.py" in brief, brief[:1200]
    assert "exit 1" in brief, brief[:2000]
    record = _run_record(app, project)
    assert record is not None
    assert record.get("success") is True, record.get("summary")


# -- L7: no-check + why ----------------------------------------------------------

def test_l7_why_no_check_nothing_done_fails(tmp_path):
    project = "fxloop-l7"
    folder = _project_dir(tmp_path, project)

    def _worker(n_calls, messages):
        return json.dumps({"actions": [], "done": True})

    plan = [{"part_id": "p1", "goal": "Think about it",
             "files": [], "check_commands": [],
             "why": "director note: no checks needed",
             "depends_on": []}]
    factory = _FakeFactory({
        "director": [json.dumps({"parts": plan})],
        "manager": [_manager_one()],
        "worker": [_worker],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    record = _run_record(app, project)
    assert record is not None
    assert record.get("success") is not True, record.get("summary")
    assert "Part p1: FAILED" in _all_text(_parse_sse(resp.text))


def test_l7_why_no_check_changed_passes(tmp_path):
    project = "fxloop-l7b"
    folder = _project_dir(tmp_path, project)
    _seed(os.path.join(str(folder), "seeded.txt"), "v1\n")

    def _worker(n_calls, messages):
        if n_calls == 0:
            return json.dumps({
                "actions": [{"action": "write_file", "path": "seeded.txt",
                             "content": "v2\n"}],
                "done": False})
        return json.dumps({"actions": [], "done": True})

    plan = [{"part_id": "p1", "goal": "Bump seeded.txt",
             "files": ["seeded.txt"], "check_commands": [],
             "why": "director note: change is self-evident",
             "depends_on": []}]
    factory = _FakeFactory({
        "director": [json.dumps({"parts": plan})],
        "manager": [_manager_one()],
        "worker": [_worker],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder)
    assert resp.status_code == 200, resp.text
    record = _run_record(app, project)
    assert record is not None
    assert record.get("success") is True, record.get("summary")


# -- L8: build-task answer -------------------------------------------------------

def test_l8_build_answer_reasks_then_nothing_built(tmp_path):
    project = "fxloop-l8"
    folder = _project_dir(tmp_path, project)
    box = {"n": 0}

    def _director(n_calls, messages):
        box["n"] += 1
        return json.dumps({"answer": "do it yourself %d" % box["n"]})

    factory = _FakeFactory({
        "director": [_director],
        "manager": [_manager_one()],
        "worker": [json.dumps({"actions": [], "done": True})],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder, message="Write report.md")
    assert resp.status_code == 200, resp.text
    assert box["n"] == 2, box
    record = _run_record(app, project)
    assert record is not None
    assert record.get("success") is False, record.get("summary")
    assert record.get("summary") == NOTHING_BUILT, record.get("summary")
    text = _all_text(_parse_sse(resp.text))
    assert NOTHING_BUILT in text, text[:800]


def test_l8_plain_question_untouched(tmp_path):
    project = "fxloop-l8b"
    folder = _project_dir(tmp_path, project)
    box = {"n": 0}

    def _director(n_calls, messages):
        box["n"] += 1
        return json.dumps({"answer": "clean code is readable"})

    factory = _FakeFactory({
        "director": [_director],
        "manager": [_manager_one()],
        "worker": [json.dumps({"actions": [], "done": True})],
        "auditor": [_audit_pass],
    })
    app = _served_app(tmp_path, project, factory)
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder,
                      message="What is clean code?")
    assert resp.status_code == 200, resp.text
    assert box["n"] == 1, box
    record = _run_record(app, project)
    assert record is not None
    assert record.get("success") is True, record.get("summary")
