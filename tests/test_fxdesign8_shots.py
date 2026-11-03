"""FXDESIGN8 shots: chat empty, chat after a run, agents, watcher at
1280x800 + 1024x700, dark-en + light-en + dark-uk. Saves to the audit
shot directory (D8SHOTS). Also logs centre-column widths per shot.
"""
import json
import os
import shutil
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(WS, "frontend")
DIST = os.path.join(FRONTEND, "dist")
REPO = os.path.dirname(os.path.dirname(WS))
SHOT_DIR = os.path.join(REPO, "DIRECTOR", "AUDIT", "D8SHOTS")

THEME_KEY = "agentsi.theme"
LOCALE_KEY = "agentsi.locale"

VARIANTS = [
    ("en", "dark", "en-dark"),
    ("en", "light", "en-light"),
    ("uk", "dark", "uk-dark"),
]
VIEWPORTS = [(1280, 800), (1024, 700)]

PROJECTS = {"projects": [
    {"project_id": "p-1", "name": "Seed One",
     "created_at": "2026-02-11T06:42:44Z"},
]}
PROJECT = {"project": PROJECTS["projects"][0]}
LIVE = {"agents": [
    {"agent": "agent-1", "scope": "scope-1", "deliverable": "part-1",
     "status": "RETURNED", "role": "manager", "provider": "meta",
     "model": "meta-llama/long-model-name-70b", "step": 4,
     "file": "hello.txt", "last_action": "wrote hello",
     "tokens": {"input": 4000, "output": 912},
     "context": 4912, "window": 1000000, "errors": [], "waits": []},
    {"agent": "agent-2", "scope": "scope-2", "deliverable": "part-2",
     "status": "QUEUED", "role": "worker"},
]}
EMPTY_LIVE = {"agents": []}
TASKS = {"tasks": [
    {"task_id": "t-9", "project_id": "p-1", "title": "running nine",
     "status": "RUNNING", "created_at": "2026-02-11T06:42:44Z"},
]}
LEDGER = {"rows": [
    {"package_id": "pkg-1", "agents": 2, "peak_concurrency": 2,
     "wall_time_s": 60},
], "runs": [
    {"run_id": "run-7", "project": "p-1", "task": "say hi",
     "start": "2026-02-11T06:40:00Z", "end": "2026-02-11T06:42:44Z",
     "success": True, "stopped": False,
     "summary": "greeted the owner with hello",
     "parts": [{"part_id": "part-1", "verdict": "accepted",
                "attempts": 1, "reason": ""}],
     "verdicts": {"part-1": "accepted"},
     "tokens": 4912, "cost": "UNKNOWN", "files": ["hello.txt"]},
]}
EMPTY_LEDGER = {"rows": []}
TELEMETRY = {"metric_records": 3, "telemetry_events": 9,
             "totals": {"tokens_total": 4912, "cloud_calls": 9},
             "tasks": ["say hi"],
             "models": [{"model": "m-1", "calls": 2, "tokens": 4912,
                         "cost": "UNAVAILABLE"}],
             "providers": [{"provider": "meta", "calls": 2, "tokens": 4912,
                            "cost": "UNAVAILABLE"}],
             "source": "telemetry_store", "unavailable": []}
NUDGE = {"package_id": "pkg-1", "load": LEDGER["rows"][0],
         "nudge": "next-up", "auto_push": False}
BUDGET = {"project_id": "p-1", "budget": {
    "project_id": "p-1", "hard_limit": 100, "spent": 30,
    "reserved": 20, "currency": "USD"}}
WATCHER_STATUS = {"project_id": "p-1", "integrity_ok": True,
                  "journal_head": "evt-0042",
                  "generated_at": "2026-02-11T00:00:00Z"}
WATCHER_JOURNAL = [{"entry_id": "evt-0042",
                    "timestamp": "2026-02-11T06:42:44Z", "hash": "h-42"}]
APPS_CARD = {"project_id": "p-1", "service_ids": [], "paused": False,
             "generated_at": "t-0"}
KB_STATUS = {"kb_version": 2, "updated_at": "2026-02-11T06:42:44Z",
             "per_provider": {"meta": 3}}


def _build_frontend():
    from tests._distbuild import build_once
    build_once(WS)


class _DistHandler(SimpleHTTPRequestHandler):
    extensions_map = dict(
        SimpleHTTPRequestHandler.extensions_map,
        **{".js": "text/javascript", ".css": "text/css",
           ".html": "text/html", ".json": "application/json"})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIST, **kwargs)

    def log_message(self, *args):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        _, ext = os.path.splitext(path)
        if ext == "" and path != "/":
            self.path = "/index.html"
        super().do_GET()


def _api_live(route):
    url = route.request.url
    if url.endswith("/api/v1/projects") and route.request.method == "GET":
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(PROJECTS))
    elif "/api/v1/projects/p-1" in url and route.request.method == "GET":
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(PROJECT))
    elif url.endswith("/api/v1/agents/live"):
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(LIVE))
    elif "/api/v1/tasks" in url:
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(TASKS))
    elif "/api/v1/runs/ledger" in url:
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(LEDGER))
    elif "/api/v1/reports/next-package-nudge" in url:
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(NUDGE))
    elif "/api/v1/budget" in url:
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(BUDGET))
    elif "/api/v1/watcher/status" in url:
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(WATCHER_STATUS))
    elif "/api/v1/watcher/journal" in url:
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(WATCHER_JOURNAL))
    elif "/api/v1/apps/card" in url:
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(APPS_CARD))
    elif "/api/v1/analytics/telemetry" in url:
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(TELEMETRY))
    elif "/api/v1/kb/status" in url:
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(KB_STATUS))
    elif "/api/v1/kb/refresh/proposal" in url:
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"kb_id": None, "stale": False,
                                       "proposals": []}))
    else:
        route.fulfill(status=404, content_type="application/json",
                      body=json.dumps({"code": "FX8_UNEXPECTED_API"}))


def _api_empty(route):
    url = route.request.url
    if url.endswith("/api/v1/agents/live"):
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(EMPTY_LIVE))
    elif "/api/v1/runs/ledger" in url:
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(EMPTY_LEDGER))
    else:
        _api_live(route)


@pytest.fixture(scope="session")
def served_base():
    _build_frontend()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _DistHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:%d" % server.server_port
    finally:
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()


@pytest.fixture(scope="session")
def edge():
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
    except Exception:
        playwright.stop()
        raise
    try:
        yield browser
    finally:
        browser.close()
        playwright.stop()


SHOTS = [
    ("chat-empty", "/", "empty"),
    ("chat-live", "/", "live"),
    ("agents", "/agents/live", "live"),
    ("watcher", "/watcher", "live"),
]


@pytest.mark.parametrize("locale,theme,tag", VARIANTS)
@pytest.mark.parametrize("width,height", VIEWPORTS)
def test_fxdesign8_shots(served_base, edge, locale, theme, tag, width,
                         height):
    os.makedirs(SHOT_DIR, exist_ok=True)
    context = edge.new_context(viewport={"width": width, "height": height})
    try:
        for name, route, mode in SHOTS:
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            handler = _api_live if mode == "live" else _api_empty
            page.route("**/api/**", handler)
            page.add_init_script(
                "window.localStorage.setItem('%s', '%s');"
                "window.localStorage.setItem('agentsi.firstrun.done', 'true')"
                % (LOCALE_KEY, locale))
            page.goto(served_base + route, wait_until="load")
            page.evaluate(
                "window.localStorage.setItem('%s', '%s')" % (THEME_KEY, theme))
            page.reload(wait_until="networkidle")
            page.wait_for_timeout(800)
            widths = page.evaluate("""() => {
              const q = (s) => document.querySelector(s);
              const w = (el) => el ? Math.round(
                el.getBoundingClientRect().width) : -1;
              return {
                main: w(q('[data-testid="app-main"]')),
                messages: w(q('[data-testid="chat-messages"]')),
                composer: w(q('[data-testid="chat-composer"]')),
                openLinkH: (() => {
                  const a = document.querySelector(
                    '[data-testid^="result-open-"]');
                  return a ? Math.round(
                    a.getBoundingClientRect().height) : -1;
                })(),
              };
            }""")
            print("FXDESIGN8_SHOT %s %dx%d %s widths=%s errors=%s"
                  % (name, width, height, tag, json.dumps(widths),
                     json.dumps(errors[:3])))
            shot = os.path.join(
                SHOT_DIR, "fx8-%s-%dx%d-%s.png" % (name, width, height, tag))
            page.screenshot(path=shot)
            assert os.path.isfile(shot), shot
            page.close()
    finally:
        context.close()
