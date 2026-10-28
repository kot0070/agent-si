"""HTTP token-refusal tests for the 3 USER POST watcher routes (RED until K02).

Through the K02 composition-root app seam (``create_app`` + TestClient):
each of POST /api/v1/watcher/integrity-check,
POST /api/v1/watcher/rules/rule-tamper/evaluate and POST /api/v1/stop-all
refuses requests without a session token and with a wrong session token
(401 or 403), leaving GET /api/v1/watcher/status unchanged. RED with
'create_app missing (K02 composition root)' until K02 lands in int.
"""

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

from agent_si.watcher.interface import WatcherError


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
    """Call one route through the K02 composition-root app (HD APP SEAM).

    Builds ``create_app(test settings)``, wraps it in TestClient and
    performs the client call. Fails RED with the exact SEAM RULE line when
    the composition root is not integrated.
    """
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


def _assert_refused(method, path, **kwargs):
    """Refused POST leaves GET status unchanged: 401-or-403 plus equal status json."""
    before = _seam_call("GET", "/api/v1/watcher/status", project_id="proj-a")
    refused = _seam_call(method, path, **kwargs)
    assert refused.status_code in (401, 403)
    after = _seam_call("GET", "/api/v1/watcher/status", project_id="proj-a")
    assert after.json() == before.json()


def test_http_integrity_check_refuses_without_token():
    _assert_refused("POST", "/api/v1/watcher/integrity-check",
                    project_id="proj-a")


def test_http_integrity_check_refuses_with_wrong_token():
    _assert_refused("POST", "/api/v1/watcher/integrity-check",
                    project_id="proj-a", session_token="token-wrong")


def test_http_rule_evaluate_refuses_without_token():
    _assert_refused("POST", "/api/v1/watcher/rules/rule-tamper/evaluate",
                    project_id="proj-a")


def test_http_rule_evaluate_refuses_with_wrong_token():
    _assert_refused("POST", "/api/v1/watcher/rules/rule-tamper/evaluate",
                    project_id="proj-a", session_token="token-wrong")


def test_http_stop_all_refuses_without_token():
    _assert_refused("POST", "/api/v1/stop-all", actor="user",
                    project_id="proj-a")


def test_http_stop_all_refuses_with_wrong_token():
    _assert_refused("POST", "/api/v1/stop-all", actor="user",
                    project_id="proj-a", session_token="token-wrong")
