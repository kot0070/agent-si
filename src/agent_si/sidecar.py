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

POST /api/v1/sidecar/pick-folder opens the native folder dialog on the
window through ``webview.FOLDER_DIALOG`` and answers the chosen path;
a cancelled dialog answers ``{"path": null}`` and a context with no
native window (headless or browser) answers 409 carrying the
``_PICK_FOLDER_UNAVAILABLE_CODE`` machine code. The route requires the
session token exactly like the other write routes (401 without
x-actor, 403 with a bad x-ui-session-token).

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

from fastapi import HTTPException, Request

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

#: Machine-readable code carried by the 409 answer of POST
#: /api/v1/sidecar/pick-folder when no native window can open the
#: folder dialog (headless or browser context). The answer body keeps
#: the repo {code, message} refusal shape.
_PICK_FOLDER_UNAVAILABLE_CODE = "NATIVE_DIALOG_UNAVAILABLE"


#: Default native window size (F3): pywebview opens 800x600 without
#: an explicit size, which hides nav behind the condensed bar.
_WINDOW_DEFAULT_WIDTH = 1280
_WINDOW_DEFAULT_HEIGHT = 800

#: Minimum native window size: never restored smaller than this
#: (floor applied before the work-area cap, so the cap always wins
#: on tiny screens and the window never exceeds the screen).
_WINDOW_MIN_WIDTH = 1024
_WINDOW_MIN_HEIGHT = 700

#: Window-size record under the product data dir. The DATA DIR is
#: used on purpose and never localStorage: the UI origin port
#: changes on every launch, so a per-origin store would lose the
#: size. JSON body ``{"width": int, "height": int}``.
_WINDOW_SIZE_FILE_NAME = "sidecar.window.json"


#: WebView2 runtime download hub, named in the missing-runtime
#: notice so a windowed start without WebView2 tells the operator
#: exactly where to get it.
_WEBVIEW2_DOWNLOAD_URL = (
    "https://developer.microsoft.com/microsoft-edge/webview2/")

#: Single-instance port record under the product data dir. The first
#: start writes ``<port>\\n<token>`` after the server is up and removes
#: it on exit; a second start with a live port opens the same URL in
#: the browser and ends without a second server.
_PORT_FILE_NAME = "sidecar.port"


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


def _open_in_browser(url: str) -> bool:
    """Open the sidecar URL in the default browser; False on failure."""
    try:
        import webbrowser

        webbrowser.open(str(url))
        return True
    except Exception:
        return False


def _note_webview_missing(url: str) -> bool:
    """Tell the operator the window needs the WebView2 runtime.

    Windowed native message box on Windows (plain words plus the
    download link and the browser fallback); stderr log elsewhere or
    when the box cannot show. Returns True when a box was shown.
    """
    message = (
        "Agent SI is running but its window cannot open: "
        "the WebView2 runtime is missing. "
        "Install it from " + _WEBVIEW2_DOWNLOAD_URL + " "
        "and start Agent SI again. "
        "The app was also opened in your default browser: " + str(url)
    )
    shown = False
    if os.name == "nt":
        try:
            import ctypes

            shown = bool(ctypes.windll.user32.MessageBoxW(
                None, message, "Agent SI", 0x40))
        except Exception:
            shown = False
    if not shown:
        _log("agent-si-sidecar: " + message)
    return shown


def _sidecar_data_dir() -> str | None:
    """Product data dir for the port record; None when unresolvable."""
    try:
        from agent_si.backend.app import get_data_dir

        return get_data_dir()
    except Exception:
        return None


def _port_file_path(root: str) -> str:
    """Port-record path under the product data dir."""
    return os.path.join(os.path.abspath(str(root)), _PORT_FILE_NAME)


def _port_is_live(port: int) -> bool:
    """True when a loopback server answers on the recorded port."""
    try:
        with socket.create_connection((HOST, int(port)), timeout=1):
            pass
        return True
    except (OSError, ValueError, OverflowError):
        return False


def _read_port_file(path: str) -> tuple[int, str] | None:
    """Parse the port record; None when absent or malformed."""
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return None
    if not lines:
        return None
    try:
        port = int(lines[0].strip())
    except ValueError:
        return None
    if not 1 <= port <= 65535:
        return None
    token = lines[1].strip() if len(lines) > 1 else ""
    return port, token


def _write_port_file(path: str, port: int, token: str) -> None:
    """Record the live port plus token; failures never break start."""
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("%d\n%s\n" % (int(port), str(token)))
    except OSError:
        return


def _clear_port_file(path: str) -> None:
    """Remove the port record on exit; failures are silent."""
    try:
        os.unlink(path)
    except OSError:
        return


def _window_size_file_path(root: str) -> str:
    """Size-record path under the product data dir."""
    return os.path.join(os.path.abspath(str(root)), _WINDOW_SIZE_FILE_NAME)


def _screen_work_area() -> tuple[int, int] | None:
    """Return the usable screen work area (width, height).

    Windows reads SPI_GETWORKAREA (the screen minus the taskbar);
    elsewhere there is no portable stdlib probe, so None is
    returned and the caller keeps the uncapped size. Tests fake
    this hook with small/normal screens.
    """
    if os.name == "nt":
        try:
            import ctypes

            rect = (ctypes.c_long * 4)()
            SPI_GETWORKAREA = 0x0030
            ok = ctypes.windll.user32.SystemParametersInfoW(
                SPI_GETWORKAREA, 0, rect, 0)
            if ok:
                width = int(rect[2]) - int(rect[0])
                height = int(rect[3]) - int(rect[1])
                if width > 0 and height > 0:
                    return width, height
        except Exception:
            return None
        return None
    return None


def _read_window_size(path: str) -> tuple[int, int] | None:
    """Parse the saved size record; None when absent or malformed."""
    try:
        with open(path, encoding="utf-8") as handle:
            import json

            data = json.load(handle)
    except (OSError, ValueError):
        return None
    try:
        if isinstance(data, dict):
            width = int(data.get("width"))
            height = int(data.get("height"))
        elif isinstance(data, (list, tuple)) and len(data) == 2:
            width, height = int(data[0]), int(data[1])
        else:
            return None
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _write_window_size(path: str, width: int, height: int) -> None:
    """Persist the close size in the DATA DIR; failures never break exit."""
    try:
        import json

        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"width": int(width), "height": int(height)}, handle)
    except (OSError, ValueError):
        return


def _cap_window_size(
    width: int, height: int, work: tuple[int, int] | None,
) -> tuple[int, int]:
    """Floor to the minimum, then cap to the work area (cap wins)."""
    try:
        w, h = int(width), int(height)
    except (TypeError, ValueError):
        w, h = _WINDOW_DEFAULT_WIDTH, _WINDOW_DEFAULT_HEIGHT
    if w <= 0 or h <= 0:
        w, h = _WINDOW_DEFAULT_WIDTH, _WINDOW_DEFAULT_HEIGHT
    w = max(w, _WINDOW_MIN_WIDTH)
    h = max(h, _WINDOW_MIN_HEIGHT)
    if work is not None:
        try:
            ww, hh = int(work[0]), int(work[1])
        except (TypeError, ValueError, IndexError):
            return w, h
        if ww > 0:
            w = min(w, ww)
        if hh > 0:
            h = min(h, hh)
    return w, h


def resolve_window_size(data_root: str | None = None) -> tuple[int, int]:
    """Return the window size: saved record else the 1280x800 default.

    The saved record (DATA DIR JSON) is restored when present and
    valid; the result is floored to the 1024x700 minimum and capped
    to the screen work area. A bad record or an unknown screen
    falls back to the default (still floored, cap skipped).
    """
    width, height = _WINDOW_DEFAULT_WIDTH, _WINDOW_DEFAULT_HEIGHT
    if data_root is not None:
        try:
            saved = _read_window_size(_window_size_file_path(data_root))
        except Exception:
            saved = None
        if saved is not None:
            width, height = saved
    try:
        work = _screen_work_area()
    except Exception:
        work = None
    return _cap_window_size(width, height, work)


def _reattach_running() -> bool:
    """Open the already-running instance; True when one was live.

    A second start while one server runs opens the same URL in the
    default browser and ends at once: no second server, no second
    window. A stale record (port dead) is cleared and start proceeds.
    """
    root = _sidecar_data_dir()
    if not root:
        return False
    path = _port_file_path(root)
    record = _read_port_file(path)
    if record is None:
        return False
    port, token = record
    if not _port_is_live(port):
        _clear_port_file(path)
        return False
    url = f"http://{HOST}:{port}/?token={token}" if token else (
        f"http://{HOST}:{port}/")
    _open_in_browser(url)
    _log(f"agent-si-sidecar: already running on {HOST}:{port}; "
         "opened in browser, no second server started")
    return True


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
    from fastapi.responses import (
        FileResponse,
        JSONResponse,
        PlainTextResponse,
    )

    from agent_si.backend.app import create_app

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

    def _pick_unavailable():
        return JSONResponse(
            status_code=409,
            content={
                "code": _PICK_FOLDER_UNAVAILABLE_CODE,
                "message": (
                    "native folder dialog is unavailable: "
                    "no native window"
                ),
            },
        )

    async def sidecar_pick_folder(request: Request):
        """Open the native folder dialog; answer the chosen path.

        Guarded exactly like the other write routes: 401 without an
        x-actor header, 403 with a bad x-ui-session-token checked
        through app.state.auth_hook (falling back to the bound
        ui_session_token). A dialog choice answers ``{"path": ...}``,
        a cancelled (or empty) dialog answers ``{"path": null}``, and
        a context with no native window answers 409.
        """
        actor = (request.headers.get("x-actor") or "").strip()
        if not actor:
            raise HTTPException(
                status_code=401, detail="missing x-actor header")
        token = request.headers.get("x-ui-session-token")
        check = getattr(app.state, "auth_hook", None)
        allowed = False
        if callable(check):
            try:
                allowed = bool(check(token, actor, "USER_WRITE"))
            except Exception:
                allowed = False
        else:
            expected = getattr(app.state, "ui_session_token", None)
            allowed = expected is not None and token == expected
        if not allowed:
            raise HTTPException(status_code=403, detail="forbidden")
        try:
            import webview as _webview
        except Exception:
            return _pick_unavailable()
        windows = getattr(_webview, "windows", None) or []
        if not windows:
            return _pick_unavailable()
        dialog_type = getattr(_webview, "FOLDER_DIALOG", None)
        if dialog_type is None:
            return _pick_unavailable()
        try:
            chosen = windows[0].create_file_dialog(dialog_type)
        except Exception:
            return _pick_unavailable()
        if isinstance(chosen, (list, tuple)):
            path = chosen[0] if chosen else None
        else:
            path = chosen
        if not isinstance(path, str) or not path:
            return {"path": None}
        return {"path": path}

    app.get("/api/v1/sidecar/about", include_in_schema=False)(sidecar_about)
    app.post("/api/v1/sidecar/pick-folder", include_in_schema=False)(
        sidecar_pick_folder
    )
    app.get("/", include_in_schema=False)(sidecar_index)
    app.get("/{full_path:path}", include_in_schema=False)(sidecar_page)
    return app


#: CLI flag routing the frozen exe (or a source checkout) to one QA
#: runner module with the host stdio contract. Handled first in main(),
#: before any window, port pick or server start.
_QA_RUNNER_FLAG = "--qa-runner"


def _qa_runner_ref(argv: list[str] | None) -> str | None:
    """Return the runner ref after --qa-runner, or None when absent."""
    args = list(sys.argv[1:] if argv is None else argv)
    if _QA_RUNNER_FLAG not in args:
        return None
    index = args.index(_QA_RUNNER_FLAG)
    if index + 1 >= len(args):
        return ""
    return args[index + 1]


def run_qa_runner(runner_ref: str) -> int:
    """Run one QA runner module with the host stdio contract.

    Reads the host input JSON on stdin and lets the runner module emit
    exactly one result JSON on stdout, then exits: no window, no port
    pick, no server. Unknown runners answer a BLOCKED envelope.
    """
    import importlib.util
    import json

    def envelope(runner_id: str, status: str, reason: str) -> None:
        try:
            stream = sys.stdout
            if stream is None:
                return
            stream.write(
                json.dumps(
                    {
                        "test_id": "",
                        "runner_id": runner_id,
                        "status": status,
                        "reason": reason,
                        "assertions": 0,
                        "evidence": [],
                    }
                )
                + "\n"
            )
        except Exception:
            return

    ref = (runner_ref or "").strip()
    if not ref:
        envelope("", "BLOCKED", "missing_runner")
        return 0
    here = os.path.dirname(os.path.abspath(__file__))
    src_root = os.path.dirname(here)
    if src_root and src_root not in sys.path:
        sys.path.insert(0, src_root)
    stem = os.path.basename(ref)
    if stem.endswith(".py"):
        stem = stem[:-3]
    if not stem.isidentifier():
        envelope(ref, "BLOCKED", "unknown_runner")
        return 0
    module = None
    if ref.endswith(".py") and os.path.isfile(ref):
        try:
            spec = importlib.util.spec_from_file_location(
                "agent_si.qa_catalog.runners." + stem, ref)
            if spec is not None and spec.loader is not None:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
        except Exception:
            module = None
    else:
        try:
            module = importlib.import_module(
                "agent_si.qa_catalog.runners." + stem)
        except Exception:
            module = None
    if module is None:
        envelope(stem, "BLOCKED", "unknown_runner")
        return 0
    entry = getattr(module, "main", None)
    if not callable(entry):
        envelope(stem, "BLOCKED", "unknown_runner")
        return 0
    try:
        return int(entry())
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        return 0


def main(argv: list[str] | None = None) -> int:
    """Run the sidecar: serve on loopback, open the native window."""
    qa_ref = _qa_runner_ref(argv)
    if qa_ref is not None:
        return run_qa_runner(qa_ref)
    _ = argv
    if _reattach_running():
        return 0
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
    port_path: str | None = None
    data_root = _sidecar_data_dir()
    if data_root:
        port_path = _port_file_path(data_root)
        _write_port_file(port_path, port, str(token))
    stop = threading.Event()

    def request_stop(*_args: object) -> None:
        server.should_exit = True
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(OSError, ValueError):
            signal.signal(sig, request_stop)

    try:
        import webview

        width, height = resolve_window_size(data_root)
        window = webview.create_window(
            "Agent SI", url, width=width, height=height)
        _ = window
        webview.start(private_mode=False, storage_path=webview_storage_dir())
        if data_root is not None:
            try:
                end_w = int(getattr(window, "width", width))
                end_h = int(getattr(window, "height", height))
            except (TypeError, ValueError):
                end_w, end_h = width, height
            if end_w > 0 and end_h > 0:
                _write_window_size(
                    _window_size_file_path(data_root), end_w, end_h)
    except Exception as exc:
        _log(
            "agent-si-sidecar: webview unavailable "
            f"({exc}); opened in default browser, serving until stopped"
        )
        _open_in_browser(url)
        _note_webview_missing(url)
        stop.wait()
    finally:
        server.should_exit = True
        if port_path is not None:
            _clear_port_file(port_path)
    thread.join(timeout=10)
    return 0


if __name__ == "__main__":
    sys.exit(main())
