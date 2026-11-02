"""FXHIGH item 4: long model replies are trimmed in loop history.

RED: the whole response.output_text rides into history, so one 200 KB
write lands in every next call. Expected: history keeps head 8 KB +
tail 8 KB + one line naming the cut; the run log keeps the whole text;
current-turn parsing is untouched.
"""
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

from agent_si.runtime.devrun import engine as _engine  # noqa: E402

LONG = "x" * 200000


def _long_reply():
    return json.dumps({"actions": [], "done": False, "pad": LONG})


def test_helper_trims_long_reply():
    out = _engine._cap_reply_text(_long_reply())
    assert len(out) <= 8192 + 8192 + 500, len(out)
    assert out.startswith(_long_reply()[:8192])
    assert out.endswith(_long_reply()[-8192:])
    assert "cut" in out


def test_helper_keeps_short_reply_verbatim():
    assert _engine._cap_reply_text("ok") == "ok"
    assert _engine._cap_reply_text("") == ""


def _run_loop(tmp_path):
    seen = []
    replies = [_long_reply(),
               json.dumps({"actions": [], "done": True})]

    def _call(_role, _spec, _adapter, history, _part, _attempt, waits=None):
        seen.append([dict(msg) for msg in history])
        return types.SimpleNamespace(output_text=replies.pop(0))

    row: dict = {}
    out = _engine._agent_loop(
        record={}, app=None,
        spec={"part_id": "p1", "goal": "write it", "files": ["out.txt"]},
        row=row, adapter=None,
        worker_spec={"provider": "no-such", "model": "no-such"},
        folder=str(tmp_path), project="fxhigh-echo", run_id="run-1",
        part_id="p1", attempt=1, turn=0, turn_cap=3, state={},
        procs=[], failing=[], reasons=[], message="do it",
        publish=lambda *a, **k: None, check_stop=lambda: None,
        live=lambda *a, **k: None, call=_call)
    return out, seen, row


def test_next_call_history_bounded_after_long_reply(tmp_path):
    out, seen, _row = _run_loop(tmp_path)
    assert out[1] is True
    assert len(seen) >= 2
    second = seen[1]
    biggest = max(len(str(msg.get("content", ""))) for msg in second)
    assert biggest <= 8192 + 8192 + 500, biggest
    assert any("cut" in str(msg.get("content", "")) for msg in second
               if msg.get("role") == "assistant")


def test_run_log_keeps_whole_reply(tmp_path):
    _run_loop(tmp_path)
    log_path = tmp_path / ".devrun" / "agent" / "p1-a1.jsonl"
    blob = log_path.read_text(encoding="utf-8")
    assert LONG in blob
