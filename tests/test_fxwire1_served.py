# FXWIRE1 served proof: the five k07next boundary modules mounted by
# create_app answer over REAL HTTP (TestClient), each route reaching its
# real implementation, with no duplicate method+path. RED shape: before
# the FXWIRE1 mount block the /api/v1/app/* boundary paths 404.
import os
import sys

from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402

TEST_TOKEN = "fxwire1-served-token"
ACTOR = "fxwire1-actor"


def _settings(**overrides):
    base = {"ui_session_token": TEST_TOKEN, "testing": True,
            "secret_store": "memory"}
    base.update(overrides)
    return base


def _client(tmp_path=None, monkeypatch=None):
    if tmp_path is not None and monkeypatch is not None:
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))
        monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    app = create_app(dict(_settings()))
    return TestClient(app), app


def _authed():
    return {"x-actor": ACTOR, "x-ui-session-token": TEST_TOKEN}


OPEN_GETS = [
    # (path, expected row marker)
    ("/api/v1/app/adopted-decision", "163"),
    ("/api/v1/app/drive-comfort", "162"),
    ("/api/v1/app/design-signoff", "168"),
    ("/api/v1/app/display-labels", "242"),
    ("/api/v1/app/card-parity", "248"),
    ("/api/v1/app/edit-guard", "R-316"),
    ("/api/v1/app/agents-panel", "R-317"),
    ("/api/v1/app/inspector-panel-state", "R-318"),
    ("/api/v1/app/newcomer-guide", "R-319"),
    ("/api/v1/app/locale-switch", "R-334"),
    ("/api/v1/app/licence", "R-342"),
    ("/api/v1/app/runs-explained", "R-348"),
    ("/api/v1/app/locale-coverage", "R-362"),
    ("/api/v1/app/telemetry-themes", "M-P3-92"),
    ("/api/v1/app/copyright", "M-P4-139"),
    ("/api/v1/app/context-card", "M-P4-159"),
    ("/api/v1/app/channel-lane", "M-D-D5"),
    ("/api/v1/app/app-id", "HD-APP-ID"),
    ("/api/v1/app/brand", "M-R-BRAND"),
    ("/api/v1/app/retry-policy", "B0B-BP09-27"),
    ("/api/v1/app/local-config-gate", "B0B-UNCOVERED_BP06-67"),
    ("/api/v1/app/planner-router", "B0B-UNCOVERED_ARCH-541"),
    ("/api/v1/app/shell-menus", "B0B-UNCOVERED_ARCH-679"),
    ("/api/v1/app/policy-lifecycle", "B0B-BP09-30"),
    ("/api/v1/app/gate-verdicts", "B0B-UNCOVERED_ARCH-563"),
    ("/api/v1/app/ledger-register", "B0B-UNCOVERED_ARCH-683"),
    ("/api/v1/app/step-limits", "B0B-UNCOVERED_ARCH-686"),
    ("/api/v1/app/project-defaults", "B0B-UNCOVERED_ARCH-716"),
    ("/api/v1/app/control-plane", "B0B-UNCOVERED_ARCH-718"),
    ("/api/v1/app/team-card", "B0B-UNCOVERED_ARCH-720"),
    ("/api/v1/app/projects", None),
    ("/api/v1/app/page-shell", "LIVE0B-04"),
    ("/api/v1/app/step-turn?advance=1", "MH-5"),
    ("/api/v1/app/turn-triple", "MH-6"),
    ("/api/v1/app/bench/tab?model_id=m&level=Quick", "R-341-UI"),
    ("/api/v1/app/local-ai/view?project_key=proj-a", "111-UI"),
    ("/api/v1/app/local-ai/settings-view?project_key=proj-a",
     "B0B-UNCOVERED_ARCH-526"),
    ("/api/v1/app/provider-health/transitions",
     "B0B-UNCOVERED_MVP_ACCEPT-199"),
]

GUARDED_POSTS = [
    "/api/v1/app/session-write",
    "/api/v1/app/projects",
    "/api/v1/app/chat-task",
    "/api/v1/app/local-ai/decision-update",
]


def test_fxwire1_open_reads_reach_real_impl(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    for path, row in OPEN_GETS:
        resp = client.get(path)
        assert resp.status_code == 200, (path, resp.text)
        payload = resp.json()
        if row is not None:
            assert payload.get("row") == row, (path, payload)
        if path == "/api/v1/app/agents-panel":
            assert payload["mapping"] == {
                "who": "agent", "where": "scope",
                "result": "deliverable", "state": "status",
            }, payload
        if path == "/api/v1/app/projects":
            assert payload["projects"] == [], payload
        if path == "/api/v1/app/locale-coverage":
            assert payload["parity"] in (True, False), payload
            assert isinstance(payload["en_leaves"], int), payload
        if path == "/api/v1/app/bench/tab?model_id=m&level=Quick":
            assert payload["estimate"]["model_id"] == "m", payload
            assert payload["scan"] == [], payload


def test_fxwire1_guards_refuse_before_writes(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    for path in GUARDED_POSTS:
        no_actor = client.post(path, json={})
        assert no_actor.status_code == 401, (path, no_actor.text)
        bad_token = client.post(
            path, json={},
            headers={"x-actor": ACTOR,
                     "x-ui-session-token": "wrong-token"})
        assert bad_token.status_code == 403, (path, bad_token.text)


def test_fxwire1_guarded_writes_reach_real_impl(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/app/session-write", json={},
                       headers=_authed())
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"row": "LIVE0-08", "token_ok": True,
                           "actor": ACTOR}

    created = client.post(
        "/api/v1/app/projects",
        json={"name": "fxwire1", "folder_ref": "fxwire1-dir"},
        headers=_authed())
    assert created.status_code == 200, created.text
    project = created.json()["project"]
    assert project["name"] == "fxwire1", created.text
    listed = client.get("/api/v1/app/projects")
    assert listed.status_code == 200, listed.text
    assert any(row["project_id"] == project["project_id"]
               for row in listed.json()["projects"]), listed.text

    task = client.post(
        "/api/v1/app/chat-task",
        json={"prompt_ref": "fxwire1-prompt"},
        headers=_authed())
    assert task.status_code == 200, task.text
    assert task.json()["status"] == "started", task.text
    assert task.json()["prompt_ref"] == "fxwire1-prompt", task.text

    decision = client.post(
        "/api/v1/app/local-ai/decision-update",
        json={"project_key": "fxwire1-new",
              "patch": {"local_only_mode": True},
              "statement": "fxwire1 records its decision",
              "reason": "lane proof",
              "authority": "coder-1-sable"},
        headers=_authed())
    assert decision.status_code == 200, decision.text
    assert decision.json()["row"] == "111-UI", decision.text
    assert decision.json()["config"]["local_only_mode"] is True, \
        decision.text
    view = client.get("/api/v1/app/local-ai/view",
                      params={"project_key": "fxwire1-new"})
    assert view.status_code == 200, view.text
    assert view.json()["config"]["local_only_mode"] is True, view.text


def test_fxwire1_step_turn_advance_reaches_real_impl(tmp_path,
                                                     monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    resp = client.get("/api/v1/app/step-turn", params={"advance": 2})
    assert resp.status_code == 200, resp.text
    assert resp.json()["turn"] == 2, resp.text
    assert "model input" in resp.json()["model_input"], resp.text


def test_fxwire1_no_duplicate_method_path(tmp_path, monkeypatch):
    _, app = _client(tmp_path, monkeypatch)
    seen = {}
    for route in app.routes:
        methods = sorted(getattr(route, "methods", None) or [])
        path = getattr(route, "path", None)
        if not methods or not path:
            continue
        for method in methods:
            key = (method, path)
            seen[key] = seen.get(key, 0) + 1
    mounted = [item for item in list(OPEN_GETS) + [(p, None) for p in
               GUARDED_POSTS] if item[0].split("?")[0].startswith(
        "/api/v1/app/")]
    for path, _ in mounted:
        base = path.split("?")[0]
        method = "POST" if base in GUARDED_POSTS else "GET"
        assert seen.get((method, base), 0) == 1, (method, base)
    app_dupes = sorted(
        key for key, count in seen.items()
        if count > 1 and key[1].startswith("/api/v1/app/"))
    assert app_dupes == [], app_dupes
