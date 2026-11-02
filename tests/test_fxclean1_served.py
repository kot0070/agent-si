"""FXCLEAN1 served proof: route floor, dead seams unimportable, unmounted.

testid fxclean1-served; drives the real seam app (create_app) plus the
frozen-style agent_si.sidecar import. PRE_REMOVAL_ROUTE_COUNT is the
create_app route count recorded BEFORE removal (commit 464160a deleted
the dead seam modules plus their tests); it is a FLOOR now, not an
exact number: later lanes add routes (268 served at int 23574c2), so
the count must never drop below it. The removed-module asserts fail
while the dead files exist (RED) and pass once they are gone (GREEN);
the removed-route assert fails if any dead seam path is ever mounted
again. No fakes: real create_app, real sidecar build_app.
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

PRE_REMOVAL_ROUTE_COUNT = 248

REMOVED_MODULES = [
    "agent_si.backend.orchestration.hierarchy_routes",
    "agent_si.backend.orchestration.hierarchy_claims",
    "agent_si.hierarchy_routes",
]


REMOVED_MODULES = [
    "agent_si.backend.orchestration.hierarchy_routes",
    "agent_si.backend.orchestration.hierarchy_claims",
    "agent_si.hierarchy_routes",
]

# Dead seam paths mounted by the modules deleted in commit 464160a
# (orchestration/hierarchy_routes.py mounted the bare /hierarchy/*
# paths; agent_si/hierarchy_routes.py mounted the /api/v1/hierarchy/*
# paths). /api/v1/hierarchy/control-plane is NOT listed: the live
# src/agent_si/backend/hierarchy_routes.py:222 still serves it.
REMOVED_ROUTE_PATHS = [
    "/hierarchy/emergency-restore",
    "/hierarchy/scopes/validate",
    "/hierarchy/parent-close",
    "/hierarchy/contributor-bindings",
    "/hierarchy/role-authority",
    "/hierarchy/scopes/distinct",
    "/hierarchy/route-plan",
    "/hierarchy/demand-queue",
    "/hierarchy/cap-queue",
    "/hierarchy/chain-activate",
    "/hierarchy/parts-disjoint",
    "/hierarchy/user-correction",
    "/hierarchy/offload-switch",
    "/hierarchy/combined-flow",
    "/hierarchy/decision-record",
    "/hierarchy/rejection-surface",
    "/hierarchy/sdk-transport",
    "/hierarchy/sdk-surface",
    "/hierarchy/run-config",
    "/hierarchy/target-flow",
    "/hierarchy/chain-guard",
    "/hierarchy/schema",
    "/hierarchy/project",
    "/hierarchy/projects",
    "/hierarchy/project-disk-write",
    "/hierarchy/project-disk-read",
    "/hierarchy/gate-threshold",
    "/hierarchy/gate-verdict",
    "/api/v1/hierarchy/delta-intake",
    "/api/v1/hierarchy/delta-close",
    "/api/v1/hierarchy/phase-gate",
    "/api/v1/hierarchy/part-register",
    "/api/v1/hierarchy/ledger-nudge",
    "/api/v1/hierarchy/decomposition-record",
    "/api/v1/hierarchy/team-sizing",
    "/api/v1/hierarchy/team-config-change",
    "/api/v1/hierarchy/multi-manager-settings",
    "/api/v1/hierarchy/closed-part-ref",
    "/api/v1/hierarchy/ledger-roundtrip",
    "/api/v1/hierarchy/sdk-transport",
    "/api/v1/hierarchy/sdk-surface",
    "/api/v1/hierarchy/run-config",
    "/api/v1/hierarchy/target-flow",
    "/api/v1/hierarchy/plan",
    "/api/v1/hierarchy/dispatch",
    "/api/v1/hierarchy/issue",
]


def _make_app():
    return create_app(
        {"testing": True, "ui_session_token": "fxclean1-served-token"})


def test_route_count_never_shrinks():
    app = _make_app()
    assert len(app.routes) >= PRE_REMOVAL_ROUTE_COUNT


def test_removed_routes_not_mounted():
    app = _make_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    mounted = [p for p in REMOVED_ROUTE_PATHS if p in paths]
    assert not mounted, "dead seam routes mounted again: %r" % (mounted,)


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
