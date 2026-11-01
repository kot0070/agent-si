# Copyright (c) 2026 Ivan Soprun
"""Agent SI frozen sidecar entry (windowed exe, console=False).

Starts the product HTTP app (``agent_si.backend.app.create_app``) with
uvicorn on 127.0.0.1 in a background thread, then opens the UI URL in a
native pywebview window. The UI URL carries a per-launch token
(``app.state.ui_session_token``, generated fresh by every ``create_app``
call); closing the window stops the server and ends the process.

Headless fallback: when no native window can be created (no GUI), the
entry keeps serving on 127.0.0.1 until the process is stopped. Probes
drive the exe through this path with hidden process control.

Only portable stdlib-plus-app APIs are used here: no machine paths, no
secrets in logs, no network beyond loopback.
"""

from __future__ import annotations

import contextlib
import signal
import socket
import sys
import threading

VERSION = "0.1.0"
COPYRIGHT = "Copyright (c) 2026 Ivan Soprun"
LICENSE_NAME = "MIT"
HOST = "127.0.0.1"


def pick_free_port() -> int:
    """Return a free loopback port (bound briefly, then released)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def build_app():
    """Create the product app and attach the sidecar root endpoint."""
    from agent_si.backend.app import create_app

    app = create_app()

    async def sidecar_root() -> dict:
        return {
            "service": "agent-si-sidecar",
            "version": VERSION,
            "status": "ok",
            "copyright": COPYRIGHT,
            "license": LICENSE_NAME,
            "license_file": "LICENSE",
            "notices": "docs/third_party_notices/NOTICES.md",
        }

    app.get("/", include_in_schema=False)(sidecar_root)
    return app


def main(argv: list[str] | None = None) -> int:
    """Run the sidecar: serve on loopback, open the native window."""
    _ = argv
    app = build_app()
    token = getattr(app.state, "ui_session_token", "")
    port = pick_free_port()

    import uvicorn

    config = uvicorn.Config(
        app, host=HOST, port=port, log_level="warning")
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
        print("agent-si-sidecar: server did not start", file=sys.stderr)
        return 1
    print(
        f"agent-si-sidecar: listening on http://{HOST}:{port}/",
        file=sys.stderr,
    )

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
        webview.start()
    except Exception as exc:
        print(
            "agent-si-sidecar: webview unavailable "
            f"({exc}); serving until stopped",
            file=sys.stderr,
        )
        stop.wait()
    finally:
        server.should_exit = True
    thread.join(timeout=10)
    return 0


if __name__ == "__main__":
    sys.exit(main())
