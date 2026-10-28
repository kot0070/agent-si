"""LIVEWIRE1 wire fixtures (BE): generate all 5 JSON from REAL routes.

Builds the real seam app (create_app), drives REAL routes (project
create, budget GET, chat stream/cancel, report GET) and writes the five
pinned wire files under frontend/src/api/wire/:

- budget-state.json        GET /api/v1/budget 200 {project_id, budget}
- chat-open-request.json   POST /api/v1/chat/stream body {project, message}
- chat-stream-events.json  SSE byte sequence, one start + deltas + one done
- error-body.json          {code, message} samples from real error paths
- report-body.json         GET /api/v1/reports/next-package-nudge 200

Volatile ids/timestamps are canonicalized to fixed sentinels (documented
below); stable contract values are asserted on the LIVE payloads before
canonicalization. The provider boundary alone uses the sanctioned K04
MockProviderAdapter (no network, no keys, no token in URL). No secret,
key or token text may appear in any fixture.
"""

import json
import os
import re
import sys

import pytest
from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import agents_live as _agents_live  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.orchestration import steplimits as _steplimits  # noqa: E402
from agent_si.providers.adapters.base import (  # noqa: E402
    AdapterConfig,
    make_secret_ref,
)
from agent_si.providers.adapters.mock_provider import (  # noqa: E402
    MockProviderAdapter,
)

WIRE_DIR = os.path.join(_WS, "frontend", "src", "api", "wire")

TEST_TOKEN = "livewire-wire-token"

# Canonical sentinels for volatile values (ids, timestamps). The live
# payload is asserted BEFORE canonicalization; the file pins shape plus
# stable values so a byte-for-byte regeneration stays stable.
CANON_PROJECT = "wire-project-001"
CANON_STREAM = "wire-stream-001"
CANON_RUN = "wire-run-001"
CANON_TS = "2026-10-28T00:00:00+00:00"
# The manager run mints its own internal run id, which surfaces only
# inside output_ref values; it is pinned to a separate sentinel so the
# fixture keeps the information that it differs from the stream run id.
CANON_MANAGER_RUN = "wire-manager-run-001"
_MANAGER_RUN_RE = re.compile(r"artifact:run/[0-9a-f]{32}/output")

CHAT_PROJECT = "wire-chat-project"
CHAT_MESSAGE = "wire hello"
CHAT_CANNED = ("Wire mock reply one.",)

BANNED_SUBSTRINGS = (
    "secret", "token", "api_key", "apikey", "password", "credential",
    "private_key", "bearer", "authorization",
)


def _auth(token=TEST_TOKEN, actor="tester-livewire"):
    headers = {}
    if actor is not None:
        headers["x-actor"] = actor
    if token is not None:
        headers["x-ui-session-token"] = token
    return headers


def _settings(store_dir=None):
    settings = {"testing": True, "ui_session_token": TEST_TOKEN}
    if store_dir is not None:
        settings["store_dir"] = str(store_dir)
    return settings


def _mock_adapter(canned=CHAT_CANNED):
    config = AdapterConfig(
        provider_id="mock",
        instance_id="livewire-test",
        model="mock-canned",
        secret_ref=make_secret_ref(
            secret_id="mock-secret", provider_id="mock"),
    )
    return MockProviderAdapter(config, transport=None, canned=canned)


def setup_function(_func):
    _steplimits._reset_state()


def teardown_function(_func):
    _steplimits._reset_state()


def _apply_chat_limits(project_id):
    outcome = _steplimits.apply_steplimit_config_change({
        "project_id": project_id,
        "authority": "livewire-wire-test",
        "reason": "configure test project limits for wire fixtures",
        "task_max_steps": 10,
        "chat_max_steps": 10,
    })
    assert outcome.applied, outcome.reason


def _canon(value, swaps):
    if isinstance(value, str):
        for real, fixed in swaps:
            if real:
                value = value.replace(real, fixed)
        return value
    if isinstance(value, list):
        return [_canon(item, swaps) for item in value]
    if isinstance(value, dict):
        return {key: _canon(item, swaps) for key, item in value.items()}
    return value


def _parse_sse(text):
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:"):].strip()))
    return events


def _sse_text(events):
    from agent_si.backend.chat_stream import sse_bytes

    return b"".join(
        sse_bytes(event) for event in events).decode("utf-8")


def _write_wire(name, payload_bytes):
    os.makedirs(WIRE_DIR, exist_ok=True)
    path = os.path.join(WIRE_DIR, name)
    with open(path, "wb") as handle:
        handle.write(payload_bytes)
    return path


def _dump_json(payload):
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode(
        "utf-8")


def build_wire_artifacts(tmp_path):
    """Drive REAL routes; return {filename: bytes} for all 5 wire files."""
    _steplimits._reset_state()
    _agents_live.clear_live_rows()
    try:
        app = create_app(_settings(tmp_path))
        client = TestClient(app, raise_server_exceptions=False)

        # -- budget state: real project create -> real budget GET ----------
        created = client.post(
            "/api/v1/projects",
            json={"name": "wire", "folder_ref": "wire-dock"},
            headers=_auth(),
        )
        assert created.status_code == 200, created.text
        pid = created.json()["project"]["project_id"]
        budget_resp = client.get(
            "/api/v1/budget", params={"project_id": pid})
        assert budget_resp.status_code == 200, budget_resp.text
        budget_live = budget_resp.json()
        assert budget_live["project_id"] == pid
        budget = budget_live["budget"]
        assert budget["currency"] == "USD"
        assert budget["budget_limit"] == "5.00"
        assert budget["soft_limit"] == "4.00"
        assert budget["hard_limit"] == "5.00"
        budget_state = _canon(
            budget_live,
            [(pid, CANON_PROJECT),
             (budget.get("updated_at", ""), CANON_TS)],
        )

        # -- chat stream: fixed project (limits applied) + mock provider --
        _apply_chat_limits(CHAT_PROJECT)
        app.state.chat_provider_adapter = _mock_adapter()
        open_body = {"project": CHAT_PROJECT, "message": CHAT_MESSAGE}
        stream_resp = client.post(
            "/api/v1/chat/stream", json=open_body, headers=_auth())
        assert stream_resp.status_code == 200, stream_resp.text
        stream_id = stream_resp.headers.get("x-stream-id")
        assert stream_id, "chat stream must return an x-stream-id header"
        events = _parse_sse(stream_resp.text)
        assert events, "expected SSE events, got none"
        assert events[0].get("type") == "start"
        kinds = [event.get("type") for event in events]
        assert kinds.count("start") == 1, kinds
        assert "delta" in kinds, kinds
        assert kinds[-1] == "done", kinds
        assert events[-1].get("mock") is True
        delta_text = " ".join(
            str(event.get("text", "")) for event in events
            if event.get("type") == "delta")
        assert CHAT_CANNED[0] in delta_text
        run_id = events[0].get("run_id", "")
        canon_events = _canon(
            events, [(stream_id, CANON_STREAM), (run_id, CANON_RUN)])
        stream_text = _MANAGER_RUN_RE.sub(
            "artifact:run/%s/output" % CANON_MANAGER_RUN,
            _sse_text(canon_events))

        # -- error bodies: real error paths, fixed ids --------------------
        budget_404 = client.get(
            "/api/v1/budget", params={"project_id": "wire-no-such-project"})
        assert budget_404.status_code == 404, budget_404.text
        budget_400 = client.get(
            "/api/v1/budget", params={"project_id": ""})
        assert budget_400.status_code == 400, budget_400.text
        chat_400 = client.post(
            "/api/v1/chat/stream", json={}, headers=_auth())
        assert chat_400.status_code == 400, chat_400.text
        chat_401 = client.post("/api/v1/chat/stream", json=open_body)
        assert chat_401.status_code == 401, chat_401.text
        report_404 = client.get(
            "/api/v1/reports/next-package-nudge",
            params={"package_id": "wire-no-such-pkg"})
        assert report_404.status_code == 404, report_404.text

        # no-provider stream: configured app, nothing bound -> 200 SSE
        # with a terminal NO_PROVIDER_BOUND error event (never a 404).
        bare_app = create_app(_settings(tmp_path))
        bare_client = TestClient(bare_app, raise_server_exceptions=False)
        bare_resp = bare_client.post(
            "/api/v1/chat/stream", json=open_body, headers=_auth())
        assert bare_resp.status_code == 200, bare_resp.text
        bare_events = _parse_sse(bare_resp.text)
        assert [e.get("type") for e in bare_events] == [
            "start", "error"], bare_events
        assert bare_events[1].get("code") == "NO_PROVIDER_BOUND"
        bare_stream = bare_resp.headers.get("x-stream-id", "")
        bare_run = bare_events[0].get("run_id", "")
        no_provider = _canon(
            bare_events[1],
            [(bare_stream, CANON_STREAM), (bare_run, CANON_RUN)])

        error_body = {
            "budget_400": budget_400.json(),
            "budget_404": budget_404.json(),
            "chat_400": chat_400.json(),
            "chat_401": chat_401.json(),
            "no_provider_error_event": no_provider,
            "no_provider_http_status": bare_resp.status_code,
            "report_404": report_404.json(),
        }
        for _name, sample in error_body.items():
            if isinstance(sample, dict):
                body = sample.get("detail", sample)
                assert isinstance(body, dict), sample
                assert body.get("code"), sample
                assert body.get("message"), sample

        # -- report body: real ledger rows -> real report GET -------------
        ledger = app.state.ledger_for(CANON_PROJECT)
        ledger.record_row("wire-pkg-a", 2, 2, 5.0)
        ledger.record_row("wire-pkg-b", 4, 3, 9.0)
        report_resp = client.get(
            "/api/v1/reports/next-package-nudge",
            params={"package_id": "wire-pkg-a",
                    "project_id": CANON_PROJECT})
        assert report_resp.status_code == 200, report_resp.text
        report_live = report_resp.json()
        assert report_live["package_id"] == "wire-pkg-a"
        assert report_live["load"]["agents"] == 2
        assert report_live["auto_push"] is False

        return {
            "budget-state.json": _dump_json(budget_state),
            "chat-open-request.json": _dump_json(open_body),
            "chat-stream-events.json": stream_text.encode("utf-8"),
            "error-body.json": _dump_json(error_body),
            "report-body.json": _dump_json(report_live),
        }
    finally:
        _steplimits._reset_state()


def test_generate_wire_fixtures(tmp_path):
    """Generate all 5 wire fixtures from REAL routes through the real app."""
    artifacts = build_wire_artifacts(tmp_path)
    assert sorted(artifacts) == [
        "budget-state.json",
        "chat-open-request.json",
        "chat-stream-events.json",
        "error-body.json",
        "report-body.json",
    ]
    for name, payload in artifacts.items():
        path = _write_wire(name, payload)
        assert os.path.isfile(path), path
    for name in artifacts:
        with open(os.path.join(WIRE_DIR, name), "rb") as handle:
            text = handle.read().decode("utf-8")
        lowered = text.lower()
        for banned in BANNED_SUBSTRINGS:
            assert banned not in lowered, (
                "%s carries forbidden %r" % (name, banned))
