"""FXHIGH item 3: pool mode with no members is a plain 400, nothing stored.

RED: set_role with mode "pool" and no pool members currently stores the
profile (pass) and leaves resolve to BLOCK later. Expected: 400
{"error": "pool needs at least one member"} before anything is stored.
"""
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
_WS = os.path.dirname(_TESTS_DIR)
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import pools_routes as PR  # noqa: E402
from agent_si.routing import roles as RL  # noqa: E402
from agent_si.routing import store as ST  # noqa: E402

_PROJ = "fxhigh-pool-proj"


def _ctx(tmp_path):
    return PR.RoutingCtx(
        store=ST.RoutingStore(str(tmp_path / "data")),
        role_table=RL.RoleTable(),
        kb=None)


def test_pool_mode_without_members_is_400(tmp_path):
    ctx = _ctx(tmp_path)
    status, payload = PR.set_role(ctx, {}, {
        "project_id": _PROJ, "role": "worker", "mode": "pool"})
    assert status == 400
    assert payload == {"error": "pool needs at least one member"}
    assert ctx.role_table.get_profile(_PROJ, "worker") is None
    assert ctx.store.get_pool(_PROJ, "worker") is None


def test_pool_mode_with_empty_list_is_400(tmp_path):
    ctx = _ctx(tmp_path)
    status, payload = PR.set_role(ctx, {}, {
        "project_id": _PROJ, "role": "worker", "mode": "pool", "pool": []})
    assert status == 400
    assert payload == {"error": "pool needs at least one member"}
    assert ctx.role_table.get_profile(_PROJ, "worker") is None
    assert ctx.store.get_pool(_PROJ, "worker") is None


def test_pool_mode_with_members_still_stores(tmp_path):
    ctx = _ctx(tmp_path)
    status, payload = PR.set_role(ctx, {}, {
        "project_id": _PROJ, "role": "worker", "mode": "pool",
        "pool": [{"provider": "pa", "model": "pa/a-1"}]})
    assert status == 200, payload
    assert payload["binding"] is not None
    assert ctx.role_table.get_profile(_PROJ, "worker") is not None
    assert ctx.store.get_pool(_PROJ, "worker") is not None
