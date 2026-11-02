"""FXOPEN O4 (photos 01/05/17): chat run log without host paths.

Served: manager-event text forwarded to chat SSE carries file names
plus project-relative paths only — no drive-letter absolute paths,
no user name. Unit pins: sibling stems never collide, forward-slash
forms work, a lone folder mention becomes its base name.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

_WS = Path(__file__).resolve().parents[1]
_SRC = _WS / "src"
for _entry in (str(_WS), str(_SRC)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from agent_si.backend.chat_stream import (  # noqa: E402
    ChatStreamRequest,
    ManagerSdkBridge,
    _chat_display_text,
)


def _sse_texts(chunks: list[bytes]) -> list[str]:
    texts = []
    for chunk in chunks:
        for line in chunk.decode("utf-8", "replace").splitlines():
            if line.startswith("data: "):
                try:
                    payload = json.loads(line[6:])
                except ValueError:
                    continue
                if isinstance(payload.get("text"), str):
                    texts.append(payload["text"])
    return texts


def test_fxopen_chat_paths_served_no_host_paths(tmp_path):
    """Real _manager_events path: SSE text has no absolute host paths."""
    bridge = ManagerSdkBridge()
    bridge._app = SimpleNamespace(
        state=SimpleNamespace(data_dir=str(tmp_path)))
    workspace = tmp_path / "ws"
    workspace.mkdir()
    raw = (
        "Working folder: %s\n"
        "Check p1 $ C:\\Windows\\system32\\findstr.EXE hello hello.txt\n"
        "Run dir: C:\\Users\\kot00\\work\n"
        "log %s\\run.log\n"
        "run success: all 1 parts PASS"
    ) % (workspace, workspace)

    def fake_entry(dev_request, **kwargs):
        yield {"type": "delta", "text": raw}
        yield {"type": "done", "text": "run success: all 1 parts PASS",
               "run_id": "r"}

    request = ChatStreamRequest(
        project="p", folder=str(workspace), message="hi")
    chunks = list(bridge._manager_events(
        "s", "r", request, {"cancelled": False}, fake_entry))
    blob = "\n".join(_sse_texts(chunks))
    assert "C:\\" not in blob
    assert "D:\\" not in blob
    assert "kot00" not in blob
    assert "Users" not in blob
    assert "findstr" in blob
    assert "run.log" in blob
    assert "Working folder:" in blob


def test_fxopen_chat_display_sibling_stem_never_collides():
    """D:\\proj2 keeps its own tail; only the exact folder shortens."""
    out = _chat_display_text(
        "a D:\\proj\\run.log b D:\\proj2\\run.log c D:\\proj",
        "D:\\proj")
    assert "run.log" in out
    assert "proj2" in out
    assert "D:\\" not in out


def test_fxopen_chat_display_forward_slash_folder():
    out = _chat_display_text(
        "open D:/proj/sub/note.txt now", "D:\\proj")
    assert out == "open sub/note.txt now"


def test_fxopen_chat_display_lone_folder_becomes_base():
    out = _chat_display_text("Working folder: D:\\Test2\\app", "D:\\Test2\\app")
    assert out == "Working folder: app"


def test_fxopen_chat_display_outside_path_becomes_filename():
    out = _chat_display_text(
        "Check p1 $ C:\\Windows\\system32\\findstr.EXE ok", "")
    assert out == "Check p1 $ findstr.EXE ok"


def test_fxopen_chat_display_non_string_passthrough():
    assert _chat_display_text("", "D:\\x") == ""
    assert _chat_display_text(None, "D:\\x") is None  # type: ignore[arg-type]
