"""FXR2E-LOG: rotating file log under the data dir (RED-first).

The app writes no log file today: sidecar._log goes to stderr only
and the frozen exe has no console, so backend errors vanish. The
data-dir log (logs/agent-si.log, rotating 5MB x 3, UTF-8) must
capture: start/stop/version/port lines, unhandled exceptions with
tracebacks, engine + chat terminal failures with run id, provider
4xx/5xx status only. Redaction reuses actions.redact_text: no fake
key or token pattern may reach the file. A stream ending with no
terminal event names NO_TERMINAL_EVENT for the UI and logs why.
"""
import json
import logging
import os
import sys

from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agent_si import file_log as _file_log  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402

TOKEN = "fxlog-token"


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_exception_in_run_writes_traceback_to_file(tmp_path, monkeypatch):
    """Served 500: traceback lands in the data-dir log, secrets don't."""
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    root = str(tmp_path / "appdata")
    app = create_app({"store_dir": root, "secret_store": "memory",
                      "testing": True, "ui_session_token": TOKEN})

    @app.get("/api/v1/fxlog/boom")
    async def _boom():
        raise RuntimeError(
            "boom api-key=FAKE-LOG-KEY-9 token=FAKE-LOG-TOK-9")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/v1/fxlog/boom")
    assert resp.status_code == 500, resp.text
    assert resp.json().get("code"), resp.text

    path = _file_log.log_file_for(root)
    assert os.path.isfile(path), path
    text = _read(path)
    assert "Traceback" in text, text[-2000:]
    assert "RuntimeError" in text, text[-2000:]
    assert "FAKE-LOG-KEY-9" not in text
    assert "FAKE-LOG-TOK-9" not in text
    assert "[REDACTED]" in text


def test_no_terminal_event_logs_why_and_names_code(tmp_path):
    """Delta-only manager run: done names NO_TERMINAL_EVENT; log tells why."""
    from agent_si.backend.chat_stream import (
        ChatStreamRequest, build_bridge)
    from agent_si.runtime.manager import RunEvent

    root = str(tmp_path / "appdata")
    _file_log.install(root, version="fxlog-test")

    def _run(request, **kwargs):
        yield RunEvent(event="delta", turn=1, subtask_id="s",
                       detail="half a thought", data={})

    bridge = build_bridge(
        provider_adapter=object(), run_task_streamed=_run)
    request = ChatStreamRequest.from_body(
        {"project": "fxlog-p", "message": "hi"}, "fxlog-actor")
    _stream_id, iterator = bridge.run(request)
    events = [json.loads(line[len("data:"):].strip())
              for line in b"".join(iterator).decode("utf-8").splitlines()
              if line.startswith("data:")]
    kinds = [event.get("type") for event in events]
    assert kinds[0] == "start", kinds
    assert kinds[-1] == "done", kinds
    assert events[-1].get("code") == "NO_TERMINAL_EVENT", events[-1]

    text = _read(_file_log.log_file_for(root))
    assert "NO_TERMINAL_EVENT" in text, text[-2000:]
    assert events[-1].get("run_id") in text, text[-2000:]


def test_frozen_path_resolved_from_data_root(tmp_path, monkeypatch):
    """Same data root the frozen sidecar resolves: <root>/logs/agent-si.log."""
    from agent_si import sidecar

    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(tmp_path / "frozen"))
    root = sidecar._sidecar_data_dir()
    assert root == str(tmp_path / "frozen"), root
    path = _file_log.log_file_for(root)
    assert path == os.path.join(
        str(tmp_path / "frozen"), "logs", "agent-si.log"), path
    _file_log.install(root, version="fxlog-frozen")
    sidecar._log("fxlog frozen probe line")
    assert os.path.isfile(path), path
    assert "fxlog frozen probe line" in _read(path)


def test_rotation_by_size(tmp_path):
    """Tiny cap: the log rolls to .1 instead of growing."""
    root = str(tmp_path / "appdata")
    path = _file_log.install(root, version="fxlog-rot", max_bytes=300)
    logger = logging.getLogger("agent_si.filelog.probe")
    for index in range(60):
        logger.info("rotation probe line %d padding padding padding", index)
    for handler in logging.getLogger().handlers:
        try:
            handler.flush()
        except Exception:
            pass
    assert os.path.isfile(path + ".1"), os.listdir(os.path.dirname(path))
    assert os.path.getsize(path) < 5000


def test_unhandled_hook_logs_traceback(tmp_path, monkeypatch):
    """sys.excepthook path: traceback in the file, key pattern redacted."""
    root = str(tmp_path / "appdata")
    _file_log.install(root, version="fxlog-hook")
    try:
        raise ValueError("hook api-key=FAKE-HOOK-KEY-3")
    except ValueError:
        _file_log.log_exception("probe", "run-hook-1",
                                sys.exc_info()[1])
    text = _read(_file_log.log_file_for(root))
    assert "Traceback" in text and "run-hook-1" in text, text[-2000:]
    assert "FAKE-HOOK-KEY-3" not in text


def test_sidecar_about_names_log_dir(tmp_path, monkeypatch):
    """GET /api/v1/sidecar/about carries the logs_dir for Diagnostics."""
    from agent_si import sidecar

    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(tmp_path / "frozen"))
    app = sidecar.build_app()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/v1/sidecar/about")
    assert resp.status_code == 200, resp.text
    assert resp.json().get("logs_dir") == os.path.join(
        str(tmp_path / "frozen"), "logs"), resp.text


def test_sidecar_open_logs_guarded_and_plain(tmp_path, monkeypatch):
    """POST /api/v1/sidecar/open-logs: 401/403 guarded, plain 409 or open."""
    from agent_si import sidecar

    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(tmp_path / "frozen"))
    app = sidecar.build_app()
    client = TestClient(app, raise_server_exceptions=False)
    path = "/api/v1/sidecar/open-logs"
    assert client.post(path).status_code == 401
    assert client.post(
        path, headers={"x-actor": "a",
                       "x-ui-session-token": "wrong"}).status_code == 403
    token = app.state.ui_session_token
    opened = []
    monkeypatch.setattr(
        sidecar.os, "startfile",
        lambda target: opened.append(target) or None, raising=False)
    resp = client.post(
        path, headers={"x-actor": "a", "x-ui-session-token": token})
    body = resp.json()
    if resp.status_code == 200:
        assert body.get("opened") is True, body
        assert opened == [os.path.join(str(tmp_path / "frozen"), "logs")]
    else:
        assert resp.status_code == 409, resp.text
        assert body.get("code") == "LOGS_REVEAL_UNAVAILABLE", body
