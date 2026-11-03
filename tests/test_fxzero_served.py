"""FXZERO served proof: zero-part runs are never success (RED first).

Item 1: a statement-like message ("Demo task") answered with no parts must
not succeed: success False + the guidance sentence on record, stream and
task mirror. A phrased question keeps the pinned L8b answer behaviour.
Item 4 (H91): one condition = one alert (repeats count into rules_fired,
no new row); a finished run is not watched (RETURNED rows count 0).
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


def setup_function(_func):
    agents_live.clear_live_rows()
    _steplimits._reset_state()


def teardown_function(_func):
    agents_live.clear_live_rows()
    _steplimits._reset_state()


def _answer_factory(text):
    return _FakeFactory({
        "director": [json.dumps({"answer": text})],
        "manager": [json.dumps({"order": []})],
        "worker": [json.dumps({"actions": [], "done": True})],
        "auditor": [_audit_pass],
    })


# -- item 1: statement-like BUILD-task zero-part run is not success ---------
# FXANSWER narrowed this pin: a Director answer for a message with no
# build-task verb is a plain answer (success + marker) even without "?",
# so the not-success case names a build verb ("Demo build").

def test_fxzero_statement_answer_no_parts_not_success(tmp_path):
    project = "fxzero-i1"
    folder = _project_dir(tmp_path, project)
    factory = _answer_factory("Here is a plain answer with no parts.")
    app = _served_app(tmp_path, project, factory)
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder, message="Demo build")
    assert resp.status_code == 200, resp.text
    text = _all_text(_parse_sse(resp.text))
    assert "Nothing was built" in text, text[:800]
    record = _run_record(app, project)
    assert record is not None
    assert record.get("parts", []) == [], record.get("parts")
    assert record.get("success") is False, record.get("summary")
    assert "Nothing was built" in str(record.get("summary")), (
        record.get("summary"))


def test_fxzero_question_answer_stays_success(tmp_path):
    project = "fxzero-i1b"
    folder = _project_dir(tmp_path, project)
    factory = _answer_factory("clean code is readable")
    app = _served_app(tmp_path, project, factory)
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    resp = _post_chat(client, project, folder,
                      message="What is clean code?")
    assert resp.status_code == 200, resp.text
    record = _run_record(app, project)
    assert record is not None
    assert record.get("success") is True, record.get("summary")
