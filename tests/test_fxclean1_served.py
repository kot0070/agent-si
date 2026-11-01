"""FXCLEAN1 served proof: route count frozen, dead seams unimportable.

testid fxclean1-served; drives the real seam app (create_app) plus the
frozen-style agent_si.sidecar import. PRE_REMOVAL_ROUTE_COUNT is the
create_app route count recorded BEFORE removal (dead seams were never
mounted, so the count is identical after removal). The removed-module
asserts fail while the dead files exist (RED) and pass once they are
gone (GREEN). No fakes: real create_app, real sidecar build_app.
"""

import importlib
import os
import sys

import pytest

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend.app import create_app  # noqa: E402

PRE_REMOVAL_ROUTE_COUNT = 245

REMOVED_MODULES = [
    "agent_si.backend.orchestration.hierarchy_routes",
    "agent_si.backend.orchestration.hierarchy_claims",
    "agent_si.hierarchy_routes",
]


def _make_app():
    return create_app(
        {"testing": True, "ui_session_token": "fxclean1-served-token"})


def test_route_count_frozen():
    app = _make_app()
    assert len(app.routes) == PRE_REMOVAL_ROUTE_COUNT


def test_removed_modules_not_importable():
    for name in REMOVED_MODULES:
        with pytest.raises(ImportError):
            importlib.import_module(name)


def test_create_app_builds():
    app = _make_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/v1/public-text/check" in paths
    assert "/api/v1/contributions" in paths


def test_sidecar_import_and_build():
    import agent_si.sidecar as sidecar  # noqa: E402

    app = sidecar.build_app()
    assert len(app.routes) > PRE_REMOVAL_ROUTE_COUNT
