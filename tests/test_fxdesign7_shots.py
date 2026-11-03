"""Interface screenshots: real dev build served, API faked at the network
boundary only. Walks first-run, chat empty/live, projects, overview tabs,
reports, settings, providers + connect modal, agents, watcher at
1280x800 dark-en + light-en + dark-uk. Saves to the local audit shots folder.
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
SHOT_DIR = os.path.join(REPO, "DIRECTOR", "AUDIT", "D6SHOTS")

THEME_KEY = "agentsi.theme"
LOCALE_KEY = "agentsi.locale"

VARIANTS = [
    ("en", "dark", "en-dark"),
    ("en", "light", "en-light"),
    ("uk", "dark", "uk-dark"),
]

PROJECTS = {"projects": [
    {"project_id": "p-1", "name": "Seed One",
     "created_at": "2026-02-11T06:42:44Z"},
    {"project_id": "p-1", "name": "Seed One Duplicate",
     "created_at": "2026-02-11T06:42:44Z"},
    {"project_id": "p-2", "name": "Second",
     "created_at": "2026-01-05T00:00:00Z"},
]}
PROJECT = {"project": PROJECTS["projects"][0]}
LIVE = {"agents": [
    {"agent": "agent-1", "scope": "scope-1", "deliverable": "part-1",
     "status": "RUNNING", "role": "manager", "provider": "meta",
     "model": "m-1", "step": 2, "file": "f-1.ts",
     "tokens": {"input": 400, "output": 600},
     "context": 424200, "window": 1000000, "errors": [], "waits": []},
    {"agent": "agent-2", "scope": "scope-2", "deliverable": "part-2",
     "status": "QUEUED", "role": "worker"},
]}
EMPTY_LIVE = {"agents": []}
TASKS = {"tasks": [
    {"task_id": "t-9", "project_id": "p-1", "title": "running nine",
     "status": "RUNNING", "created_at": "2026-02-11T06:42:44Z"},
    {"task_id": "t-10", "project_id": "p-1", "title": "queued ten",
     "status": "QUEUED", "created_at": "2026-02-11T08:00:00Z"},
]}
LEDGER = {"rows": [
    {"package_id": "pkg-1", "agents": 2, "peak_concurrency": 2,
     "wall_time_s": 60},
    {"package_id": "pkg-2", "agents": 1, "peak_concurrency": 1,
     "wall_time_s": 30},
]}
NUDGE = {"package_id": "pkg-2", "load": LEDGER["rows"][1],
         "nudge": "next-up", "auto_push": False}
BUDGET = {"project_id": "p-1", "budget": {
    "project_id": "p-1", "hard_limit": 100, "spent": 30,
    "reserved": 20, "currency": "USD"}}
WATCHER_STATUS = {"project_id": "p-1", "integrity_ok": True,
                  "journal_head": "jh-1", "generated_at": "2026-02-11T00:00:00Z"}
WATCHER_JOURNAL = [{"entry_id": "e-1", "timestamp": "2026-02-11T00:00:00Z",
                    "hash": "h-1"}]
APPS_CARD = {"project_id": "p-1", "service_ids": ["svc-a", "svc-b"],
             "paused": False, "generated_at": "t-0"}
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
        # SPA fallback: every non-file route serves the app shell; the
        # page.route API fake answers all /api calls, so the server only
        # ever serves the built HTML/JS/CSS.
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
    elif "/api/v1/kb/status" in url:
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(KB_STATUS))
    elif "/api/v1/kb/refresh/proposal" in url:
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"kb_id": None, "stale": False,
                                       "proposals": []}))
    else:
        route.fulfill(status=404, content_type="application/json",
                      body=json.dumps({"code": "FX7_UNEXPECTED_API"}))


def _api_empty(route):
    url = route.request.url
    if url.endswith("/api/v1/agents/live"):
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(EMPTY_LIVE))
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
    ("firstrun", "/firstrun", "live", None),
    ("chat-empty", "/", "empty", None),
    ("chat-live", "/", "live", None),
    ("projects", "/projects", "live", None),
    ("project-tabs", "/projects/p-1/overview", "live", None),
    ("reports", "/projects/p-1/reports", "live", None),
    ("settings", "/settings", "live", None),
    ("providers", "/settings/models", "live", None),
    ("providers-connect", "/settings/models", "live", "connect"),
    ("agents", "/agents/live", "live", None),
    ("watcher", "/watcher", "live", None),
]


@pytest.mark.parametrize("locale,theme,tag", VARIANTS)
def test_fxdesign7_shots(served_base, edge, locale, theme, tag):
    context = edge.new_context(viewport={"width": 1280, "height": 800})
    try:
        for name, route, mode, action in SHOTS:
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
            if locale == "en":
                try:
                    page.select_option(
                        '[data-testid="topbar-language"]', "uk", timeout=3000)
                    page.select_option(
                        '[data-testid="topbar-language"]', "en", timeout=3000)
                except Exception:
                    pass
            page.wait_for_timeout(800)
            if action == "connect":
                try:
                    btn = page.locator(
                        '[data-testid="provider-card"] button').first
                    btn.click(timeout=5000)
                    page.wait_for_timeout(600)
                except Exception:
                    pass
            shot = os.path.join(
                SHOT_DIR, "fx7-%s-%s.png" % (name, tag))
            page.screenshot(path=shot)
            assert os.path.isfile(shot), shot
            page.close()
    finally:
        context.close()
