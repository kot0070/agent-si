# K07NEXT split B: 7 frontend rows over the REAL HttpApiClient.
# One test per row: R-319, R-334, R-342, R-348, R-362, M-P3-92, M-P4-139.
# Each test proves two things: (a) the K07-owned screen is wired to the
# REAL HttpApiClient (real client + provider imports, no FakeApiClient,
# no data injected into a mounted component) with its network stand-in
# quoting the backend route schema; (b) the quoted schema is the live
# served answer, fetched over REAL HTTP from create_app() + mount.
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_WS = os.path.abspath(os.path.join(_HERE, ".."))
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

TEST_TOKEN = "k07next-solo-token-b"
BASE_SETTINGS = {
    "testing": True,
    "ui_session_token": TEST_TOKEN,
    "secret_store": "memory",
}

FRONT = os.path.join(_WS, "frontend", "src", "k07next")
SUITES = os.path.join(FRONT, "__tests__")

LICENCE_LINE = "Copyright (c) 2026 Ivan Soprun"


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture(scope="module")
def served():
    from agent_si.backend.app import create_app
    from agent_si.http import k07next as boundary

    app = create_app(dict(BASE_SETTINGS))
    boundary.mount(app)
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=0,
                            log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if getattr(server, "started", False):
            break
        time.sleep(0.05)
    assert getattr(server, "started", False), "uvicorn never started"
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=15)


def _get(base, path):
    request = urllib.request.Request(base + path, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return (response.status,
                    json.loads(response.read().decode("utf-8")))
    except urllib.error.HTTPError as err:
        return (err.code, json.loads(err.read().decode("utf-8")))


def _check_wiring(screen_file, suite_file, route_path, quote_token):
    screen = _read(os.path.join(FRONT, screen_file))
    suite = _read(os.path.join(SUITES, suite_file))
    assert "k07nextApi" in screen
    assert "../../api/client" in suite
    assert "ApiClientProvider" in suite
    assert "fakeApiClient" not in screen.lower()
    assert "fakeApiClient" not in suite.lower()
    assert route_path in suite
    assert quote_token in suite


def test_row_r319_newcomer_guide_served(served):
    _check_wiring("NewcomerGuide.tsx", "k07next-r319.test.tsx",
                 "/api/v1/app/newcomer-guide", "newcomer_start_guide")
    status, payload = _get(served, "/api/v1/app/newcomer-guide")
    assert status == 200, payload
    assert payload == {
        "row": "R-319",
        "guide": "newcomer_start_guide",
        "steps": [
            {"id": "connectProvider"},
            {"id": "oneClickTeam"},
            {"id": "projectFolder"},
            {"id": "firstTask"},
        ],
    }


def test_row_r334_locale_switch_served(served):
    _check_wiring("LocaleSwitch.tsx", "k07next-r334.test.tsx",
                 "/api/v1/app/locale-switch", "agentsi.locale")
    status, payload = _get(served, "/api/v1/app/locale-switch")
    assert status == 200, payload
    assert payload == {
        "row": "R-334",
        "locales": ["en", "uk"],
        "visible_switch": {"top_bar": True, "settings": True},
        "persisted_via": "agentsi.locale",
    }


def test_row_r342_licence_served(served):
    _check_wiring("LicenceNotice.tsx", "k07next-r342.test.tsx",
                 "/api/v1/app/licence", LICENCE_LINE)
    status, payload = _get(served, "/api/v1/app/licence")
    assert status == 200, payload
    assert payload == {
        "row": "R-342",
        "licence_line": LICENCE_LINE,
        "mit_ref": "about.licence.mitText",
        "third_party_title_ref": "about.thirdParty.title",
    }


def test_row_r348_runs_explained_served(served):
    _check_wiring("RunsExplained.tsx", "k07next-r348.test.tsx",
                 "/api/v1/app/runs-explained", "codeTests")
    status, payload = _get(served, "/api/v1/app/runs-explained")
    assert status == 200, payload
    assert payload == {
        "row": "R-348",
        "sections": [
            {"key": "runs"},
            {"key": "codeTests"},
            {"key": "localTests"},
        ],
    }


def test_row_r362_locale_coverage_served(served):
    _check_wiring("LocaleCoverage.tsx", "k07next-r362.test.tsx",
                 "/api/v1/app/locale-coverage", "en_leaves")
    status, payload = _get(served, "/api/v1/app/locale-coverage")
    assert status == 200, payload
    assert payload["row"] == "R-362", payload
    assert payload["en_leaves"] == payload["uk_leaves"], payload
    assert payload["parity"] is True, payload
    assert payload["missing_in_uk"] == [], payload
    assert payload["missing_in_en"] == [], payload
    assert payload["en_leaves"] >= 590, payload


def test_row_mp392_telemetry_themes_served(served):
    _check_wiring("TelemetryThemes.tsx", "k07next-mp392.test.tsx",
                 "/api/v1/app/telemetry-themes", "visual-standard")
    status, payload = _get(served, "/api/v1/app/telemetry-themes")
    assert status == 200, payload
    assert payload == {
        "row": "M-P3-92",
        "themes": ["dark", "light"],
        "charts": "accessible",
        "standard": "visual-standard",
        "tokens_key": "telemetry.tokens",
        "cost_key": "telemetry.cost",
    }


def test_row_mp4139_copyright_served(served):
    _check_wiring("CopyrightLine.tsx", "k07next-mp4139.test.tsx",
                 "/api/v1/app/copyright", "installer-metadata")
    status, payload = _get(served, "/api/v1/app/copyright")
    assert status == 200, payload
    assert payload == {
        "row": "M-P4-139",
        "line_en": LICENCE_LINE,
        "line_uk": LICENCE_LINE,
        "shown_in": ["About", "installer-metadata"],
    }
