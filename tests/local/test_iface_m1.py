"""K05 M1 STEP1 contract test (RED until impl; fakes live here only, marked FAKE-OF)."""
from __future__ import annotations

import contextlib
import hashlib
import http.client
import importlib.util
import inspect
import io
import json
import pathlib
import sys
import threading
import unittest.mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

import pytest

from agent_si.backend import local_connect
from agent_si.local import adapter, gateway
from agent_si.local.adapter import EvidenceTier, LifecycleStage

_WS_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Frozen K04 interface stubs: byte-exact repo copies under iface/frozen_k04/
# (copies are never edited). sha256 values confirmed against the RECORDS/day1
# originals; the loader checks each copy before use.
_K04_SHA256 = "c2ff19b32928d93c30264ac5ad1a98414eab6cc9051af6e0559d6a6af9afaf02"
_K04_V2_MAP13_SHA256 = (
    "e6a0d09eda7598d641ffad35998dc4ee50b99243d3b95cc72808aeefc0ab04c3"
)
_K04_V3_ADD412_SHA256 = (
    "20ca34bf342ee78f25128bf297acbd7a90cfb290edb6016a05d9ac021e4dbb99"
)
_FROZEN_K04_FILES = (
    ("K04_INTERFACE_STUB.py", _K04_SHA256),
    ("K04_INTERFACE_STUB_v2_MAP13.py", _K04_V2_MAP13_SHA256),
    ("K04_INTERFACE_STUB_v3_ADD412.py", _K04_V3_ADD412_SHA256),
)


def _load_frozen_k04():
    frozen_dir = _WS_ROOT / "iface" / "frozen_k04"
    for name, expected in _FROZEN_K04_FILES:
        digest = hashlib.sha256((frozen_dir / name).read_bytes()).hexdigest()
        assert digest == expected, f"frozen K04 copy changed: {name}"
    path = frozen_dir / "K04_INTERFACE_STUB.py"
    spec = importlib.util.spec_from_file_location("k04_frozen_iface", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


K04 = _load_frozen_k04()


# FAKE-OF: agent_si.routing.router (K04-owned; test-only stand-in, never product code)
class FakeRouter:
    """Mimics the frozen K04 select signature for SPLIT-route sourcing."""

    def select(self, task_contract_ref: str, candidates: list) -> dict:
        assert isinstance(task_contract_ref, str)
        assert isinstance(candidates, list)
        return {"route": "SPLIT", "reason": "local draft plus cloud verify"}


# FAKE-OF: agent_si.verification.checker (K03-owned; test-only stand-in, never product code)
class FakeVerifier:
    """Records the order of cloud-verify versus audit calls."""

    def __init__(self) -> None:
        self.calls: list = []

    def verify(self, output_ref: str) -> dict:
        self.calls.append(("verify", output_ref))
        return {"result": "PASS", "output_ref": output_ref}

    def audit(self, output_ref: str) -> dict:
        self.calls.append(("audit", output_ref))
        return {"result": "PASS", "output_ref": output_ref}


# FAKE-OF: K02 PackageLedger NEW side (C9/C10 row plus report shape; test-only stand-in)
class FakePackageLedger:
    """Minimal NEW-side ledger: rows keyed by package with run identity."""

    def __init__(self) -> None:
        self.rows: dict = {}

    def record_row(self, package_id: str, agents: int, peak_concurrency: int, wall_time_s: int) -> dict:
        row = {
            "package_id": package_id,
            "agents": agents,
            "peak_concurrency": peak_concurrency,
            "wall_time_s": wall_time_s,
        }
        self.rows[package_id] = row
        return row

    def package_report(self, package_id: str) -> dict:
        row = self.rows[package_id]
        return {"row": row, "nudge": "", "auto_push": False}


FROZEN_STAGE_ORDER = [
    "SCAN",
    "DISCOVER",
    "IDENTIFY",
    "REGISTER",
    "PROBE",
    "BENCHMARK",
    "ROUTING_ELIGIBILITY",
]


def test_lifecycle_stage_order_exact() -> None:
    assert [stage.value for stage in LifecycleStage] == FROZEN_STAGE_ORDER


def test_lifecycle_position_values() -> None:
    for index, name in enumerate(FROZEN_STAGE_ORDER):
        assert adapter.lifecycle_position(LifecycleStage(name)) == index


def test_advance_lifecycle_single_step() -> None:
    assert adapter.advance_lifecycle(LifecycleStage.SCAN, LifecycleStage.DISCOVER) == LifecycleStage.DISCOVER
    assert (
        adapter.advance_lifecycle(LifecycleStage.BENCHMARK, LifecycleStage.ROUTING_ELIGIBILITY)
        == LifecycleStage.ROUTING_ELIGIBILITY
    )


def test_error_lifecycle_skip_refused_condition() -> None:
    with pytest.raises(Exception) as excinfo:
        adapter.advance_lifecycle(LifecycleStage.SCAN, LifecycleStage.IDENTIFY)
    assert "LIFECYCLE_SKIP_REFUSED" in str(excinfo.value)


def test_evidence_tier_values_exact() -> None:
    assert [tier.value for tier in EvidenceTier] == ["UNKNOWN", "PROXY", "MEASURED"]


def test_error_unknown_tier_condition() -> None:
    verdict = adapter.check_eligibility("store-ref-with-only-unknown", "gateway-state-idle")
    assert verdict.eligible is False
    assert "UNKNOWN_TIER_INELIGIBLE" in verdict.reason


def test_passive_check_idle_allowed() -> None:
    result = gateway.passive_check()
    assert result.allowed is True
    assert result.reason == gateway.GATEWAY_IDLE_REASON


def test_error_gateway_busy_condition() -> None:
    result = gateway.passive_check()
    assert result.allowed is False
    assert result.reason in gateway.GATEWAY_SKIP_REASONS


def test_passive_check_never_force() -> None:
    params = inspect.signature(gateway.passive_check).parameters
    assert "force" not in params


def test_check_eligibility_records_evidence_refs() -> None:
    verdict = adapter.check_eligibility("store-ref-measured-1", "gateway-state-idle")
    assert verdict.eligible is True
    assert verdict.gateway_allowed is True
    assert isinstance(verdict.evidence_refs, tuple) and len(verdict.evidence_refs) > 0
    assert "store" in verdict.eligibility_source and "gateway" in verdict.eligibility_source


def test_every_decision_records_evidence_refs() -> None:
    pin = adapter.record_explicit_pin("local-model-ref-1")
    assert isinstance(pin.capability_evidence_refs, tuple)
    split = adapter.record_split_decision("draft-ref-1", "verify-ref-1", "hash-1")
    assert isinstance(split, adapter.SplitAssignment)
    assert split.local_draft_ref == "draft-ref-1"
    assert split.cloud_verify_ref == "verify-ref-1"


def test_explicit_pin_route_quality_zero_measured() -> None:
    decision = adapter.record_explicit_pin("local-model-ref-1")
    assert decision.route == adapter.ROUTE_EXPLICIT_PIN
    assert decision.quality_basis == K04.QualityBasis.UNVERIFIED_PIN.value
    assert decision.measured_evidence_count == 0


def test_k04_quality_basis_readonly() -> None:
    assert [basis.value for basis in K04.QualityBasis] == [
        "MEASURED",
        "STATIC_VERIFIED",
        "UNVERIFIED_PIN",
        "UNKNOWN",
    ]


def test_split_carries_both_refs_atomically() -> None:
    split = adapter.record_split_decision("draft-ref-9", "verify-ref-9", "draft-hash-9")
    assert (split.local_draft_ref, split.cloud_verify_ref) == ("draft-ref-9", "verify-ref-9")
    assert split.draft_hash == "draft-hash-9"


def test_split_cloud_verify_before_audit() -> None:
    verifier = FakeVerifier()
    split = adapter.record_split_decision("draft-ref-2", "verify-ref-2", "draft-hash-2")
    verifier.verify(split.cloud_verify_ref)
    verifier.audit(split.cloud_verify_ref)
    assert verifier.calls[0] == ("verify", "verify-ref-2")
    assert verifier.calls[1] == ("audit", "verify-ref-2")


def test_split_route_source_from_router() -> None:
    router = FakeRouter()
    routed = router.select("contract-ref-1", [])
    assert routed["route"] == adapter.ROUTE_SPLIT
    split = adapter.record_split_decision("draft-ref-3", "verify-ref-3", "draft-hash-3")
    assert split.local_draft_ref and split.cloud_verify_ref


def test_error_not_configured_condition() -> None:
    status = local_connect.get_status()
    assert status.status == adapter.STATUS_NOT_CONFIGURED
    assert adapter.routing_continues(status.status) is True


def test_local_decision_carries_run_identity() -> None:
    ledger = FakePackageLedger()
    ledger.record_row("pkg-1", 2, 2, 10)
    report = ledger.package_report("pkg-1")
    assert set(report.keys()) == {"row", "nudge", "auto_push"}
    assert report["auto_push"] is False
    decision = adapter.record_explicit_pin("local-model-ref-7")
    assert (decision.project_id, decision.task_id, decision.run_id) != (None, None, None)


def test_error_codes_exact_set() -> None:
    assert tuple(adapter.ERROR_CODES_LOCAL) == (
        "NOT_CONFIGURED",
        "GATEWAY_BUSY",
        "LIFECYCLE_SKIP_REFUSED",
        "UNKNOWN_TIER_INELIGIBLE",
        "SESSION_TOKEN_REFUSED",
    )


def _wsgi_request(app: object, method: str, path: str, body: bytes) -> tuple:
    """Drive one request against a WSGI app object in-process; returns (status_code, text)."""
    caller = getattr(app, "__call__", None)
    assert callable(caller), "K05-M1: WSGI app object is not callable"
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "SERVER_NAME": "127.0.0.1",
        "SERVER_PORT": "80",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        "wsgi.input": io.BytesIO(body),
        "wsgi.errors": sys.stderr,
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
        "CONTENT_LENGTH": str(len(body)),
    }
    if body:
        environ["CONTENT_TYPE"] = "application/json"
    captured: dict = {}

    def start_response(status: str, headers: list, exc_info: object = None) -> None:
        captured["status"] = status
        captured["headers"] = headers

    chunks = caller(environ, start_response)
    try:
        raw = b"".join(chunks)
    finally:
        close = getattr(chunks, "close", None)
        if callable(close):
            close()
    return int(str(captured["status"]).split(" ", 1)[0]), raw.decode("utf-8", "replace")


# FAKE-OF: sidecar loopback transport (a stdlib HTTP server over 127.0.0.1 in a daemon
# thread; test-only request driver, never product code)
def _loopback_request(server: object, method: str, path: str, body: bytes) -> tuple:
    """Drive one request against a stdlib HTTP server object; returns (status_code, text)."""
    serve = getattr(server, "serve_forever", None)
    assert callable(serve), "K05-M1: server object has no serve_forever"
    thread = threading.Thread(target=serve, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        address = getattr(server, "server_address", ("127.0.0.1", 0))
        host = address[0] or "127.0.0.1"
        connection = http.client.HTTPConnection(host, address[1], timeout=10)
        headers = {"Content-Type": "application/json"} if body else {}
        connection.request(method, path, body=body or None, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        code = response.status
        connection.close()
    finally:
        shutdown = getattr(server, "shutdown", None)
        if callable(shutdown):
            shutdown()
        thread.join(timeout=10)
        close_server = getattr(server, "server_close", None)
        if callable(close_server):
            close_server()
    return code, raw.decode("utf-8", "replace")


def _drive_local_route(app: object, method: str, path: str, payload: object) -> tuple:
    """Send one (method, path) request through the real app object.

    Returns (status_code, body_text). Seams in order: the app object's own
    test_client() hook; starlette/fastapi TestClient when the app uses it;
    a direct in-process WSGI call; a stdlib HTTP server on loopback.
    """
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    factory = getattr(app, "test_client", None)
    if callable(factory):
        client = factory()
        if body:
            response = client.request(method, path, data=body, content_type="application/json")
        else:
            response = client.request(method, path)
        text = getattr(response, "data", None) or getattr(response, "content", b"") or getattr(response, "text", "")
        if isinstance(text, bytes):
            text = text.decode("utf-8", "replace")
        return int(response.status_code), text
    if hasattr(app, "routes"):
        try:
            from starlette.testclient import TestClient
        except ImportError:
            pass
        else:
            client = TestClient(app)
            if body:
                response = client.request(
                    method, path, content=body, headers={"Content-Type": "application/json"}
                )
            else:
                response = client.request(method, path)
            return int(response.status_code), response.text
    if callable(app):
        return _wsgi_request(app, method, path, body)
    if hasattr(app, "serve_forever"):
        return _loopback_request(app, method, path, body)
    pytest.fail(
        "K05-M1: app seam unknown; agent_si.backend.app.app must expose test_client(), "
        "a WSGI callable, starlette routes, or serve_forever()"
    )


def test_http_routes_reach_entry_points() -> None:
    """W2: every local HTTP route through the REAL app router reaches its entry point."""
    try:
        from agent_si.backend.app import create_app
    except ImportError as exc:
        pytest.fail(f"K05-M1: create_app missing (K02 composition root): {exc}")
    # FAKE-OF: K02 composition-root boundary hooks/model_factory (test-only stand-ins, never product code)
    def _fake_auth_hook(*args, **kwargs):
        return None

    def _fake_rate_hook(*args, **kwargs):
        return None

    def _fake_model_factory(*args, **kwargs):
        return None

    app = create_app(
        {"env": "test"}, _fake_auth_hook, _fake_rate_hook, _fake_model_factory
    )
    app_module = sys.modules["agent_si.backend.app"]
    for method, path in local_connect.HTTP_ROUTES:
        entry_name = local_connect.ROUTE_ENTRY_POINTS[(method, path)]
        entry_fn = getattr(local_connect, entry_name)
        if entry_name == "connect":
            payload: object = {"runtime_ref": "runtime-ref-1", "session_token": "session-1"}
        elif entry_name == "disconnect":
            payload = {"session_token": "session-1"}
        else:
            payload = None
        with contextlib.ExitStack() as stack:
            spies = [stack.enter_context(unittest.mock.patch.object(local_connect, entry_name, wraps=entry_fn))]
            app_fn = getattr(app_module, entry_name, None)
            if callable(app_fn):
                spies.append(stack.enter_context(unittest.mock.patch.object(app_module, entry_name, wraps=app_fn)))
            status_code, text = _drive_local_route(app, method, path, payload)
            assert any(spy.called for spy in spies), f"{method} {path} did not reach entry {entry_name}"
            if method == "GET":
                assert 200 <= status_code < 300, f"{method} {path} -> {status_code}: {text}"
            else:
                refused = 400 <= status_code < 500 and "SESSION_TOKEN_REFUSED" in text
                assert (200 <= status_code < 300) or refused, f"{method} {path} -> {status_code}: {text}"


def test_entry_points_behave() -> None:
    status = local_connect.get_status()
    assert isinstance(status, local_connect.LocalStatus)
    connected = local_connect.connect("runtime-ref-1", session_token="session-1")
    assert isinstance(connected, local_connect.LocalStatus)
    disconnected = local_connect.disconnect(session_token="session-1")
    assert isinstance(disconnected, local_connect.LocalStatus)
    rows = local_connect.list_models()
    assert isinstance(rows, tuple)


def test_write_entries_refuse_missing_session_token() -> None:
    before = local_connect.get_status()
    with pytest.raises(Exception) as excinfo:
        local_connect.connect("runtime-ref-1", session_token=None)
    assert "SESSION_TOKEN_REFUSED" in str(excinfo.value)
    with pytest.raises(Exception) as excinfo:
        local_connect.disconnect(session_token=None)
    assert "SESSION_TOKEN_REFUSED" in str(excinfo.value)
    assert local_connect.get_status() == before


def test_write_entries_refuse_wrong_session_token() -> None:
    before = local_connect.get_status()
    with pytest.raises(Exception) as excinfo:
        local_connect.connect("runtime-ref-1", session_token="wrong-token-1")
    assert "SESSION_TOKEN_REFUSED" in str(excinfo.value)
    with pytest.raises(Exception) as excinfo:
        local_connect.disconnect(session_token="wrong-token-1")
    assert "SESSION_TOKEN_REFUSED" in str(excinfo.value)
    assert local_connect.get_status() == before


def test_read_entries_need_no_session_token() -> None:
    assert "session_token" not in inspect.signature(local_connect.get_status).parameters
    assert "session_token" not in inspect.signature(local_connect.list_models).parameters
    status = local_connect.get_status()
    assert isinstance(status, local_connect.LocalStatus)
    rows = local_connect.list_models()
    assert isinstance(rows, tuple)
    assert all(isinstance(row, local_connect.LocalModelRow) for row in rows)


def test_realization_map_points_to_lane_impl() -> None:
    for name, target in adapter.REALIZATION_MAP.items():
        assert callable(getattr(adapter, name))
        assert target.startswith("agent_si.local.")
    for name, target in gateway.REALIZATION_MAP.items():
        assert callable(getattr(gateway, name))
        assert target.startswith("agent_si.local.")
    for name, target in local_connect.REALIZATION_MAP.items():
        assert callable(getattr(local_connect, name))
        assert target.startswith("agent_si.local.")


def test_all_call_surfaces_wired() -> None:
    import agent_si.local as local_pkg

    for name in local_pkg.__all__:
        assert getattr(local_pkg, name) is not None
    for name in ("get_status", "connect", "disconnect", "list_models"):
        assert callable(getattr(local_connect, name))
    assert callable(gateway.passive_check)
