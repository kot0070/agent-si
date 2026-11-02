"""FXWATCHLOOP served proof: background loop journals outages plus decisions.

Drives the real seam app (create_app + TestClient) with the loop interval
shortened through its parameter: a declared local TCP service stopped
mid-run -> OUTAGE_SIGNAL + SERVICE_STATE in GET /api/v1/watcher/journal
without manual POST; a live run and a live chat stream each lead to a
WATCH_DECISION row once stored facts push a card off base (idle ticks
journal nothing); shutdown leaves no task running.
"""

import os
import socket
import sys
import time

from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.automation import interface as _auto_iface  # noqa: E402
from agent_si.automation import runner as _runner  # noqa: E402
from agent_si.automation import service_status as _status  # noqa: E402
from agent_si.automation import service_watch as _watch  # noqa: E402
from agent_si.backend import agents_live as _live_rows  # noqa: E402
from agent_si.backend import stop_all as _stop_all  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.backend.chat_stream import (  # noqa: E402
    ChatStreamRequest,
    bridge_for_app,
)
from agent_si.providers.adapters.base import (  # noqa: E402
    AdapterConfig,
    make_secret_ref,
)
from agent_si.providers.adapters.mock_provider import (  # noqa: E402
    MockProviderAdapter,
)
from agent_si.watcher import engine as _engine  # noqa: E402
from agent_si.watcher import journal as _journal  # noqa: E402
from agent_si.watcher import outage as _outage  # noqa: E402
from agent_si.watcher import rules as _rules  # noqa: E402
from agent_si.watcher import watch_loop as _loop  # noqa: E402

TEST_TOKEN = "fxwatchloop-token"
ACTOR = "coder-1-loop"
PROJ = "proj-fxwatchloop"
PROJ_CHAT = "proj-fxwatchloop-chat"
SERVICE_ID = "svc-fxwatchloop-tcp"
SERVICE_CHAT = "svc-fxwatchloop-chat-tcp"
TEMPLATE_ID = "tpl-fxwatchloop"

POLL_TIMEOUT_S = 15.0
POLL_STEP_S = 0.05


def _settings(interval_s=0.05):
    return {
        "testing": True,
        "ui_session_token": TEST_TOKEN,
        "watch_loop_interval_s": interval_s,
    }


def _mock_adapter():
    config = AdapterConfig(
        provider_id="mock",
        instance_id="fxwatchloop-behavior",
        model="mock-canned",
        secret_ref=make_secret_ref(
            secret_id="mock-secret", provider_id="mock"),
    )
    return MockProviderAdapter(
        config, transport=None, canned=("Canned loop reply.",))


def _reset_all():
    _journal.reset_state()
    _rules.reset_state()
    _engine.reset_state()
    _outage.reset_state()
    _stop_all.reset_state()
    _status.reset_state()
    _watch.reset_baseline()
    _runner.reset_state()
    _live_rows.clear_live_rows()


_SAVED_JOURNAL_HOOK = None
_SAVED_SERVICES = None


def _snapshot_services():
    """Snapshot the stored service registries (test isolation only)."""
    return {
        "services": {key: dict(row)
                     for key, row in _status._SERVICES.items()},
        "dispatch": {key: dict(row)
                     for key, row in _status._DISPATCH_META.items()},
        "egress": {key: dict(row)
                   for key, row in _status._EGRESS_META.items()},
        "containers": {
            key: {"env": dict(row.get("env", {})),
                  "files": row.get("files", ())}
            for key, row in _status._CONTAINER_DESCRIPTORS.items()},
    }


def _restore_services(snapshot):
    """Restore the stored service registries exactly (test isolation)."""
    _status._SERVICES.clear()
    _status._SERVICES.update(
        {key: dict(row) for key, row in snapshot["services"].items()})
    _status._DISPATCH_META.clear()
    _status._DISPATCH_META.update(
        {key: dict(row) for key, row in snapshot["dispatch"].items()})
    _status._EGRESS_META.clear()
    _status._EGRESS_META.update(
        {key: dict(row) for key, row in snapshot["egress"].items()})
    _status._CONTAINER_DESCRIPTORS.clear()
    _status._CONTAINER_DESCRIPTORS.update({
        key: {"env": dict(row["env"]), "files": row["files"]}
        for key, row in snapshot["containers"].items()})


def setup_function(_func):
    global _SAVED_JOURNAL_HOOK, _SAVED_SERVICES
    _SAVED_JOURNAL_HOOK = _auto_iface.journal_append_event
    _reset_all()
    # Trim the stored registry to this file's services: seed rows stay
    # untouched and sandbox-closed ports cost a 2 s probe timeout each,
    # so probing seeds here would only slow the served proof down.
    _SAVED_SERVICES = _snapshot_services()
    _status._SERVICES.clear()
    _status._DISPATCH_META.clear()
    _status._EGRESS_META.clear()
    _status._CONTAINER_DESCRIPTORS.clear()


def teardown_function(_func):
    _auto_iface.journal_append_event = _SAVED_JOURNAL_HOOK
    _restore_services(_SAVED_SERVICES)
    _reset_all()


def _open_listener():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    return listener


def _kinds_for(project_id):
    return {
        row.kind for row in _journal.stored_rows(project_id)
    }


def _wait_for(project_id, wanted, timeout_s=POLL_TIMEOUT_S):
    """Poll stored journal rows until all wanted kinds land (or timeout)."""
    deadline = time.monotonic() + timeout_s
    kinds = set()
    while time.monotonic() < deadline:
        kinds = _kinds_for(project_id)
        if set(wanted) <= kinds:
            return kinds
        time.sleep(POLL_STEP_S)
    return kinds


def _wait_for_route(client, project_id, wanted, timeout_s=POLL_TIMEOUT_S):
    """Poll the served journal route until all wanted kinds land."""
    deadline = time.monotonic() + timeout_s
    kinds = set()
    while time.monotonic() < deadline:
        resp = client.get(
            "/api/v1/watcher/journal", params={"project_id": project_id})
        assert resp.status_code == 200, resp.text
        kinds = set()
        for row in resp.json():
            if isinstance(row, dict) and row.get("kind"):
                kinds.add(row.get("kind"))
        if set(wanted) <= kinds:
            return kinds
        time.sleep(POLL_STEP_S)
    return kinds


def test_product_interval_constant():
    """The product pass interval stays 30 s; tests shorten via parameter."""
    assert _loop.INTERVAL_S == 30.0


def test_live_chat_stream_tick_once_records_decision():
    """An open chat stream marks the pass live: engine.tick journals."""
    listener = _open_listener()
    try:
        port = listener.getsockname()[1]
        _status.declare_service(
            SERVICE_CHAT, kind="tcp", host="127.0.0.1", tcp_port=port,
            project_id=PROJ_CHAT)
        app = create_app(_settings())
        app.state.chat_provider_adapter = _mock_adapter()
        bridge = bridge_for_app(app)
        request = ChatStreamRequest(
            project=PROJ_CHAT, task="t-loop", message="hello loop",
            actor=ACTOR)
        stream_id, events = bridge.run(request)
        try:
            assert stream_id in bridge._live
            assert "WATCH_DECISION" not in _kinds_for(PROJ_CHAT)
            # Idle first: normal verdicts journal nothing (no row, no call).
            idle = _loop.tick_once(app)
            assert PROJ_CHAT in idle["watched"]
            assert "WATCH_DECISION" not in _kinds_for(PROJ_CHAT)
            # Abnormal next: stored tamper facts push the card off base.
            _journal.append_event(
                PROJ_CHAT, "agent-x", "TAMPER_ATTEMPT",
                "loop probe tamper", ("ref-fxwatchloop-chat",))
            summary = _loop.tick_once(app)
            assert PROJ_CHAT in summary["watched"]
            kinds = _kinds_for(PROJ_CHAT)
            assert "WATCH_DECISION" in kinds
            decisions = list(_journal.stored_rows(
                PROJ_CHAT, "WATCH_DECISION"))
            assert decisions, "live stream left no WATCH_DECISION row"
            assert any(
                "model=" in row.summary
                or "no watcher model: default action" in row.summary
                for row in decisions), (
                "WATCH_DECISION names no deciding model: %r"
                % ([row.summary for row in decisions],))
            assert not any("run_check" in row.summary
                           or "cmd" in row.summary.lower()
                           for row in decisions), (
                "WATCH_DECISION carries a raw command: %r"
                % ([row.summary for row in decisions],))
        finally:
            list(events)
            assert stream_id not in bridge._live
    finally:
        listener.close()


def test_served_loop_outage_and_decision_no_manual_post():
    """Served app: stopped TCP service -> OUTAGE_SIGNAL; live run -> tick."""
    listener = _open_listener()
    try:
        port = listener.getsockname()[1]
        _status.declare_service(
            SERVICE_ID, kind="tcp", host="127.0.0.1", tcp_port=port,
            project_id=PROJ)
        app = create_app(_settings(interval_s=0.05))
        with TestClient(app) as client:
            assert _loop.is_running(), "lifespan left no loop task running"
            kinds = _wait_for_route(client, PROJ, ("SERVICE_STATE",))
            assert "SERVICE_STATE" in kinds, (
                "loop never probed the declared service: %r" % (kinds,))
            assert "OUTAGE_SIGNAL" not in kinds, (
                "healthy service wrongly signalled outage")
            first = len(_journal.stored_rows(PROJ, "SERVICE_STATE"))
            time.sleep(1.0)
            second = len(_journal.stored_rows(PROJ, "SERVICE_STATE"))
            assert second > first, (
                "shortened interval never re-passed: %d -> %d"
                % (first, second))
            _runner.register_template(TEMPLATE_ID, PROJ, name="loop")
            _runner.start_run(PROJ, TEMPLATE_ID)
            # The live run idles normal until stored facts push a card
            # off base; the tamper fact below makes the tick abnormal.
            _journal.append_event(
                PROJ, "agent-x", "TAMPER_ATTEMPT",
                "loop probe tamper", ("ref-fxwatchloop",))
            kinds = _wait_for_route(client, PROJ, ("WATCH_DECISION",))
            assert "WATCH_DECISION" in kinds, (
                "live run never ticked the watcher: %r" % (kinds,))
            listener.close()
            listener = None
            kinds = _wait_for_route(
                client, PROJ, ("OUTAGE_SIGNAL", "SERVICE_STATE"))
            assert "OUTAGE_SIGNAL" in kinds, (
                "stopped service never signalled outage: %r" % (kinds,))
            outages = _journal.stored_rows(PROJ, "OUTAGE_SIGNAL")
            assert outages, "no OUTAGE_SIGNAL row stored"
            assert any(SERVICE_ID in row.refs for row in outages), (
                "OUTAGE_SIGNAL names no service: %r"
                % ([row.refs for row in outages],))
            downs = [
                row for row in _journal.stored_rows(PROJ, "SERVICE_STATE")
                if "DOWN" in row.summary
            ]
            assert downs, "no DOWN SERVICE_STATE row stored"
            kinds = _wait_for_route(
                client, PROJ,
                ("WATCH_DECISION", "SERVICE_STATE", "OUTAGE_SIGNAL"))
            assert {"WATCH_DECISION", "SERVICE_STATE",
                    "OUTAGE_SIGNAL"} <= kinds
        assert not _loop.is_running(), "shutdown left the loop task running"
    finally:
        if listener is not None:
            listener.close()
