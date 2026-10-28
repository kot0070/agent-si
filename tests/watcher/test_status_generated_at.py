"""Watcher status generated_at is the stored head stamp, not the request time.

Through the K02 composition-root app seam (``create_app`` + TestClient):
GET status, refused POST, GET status serve equal json (no state change),
then one real journal event moves generated_at.
"""

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

import agent_si.watcher.interface as iface
import agent_si.watcher.journal as _journal
import agent_si.watcher.status as _status
from agent_si.watcher.interface import WatcherError

# Wiring (same as tests/watcher/test_iface_contract.py:239): serve the real
# owning-lane realisation through the seam so GET status returns stored
# facts even when that module is not collected in the same run.
iface.get_status = _status.get


# FAKE-OF: backend auth-hook boundary (test settings only)
def _fake_auth_hook(token):
    """Boundary auth hook: only the live UI session token is accepted."""
    return token == "ui-live"


# FAKE-OF: backend rate-hook boundary (test settings only)
def _fake_rate_hook(key):
    """Boundary rate hook: test traffic is never throttled."""
    return True


# FAKE-OF: backend model_factory boundary (test settings only)
def _fake_model_factory(name):
    """Boundary model factory: no model calls in STEP1 seam tests."""
    raise WatcherError("RULE_NOT_FOUND")


def _seam_settings():
    """Test settings for the seam app: fakes only at the boundary hooks."""
    return {
        "env": "test",
        "auth_hook": _fake_auth_hook,
        "rate_hook": _fake_rate_hook,
        "model_factory": _fake_model_factory,
    }


def _seam_call(method, path, **kwargs):
    """Call one route through the K02 composition-root app (HD APP SEAM)."""
    try:
        from agent_si.backend.app import create_app
    except ImportError:
        pytest.fail("create_app missing (K02 composition root)")
    if not callable(create_app):
        pytest.fail("create_app missing (K02 composition root)")
    from fastapi.testclient import TestClient
    client = TestClient(create_app(_seam_settings()))
    if method == "GET":
        return client.get(path, params=kwargs)
    return client.post(path, json=kwargs)


def test_status_generated_at_stable_then_moves_on_new_event():
    """Refused write keeps status json equal; a real event moves the stamp."""
    before = _seam_call("GET", "/api/v1/watcher/status",
                        project_id="proj-gen-stamp")
    refused = _seam_call("POST", "/api/v1/watcher/integrity-check",
                         project_id="proj-gen-stamp")
    assert refused.status_code in (401, 403)
    after = _seam_call("GET", "/api/v1/watcher/status",
                       project_id="proj-gen-stamp")
    assert after.json() == before.json()
    _journal.append_event("proj-gen-stamp", "watcher", "SERVICE_STATE",
                          "stamp-moves", ())
    moved = _seam_call("GET", "/api/v1/watcher/status",
                       project_id="proj-gen-stamp")
    assert moved.json()["generated_at"] != before.json()["generated_at"]
