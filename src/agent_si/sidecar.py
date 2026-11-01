# Copyright (c) 2026 Ivan Soprun
"""Agent SI frozen sidecar entry (windowed exe, console=False).

Starts the product HTTP app (``agent_si.backend.app.create_app``) with
uvicorn on 127.0.0.1 in a background thread, then opens the UI URL in a
native pywebview window. The UI URL carries a per-launch token
(``app.state.ui_session_token``, generated fresh by every ``create_app``
call); closing the window stops the server and ends the process.

The sidecar also serves the built web tree: GET / answers the tree
``index.html``, built assets are served from the tree, and any other
non-API GET without a file extension answers ``index.html`` (the UI
router owns those paths). Unknown ``/api/*`` paths stay JSON 404; the
previous root JSON document moved to GET /api/v1/sidecar/about. The
tree resolves to the ``frontend`` dir under ``sys._MEIPASS`` in the
frozen exe and to ``frontend/dist`` from a source checkout; an empty
tree answers a clear 503 text body. Every path here tolerates
``sys.stdout=None`` and ``sys.stderr=None`` (windowed exe).

Headless fallback: when no native window can be created (no GUI), the
entry keeps serving on 127.0.0.1 until the process is stopped. Probes
drive the exe through this path with hidden process control.

Only portable stdlib-plus-app APIs are used here: no machine paths, no
secrets in logs, no network beyond loopback.
"""

from __future__ import annotations

import contextlib
import os
import posixpath
import signal
import socket
import sys
import threading

VERSION = "0.1.0"
COPYRIGHT = "Copyright (c) 2026 Ivan Soprun"
LICENSE_NAME = "MIT"
HOST = "127.0.0.1"

#: Web-tree destination name inside the frozen bundle.
_WEB_DEST = "frontend"

#: Profile dir name for the webview window under the product data dir.
_WEBVIEW_DIR_NAME = "webview"

#: Clear text body answered when the web tree holds no index.html.
_UNSTAGED_TEXT = (
    "Agent SI web UI is not staged: the web tree holds no index.html"
)


def pick_free_port() -> int:
    """Return a free loopback port (bound briefly, then released)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def _log(message: str) -> None:
    """Write one line to stderr; silent when streams are unavailable."""
    try:
        stream = sys.stderr
        if stream is None:
            return
        stream.write(str(message) + "\n")
    except Exception:
        return


def _here_root() -> str:
    """Return the source-checkout root anchored at this file."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(here))


def _resolve_web_dir() -> str:
    """Return the web-tree dir (frozen bundle else source dist)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and meipass:
        return os.path.join(str(meipass), _WEB_DEST)
    return os.path.join(_here_root(), "frontend", "dist")


def _index_path(web_dir: str) -> str | None:
    """Return the tree index.html path, or None when it is absent."""
    candidate = os.path.join(web_dir, "index.html")
    if os.path.isfile(candidate):
        return candidate
    return None


def _has_extension(full_path: str) -> bool:
    """Tell whether the last URL segment carries a file extension."""
    leaf = full_path.replace("\\", "/").rsplit("/", 1)[-1]
    return os.path.splitext(leaf)[1] != ""


def _asset_path(web_dir: str, full_path: str) -> str | None:
    """Resolve a tree-relative asset file; None when absent or escaping."""
    cleaned = posixpath.normpath(full_path.replace("\\", "/"))
    if cleaned in ("", ".", "..") or cleaned.startswith("../"):
        return None
    if os.path.isabs(cleaned):
        return None
    candidate = os.path.join(web_dir, *cleaned.split("/"))
    try:
        base = os.path.abspath(web_dir)
        if os.path.commonpath([base, os.path.abspath(candidate)]) != base:
            return None
    except ValueError:
        return None
    if os.path.isfile(candidate):
        return candidate
    return None


def _make_config(app, port: int):
    """Build the uvicorn config without touching logging streams."""
    import uvicorn

    return uvicorn.Config(app, host=HOST, port=port, log_config=None)


def webview_storage_dir() -> str:
    """Return the per-user webview profile dir under the product data root.

    The operator ``WEBVIEW2_USER_DATA_FOLDER`` value keeps working: when
    it names a dir it is used as-is. Otherwise the dir lives under the
    same data root the product resolves (``get_data_dir``), falling back
    to a per-user home dir when no data root is configured.
    """
    override = os.environ.get("WEBVIEW2_USER_DATA_FOLDER")
    if override is not None and str(override).strip():
        path = os.path.abspath(os.path.expanduser(str(override)))
    else:
        root = None
        try:
            from agent_si.backend.app import get_data_dir

            root = get_data_dir()
        except Exception:
            root = None
        if root is None:
            root = os.path.join(os.path.expanduser("~"), ".agent_si")
        path = os.path.join(os.path.abspath(str(root)), _WEBVIEW_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def build_app():
    """Create the product app and attach the sidecar web endpoints."""
    from agent_si.backend.app import create_app
    from fastapi.responses import (
        FileResponse,
        JSONResponse,
        PlainTextResponse,
    )

    app = create_app()

    about = {
        "service": "agent-si-sidecar",
        "version": VERSION,
        "status": "ok",
        "copyright": COPYRIGHT,
        "license": LICENSE_NAME,
        "license_file": "LICENSE",
        "notices": "docs/third_party_notices/NOTICES.md",
    }

    async def sidecar_about() -> dict:
        return dict(about)

    async def sidecar_index():
        index = _index_path(_resolve_web_dir())
        if index is None:
            return PlainTextResponse(_UNSTAGED_TEXT, status_code=503)
        return FileResponse(index, media_type="text/html")

    async def sidecar_page(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse(
                status_code=404, content={"detail": "Not Found"})
        web_dir = _resolve_web_dir()
        if _has_extension(full_path):
            asset = _asset_path(web_dir, full_path)
            if asset is None:
                return PlainTextResponse("Not Found", status_code=404)
            return FileResponse(asset)
        index = _index_path(web_dir)
        if index is None:
            return PlainTextResponse(_UNSTAGED_TEXT, status_code=503)
        return FileResponse(index, media_type="text/html")

    app.get("/api/v1/sidecar/about", include_in_schema=False)(sidecar_about)
    app.get("/", include_in_schema=False)(sidecar_index)
    app.get("/{full_path:path}", include_in_schema=False)(sidecar_page)
    return app


def main(argv: list[str] | None = None) -> int:
    """Run the sidecar: serve on loopback, open the native window."""
    _ = argv
    app = build_app()
    token = getattr(app.state, "ui_session_token", "")
    port = pick_free_port()

    config = _make_config(app, port)
    import uvicorn

    server = uvicorn.Server(config)
    thread = threading.Thread(
        target=server.run, name="agent-si-uvicorn", daemon=True)
    thread.start()
    if not server.started:
        for _ in range(200):
            if server.started:
                break
            thread.join(timeout=0.1)
    if not server.started:
        _log("agent-si-sidecar: server did not start")
        return 1
    _log(f"agent-si-sidecar: listening on http://{HOST}:{port}/")

    url = f"http://{HOST}:{port}/?token={token}"
    stop = threading.Event()

    def request_stop(*_args: object) -> None:
        server.should_exit = True
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(OSError, ValueError):
            signal.signal(sig, request_stop)

    try:
        import webview

        window = webview.create_window("Agent SI", url)
        _ = window
        webview.start(private_mode=False, storage_path=webview_storage_dir())
    except Exception as exc:
        _log(
            "agent-si-sidecar: webview unavailable "
            f"({exc}); serving until stopped"
        )
        stop.wait()
    finally:
        server.should_exit = True
    thread.join(timeout=10)
    return 0


if __name__ == "__main__":
    sys.exit(main())
