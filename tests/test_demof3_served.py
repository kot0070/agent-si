"""DEMOF3 served proof: GET /api/v1/routing/auto over the frozen seams.

testid demof3-served; RED first (route missing -> 404), then GREEN.

Contract (derived from the repo, frozen here):
- 200 case: response is exactly {"manager", "model"} and equals the
  seam-resolved choice: first candidates_for_auto entry for the
  connected providers, verified through loader.find_row, bound through
  roles.resolve_manager (no literals invented here).
- 422 case: unknown task_type is refused. Param names follow the
  existing k04n4 convention (budget/routes.py k04n4_kb_auto):
  `task_type` (default "coding", known {"coding", "general"} from
  loader.auto_fit_price_quality default + orchestration/graph.py
  default task_class) and comma-separated `connected` providers.
"""

import os
import sys

from fastapi.testclient import TestClient

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.model_kb import kb as _kb  # noqa: E402
from agent_si.model_kb import loader as _loader  # noqa: E402

try:
    from agent_si.backend import routing_auto as _seam
    _SEAM_ERROR = None
except Exception as err:  # seam unserved: every test below fails RED
    _seam = None
    _SEAM_ERROR = err

TEST_TOKEN = "demof3-served-token"

_META_MODEL = "meta/muse-spark-1.3-contributor"


def _test_catalog():
    rows = [
        _kb.make_model_row("openai", "gpt-4o"),
        _kb.make_model_row("meta", _META_MODEL),
    ]
    return _kb.make_catalog(rows, kb_version=1, updated_at="2026-10-31",
                            change_log=[], sources=[])


def make_client():
    app = create_app({"testing": True, "ui_session_token": TEST_TOKEN})
    mounted = any(getattr(route, "path", None) == "/api/v1/routing/auto"
                  for route in getattr(app, "routes", []))
    if not mounted and _seam is not None and hasattr(
            _seam, "register_routing_auto_routes"):
        _seam.register_routing_auto_routes(app)
    return TestClient(app)


def setup_function(_func):
    _previous = _kb.bound_catalog()
    _func._demof3_previous = _previous
    _kb.bind_catalog(_test_catalog())


def teardown_function(func):
    _kb.bind_catalog(func._demof3_previous)


def _expected_choice(connected):
    catalog = _kb.bound_catalog()
    auto = _loader.candidates_for_auto(catalog, connected)
    for cand in auto["candidates"]:
        row = _loader.find_row(
            catalog, cand.get("provider_id"), cand.get("model_id"))
        assert row is not None
        return {"manager": cand.get("provider_id"),
                "model": cand.get("model_id")}
    raise AssertionError("no seam-resolved choice for %r" % (connected,))


def test_demof3_served_auto_200():
    """GET /api/v1/routing/auto 200 with the seam-resolved manager+model."""
    client = make_client()
    resp = client.get("/api/v1/routing/auto",
                      params={"task_type": "coding",
                              "connected": "meta"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == _expected_choice(["meta"])
    assert resp.json() == {"manager": "meta", "model": _META_MODEL}


def test_demof3_served_auto_unknown_task_422():
    """GET /api/v1/routing/auto with an unknown task_type -> 422."""
    client = make_client()
    resp = client.get("/api/v1/routing/auto",
                      params={"task_type": "teleport",
                              "connected": "meta"})
    assert resp.status_code == 422, resp.text
