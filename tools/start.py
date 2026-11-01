"""K10ST1 lane A start path: clean boot of the served entries.

Runs the served app (backend app plus frontend index) from a copy of the
checkout. Either checks the whole path without opening anything (--smoke)
or serves both entries over loopback (--serve). Steps run in order:
checkout, configure from an environment example, offline install from
lockfiles, launch. Records sha256 hashes plus smoke output. The data dir
comes from --data-dir or AGENT_SI_DATA_DIR; loopback TEST data only.
"""

import argparse
import contextlib
import hashlib
import importlib
import json
import os
import socket
import sys
import tempfile
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ENV_NAME = "AGENT_SI_DATA_DIR"
ENTRY_SCRIPT = "/src/app/main.tsx"
START_META = '<meta name="agent-si-start" content="tools/start.py" />'
BACKEND_MODULE = "agent_si.backend.app"
TESTCLIENT_MODULE = "fastapi.testclient"
SMOKE_TOKEN = "k10st1-smoke-token"
SERVE_TOKEN = "k10st1-serve-token"
STEP_ORDER = ("checkout", "configure", "lockfiles", "launch")
ENTRY_FILES = {
    "backend_app": "src/agent_si/backend/app.py",
    "frontend_index": "frontend/index.html",
    "frontend_entry": "frontend/src/app/main.tsx",
    "frontend_lockfile": "frontend/package-lock.json",
    "pyproject": "pyproject.toml",
}
LOCKFILES = ("frontend/package-lock.json", "pyproject.toml")


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def ensure_importable(root: Path) -> list:
    saved = list(sys.path)
    for entry in (str(root), str(root / "src")):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    return saved


def parse_env_example(path: Path) -> dict:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_entries(root: Path) -> dict:
    return {
        name: ("ok" if (root / rel).is_file() else "missing")
        for name, rel in ENTRY_FILES.items()
    }


def resolve_data_dir(root: Path, argv_value: str | None) -> str:
    raw = argv_value or os.environ.get(ENV_NAME) or str(root / "DATA")
    data_dir = os.path.abspath(raw)
    os.environ.setdefault(ENV_NAME, data_dir)
    return data_dir


def apply_example(example: str | None) -> dict:
    if not example:
        return {"example": None, "applied": {},
                "note": "no env example; defaults used"}
    path = Path(example)
    if not path.is_file():
        return {"example": str(path), "applied": {},
                "note": "env example not found; defaults used"}
    parsed = parse_env_example(path)
    for key, value in parsed.items():
        os.environ.setdefault(key, value)
    applied = {key: os.environ.get(key) for key in parsed}
    return {"example": str(path), "applied": applied,
            "note": "existing env kept; example fills defaults only"}


def check_lockfiles(root: Path) -> dict:
    files = list(LOCKFILES)
    missing = [rel for rel in files if not (root / rel).is_file()]
    if missing:
        return {"files": files, "offline": True, "status": "error",
                "missing": missing}
    return {"files": files, "offline": True, "status": "ok",
            "note": "offline; nothing installed"}


def read_frontend_index(root: Path) -> str:
    return (root / "frontend" / "index.html").read_text(encoding="utf-8")


def smoke_backend(root: Path) -> dict:
    saved = ensure_importable(root)
    try:
        module = importlib.import_module(BACKEND_MODULE)
        client_cls = importlib.import_module(TESTCLIENT_MODULE).TestClient
        app = module.create_app({"ui_session_token": SMOKE_TOKEN})
        resp = client_cls(app).get("/openapi.json")
        if resp.status_code == 200:
            return {"status": "pass", "openapi_status": 200,
                    "entry_ok": True, "meta_ok": True, "error": None}
        return {"status": "fail",
                "openapi_status": resp.status_code,
                "entry_ok": False, "meta_ok": False,
                "error": f"openapi status {resp.status_code}"}
    except Exception as exc:
        return {"status": "fail", "openapi_status": None,
                "entry_ok": False, "meta_ok": False,
                "error": f"{type(exc).__name__}: {exc}"}
    finally:
        sys.path[:] = saved


def fresh_data_dir(data_dir: str) -> dict:
    found = []
    if os.path.isdir(data_dir):
        for dirpath, _dirnames, filenames in os.walk(data_dir):
            for name in filenames:
                full = os.path.join(dirpath, name)
                found.append(
                    os.path.relpath(full, data_dir).replace(os.sep, "/"))
    found.sort()
    return {"seeded": False, "files": found}


def build_record(root: Path, tag: str, data_dir: str, record_path: str | None,
                 step_status: dict, entries: dict, configure: dict,
                 lockfiles: dict, smoke: dict) -> dict:
    return {
        "tool": "tools/start.py",
        "tag": tag,
        "root": str(root),
        "data_dir": data_dir,
        "record_path": record_path,
        "steps": list(STEP_ORDER),
        "step_status": dict(step_status),
        "entries": dict(entries),
        "configure": dict(configure),
        "lockfiles": {k: v for k, v in lockfiles.items() if k != "status"},
        "sha256": {
            "tools/start.py": sha256_file(root / "tools" / "start.py"),
            "frontend/index.html":
                sha256_file(root / "frontend" / "index.html"),
        },
        "smoke": dict(smoke),
        "fresh": fresh_data_dir(data_dir),
    }


def write_record(path: str, record: dict) -> None:
    target = Path(path)
    if target.parent and not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def run_launch_checks(root: Path) -> tuple:
    entries = check_entries(root)
    step_status = {
        "checkout": ("ok" if all(v == "ok" for v in entries.values())
                     else "error"),
        "configure": "ok",
        "lockfiles": "ok",
        "launch": "pending",
    }
    return entries, step_status


def cmd_smoke(args: argparse.Namespace) -> int:
    root = repo_root()
    entries, step_status = run_launch_checks(root)
    configure = apply_example(args.env_example)
    lockfiles = check_lockfiles(root)
    if lockfiles.get("status") != "ok":
        step_status["lockfiles"] = "error"
    data_dir = resolve_data_dir(root, args.data_dir)
    smoke = {"status": "fail", "openapi_status": None,
             "entry_ok": False, "meta_ok": False,
             "error": "launch skipped: earlier step failed"}
    if (step_status["checkout"] == "ok"
            and step_status["lockfiles"] == "ok"):
        smoke = smoke_backend(root)
        try:
            html = read_frontend_index(root)
            entry_ok = (ENTRY_SCRIPT in html
                        and (root / "frontend" / "src" / "app"
                             / "main.tsx").is_file())
            meta_ok = START_META in html
        except OSError as exc:
            smoke = {"status": "fail", "openapi_status": None,
                     "entry_ok": False, "meta_ok": False,
                     "error": f"{type(exc).__name__}: {exc}"}
        else:
            smoke["entry_ok"] = entry_ok
            smoke["meta_ok"] = meta_ok
            if smoke["status"] == "pass" and not (entry_ok and meta_ok):
                smoke["status"] = "fail"
                smoke["error"] = "frontend entry wiring missing"
    step_status["launch"] = "ok" if smoke["status"] == "pass" else "error"
    record = build_record(root, args.tag, data_dir, args.record,
                          step_status, entries, configure, lockfiles, smoke)
    if args.record:
        write_record(args.record, record)
        print(f"recorded {args.record}")
    else:
        print(json.dumps(record, indent=2, sort_keys=True))
    if all(v == "ok" for v in step_status.values()):
        return 0
    return 1


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        return None


def pick_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def serve_entries(root: Path, port: int, frontend_port: int):
    uvicorn = importlib.import_module("uvicorn")
    saved = ensure_importable(root)
    try:
        module = importlib.import_module(BACKEND_MODULE)
        app = module.create_app({"ui_session_token": SERVE_TOKEN})
    finally:
        sys.path[:] = saved
    config = uvicorn.Config(app, host="127.0.0.1", port=port,
                            log_level="error", access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20.0
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=20)
        return None
    # Root requests gain a trailing slash, which os.path.isdir rejects
    # on a Win32 extended-path prefix, so serve the plain form here.
    frontend_dir = str(root / "frontend")
    if frontend_dir.startswith("\\\\?\\UNC\\"):
        frontend_dir = "\\\\" + frontend_dir[8:]
    elif frontend_dir.startswith("\\\\?\\"):
        frontend_dir = frontend_dir[4:]
    handler = partial(_QuietHandler, directory=frontend_dir)
    httpd = ThreadingHTTPServer(("127.0.0.1", frontend_port), handler)
    frontend_thread = threading.Thread(target=httpd.serve_forever,
                                       daemon=True)
    frontend_thread.start()
    return server, thread, httpd, frontend_thread


def cmd_serve(args: argparse.Namespace) -> int:
    root = repo_root()
    entries, step_status = run_launch_checks(root)
    configure = apply_example(args.env_example)
    lockfiles = check_lockfiles(root)
    if lockfiles.get("status") != "ok":
        step_status["lockfiles"] = "error"
    data_dir = resolve_data_dir(root, args.data_dir)
    if step_status["checkout"] != "ok" or step_status["lockfiles"] != "ok":
        print("start path not ready", file=sys.stderr)
        return 1
    port = args.port or pick_port()
    frontend_port = args.frontend_port or pick_port()
    try:
        running = serve_entries(root, port, frontend_port)
    except Exception as exc:
        print(f"serve failed: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 1
    if running is None:
        print("backend did not start", file=sys.stderr)
        return 1
    server, thread, httpd, frontend_thread = running
    step_status["launch"] = "ok"
    if args.record:
        record = build_record(
            root, args.tag, data_dir, args.record, step_status, entries,
            configure, lockfiles,
            {"status": "not-run", "openapi_status": None,
             "entry_ok": None, "meta_ok": None, "error": None})
        write_record(args.record, record)
    print(f"ready backend=http://127.0.0.1:{port} "
          f"frontend=http://127.0.0.1:{httpd.server_port} "
          f"index={root / 'frontend' / 'index.html'}", flush=True)
    with contextlib.suppress(OSError):
        sys.stdin.buffer.read()
    server.should_exit = True
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=20)
    frontend_thread.join(timeout=20)
    return 0


def k10d_command_index() -> dict:
    """K10D row -129: setup plus demo plus fixture command index.

    Returns the checkout-root commands also recorded in
    docs/reports/K10D.md. Read-only; no process is started here.
    """
    return {
        "setup": [
            "python tools/start.py --smoke --tag k10d",
            "python -m pytest tests/test_k10d_served.py -q "
            "-p no:cacheprovider",
        ],
        "demo": [
            "python tools/start.py --smoke --tag k10d-demo "
            "--data-dir DATA",
            "python tools/start.py --serve --tag k10d-demo "
            "--data-dir DATA",
        ],
        "fixture": [
            "python -m pytest tests/test_k10d_served.py -q "
            "-p no:cacheprovider -k fixture",
            "python -m pytest tests/test_k10d_served.py -q "
            "-p no:cacheprovider",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="start.py",
        description="K10ST1 lane A start path: checkout, configure, "
                    "lockfiles, launch for the served backend plus "
                    "frontend index.")
    parser.add_argument("--smoke", action="store_true",
                        help="run the startup steps plus the smoke "
                             "check and exit")
    parser.add_argument("--serve", action="store_true",
                        help="run the startup steps then serve both "
                             "entries over loopback until stdin closes")
    parser.add_argument("--data-dir", default=None,
                        help="app data dir (else AGENT_SI_DATA_DIR, "
                             "else DATA under the checkout)")
    parser.add_argument("--tag", default="",
                        help="label stored in the record")
    parser.add_argument("--record", default=None,
                        help="write the JSON record to this path")
    parser.add_argument("--env-example", default=None,
                        help="environment example file with defaults")
    parser.add_argument("--port", type=int, default=0,
                        help="backend loopback port (0 picks one)")
    parser.add_argument("--frontend-port", type=int, default=0,
                        help="frontend loopback port (0 picks one)")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.smoke == args.serve:
        parser.error("choose one of --smoke or --serve")
    if args.serve:
        return cmd_serve(args)
    return cmd_smoke(args)


if __name__ == "__main__":
    sys.exit(main())
