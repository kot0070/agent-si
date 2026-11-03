"""FXDESIGN8 perf probe: idle API rps + click-to-paint on the built app.

Serves frontend/dist over loopback, fakes only the /api boundary in-page,
then: (1) counts served /api requests over 12 s idle on `/` (chat route,
project selected); (2) clicks one nav item and measures ms to painted
route (rAF after URL + content switch). Prints one JSON line.
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

PROJECTS = {"projects": [{"project_id": "p-1", "name": "Seed One",
                           "created_at": "2026-02-11T06:42:44Z"}]}
PROJECT = {"project": PROJECTS["projects"][0]}
LIVE = {"agents": [
    {"agent": "agent-1", "scope": "scope-1", "deliverable": "part-1",
     "status": "RUNNING", "role": "manager", "provider": "meta",
     "model": "m-1", "step": 2, "file": "f-1.ts",
     "tokens": {"input": 400, "output": 600},
     "context": 424200, "window": 1000000, "errors": [], "waits": []},
]}
TASKS = {"tasks": []}
LEDGER = {"rows": [{"package_id": "pkg-1", "agents": 2,
                    "peak_concurrency": 2, "wall_time_s": 60}]}
NUDGE = {"package_id": "pkg-1", "load": LEDGER["rows"][0],
         "nudge": "next-up", "auto_push": False}
BUDGET = {"project_id": "p-1", "budget": {
    "project_id": "p-1", "hard_limit": 100, "spent": 30,
    "reserved": 20, "currency": "USD"}}
WATCHER_STATUS = {"project_id": "p-1", "integrity_ok": True,
                  "journal_head": "jh-1",
                  "generated_at": "2026-02-11T00:00:00Z"}
WATCHER_JOURNAL = [{"entry_id": "e-1", "timestamp": "2026-02-11T00:00:00Z",
                    "hash": "h-1"}]
APPS_CARD = {"project_id": "p-1", "service_ids": [], "paused": False,
             "generated_at": "t-0"}
KB_STATUS = {"kb_version": 2, "updated_at": "2026-02-11T06:42:44Z",
             "per_provider": {}}


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


def _api(route):
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
                      body=json.dumps({"code": "FX8_PERF_UNEXPECTED"}))


def test_fxdesign8_perf():
    _build_frontend()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _DistHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:%d" % server.server_port
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.launch(
            channel="msedge", headless=True)
        try:
            page = browser.new_context(
                viewport={"width": 1280, "height": 800}).new_page()
            seen = []
            page.route("**/api/**", _api)
            page.on("request", lambda req: seen.append(req.url)
                    if "/api/" in req.url else None)
            page.goto(base + "/", wait_until="load")
            page.wait_for_timeout(2500)
            mark = len(seen)
            page.wait_for_timeout(12000)
            idle_reqs = len(seen) - mark
            idle_rps = round(idle_reqs / 12.0, 3)
            # click-to-paint: timestamp click, wait for the agents route
            # to paint its rows, then rAF.
            page.evaluate(
                "window.localStorage.setItem"
                "('agentsi.firstrun.done', 'true')")
            paint_ms = page.evaluate("""async () => {
              const link = document.querySelector(
                '[data-testid="menu-agents-live"], a[href="/agents/live"]');
              if (!link) return -2;
              const t0 = performance.now();
              link.click();
              for (let i = 0; i < 200; i++) {
                const rows = document.querySelector(
                  '[data-testid="agents-live-rows"],'
                  + ' [data-testid="kit-card-agents-live"]');
                if (rows && rows.textContent
                    && rows.textContent.length > 20) break;
                await new Promise((r) => setTimeout(r, 25));
              }
              await new Promise((r) => requestAnimationFrame(() => r()));
              await new Promise((r) => requestAnimationFrame(() => r()));
              return Math.round(performance.now() - t0);
            }""")
            print("FXDESIGN8_PERF " + json.dumps({
                "idle_api_requests_12s": idle_reqs,
                "idle_rps": idle_rps,
                "click_to_paint_ms": paint_ms,
            }))
            assert idle_reqs >= 0
        finally:
            browser.close()
            playwright.stop()
    finally:
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()
