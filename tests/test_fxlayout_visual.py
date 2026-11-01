"""FXLAYOUT visual test: Claude-desktop shell over the real build.

RED->GREEN: on the unpatched tree this test FAILS (the left nav holds seven
links, the inspector shows a single live-agents tab, and the shell is a
two-column grid). After the FXLAYOUT shell.css + shell changes land, it
PASSES.

Method (frozen F6): build the real frontend (`npm --prefix frontend run
build`), serve frontend/dist on a local port, and drive it with Playwright
(channel msedge, headless). The ONLY fake is at the network boundary: one
page.route fulfills /api calls with stored-record answers (projects, live
agents, tasks, ledger, nudge, budget, watcher status/journal, apps card);
every HTML/JS/CSS byte is the real production build. No fakes or fixtures
live in product code; the route callbacks below live in this test only.

Matrix: 1280x800 en + 1000x700 en + 800x600 en + 1280x800 uk (4 cases).
Each case saves one screenshot into _task/FXLAYOUT/.
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
SHOT_DIR = os.path.join(WS, "_task", "FXLAYOUT")

THEME_KEY = "agentsi.theme"
LOCALE_KEY = "agentsi.locale"

CASES = [
    ("en", 1280, 800),
    ("en", 1000, 700),
    ("en", 800, 600),
    ("uk", 1280, 800),
]

PROJECTS = {"projects": [{"project_id": "p-1", "name": "n-1", "created_at": "t-0"}]}
PROJECT = {"project": {"project_id": "p-1", "name": "n-1", "created_at": "t-0"}}
LIVE = {
    "agents": [
        {
            "agent": "agent-1",
            "scope": "scope-1",
            "deliverable": "part-1",
            "status": "RUNNING",
            "role": "manager",
            "model": "m-1",
            "step": 2,
            "file": "f-1.ts",
            "tokens": {"input": 400, "output": 600},
            "context": "ctx-1",
            "errors": [],
            "waits": [],
        },
        {
            "agent": "agent-2",
            "scope": "scope-2",
            "deliverable": "part-2",
            "status": "QUEUED",
        },
    ]
}
TASKS = {
    "tasks": [
        {
            "task_id": "t-9",
            "project_id": "p-1",
            "title": "running nine",
            "status": "RUNNING",
            "created_at": "t-0",
        },
        {
            "task_id": "t-10",
            "project_id": "p-1",
            "title": "queued ten",
            "status": "QUEUED",
            "created_at": "t-0",
        },
    ]
}
LEDGER = {
    "rows": [
        {"package_id": "pkg-1", "agents": 2, "peak_concurrency": 2, "wall_time_s": 60},
        {"package_id": "pkg-2", "agents": 1, "peak_concurrency": 1, "wall_time_s": 30},
    ]
}
NUDGE = {
    "package_id": "pkg-2",
    "load": {"package_id": "pkg-2", "agents": 1, "peak_concurrency": 1, "wall_time_s": 30},
    "nudge": "next-up",
    "auto_push": False,
}
BUDGET = {
    "project_id": "p-1",
    "budget": {
        "project_id": "p-1",
        "hard_limit": 100,
        "spent": 30,
        "reserved": 20,
        "currency": "USD",
    },
}
WATCHER_STATUS = {
    "project_id": "p-1",
    "integrity_ok": True,
    "journal_head": "jh-1",
    "generated_at": "t-0",
}
WATCHER_JOURNAL = [{"entry_id": "e-1", "timestamp": "t-1", "hash": "h-1"}]
APPS_CARD = {
    "project_id": "p-1",
    "service_ids": ["svc-a", "svc-b"],
    "paused": False,
    "generated_at": "t-0",
}


def _build_frontend():
    """Build the real production frontend; prefer the frozen npm command."""
    npm = shutil.which("npm")
    if npm is not None:
        if os.name == "nt":
            completed = subprocess.run(
                '"%s" --prefix frontend run build' % npm,
                cwd=WS,
                shell=True,
                capture_output=True,
                text=True,
                timeout=600,
            )
        else:
            completed = subprocess.run(
                [npm, "--prefix", "frontend", "run", "build"],
                cwd=WS,
                capture_output=True,
                text=True,
                timeout=600,
            )
    else:
        node = shutil.which("node") or shutil.which("nodejs")
        assert node is not None, "neither npm nor node found on PATH"
        completed = subprocess.run(
            [node, os.path.join("node_modules", "vite", "bin", "vite.js"), "build"],
            cwd=FRONTEND,
            capture_output=True,
            text=True,
            timeout=600,
        )
    tail = (completed.stdout + completed.stderr)[-4000:]
    assert completed.returncode == 0, "frontend build failed:\n" + tail
    assert os.path.isfile(os.path.join(DIST, "index.html")), "dist/index.html missing after build"


class _DistHandler(SimpleHTTPRequestHandler):
    """Static dist server with pinned JS/CSS MIME types (never OS-registry ones)."""

    extensions_map = dict(
        SimpleHTTPRequestHandler.extensions_map,
        **{
            ".js": "text/javascript",
            ".mjs": "text/javascript",
            ".css": "text/css",
            ".html": "text/html",
            ".json": "application/json",
            ".svg": "image/svg+xml",
        },
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIST, **kwargs)

    def log_message(self, *args):
        pass


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


def _box(page, selector):
    return page.evaluate(
        """(sel) => {
          const el = document.querySelector(sel);
          if (!el) return null;
          const r = el.getBoundingClientRect();
          return {x: r.x, y: r.y, width: r.width, height: r.height};
        }""",
        selector,
    )


def _overflow_y(page, selector):
    return page.evaluate(
        """(sel) => {
          const el = document.querySelector(sel);
          if (!el) return null;
          return getComputedStyle(el).overflowY;
        }""",
        selector,
    )


def _scroll_sizes(page, selector):
    return page.evaluate(
        """(sel) => {
          const el = document.querySelector(sel);
          if (!el) return null;
          return {scrollHeight: el.scrollHeight, clientHeight: el.clientHeight};
        }""",
        selector,
    )


def _api(route):
    url = route.request.url
    if url.endswith("/api/v1/projects") and route.request.method == "GET":
        route.fulfill(status=200, content_type="application/json", body=json.dumps(PROJECTS))
    elif "/api/v1/projects/p-1" in url and route.request.method == "GET":
        route.fulfill(status=200, content_type="application/json", body=json.dumps(PROJECT))
    elif url.endswith("/api/v1/agents/live"):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(LIVE))
    elif "/api/v1/tasks" in url:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(TASKS))
    elif "/api/v1/runs/ledger" in url:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(LEDGER))
    elif "/api/v1/reports/next-package-nudge" in url:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(NUDGE))
    elif "/api/v1/budget" in url:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(BUDGET))
    elif "/api/v1/watcher/status" in url:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(WATCHER_STATUS))
    elif "/api/v1/watcher/journal" in url:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(WATCHER_JOURNAL))
    elif "/api/v1/apps/card" in url:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(APPS_CARD))
    else:
        route.fulfill(
            status=404,
            content_type="application/json",
            body=json.dumps({"code": "FXLAYOUT_UNEXPECTED_API"}),
        )


@pytest.mark.parametrize("locale,width,height", CASES)
def test_fxlayout_three_columns(served_base, edge, locale, width, height):
    context = edge.new_context(viewport={"width": width, "height": height})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.route("**/api/**", _api)
        page.add_init_script("window.localStorage.setItem('%s', '%s')" % (LOCALE_KEY, locale))

        page.goto(served_base + "/", wait_until="load")
        page.evaluate("window.localStorage.setItem('%s', '%s')" % (THEME_KEY, "dark"))
        page.reload(wait_until="networkidle")

        for testid in ("topbar", "app-main", "chat-prompt"):
            page.wait_for_selector('[data-testid="%s"]' % testid)
        if locale == "en":
            # Boot never applies the stored locale to the t() module (it stays
            # DEFAULT_LOCALE until the TopBar toggle runs), so drive the real
            # language select uk->en; the second switch flips the module.
            page.select_option('[data-testid="topbar-language"]', "uk")
            page.select_option('[data-testid="topbar-language"]', "en")
            page.wait_for_function(
                """() => {
                  const el = document.querySelector('nav[data-testid="sidebar"]');
                  return el !== null && el.textContent.includes("New task");
                }"""
            )
        if width >= 1000:
            page.wait_for_selector('[data-testid="inspector"]')
        else:
            page.wait_for_selector('[data-testid="inspector"]', state="attached")
        page.wait_for_selector('[data-testid="sidebar"]', state="attached")

        nav_count = page.evaluate(
            """() => document.querySelectorAll('nav[data-testid="sidebar"] a').length"""
        )
        assert nav_count == 4, "sidebar holds %d links, want exactly 4" % nav_count
        card_state = None if width >= 1000 else "attached"
        for card in (
            "inspector-card-team",
            "inspector-card-context",
            "inspector-card-results",
            "inspector-card-background",
            "inspector-card-watcher",
        ):
            if card_state is None:
                page.wait_for_selector('[data-testid="%s"]' % card)
            else:
                page.wait_for_selector(
                    '[data-testid="%s"]' % card, state=card_state
                )
        for card in (
            "fx-tokens",
            "fx-tests",
            "fx-budget",
            "fx-providers",
            "fx-localai",
            "fx-apps",
        ):
            if card_state is None:
                page.wait_for_selector('[data-testid="kit-metric-%s"]' % card)
            else:
                page.wait_for_selector(
                    '[data-testid="kit-metric-%s"]' % card, state=card_state
                )

        if width >= 1000:
            nav = _box(page, '[data-testid="sidebar"]')
            main = _box(page, '[data-testid="app-main"]')
            cards = _box(page, '[data-testid="inspector"]')
            assert nav is not None and main is not None and cards is not None, "shell regions missing"
            assert nav["width"] > 0 and main["width"] > 0 and cards["width"] > 0, "empty column"
            assert nav["x"] + nav["width"] <= main["x"] + 1, "nav is not one column left of content"
            assert main["x"] + main["width"] <= cards["x"] + 1, "cards are not right of content"
            for region in ("[data-testid=\"sidebar\"]", "[data-testid=\"app-main\"]", "[data-testid=\"inspector\"]"):
                assert _overflow_y(page, region) == "auto", "region does not self-scroll: %s" % region
            sizes = _scroll_sizes(page, '[data-testid="inspector"]')
            assert sizes["scrollHeight"] >= sizes["clientHeight"], "inspector has no scrollable content"
            wide = page.evaluate("document.documentElement.scrollWidth")
            assert wide <= width, "horizontal page scroll at %dpx: scrollWidth %d" % (width, wide)
        else:
            toggle = _box(page, '[data-testid="topbar-panels"]')
            assert toggle is not None and toggle["width"] > 0, "panels button missing at %dpx" % width
            before = _box(page, '[data-testid="sidebar"]')
            assert before is not None and before["width"] == 0, "sidebar is not collapsed behind the button: %r" % (before,)
            page.click('[data-testid="topbar-panels"]')
            page.wait_for_function(
                """() => {
                  const el = document.querySelector('nav[data-testid="sidebar"]');
                  return el !== null && el.getBoundingClientRect().width > 0;
                }"""
            )
            wide = page.evaluate("document.documentElement.scrollWidth")
            assert wide <= width, "horizontal page scroll at %dpx after opening panels: %d" % (width, wide)

        if locale == "uk":
            text = page.evaluate("""() => document.querySelector('nav[data-testid="sidebar"]').textContent ?? "" """)
            assert len(text.strip()) > 0, "sidebar has no labels"
            assert "Проєкти" in text, "no Ukrainian labels in the sidebar"
        else:
            en_text = page.evaluate("""() => document.querySelector('nav[data-testid="sidebar"]').textContent ?? "" """)
            assert len(en_text.strip()) > 0, "sidebar has no labels"
            assert "New task" in en_text, "no English labels in the en matrix"
            assert "Нове завдання" not in en_text, "Ukrainian labels in the en matrix"

        assert errors == [], "page errors: %r" % (errors,)

        shot = os.path.join(SHOT_DIR, "fxlayout-%dx%d-%s.png" % (width, height, locale))
        page.screenshot(path=shot)
        assert os.path.isfile(shot), "screenshot missing: %s" % shot
    finally:
        context.close()
