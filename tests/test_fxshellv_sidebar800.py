"""FXSHELLV focused test: sidebar opens behind the panels button at 800x600.

History: the first version of this test pinned the FXSHELLV order
(collapse narrowed to 799px) so the three-column layout persisted at
800px with the nav always visible. The advisor reversed that order:
FXLAYOUT design is the contract (shell.css `@media (max-width: 800px)`),
so at 800x600 the panels button is visible, the sidebar starts
collapsed behind it, and clicking the button opens it. This test now
proves that contract: toggle visible, sidebar width 0, click, sidebar
visible with the token link look, and a nav click navigates.

Method (same as frozen F6 in test_fxshell1_visual.py): build the real
production frontend, serve frontend/dist on a local port, drive it with
Playwright (channel msedge, headless). The ONLY fake is at the network
boundary (one page.route fulfills /api calls); every HTML/JS/CSS byte is
the real production build.
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

THEME_KEY = "agentsi.theme"

CASES = [
    ("dark", 800, 600),
    ("light", 800, 600),
]


def _hex_to_rgb(value):
    text = value.strip()
    assert text.startswith("#") and len(text) == 7, "expected #rrggbb, got %r" % (value,)
    return "rgb(%d, %d, %d)" % (int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16))


def _build_frontend():
    from tests._distbuild import build_once
    build_once(WS)


class _DistHandler(SimpleHTTPRequestHandler):
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


@pytest.mark.parametrize("theme,width,height", CASES)
def test_sidebar_visible_at_800x600(served_base, edge, theme, width, height):
    context = edge.new_context(viewport={"width": width, "height": height})
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        def _api(route):
            if route.request.url.endswith("/api/v1/projects") and route.request.method == "GET":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"projects": []}),
                )
            else:
                route.fulfill(
                    status=404,
                    content_type="application/json",
                    body=json.dumps({"code": "FXSHELLV_UNEXPECTED_API"}),
                )

        page.route("**/api/**", _api)

        page.goto(served_base + "/", wait_until="load")
        page.evaluate("window.localStorage.setItem('%s', '%s')" % (THEME_KEY, theme))
        page.reload(wait_until="networkidle")

        assert page.evaluate("document.documentElement.dataset.theme") == theme
        # FXLAYOUT design is the contract: at 800x600 the nav and cards
        # collapse behind the top-bar panels button (shell.css
        # max-width: 800px). The sidebar starts hidden and opens on click.
        page.wait_for_selector('[data-testid="topbar"]')
        page.wait_for_selector('[data-testid="app-main"]')
        page.wait_for_selector('[data-testid="sidebar"]', state="attached")
        page.wait_for_selector('[data-testid="menu-new-task"]', state="attached")

        toggle = _box(page, '[data-testid="topbar-panels"]')
        assert toggle is not None and toggle["width"] > 0, (
            "panels button missing at %dpx" % width
        )
        before = _box(page, '[data-testid="sidebar"]')
        assert before is not None and before["width"] == 0, (
            "sidebar is not collapsed behind the button: %r" % (before,)
        )
        page.click('[data-testid="topbar-panels"]')
        page.wait_for_function(
            """() => {
              const el = document.querySelector('nav[data-testid="sidebar"]');
              return el !== null && el.getBoundingClientRect().width > 0;
            }"""
        )

        nav = _box(page, '[data-testid="sidebar"]')
        assert nav is not None and nav["width"] > 0 and nav["height"] > 0, (
            "sidebar has no size after opening: %r" % (nav,)
        )

        scroll_wide = page.evaluate("document.documentElement.scrollWidth")
        assert scroll_wide <= width, (
            "horizontal page scroll at %dpx after opening panels: %d" % (width, scroll_wide)
        )

        link_look = page.evaluate(
            """() => {
              const a = document.querySelector('nav[data-testid="sidebar"] a');
              const cs = getComputedStyle(a);
              const root = getComputedStyle(document.documentElement);
              return {
                deco: cs.textDecorationLine,
                color: cs.color,
                accent: root.getPropertyValue('--agent-si-accent').trim(),
              };
            }"""
        )
        assert link_look["deco"] == "none", "nav link is underlined: %r" % (link_look,)
        assert link_look["color"] == _hex_to_rgb(link_look["accent"]), (
            "nav link is not the token colour: %r" % (link_look,)
        )

        # A nav click works: the projects entry navigates and selects.
        page.click('[data-testid="menu-projects"]')
        page.wait_for_url("**/projects")
        page.wait_for_function(
            """() => {
              const el = document.querySelector('[data-testid="menu-projects"]');
              return el !== null && el.getAttribute('aria-current') === 'page';
            }"""
        )

        assert errors == [], "page errors: %r" % (errors,)
    finally:
        context.close()
