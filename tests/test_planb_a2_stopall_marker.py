"""PLANB A2 (DEFECT-40, live path): Stop all flags the chat stream while the
engine runs; the stream then ends with a cancelled event. The engine's own
stop line was dropped, so the chat read a clean end ('Failed - 1 part, 0
passed'). The stream now sends the stop line before cancelled."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

_WS = Path(__file__).resolve().parents[1]
for _entry in (str(_WS), str(_WS / "src")):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from agent_si.backend.chat_stream import (  # noqa: E402
    ChatStreamRequest,
    ManagerSdkBridge,
)


def _events(chunks):
    out = []
    for chunk in chunks:
        for line in chunk.decode("utf-8", "replace").splitlines():
            if line.startswith("data: "):
                out.append(json.loads(line[6:]))
    return out


def test_stop_all_mid_run_stream_carries_the_stop_line_before_cancelled(
        tmp_path):
    bridge = ManagerSdkBridge()
    bridge._app = SimpleNamespace(
        state=SimpleNamespace(data_dir=str(tmp_path)))
    workspace = tmp_path / "ws"
    workspace.mkdir()
    state = {"cancelled": False}

    def fake_entry(dev_request, **kwargs):
        yield {"type": "delta", "text": "Part p1: attempt 1\n"}
        state["cancelled"] = True
        yield {"type": "delta", "text": "run stopped: user stop"}
        yield {"type": "cancelled", "text": "run stopped: user stop"}

    request = ChatStreamRequest(
        project="p", folder=str(workspace), message="hi")
    events = _events(bridge._manager_events(
        "s", "r", request, state, fake_entry))
    kinds = [e["type"] for e in events]
    assert kinds[-1] == "cancelled", kinds
    stop_at = [i for i, e in enumerate(events)
               if e["type"] == "delta"
               and "run stopped: user stop" in e.get("text", "")]
    assert stop_at and stop_at[0] < len(events) - 1, events
