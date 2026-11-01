"""FXFAKES1 served routes: accept/evidence/demo answer from real probes or refuse.

Routes (app.py READ-ONLY; owned product code is agent_si.k10_accept and
agent_si.k10_start):
- GET /api/v1/release/accept answers {"ok": bool, probes...}; ok is true
  only when ALL required probes pass; each probe names what was seen;
  not probed reports available false with a reason.
- GET /api/v1/release/start/evidence lists only real files of a real run
  from the named data-root store; none means ok false, an empty list and
  a reason.
- POST /api/v1/release/start/demo runs the real acceptance-probe drive it
  names or refuses with a clear code; it never writes green without work.

RED on the unpatched tree (recorded green answered, generated evidence
written, green demo stored), GREEN after. Loopback TEST data only.
"""
import inspect
import json
import os
import re
import shutil
import sys

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import fastapi.testclient  # noqa: E402

from agent_si import (  # noqa: E402
    k10_accept,
    k10_start,
)
from agent_si.backend.app import create_app  # noqa: E402


def _client_with_fresh_root(tmp_path, monkeypatch, token):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AGENT_SI_DATA_DIR", str(data_dir))
    app = create_app(
        {"ui_session_token": token, "secret_store": "memory",
         "testing": True}
    )
    assert app.state.data_dir == os.path.abspath(str(data_dir))
    return fastapi.testclient.TestClient(app), data_dir


def _path_without_docker():
    """Return PATH with the dir carrying docker removed (if any)."""
    path = os.environ.get("PATH", "")
    exe = shutil.which("docker")
    if exe is None:
        return path
    gone = os.path.dirname(os.path.abspath(exe))
    parts = [part for part in path.split(os.pathsep)
             if os.path.abspath(part) != gone]
    return os.pathsep.join(parts)


def test_fxfakes1_accept_docker_absent_from_path(tmp_path, monkeypatch):
    """R-1: docker absent from PATH => docker available false, ok false."""
    monkeypatch.setenv("PATH", _path_without_docker())
    assert shutil.which("docker") is None
    client, _data_dir = _client_with_fresh_root(
        tmp_path, monkeypatch, "fxfakes1-accept-token")
    resp = client.get("/api/v1/release/accept")
    assert resp.status_code == 200, resp.text
    assert "recorded:" not in resp.text, resp.text
    body = resp.json()
    assert body["docker"]["available"] is False, body
    assert body["docker"]["detail"], body
    assert body["ok"] is False, body
    for key in ("docker", "services", "powershell"):
        assert key in body, body
        detail = body[key]["detail"] if key != "services" else None
        if detail is not None:
            assert detail, body
    assert isinstance(body["services"], list) and body["services"], body
    for service in body["services"]:
        assert service["name"] and service["detail"], body
        assert service["available"] in (True, False), body
    by_name = {service["name"]: service for service in body["services"]}
    assert by_name["frontend"]["available"] is False, body
    assert "not probed" in by_name["frontend"]["detail"], body
    expect_ok = bool(
        body["docker"]["available"]
        and body["powershell"]["available"]
        and all(service["available"] for service in body["services"]))
    assert body["ok"] is expect_ok, body


def test_fxfakes1_evidence_fresh_root_empty(tmp_path, monkeypatch):
    """R-2: fresh data root => evidence ok false, empty list, reason."""
    client, _data_dir = _client_with_fresh_root(
        tmp_path, monkeypatch, "fxfakes1-evidence-token")
    resp = client.get("/api/v1/release/start/evidence")
    assert resp.status_code == 200, resp.text
    assert "recorded:" not in resp.text, resp.text
    body = resp.json()
    assert body["ok"] is False, body
    assert body["screenshots"] == [], body
    assert body.get("reason"), body


def test_fxfakes1_evidence_lists_only_real_files(tmp_path, monkeypatch):
    """R-2: a real file placed by a real run is listed; nothing invented."""
    client, data_dir = _client_with_fresh_root(
        tmp_path, monkeypatch, "fxfakes1-evidence-real-token")
    store = data_dir / "release-evidence"
    store.mkdir(parents=True, exist_ok=True)
    (store / "shot-01-start.png").write_bytes(b"\x89PNG-fxfakes1-real")
    (store / "evidence.json").write_text('{"run": "real"}\n',
                                         encoding="utf-8")
    resp = client.get("/api/v1/release/start/evidence")
    assert resp.status_code == 200, resp.text
    assert "recorded:" not in resp.text, resp.text
    body = resp.json()
    assert body["ok"] is True, body
    assert body["screenshots"] == ["evidence.json", "shot-01-start.png"], body


def test_fxfakes1_demo_writes_no_green_without_work(tmp_path, monkeypatch):
    """R-3: demo refuses with a code and writes no green file without work."""
    monkeypatch.setenv("PATH", _path_without_docker())
    client, data_dir = _client_with_fresh_root(
        tmp_path, monkeypatch, "fxfakes1-demo-token")
    resp = client.post("/api/v1/release/start/demo")
    assert resp.status_code == 200, resp.text
    assert "recorded:" not in resp.text, resp.text
    body = resp.json()
    assert body["project"] == "demo", body
    demo_path = data_dir / "demo.json"
    if body.get("status") == "green":
        assert body.get("drive"), body
        assert demo_path.is_file(), body
        stored = json.loads(demo_path.read_text(encoding="utf-8"))
        assert stored == {"project": "demo", "status": "green",
                          "drive": "acceptance-probes-live-pass"}, stored
    else:
        assert body["status"] == "refused", body
        assert body.get("code") == "drive-refused", body
        assert not demo_path.is_file(), body


def test_fxfakes1_no_recorded_marker_in_release_routes():
    """R-4: regex search for `recorded:` over src hits none of these routes.

    The src-wide search (mode:regex) plus the served-response checks in
    the tests above prove `recorded:` is gone from the three routes.
    """
    route_fns = (
        k10_accept.get_acceptance_status,
        k10_start.record_release_evidence,
        k10_start.drive_demo_to_green,
    )
    ranges = {}
    for fn in route_fns:
        path = os.path.abspath(inspect.getsourcefile(fn))
        lines, start = inspect.getsourcelines(fn)
        ranges.setdefault(path, []).append((start, start + len(lines)))
    hits = []
    for root, _dirs, files in os.walk(_SRC):
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.abspath(os.path.join(root, name))
            with open(path, encoding="utf-8") as handle:
                for lineno, line in enumerate(
                        handle.read().splitlines(), 1):
                    if re.search(r"recorded:", line):
                        for start, end in ranges.get(path, []):
                            if start <= lineno < end:
                                hits.append(
                                    f"{path}:{lineno}:{line.strip()}")
    assert hits == [], hits
