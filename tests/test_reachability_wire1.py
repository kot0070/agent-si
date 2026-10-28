"""M-WIRE R1 reachability: every K03/K09/K05 route on create_app reaches its declared entry.

Maintained test (no FAKE-OF): builds the real seam app, reads each route
table at runtime from its owning package module (never a copied list),
asserts method+path is registered in app.routes, then drives one request
through TestClient with a wraps-spy on the declared entry. Safe payloads
reach entries without polluting module-global lane state.
"""

from __future__ import annotations

import contextlib
import functools
import os
import sys
import unittest.mock

import pytest
from fastapi import Request as _FastAPIRequest

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import kb_routes as _kb_mod
from agent_si.backend import local_connect as _local_mod
from agent_si.backend import localbench_routes as _bench_mod
from agent_si.backend import pools_routes as _k04_mod
from agent_si.backend.app import create_app
from agent_si.test_runners import stage_runner as _stage_mod

TEST_TOKEN = "wire1-reachability-token"
TEST_SETTINGS = {"testing": True, "ui_session_token": TEST_TOKEN}

_WRITE_HEADERS = {"x-actor": "wire1", "x-ui-session-token": TEST_TOKEN}


@pytest.fixture
def _wire1_clean():
    """Snapshot module-global lane state; restore it after the test."""
    lc_paired = _local_mod._PAIRED_SESSION_TOKEN
    lc_attached = _local_mod._ATTACHED_RUNTIME
    k04_default_ctx = _k04_mod._DEFAULT_POOLS_CTX
    runs = dict(_stage_mod._RUNS)
    results = {key: list(val) for key, val in _stage_mod._RESULTS.items()}
    reservations = dict(_stage_mod._RESERVATIONS)
    cap_pending = set(_stage_mod._CAP_ASK_PENDING)
    dedupe = set(_stage_mod._SETTLED_DEDUPE_KEYS)
    seq = list(_stage_mod._RESERVATION_SEQ)
    bus = sys.modules.get("k03_stage_episode_bus")
    bus_made = bus is None
    bus_state = None
    if bus is not None:
        bus_state = (
            bus.open_project, set(bus.projects_asked), dict(bus.parked_runs))
    yield
    _local_mod._PAIRED_SESSION_TOKEN = lc_paired
    _local_mod._ATTACHED_RUNTIME = lc_attached
    _k04_mod._DEFAULT_POOLS_CTX = k04_default_ctx
    _stage_mod._RUNS.clear()
    _stage_mod._RUNS.update(runs)
    _stage_mod._RESULTS.clear()
    _stage_mod._RESULTS.update(results)
    _stage_mod._RESERVATIONS.clear()
    _stage_mod._RESERVATIONS.update(reservations)
    _stage_mod._CAP_ASK_PENDING.clear()
    _stage_mod._CAP_ASK_PENDING.update(cap_pending)
    _stage_mod._SETTLED_DEDUPE_KEYS.clear()
    _stage_mod._SETTLED_DEDUPE_KEYS.update(dedupe)
    _stage_mod._RESERVATION_SEQ[:] = seq
    if bus_made:
        sys.modules.pop("k03_stage_episode_bus", None)
    elif bus_state is not None:
        bus = sys.modules.get("k03_stage_episode_bus")
        if bus is not None:
            bus.open_project, asked, parked = bus_state
            bus.projects_asked.clear()
            bus.projects_asked.update(asked)
            bus.parked_runs.clear()
            bus.parked_runs.update(parked)


def _registered_paths(app):
    """(method, path) pairs served by the app, expanding lazy includes.

    This FastAPI version mounts APIRouter includes as a lazy wrapper
    (original_router + include_context.prefix) instead of copying routes
    into app.routes; serving is unaffected, so expand the wrapper here.
    """
    found = set()

    def _add(routes, prefix=""):
        for route in routes or []:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                context = getattr(route, "include_context", None)
                child = prefix + (getattr(context, "prefix", "") or "")
                _add(getattr(inner, "routes", []), child)
                continue
            methods = getattr(route, "methods", None) or set()
            path = getattr(route, "path", None)
            if path is None:
                continue
            for method in methods:
                found.add((method, prefix + path))

    _add(getattr(app, "routes", []))
    return found


def _drive(client, method, path, payload, headers):
    if payload is not None:
        return client.request(method, path, json=payload, headers=headers)
    return client.request(method, path, headers=headers)


def _wrap_kb_handler(handler, calls):
    """Wraps-spy preserving the real Request signature for route binding."""

    @functools.wraps(handler)
    async def _wrapper(request):
        calls.append(handler.__name__)
        return await handler(request)

    _wrapper.__annotations__ = {"request": _FastAPIRequest}
    return _wrapper


def _wrap_k04_handler(name, handler, calls):
    """Call-recorded spy preserving the (ctx, query, body) entry shape."""

    @functools.wraps(handler)
    def _wrapper(ctx, query, body):
        calls.append(name)
        return handler(ctx, query, body)

    return _wrapper


def _k04_drive_path(template):
    """Concrete drive path for a declared template (runtime-read)."""
    return "/".join(
        "wire1-nope" if seg.startswith("{") and seg.endswith("}") else seg
        for seg in template.split("/"))


def _k04_payload(method, template, write_headers):
    """Safe payload + headers + exact expected status per K04 template.

    Mirrors _stage_payload: unknown templates fail loud (never skipped).
    Payloads fail validation inside the declared entry (never in the app
    guard), so the spy proves the entry ran.
    """
    key = (method.lower(), template)
    if key == ("get", "/api/v1/providers"):
        return None, None, 200
    if key == ("post", "/api/v1/providers/connect"):
        return {}, write_headers, 400
    if key == ("post", "/api/v1/providers/{id}/disconnect"):
        return {}, write_headers, 404
    if key == ("get", "/api/v1/providers/{id}/models"):
        return None, None, 404
    if key == ("get", "/api/v1/chat/models"):
        return None, None, 200
    if key == ("get", "/api/v1/roles/pools"):
        return None, None, 200
    if key == ("put", "/api/v1/roles/pools"):
        return {}, write_headers, 400
    if key == ("get", "/api/v1/routing/decision/{id}/why"):
        return None, None, 404
    if key == ("get", "/api/v1/budget"):
        return None, None, 404
    if key == ("get", "/api/v1/kb/status"):
        return None, None, 200
    if key == ("post", "/api/v1/kb/proposals/apply"):
        return {}, write_headers, 400
    if key == ("put", "/api/v1/roles/chat-model"):
        return {}, write_headers, 400
    raise AssertionError("no safe payload for %s %s" % (method, template))


def test_wire1_routes_reach_declared_entries(_wire1_clean, monkeypatch,
                                             tmp_path):
    """Every declared K03/K09/K05 route is registered and reaches its entry."""
    from fastapi.testclient import TestClient

    # KB handlers bind at registration time from the _ROUTES declaration:
    # wrap the declared handlers (same functions, call-recorded) so the
    # app binds the spies. Method+path are read from the live declaration.
    kb_declaration = _kb_mod._ROUTES
    kb_calls: list = []
    monkeypatch.setattr(
        _kb_mod, "_ROUTES",
        tuple((m, p, _wrap_kb_handler(h, kb_calls))
              for m, p, h in kb_declaration))

    # K04 handlers bind at registration time like the KB ones: wrap the
    # live ROUTES entries (same functions, call-recorded by route name)
    # so the app binds the spies. Method+path+name are read from the live
    # declaration below; K04 is configured with a real dir (tmp_path) so
    # entries run instead of the unconfigured 500 short-circuit.
    k04_declaration = _k04_mod.ROUTES
    k04_calls: list = []
    monkeypatch.setattr(
        _k04_mod, "ROUTES",
        tuple((m, p, n, _wrap_k04_handler(n, f, k04_calls))
              for m, p, n, f in k04_declaration))

    settings = dict(TEST_SETTINGS)
    settings["store_dir"] = str(tmp_path)
    app = create_app(settings)
    token = app.state.ui_session_token
    assert token == TEST_TOKEN
    headers = {"x-actor": "wire1", "x-ui-session-token": token}
    client = TestClient(app, raise_server_exceptions=False)
    registered = _registered_paths(app)

    cases = []
    for method, path in _local_mod.HTTP_ROUTES:
        entry = _local_mod.ROUTE_ENTRY_POINTS[(method, path)]
        if entry == "connect":
            payload = {"runtime_ref": "runtime-ref-1",
                       "session_token": "wire1-not-paired"}
            kind = "local-post"
        elif entry == "disconnect":
            payload = {"session_token": "wire1-not-paired"}
            kind = "local-post"
        else:
            payload = None
            kind = "ok2xx"
        cases.append((method, path, payload, None, _local_mod, entry, kind))
    for method, path, handler in kb_declaration:
        name = handler.__name__
        if method == "GET" and path == "/kb/list":
            cases.append((method, path + "?project_id=wire1-no-proj", None,
                          None, None, name, 200))
        elif method == "GET" and path == "/kb/manifest":
            cases.append((method,
                          path + "?kb_id=wire1-no-kb&query=q", None,
                          None, None, name, 500))
        elif method == "GET" and path == "/kb/section":
            cases.append((method,
                          path + "?kb_id=wire1-no-kb&section_id=wire1-sec",
                          None, None, None, name, 500))
        else:
            cases.append((method, path, {}, None, None, name, 401))
    for path, entry, payload, kind in _bench_cases():
        bench_method = ("GET" if kind in ("bench-get", "bench-refused",
                                                     "bench-scan-empty")
                        else "POST")
        cases.append((bench_method, path, payload,
                      headers if kind == "bench-post" else None,
                      _bench_mod, entry, kind))
    for key, dotted in _stage_mod.REALIZATION_MAP.items():
        method, _, path = key.partition(" ")
        attr = dotted.rpartition(".")[2]
        owner_name, _, _ = dotted.rpartition(".")
        owner = sys.modules.get(owner_name)
        if owner is None:
            owner = __import__(owner_name, fromlist=["*"])
        payload, kind = _stage_payload(path)
        if path == "/api/v1/teststage/runs/counters":
            path = path + "?run_id=wire1-nope"
        cases.append((method, path, payload, None, owner, attr, kind))
    # K04 cases (runtime-read): method+template+name from the live ROUTES
    # declaration wrapped above; only the safe payload + exact expected
    # status are fixed per template (the file's own _stage_payload
    # pattern). Templates drive concrete paths; registration is asserted
    # on the template in the K04 loop below.
    k04_cases = []
    for method, path, name, _fn in k04_declaration:
        payload, hdrs, expected = _k04_payload(method, path, headers)
        k04_cases.append((method.upper(), _k04_drive_path(path), path,
                          payload, hdrs, name, expected))

    with contextlib.ExitStack() as stack:
        spies = {}
        by_entry = {}
        for method, path, payload, hdrs, owner, entry, kind in cases:
            if owner is not None:
                if (owner, entry) not in by_entry:
                    original = getattr(owner, entry)
                    # Signature-preserving call-through spy: a wraps-MagicMock
                    # erases the entry signature, so request-time handler
                    # introspection binds kwargs={} (stage entries 400).
                    # One patch per entry: a second patch would autospec
                    # the installed spy instead of the real entry.
                    through = unittest.mock.create_autospec(
                        original, side_effect=original)
                    by_entry[(owner, entry)] = stack.enter_context(
                        unittest.mock.patch.object(owner, entry, through))
                spies[(method, path)] = by_entry[(owner, entry)]
        for method, path, payload, hdrs, owner, entry, kind in cases:
            bare = path.split("?")[0]
            assert (method, bare) in registered, (
                "%s %s is not registered in app.routes" % (method, path))
            resp = _drive(client, method, path, payload, hdrs)
            status, text = resp.status_code, resp.text
            if owner is None:
                assert entry in kb_calls, (
                    "%s %s did not reach entry %s" % (method, path, entry))
                assert status == kind, (
                    "%s %s -> %s: %s" % (method, path, status, text))
            else:
                spy = spies.get((method, path))
                if kind == "bench-scan-empty":
                    # Empty path short-circuits to [] WITHOUT calling
                    # scan_route (the refused-path case proves the entry).
                    assert status == 200, (
                        "%s %s -> %s: %s" % (method, path, status, text))
                    assert resp.json() == [], (
                        "%s %s body: %s" % (method, path, text))
                    assert not spy.called, (
                        "%s %s must not call scan_route" % (method, path))
                else:
                    assert spy is not None and spy.called, (
                        "%s %s did not reach entry %s" % (method, path, entry))
                    if kind == "ok2xx":
                        assert 200 <= status < 300, (
                            "%s %s -> %s: %s" % (method, path, status, text))
                    elif kind == "local-post":
                        refused = (400 <= status < 500
                                   and "SESSION_TOKEN_REFUSED" in text)
                        assert (200 <= status < 300) or refused, (
                            "%s %s -> %s: %s" % (method, path, status, text))
                    elif kind == "bench-get":
                        assert 200 <= status < 300, (
                            "%s %s -> %s: %s" % (method, path, status, text))
                    elif kind == "bench-post":
                        assert 400 <= status < 500, (
                            "%s %s -> %s: %s" % (method, path, status, text))
                    elif kind == "bench-refused":
                        assert 400 <= status < 500, (
                            "%s %s -> %s: %s" % (method, path, status, text))
                    elif kind == "stage-ok":
                        assert (200 <= status < 300) or (
                            400 <= status < 500), (
                            "%s %s -> %s: %s" % (method, path, status, text))
                    else:
                        assert status == kind, (
                            "%s %s -> %s: %s" % (method, path, status, text))

    for method, drive, template, payload, hdrs, name, expected in k04_cases:
        assert (method, template) in registered, (
            "%s %s is not registered in app.routes" % (method, template))
        resp = _drive(client, method, drive, payload, hdrs)
        status, text = resp.status_code, resp.text
        assert name in k04_calls, (
            "%s %s did not reach entry %s" % (method, drive, name))
        assert status == expected, (
            "%s %s -> %s: %s" % (method, drive, status, text))


def test_wire1_unregistered_path_is_404(_wire1_clean):
    """Unregistered method+path pairs stay 404."""
    from fastapi.testclient import TestClient

    app = create_app(dict(TEST_SETTINGS))
    client = TestClient(app, raise_server_exceptions=False)
    for method, path in (("GET", "/api/v1/nope-wire1"),
                         ("POST", "/api/v1/nope-wire1")):
        resp = client.request(method, path)
        assert resp.status_code == 404, (
            "%s %s -> %s: %s (expected 404)"
            % (method, path, resp.status_code, resp.text))


def _bench_cases():
    """(path, entry, payload, kind) for the bench surface; entries are hit."""
    scan_refused = "/api/v1/local/bench/scan?path=/refused-wire1&allowlist="
    return [
        ("/api/v1/local/bench/scan", "scan_route", None,
         "bench-scan-empty"),
        # Empty path short-circuits to [] WITHOUT calling scan_route.
        (scan_refused, "scan_route", None, "bench-refused"),
        ("/api/v1/local/bench/estimate?model_id=m&level=Quick",
         "estimate_route", None, "bench-get"),
        ("/api/v1/local/bench/results?run_id=nope-wire1",
         "results_route", None, "bench-get"),
        ("/api/v1/local/bench/history", "history_route", None, "bench-get"),
        ("/api/v1/local/bench/check?endpoint=", "check_route", None,
         "bench-get"),
        ("/api/v1/local/bench/runs", "runs_route",
         {"model_id": "", "level": "Quick"}, "bench-post"),
        ("/api/v1/local/bench/runs/pause", "pause_route",
         {"run_id": "nope-wire1"}, "bench-post"),
        ("/api/v1/local/bench/runs/resume", "resume_route",
         {"run_id": "nope-wire1"}, "bench-post"),
        ("/api/v1/local/bench/runs/stop", "stop_route",
         {"run_id": "nope-wire1"}, "bench-post"),
        ("/api/v1/local/bench/import", "import_route",
         {"path": ""}, "bench-post"),
    ]


def _stage_payload(path):
    """Safe stage payload per route: entries are hit, lane state unchanged."""
    if path == "/api/v1/teststage/plans":
        return ({"catalog_ids": [], "project_id": "wire1",
                 "run_id": "wire1", "catalog_ref": "wire1",
                 "derived_by_model": "wire1"}, 400)
    if path == "/api/v1/teststage/permissions/ask":
        return ({"project_id": "wire1-proj-ask",
                 "asked_at": "2026-10-27T00:00:00+00:00"}, "stage-ok")
    if path == "/api/v1/teststage/runs/start":
        return ({"project_id": "wire1-p", "plan_id": "wire1-plan",
                 "run_id": "wire1-run-1"}, 200)
    if path == "/api/v1/teststage/runs/advance":
        # The entry IS reached: string annotations defeat handler coercion,
        # so the dict arrives raw and advance_stage raises AttributeError.
        return ({"run": {"run_id": "wire1-nope", "project_id": "wire1-p",
                         "plan_id": "wire1-plan", "state": "PLAN"},
                 "target_state": "RESULTS"}, 500)
    if path == "/api/v1/teststage/runs/results":
        return ({"run_id": "wire1-nope", "test_id": "wire1-t1",
                 "status": "PASS", "output_ref": None,
                 "reason": None}, 400)
    if path == "/api/v1/teststage/runs/counters":
        return (None, 200)
    if path == "/api/v1/teststage/runs/finish":
        return ({"run_id": "wire1-nope"}, 400)
    if path == "/api/v1/teststage/runs/refix":
        return ({"run_id": "wire1-nope", "failure_ids": [],
                 "requested_at": "2026-10-27T00:00:00+00:00"}, 400)
    if path == "/api/v1/teststage/runs/spend-leg":
        return ({"project_id": "wire1-p", "task_id": "wire1-t",
                 "run_id": "wire1-r", "estimated_amount": 6000.0,
                 "provider_request_ref": "wire1-pr", "model": "wire1-m"},
                400)
    if path == "/api/v1/teststage/runs/spend-settle":
        # The entry IS reached: string annotations defeat handler coercion,
        # so the dict arrives raw and settle_spend_leg raises AttributeError.
        return ({"settlement": {
            "settlement_id": "wire1-s", "reservation_id": "nope-wire1",
            "provider_usage_evidence_ref": None,
            "provider_request_ref": "wire1-pr", "dedupe_key": "wire1-dk",
            "actual_amount": 1.0, "status": "PENDING"}}, 500)
    if path == "/api/v1/teststage/ask/resume":
        return ({"run_id": "wire1-nope", "decision": "allow_once"}, 400)
    raise AssertionError("no safe payload for %s" % path)
