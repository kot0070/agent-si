"""FXPICK item 2: reply-language line on every builder.

ONE helper in roles.py carries the exact line; the director prompt,
the worker prompt and the auditor messages each carry it. Plain chat
and the manager path inherit their language rule from the frozen
chat_history system line (both runners build via chat_messages), so
those tests pin that invariant instead of duplicating the line.
Protocol JSON replies still parse with Ukrainian prose around them
(golden file below). Live model behaviour is checked later on the
exe. RED-first: helper missing, prompts lacked the line.
"""

import os
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import chat_history as _chat_history  # noqa: E402
from agent_si.runtime.devrun import audit as _audit  # noqa: E402
from agent_si.runtime.devrun import engine as _engine  # noqa: E402
from agent_si.runtime.devrun import protocol as _protocol  # noqa: E402
from agent_si.runtime.devrun import roles as _roles  # noqa: E402

LANG = ("Reply in the language of the user's message. "
        "Keep code, file names, commands and JSON keys unchanged.")


def test_reply_language_line_exact():
    assert _roles.reply_language_line() == LANG


def test_director_prompt_carries_language_line():
    assert LANG in _engine._director_prompt("Зроби будь ласка")


def test_worker_prompt_carries_language_line():
    spec = {"part_id": "p1", "goal": "g", "files": ["a.py"]}
    assert LANG in _engine._worker_prompt(spec, "Зроби будь ласка", 1, [], [])


def test_auditor_messages_carry_language_line():
    msgs = _audit.auditor_messages("goal", "diff", [], (), "", part_diff="")
    assert LANG in msgs[0]["content"]


def test_plain_chat_carries_language_rule():
    assert "user's language" in _chat_history._CHAT_CONTEXT_SYSTEM


def test_chat_runners_build_via_chat_messages():
    for rel in ("backend/chat_stream.py", "runtime/manager.py"):
        path = os.path.join(_SRC, "agent_si", rel)
        with open(path, encoding="utf-8") as fh:
            assert "chat_history.chat_messages" in fh.read(), rel


def test_golden_protocol_json_with_ukrainian_prose():
    director = _protocol.parse_director_reply(
        'Ось план: {"parts": [{"part_id": "p1", "goal": "ціль", '
        '"files": ["a.py"], "check_commands": [], "depends_on": []}]}')
    assert director["parts"][0]["part_id"] == "p1"
    worker = _protocol.parse_agent_reply(
        'Готово: {"actions": [], "done": true}')
    assert worker == {"actions": [], "done": True}
    auditor = _protocol.parse_auditor_reply(
        'Перевірено: {"result": "PASS", "reasons": ["добре"]}')
    assert auditor == {"result": "PASS", "reasons": ["добре"]}
