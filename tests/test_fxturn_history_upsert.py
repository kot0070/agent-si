"""FXTURN lane: one chat task leaves one history row.

Server-side upsert by run id (src/agent_si/backend/chat_history.py):
a run start (running) plus its terminal write share one run id and
collapse to a single turn; a later client replay with the same run
id closes the same row and keeps the fuller transcript. Writes with
an empty run id always append, so legacy rows without a run id
still load and never merge.
"""

from types import SimpleNamespace

import os
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import chat_history as chat_history  # noqa: E402
from agent_si.backend import chat_stream as chat_stream  # noqa: E402


def _app():
    state = SimpleNamespace(
        chat_history_turns={},
        chat_history_hydrated=True,
        k02r3_store_dir=None,
    )
    return SimpleNamespace(state=state)


def test_server_open_and_terminal_share_run_id():
    app = _app()
    chat_history.record_turn(
        app, "p1", "Create a file hello.txt", "",
        status="running", run_id="r-1",
    )
    chat_history.record_turn(
        app, "p1", "Create a file hello.txt",
        "Working folder: /tmp\nrun success: all 1 parts PASS\n",
        status="ok", run_id="r-1",
    )
    turns = chat_history.list_turns(app, "p1")
    assert len(turns) == 1
    assert turns[0]["run_id"] == "r-1"
    assert turns[0]["status"] == "ok"


def test_client_replay_same_run_id_keeps_fuller_text():
    app = _app()
    chat_history.record_turn(
        app, "p1", "Create a file hello.txt",
        "Working folder: /tmp\nhello.txt written\n"
        "run success: all 1 parts PASS\n",
        status="ok", run_id="r-1",
    )
    chat_history.record_turn(
        app, "p1", "Create a file hello.txt",
        "run success: all 1 parts PASS\n",
        status="ok", run_id="r-1",
    )
    turns = chat_history.list_turns(app, "p1")
    assert len(turns) == 1
    assert "hello.txt" in turns[0]["assistant_text"]


def test_empty_run_id_rows_never_merge():
    app = _app()
    chat_history.record_turn(
        app, "p1", "u1", "a1", status="ok", run_id="")
    chat_history.record_turn(
        app, "p1", "u2", "a2", status="ok", run_id="")
    turns = chat_history.list_turns(app, "p1")
    assert len(turns) == 2


def test_different_run_ids_make_separate_rows():
    app = _app()
    chat_history.record_turn(
        app, "p1", "q1", "a1", status="ok", run_id="r-1")
    chat_history.record_turn(
        app, "p1", "q2", "a2", status="ok", run_id="r-2")
    assert len(chat_history.list_turns(app, "p1")) == 2


def test_stream_open_write_carries_run_id():
    app = _app()
    chat_stream._record_server_turn(
        app, "p1", "hello", "", "running", run_id="r-9")
    turns = chat_history.list_turns(app, "p1")
    assert len(turns) == 1
    assert turns[0]["run_id"] == "r-9"
    assert turns[0]["status"] == "running"
