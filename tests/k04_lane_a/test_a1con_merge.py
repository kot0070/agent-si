"""A1CON merge pins (lane A1 owned): the DELTA-1 leftover-keys merge is
import-order-proof and never disturbs the frozen served tuple.

Mechanics pinned here (no behavior, no frozen files):
- the served PR.ROUTES tuple is exactly the frozen 11 (leftover rides the
  served dispatch/legacy tables, never the frozen tuple);
- the leftover key resolves via the served PR._DISPATCH in this process;
- the served leftover list answers the exact {entries: [...]} shape;
- re-running the mount changes nothing (idempotent, no duplicate rows).
"""
import os
import sys
import types

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import pools_routes as PR
from agent_si.providers import registry as _regpkg
from agent_si.routing import interface as IF

LEFTOVER_KEY = ("get", "/api/v1/providers/leftover-keys")


def _served_pairs():
    return [(str(m).lower(), str(p)) for m, p, _n, _f in PR.ROUTES]


def test_a1con_served_routes_are_exactly_frozen():
    frozen = {(str(m).lower(), str(p)) for m, p in IF.HTTP_ROUTES}
    assert set(_served_pairs()) == frozen
    assert len(_served_pairs()) == len(set(_served_pairs())) == 11


def test_a1con_leftover_served_via_dispatch():
    assert LEFTOVER_KEY in PR._DISPATCH
    assert callable(PR._DISPATCH[LEFTOVER_KEY])


def test_a1con_served_leftover_list_shape():
    fn = PR._DISPATCH[LEFTOVER_KEY]
    status, payload = fn(types.SimpleNamespace(kb=None),
                         {"app_prefix": "app:"}, None)
    assert status == 200, payload
    assert set(payload) == {"entries"}
    assert payload["entries"] == []


def test_a1con_remount_idempotent_no_duplicates():
    before = (len(PR.ROUTES), len(PR._LEGACY_ROUTES),
              len(PR._DISPATCH_BASE))
    _regpkg._mount_leftover_route()
    _regpkg._mount_leftover_route()
    after = (len(PR.ROUTES), len(PR._LEGACY_ROUTES),
             len(PR._DISPATCH_BASE))
    assert before == after
    assert LEFTOVER_KEY in PR._DISPATCH
    legacy_hits = [1 for m, p, _n, _f in PR._LEGACY_ROUTES
                   if (str(m).lower(), str(p)) == LEFTOVER_KEY]
    assert len(legacy_hits) <= 1, legacy_hits
