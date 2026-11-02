"""FXPROJ J1+J2 click proof: real dev build served, API faked at the
network boundary only (stateful: projects start empty, creation persists).

Fresh profile: first message -> project in left list + Projects page ->
Settings -> return by each of the 3 paths (left row, Projects row Open,
top picker) -> same history. One assistant message with the run log
lines, no Accept/Edit/Reject card. Shots to the audit shot
directory (HISTSHOTS).
"""
import json
import os
import re
import shutil
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(WS, "frontend")
DIST = os.path.join(FRONTEND, "dist")
REPO = os.path.dirname(os.path.dirname(WS))
SHOT_DIR = os.path.join(REPO, "DIRECTOR", "AUDIT", "HISTSHOTS")

LOG_LINES = ["log line 1", "log line 2"]
CHAT_URL = re.compile(r".*/projects/p-7/chat")


def _build_frontend():
    npm = shutil.which("npm")
    assert npm is not None
    completed = subprocess.run(
        '"%s" --prefix frontend run build' % npm, cwd=WS, shell=True,
        capture_output=True, text=True, timeout=900)
    tail = (completed.stdout + completed.stderr)[-2000:]
    assert completed.returncode == 0, "build failed:\n" + tail
    assert os.path.isfile(os.path.join(DIST, "index.html"))


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


class _FakeBackend:
    """Stateful FAKE seam: the served app starts with no projects; the
    first chat message creates p-7, later reads show it."""

    def __init__(self):
        self.projects = []
        self.turns = []

    def handle(self, route):
        req = route.request
        url = req.url
        method = req.method
        if url.endswith("/api/v1/projects") and method == "GET":
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"projects": self.projects}))
        elif url.endswith("/api/v1/projects") and method == "POST":
            project = {"project_id": "p-7", "name": "hello run",
                       "created_at": "2026-02-11T06:42:44Z"}
            self.projects = [project]
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"project": project}))
        elif "/api/v1/projects/p-7" in url and method == "GET":
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"project": self.projects[0]}))
        elif "/api/v1/tasks" in url and method == "GET":
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"tasks": []}))
        elif "/api/v1/tasks" in url and method == "POST":
            task = {"task_id": "t-7", "project_id": "p-7",
                    "title": "hello run", "status": "QUEUED",
                    "created_at": "2026-02-11T06:42:44Z"}
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"task": task}))
        elif "/api/v1/chat/history" in url and method == "GET":
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"turns": self.turns}))
        elif "/api/v1/chat/history" in url and method == "POST":
            posted = json.loads(req.post_data or "{}")
            self.turns.append({
                "project_id": posted.get("project_id", "p-7"),
                "user_text": posted.get("user_text", ""),
                "assistant_text": posted.get("assistant_text", ""),
                "time": "2026-02-11T06:42:44Z"})
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({}))
        elif url.endswith("/api/v1/chat/stream") and method == "POST":
            lines = ['data: {"type":"start","stream_id":"srv-7"}']
            for text in LOG_LINES:
                lines.append(
                    'data: {"type":"delta","stream_id":"srv-7",'
                    '"text":%s}' % json.dumps(text + "\n"))
            lines.append('data: {"type":"done","stream_id":"srv-7",'
                         '"executed":true}')
            route.fulfill(status=200, content_type="text/event-stream",
                          body="\n".join(lines) + "\n")
        elif "/api/v1/chat/models" in url:
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"models": []}))
        elif url.endswith("/api/v1/agents/live"):
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"agents": []}))
        elif "/api/v1/runs/ledger" in url:
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"rows": []}))
        elif "/api/v1/reports/next-package-nudge" in url:
            route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({
                    "package_id": "pkg-9",
                    "load": {"package_id": "pkg-9", "agents": 0,
                             "peak_concurrency": 0, "wall_time_s": 0},
                    "nudge": "pkg-9", "auto_push": False}))
        elif "/api/v1/budget" in url:
            route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({
                    "project_id": "p-7",
                    "budget": {"project_id": "p-7", "hard_limit": 100,
                               "spent": 0, "reserved": 0,
                               "currency": "USD"}}))
        elif "/api/v1/providers" in url:
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"providers": []}))
        else:
            route.fulfill(status=404, content_type="application/json",
                          body=json.dumps({"code": "FXPROJ_UNEXPECTED_API"}))


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


def _shot(page, name):
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, "fxproj-%s.png" % name)
    page.screenshot(path=path)
    assert os.path.isfile(path), path


def _history_text(page):
    return page.get_by_test_id("chat-assistant-message").inner_text()


def test_fxproj_return_to_chat(served_base, edge):
    backend = _FakeBackend()
    context = edge.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.route("**/api/**", backend.handle)
    try:
        # Fresh profile: wizard done, zero served projects.
        page.add_init_script(
            "window.localStorage.setItem('agentsi.firstrun.done','true');"
            "window.localStorage.setItem('agentsi.locale','en');")
        page.goto(served_base + "/", wait_until="load")
        expect(page.get_by_test_id("chat-area")).to_be_visible(timeout=15000)
        expect(page.get_by_test_id("chat-prompt")).to_be_visible()
        _shot(page, "01-start-empty")

        # J1: first message creates the project after every list mounted.
        page.get_by_test_id("chat-prompt").fill("hello run")
        page.get_by_test_id("chat-send").click()
        expect(page.get_by_test_id("sidebar-project-p-7")).to_be_visible(
            timeout=15000)
        expect(page.get_by_test_id("chat-assistant-message")).to_be_visible(
            timeout=15000)
        for line in LOG_LINES:
            expect(page.get_by_test_id(
                "chat-assistant-message")).to_contain_text(line)
        # Seeded run: one message, no Accept/Edit/Reject card.
        assert page.get_by_test_id("chat-assistant-message").count() == 1
        assert page.get_by_test_id("approval-card").count() == 0
        assert page.get_by_test_id("approval-accept").count() == 0
        assert page.get_by_test_id("approval-edit").count() == 0
        assert page.get_by_test_id("approval-reject").count() == 0
        first_history = _history_text(page)
        _shot(page, "02-chat-after-first-message")

        # Projects page shows the row, not the empty state.
        page.get_by_test_id("menu-projects").click()
        expect(page.get_by_test_id("project-row-p-7")).to_be_visible(
            timeout=15000)
        _shot(page, "03-projects")

        # Projects row Open lands on that project's chat, same history.
        page.get_by_test_id("project-open-p-7").click()
        expect(page).to_have_url(CHAT_URL, timeout=15000)
        expect(page.get_by_test_id(
            "chat-assistant-message")).to_have_text(first_history,
                                                    timeout=15000)
        _shot(page, "04-chat-tab")

        # Other tabs open and return to the same chat. The tab bar lives
        # on the project views: enter through Results, open Overview,
        # then take the Chat tab (the first one) back.
        page.get_by_test_id("menu-results").click()
        expect(page.get_by_test_id("kit-card-project-reports")).to_be_visible(
            timeout=15000)
        _shot(page, "05-reports")
        page.get_by_test_id("project-menu-overview").click()
        expect(page.get_by_test_id("kit-card-project-overview")).to_be_visible(
            timeout=15000)
        page.get_by_test_id("project-chat-tab").click()
        expect(page).to_have_url(CHAT_URL, timeout=15000)
        expect(page.get_by_test_id(
            "chat-assistant-message")).to_have_text(first_history,
                                                    timeout=15000)
        _shot(page, "06-tabs-return")

        # Settings, then return by path 1: the left row.
        page.get_by_test_id("menu-settings").click()
        expect(page.get_by_test_id("settings-tabs")).to_be_visible(
            timeout=15000)
        page.get_by_test_id("sidebar-project-p-7").click()
        expect(page).to_have_url(CHAT_URL, timeout=15000)
        expect(page.get_by_test_id(
            "chat-assistant-message")).to_have_text(first_history,
                                                    timeout=15000)
        _shot(page, "07-return-left-row")

        # Return by path 2: Projects row Open.
        page.get_by_test_id("menu-projects").click()
        page.get_by_test_id("project-open-p-7").click()
        expect(page).to_have_url(CHAT_URL, timeout=15000)
        expect(page.get_by_test_id(
            "chat-assistant-message")).to_have_text(first_history,
                                                    timeout=15000)
        _shot(page, "08-return-projects-open")

        # Return by path 3: the top picker.
        page.get_by_test_id("menu-settings").click()
        expect(page.get_by_test_id("settings-tabs")).to_be_visible(
            timeout=15000)
        page.get_by_test_id("topbar-project").select_option("p-7")
        expect(page.get_by_test_id(
            "chat-assistant-message")).to_have_text(first_history,
                                                    timeout=15000)
        _shot(page, "09-return-top-picker")

        # New task with a project selected opens its chat.
        page.get_by_test_id("menu-new-task").click()
        expect(page.get_by_test_id("chat-assistant-message")).to_have_text(
            first_history, timeout=15000)
        _shot(page, "10-new-task-opens-chat")

        assert errors == [], errors
    finally:
        page.close()
        context.close()
