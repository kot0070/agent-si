"""PLANB W2 (DEFECT-7): a long model call shows a live line with role, model
and seconds waited, refreshed at least every 20 s, in the run stream and in
the right panel (agents live row last_action).
"""

import os
import sys
import threading
import time

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_WS, os.path.join(_WS, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from agent_si.backend import chat_stream as _cs  # noqa: E402
from agent_si.runtime.devrun import roles as _roles  # noqa: E402


def test_waiting_line_names_role_model_and_seconds():
    line = _roles.waiting_line("director", 47.9, "ollama/muse-glimmer:30b")
    assert "director" in line
    assert "ollama/muse-glimmer:30b" in line
    assert "47 s" in line


def test_waiting_line_old_shape_still_works():
    assert _roles.waiting_line("worker", 3) == (
        "Waiting for the model: worker, 3 s")


def test_notice_cadence_is_within_20_seconds():
    assert _roles._WAIT_FIRST_S <= 20
    assert _roles._WAIT_EVERY_S <= 20


def test_invoke_timed_on_waiting_refreshes_during_a_long_call():
    seen = []

    class Slow:
        def invoke(self, messages):
            time.sleep(1.0)
            return "ok"

    out = _roles.invoke_timed(
        Slow(), [], first_notice_s=0.2, notice_every_s=0.2, tick_s=0.05,
        on_waiting=seen.append)
    assert out == "ok"
    assert len(seen) >= 3
    assert seen == sorted(seen)


def test_note_waiting_writes_state_and_clear_removes_it():
    state = {}
    _roles.note_waiting(state, "director", "director", "m1", 12)
    entry = state["waiting"]["director"]
    assert "director" in entry["line"] and "m1" in entry["line"]
    assert "12 s" in entry["line"]
    _roles.clear_waiting(state, "director")
    assert "director" not in state["waiting"]


def test_stream_heartbeat_emits_waiting_lines_while_the_engine_blocks():
    state = {}

    def engine():
        yield {"type": "delta", "text": "first\n"}
        for n in (1, 2, 3):
            _roles.note_waiting(state, "director", "director", "m1", n * 15)
            time.sleep(0.5)
        _roles.clear_waiting(state, "director")
        yield {"type": "done"}

    got = list(_cs.events_with_waiting(engine(), state, poll_s=0.1))
    kinds = [item.get("type") for item in got]
    assert kinds[0] == "delta" and kinds[-1] == "done"
    waits = [item for item in got if item.get("waiting") is True]
    assert len(waits) == 3
    assert "director" in waits[0]["text"] and "m1" in waits[0]["text"]
    assert [w["text"].count("s") > 0 for w in waits]
    assert all(w["text"].endswith("\n") for w in waits)
    assert {w["waiting_key"] for w in waits} == {"director"}


def test_stream_heartbeat_reraises_engine_error_and_stops_on_close():
    def boom():
        yield {"type": "delta", "text": "x"}
        raise RuntimeError("engine broke")

    it = _cs.events_with_waiting(boom(), {}, poll_s=0.05)
    assert next(it)["type"] == "delta"
    try:
        next(it)
    except RuntimeError as err:
        assert "engine broke" in str(err)
    else:
        raise AssertionError("engine error was swallowed")

    started = threading.Event()
    closed = threading.Event()

    def long_engine():
        try:
            for n in range(1000):
                started.set()
                yield {"type": "delta", "text": str(n)}
                time.sleep(0.02)
        finally:
            closed.set()

    gen = _cs.events_with_waiting(long_engine(), {}, poll_s=0.05)
    next(gen)
    gen.close()
    assert closed.wait(3.0), "producer thread did not close the engine"


def test_bridge_stream_forwards_waiting_line_not_into_history():
    import json

    from agent_si.backend.chat_stream import ChatStreamRequest, build_bridge
    from agent_si.providers.adapters.base import AdapterConfig, make_secret_ref
    from agent_si.providers.adapters.mock_provider import MockProviderAdapter
    from agent_si.runtime.manager import RunEvent

    holder = {}

    def fake_run(request, **kwargs):
        yield RunEvent(event="turn", turn=1, subtask_id="s", detail="t",
                       data={"text": "plan\n"})
        state = next(iter(holder["bridge"]._live.values()))
        _roles.note_waiting(state, "director", "director", "m1", 15)
        time.sleep(1.5)
        _roles.clear_waiting(state, "director")
        yield RunEvent(event="done", turn=2, subtask_id="s", detail="d",
                       data={"executed": True})

    config = AdapterConfig(
        provider_id="mock", instance_id="w2", model="mock-canned",
        secret_ref=make_secret_ref(secret_id="mock-secret",
                                   provider_id="mock"))
    bridge = build_bridge(
        provider_adapter=MockProviderAdapter(
            config, transport=None, canned=("x",)),
        run_task_streamed=fake_run)
    holder["bridge"] = bridge
    request = ChatStreamRequest.from_body(
        {"project": "w2-proj", "message": "hi"}, "w2-actor")
    _sid, iterator = bridge.run(request)
    raw = b"".join(iterator).decode("utf-8")
    events = [json.loads(line[5:].strip())
              for line in raw.splitlines() if line.startswith("data:")]
    waits = [e for e in events
             if "Waiting for the model: director on m1" in str(e.get("text"))]
    assert len(waits) == 1
    assert "waiting" not in waits[0] and waits[0]["type"] == "delta"
    assert waits[0]["live"] == "director"
    assert "waiting_key" not in waits[0]
    assert events[-1]["type"] == "done"
