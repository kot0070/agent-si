"""FXR2E-3: write-route session sweep over create_app (RED-first).

Every POST/PUT/PATCH/DELETE under /api/v1/ runs with an actor but
without a session token: the route must refuse (400/403). Anything
else must appear in ALLOWLIST with a per-line reason (frozen served
contracts pinning unauthed answers, 401-style token-header guards,
pure proof lanes). The two FXR2E write routes (teststage
local-tests, kb validate) carry the check: 403 without a token, 200
with the bound token.
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agent_si.backend.app import create_app  # noqa: E402

TOKEN = "fxr2e-sweep-token"
ACTOR_HEADERS = {"x-actor": "fxr2e-sweep"}
AUTH_HEADERS = {"x-actor": "fxr2e-sweep", "x-ui-session-token": TOKEN}

_NO_TOKEN = "401 missing x-ui-session-token header; frozen guard"
_NO_SESSION = "401 session-token-missing; frozen guard"
_PROOF = "FXR2E proof lane: pure verdict, 422 on empty probe"

# (method, path) -> why a non-400/403 answer without a token is OK.
ALLOWLIST = {
    ("POST", "/api/v1/asks"): _NO_TOKEN + "; asks lane",
    ("POST", "/api/v1/asks/{ask_id}/approve"): _NO_TOKEN + "; asks lane",
    ("POST", "/api/v1/assurance/close_stage"):
        "frozen K03A pins unauthed 200 (test_fxassur1_served)",
    ("POST", "/api/v1/assurance/runner_contract"):
        "frozen DRF3K03A pins unauthed 200 (test_drf3k03a_assure)",
    ("POST", "/api/v1/automations/pause"): _NO_SESSION,
    ("POST", "/api/v1/automations/approvals/{approval_id}"): _NO_SESSION,
    ("POST", "/api/v1/automations/checkpoints/{checkpoint_id}/resume"):
        _NO_SESSION,
    ("POST", "/api/v1/automations/pause/project"): _NO_SESSION,
    ("POST", "/api/v1/automations/rules"): _NO_SESSION,
    ("PUT", "/api/v1/automations/rules/{rule_id}"): _NO_SESSION,
    ("POST", "/api/v1/automations/rules/{rule_id}/run"): _NO_SESSION,
    ("POST", "/api/v1/automations/runs"): _NO_SESSION,
    ("POST", "/api/v1/automations/runs/{id}/cancel"): _NO_SESSION,
    ("POST", "/api/v1/automations/runs/{id}/launch"): _NO_SESSION,
    ("POST", "/api/v1/automations/runs/{id}/resume"): _NO_SESSION,
    ("POST", "/api/v1/automations/templates/{id}/instantiate"):
        _NO_SESSION,
    ("POST", "/api/v1/automations/triggers/{id}/fire"): _NO_SESSION,
    ("POST", "/api/v1/chat/decision"): _NO_TOKEN + "; chat-approval lane",
    ("POST", "/api/v1/core/finalizations"): _NO_TOKEN + "; final lane",
    ("POST", "/api/v1/local/bench/import"): _NO_TOKEN + "; bench lane",
    ("POST", "/api/v1/local/bench/runs"): _NO_TOKEN + "; bench lane",
    ("POST", "/api/v1/local/bench/runs/complete"): _NO_TOKEN + "; bench",
    ("POST", "/api/v1/local/bench/runs/pause"): _NO_TOKEN + "; bench lane",
    ("POST", "/api/v1/local/bench/runs/resume"): _NO_TOKEN + "; bench",
    ("POST", "/api/v1/local/bench/runs/stop"): _NO_TOKEN + "; bench lane",
    ("POST", "/api/v1/local/arch-352/serve"): _PROOF,
    ("POST", "/api/v1/local/arch-367/serve"): _PROOF,
    ("POST", "/api/v1/local/arch-373/serve"): _PROOF,
    ("POST", "/api/v1/local/bp05-65/serve"): _PROOF,
    ("POST", "/api/v1/local/bp05-92/serve"): _PROOF,
    ("POST", "/api/v1/local/bp05-94/serve"): _PROOF,
    ("POST", "/api/v1/local/mvp-accept-50/serve"): _PROOF,
    ("POST", "/api/v1/local/mvp-accept-53/serve"): _PROOF,
    ("POST", "/api/v1/local/mvp-accept-221/serve"): _PROOF,
    ("POST", "/api/v1/local/mvp-accept-222/serve"): _PROOF,
    ("POST", "/api/v1/offload/maybe"):
        "frozen OCK02 pins unauthed 200 (test_ock02_hierarchy_offload)",
    ("POST", "/api/v1/outage/signal"): _NO_TOKEN + "; outage lane",
    ("POST", "/api/v1/permissions/decide"): _NO_TOKEN + "; permissions",
    ("POST", "/api/v1/permissions/project-grant"):
        "401 SESSION_TOKEN_MISSING; frozen FXR1B grant guard",
    ("DELETE", "/api/v1/permissions/project-grant"):
        "401 SESSION_TOKEN_MISSING; frozen FXR1B grant guard",
    ("POST", "/api/v1/portability/run"):
        "frozen K06OC pins actor-only 200 (test_k06open10_resume_demo)",
    ("POST", "/api/v1/qa/semantic_security"):
        "frozen K03NEXT pins unauthed verdict (test_k03next_served)",
    ("POST", "/api/v1/qa/semantic_security/lenient"):
        "frozen K03REST pins unauthed verdict (test_k03rest_served)",
    ("POST", "/api/v1/qa/sourcing_gate"):
        "frozen K03NEXT pins unauthed verdict (test_k03next_served)",
    ("POST", "/api/v1/qa/sourcing_gate/basic"):
        "frozen K03REST pins unauthed verdict (test_k03rest_served)",
    ("POST", "/api/v1/qa/sourcing_gate/scoped"):
        "frozen K03NEXT2 pins unauthed verdict (test_k03next2_served)",
    ("POST", "/api/v1/release/start/demo"):
        "frozen K10 pins unauthed demo drive (test_k10open4_start_path)",
    ("PUT", "/api/v1/roles/chat-model"): _NO_TOKEN + "; roles lane",
    ("POST", "/api/v1/services/{id}/check"): _NO_TOKEN + "; services lane",
    ("POST", "/api/v1/stop-all"): _NO_TOKEN + "; stop-all lane",
    ("POST", "/api/v1/tools/installs"):
        "frozen K06OC pins unauthed view (test_k06h1_secretref_chain)",
    ("POST", "/api/v1/tools/runs/attempt"):
        "frozen K06OC pins unauthed attempt (test_k06mh1_guard)",
    ("POST", "/api/v1/tools/runs/{run_id}/discard"):
        "frozen K06OC same lane as attempt",
    ("POST", "/api/v1/tools/runs/{run_id}/resume"):
        "frozen K06OC same lane as attempt",
    ("POST", "/api/v1/watcher/checkpoints/benchmark"):
        _NO_TOKEN + "; watcher lane",
    ("POST", "/api/v1/watcher/integrity-check"): _NO_TOKEN + "; watcher",
    ("POST", "/api/v1/watcher/rules/{id}/evaluate"):
        _NO_TOKEN + "; watcher lane",
    ("POST", "/api/v1/watcher/timers/{id}/fire"): _NO_TOKEN + "; watcher",
    ("POST", "/api/v1/watcher/timers/{id}/pause"):
        _NO_TOKEN + "; watcher lane",
}


def _write_routes(app):
    out = {}

    def add(routes):
        for route in routes:
            if type(route).__name__ == "_IncludedRouter":
                add(route.original_router.routes)
            else:
                for method in sorted(
                        getattr(route, "methods", set()) or []):
                    out.setdefault((method, getattr(route, "path", "?")),
                                   route)

    add(app.routes)
    targets = []
    for (method, path) in out:
        if method in ("POST", "PUT", "PATCH", "DELETE") \
                and path.startswith("/api/v1/"):
            targets.append((method, path))
    return sorted(set(targets), key=lambda item: item[1])


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SI_SECRET_STORE", "memory")
    app = create_app({"store_dir": str(tmp_path / "appdata"),
                      "secret_store": "memory",
                      "testing": True, "ui_session_token": TOKEN})
    return TestClient(app, raise_server_exceptions=False)


def test_write_routes_without_token_refuse_or_allowlisted(client):
    """No token -> 400/403, or an allowlisted reason per line."""
    failures = []
    for method, path in _write_routes(client.app):
        probe = path
        while "{" in probe:
            start = probe.index("{")
            end = probe.index("}", start)
            probe = probe[:start] + "t" + probe[end + 1:]
        if method in ("POST", "PUT", "PATCH"):
            resp = client.request(method, probe, json={},
                                  headers=ACTOR_HEADERS)
        else:
            resp = client.request(method, probe, headers=ACTOR_HEADERS)
        if resp.status_code in (400, 403):
            continue
        reason = ALLOWLIST.get((method, path))
        if reason:
            continue
        failures.append("{} {} -> {} {}".format(
            method, path, resp.status_code, resp.text[:120]))
    assert not failures, "unguarded write routes:\n" + "\n".join(failures)


@pytest.mark.parametrize("path,body", [
    ("/api/v1/teststage/local-tests",
     {"project_id": "fxr2e-sweep-proj", "enabled": True}),
    ("/api/v1/kb/validate", {"kb_dir": "nope"}),
])
def test_fxr2e_write_routes_check_session(client, path, body):
    """The two FXR2E routes: 403 without token, served with token."""
    refused = client.post(path, json=dict(body), headers=ACTOR_HEADERS)
    assert refused.status_code == 403, refused.text
    served = client.post(path, json=dict(body), headers=AUTH_HEADERS)
    assert served.status_code == 200, served.text
