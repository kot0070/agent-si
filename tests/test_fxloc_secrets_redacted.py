"""FXLOC C4: secret-shaped text is redacted before it is stored.

journal.append_event and chat_history.record_turn (the chat_stream
server-turn path) redact SCAN_PATTERNS matches; the named short test
key sk-abc123 is stored redacted, while ordinary words stay intact.
"""
from __future__ import annotations

import json
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from agent_si.backend import chat_history  # noqa: E402
from agent_si.backend import chat_stream  # noqa: E402
from agent_si.watcher import journal  # noqa: E402

_PROJECT = "fxloc-c4-proj"
_SHORT_KEY = "sk-abc123"
_LABELLED = "api_key=abcDEF123456"


@pytest.fixture()
def _isolated_journal():
    saved_rows = {key: list(rows)
                  for key, rows in journal._ROWS.items()}
    saved_seq = journal._SEQ
    journal.reset_state()
    yield
    journal._ROWS.clear()
    journal._ROWS.update(saved_rows)
    journal._SEQ = saved_seq


def _fake_app():
    return types.SimpleNamespace(state=None)


def test_journal_redacts_short_test_key(_isolated_journal):
    journal.append_event(
        _PROJECT, "fxloc-c4", "TAMPER_ATTEMPT",
        "leak %s here" % _SHORT_KEY, ("run-%s" % _SHORT_KEY,))
    rows = journal.stored_rows(_PROJECT)
    assert rows, "row must still be stored"
    dumped = json.dumps(
        [{"kind": row.kind, "source": row.source, "summary": row.summary,
          "refs": list(row.refs)} for row in rows])
    assert _SHORT_KEY not in dumped, dumped
    assert "[redacted]" in dumped, dumped


def test_journal_redacts_labelled_secret(_isolated_journal):
    journal.append_event(
        _PROJECT, "fxloc-c4", "TAMPER_ATTEMPT",
        "leak %s here" % _LABELLED, ())
    dumped = json.dumps([row.summary
                         for row in journal.stored_rows(_PROJECT)])
    assert _LABELLED not in dumped, dumped
    assert "[redacted]" in dumped, dumped


def test_journal_keeps_ordinary_words(_isolated_journal):
    clean = "keyboard shortcut ctrl+k maps the tokenize helper"
    journal.append_event(_PROJECT, "fxloc-c4", "WATCH_DECISION", clean, ())
    assert journal.stored_rows(_PROJECT)[0].summary == clean


def test_record_turn_redacts_short_test_key():
    stored = chat_history.record_turn(
        _fake_app(), _PROJECT, "check %s now" % _SHORT_KEY,
        "assistant repeats %s" % _SHORT_KEY)
    dumped = json.dumps(stored)
    assert _SHORT_KEY not in dumped, dumped
    assert "[redacted]" in dumped, dumped


def test_server_turn_path_redacts_short_test_key():
    chat_stream._record_server_turn(
        _fake_app(), _PROJECT, "user %s" % _SHORT_KEY,
        "assistant %s" % _SHORT_KEY, "ok")
    assert "[redacted]" in chat_history._scrub("user %s" % _SHORT_KEY)


def test_record_turn_keeps_ordinary_words():
    clean = "the secretary filed the Monday report"
    stored = chat_history.record_turn(_fake_app(), _PROJECT, clean, clean)
    assert stored["user_text"] == clean
    assert stored["assistant_text"] == clean
