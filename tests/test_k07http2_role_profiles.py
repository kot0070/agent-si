# K07HTTP2 role-profile routing-store test (backend leg of the 7 K07 rows).
# Proves GET plus PUT on the role path over the REAL handlers with the
# session-token write guard, one row per role per project persisted in the
# JSON-file routing store (restart keeps rows, other project unaffected).
# Handler shapes: src/agent_si/backend/pools_routes.py:96 (_profile_payload),
# :343 (get_role read), :359 (set_role write); guard at :1247 plus :1204
# (_USER_WRITE_METHODS). Mount level: PR.mount picks up the PUT row.
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import pools_routes as PR
from agent_si.routing import roles as RL
from agent_si.routing import store as ST

ROLE_PATH = "/api/v1/routing/role"


def make_ctx(tmp_path, *, session_token=None):
    store = ST.RoutingStore(str(tmp_path / "data"))
    ctx = PR.RoutingCtx(store=store, role_table=RL.RoleTable(store), kb=None)
    if session_token is not None:
        ctx.session_token = session_token
    return ctx


def served_put():
    return PR._DISPATCH[("put", ROLE_PATH)]


def served_get():
    return PR._DISPATCH[("get", ROLE_PATH)]


def put_profile(ctx, project_id, role, mode, provider=None, model=None):
    body = {"project_id": project_id, "role": role, "mode": mode}
    if provider is not None:
        body["provider"] = provider
    if model is not None:
        body["model"] = model
    return served_put()(ctx, {}, body)


def test_put_row_registered_and_guarded(tmp_path):
    rows = [(m, p, n) for m, p, n, _f in PR.ROUTES + PR._LEGACY_ROUTES]
    assert ("put", ROLE_PATH, "set_role_put") in rows
    fn = served_put()
    assert callable(fn)
    assert getattr(fn, "__name__", "") == "guarded_set_role_put"
    assert getattr(fn, "__wrapped__", None) is PR.set_role


def test_put_without_token_refused_401(tmp_path):
    ctx = make_ctx(tmp_path)
    status, payload = put_profile(ctx, "h2p1", "worker", "AUTO")
    assert status == 401, payload
    assert payload.get("code") == "CONTEXT_MISSING"
    assert ctx.role_table.get_profile("h2p1", "worker") is None


def test_put_then_get_roundtrip(tmp_path):
    ctx = make_ctx(tmp_path, session_token="tok-k07-h2")
    status, payload = put_profile(
        ctx, "h2p1", "worker", "PINNED", "pa", "pa/h2-1")
    assert status == 200, payload
    assert payload["ok"] is True
    # Backend shape: src/agent_si/backend/pools_routes.py:96.
    assert payload["profile"] == {
        "role": "worker", "project_id": "h2p1", "mode": "PINNED",
        "provider": "pa", "model": "pa/h2-1", "binding": "DEFAULT",
        "version": 1}
    status, payload = served_get()(
        ctx, {"project_id": "h2p1", "role": "worker"}, None)
    assert status == 200, payload
    assert payload["profile"]["mode"] == "PINNED"
    assert payload["profile"]["provider"] == "pa"


def test_restart_keeps_rows_other_project_unaffected(tmp_path):
    ctx = make_ctx(tmp_path, session_token="tok-k07-h2")
    assert put_profile(
        ctx, "h2p1", "manager", "PINNED", "pa", "pa/h2-1")[0] == 200
    assert put_profile(ctx, "h2p1", "worker", "AUTO")[0] == 200
    fresh = make_ctx(tmp_path, session_token="tok-k07-h2")
    status, payload = served_get()(
        fresh, {"project_id": "h2p1", "role": "manager"}, None)
    assert status == 200, payload
    assert payload["profile"]["model"] == "pa/h2-1"
    status, payload = served_get()(
        fresh, {"project_id": "h2p1", "role": "worker"}, None)
    assert status == 200, payload
    assert payload["profile"]["mode"] == "AUTO"
    status, _payload = served_get()(
        fresh, {"project_id": "h2p2", "role": "manager"}, None)
    assert status == 404, _payload


def test_unknown_role_refused_never_stored(tmp_path):
    ctx = make_ctx(tmp_path, session_token="tok-k07-h2")
    status, payload = put_profile(ctx, "h2p1", "stranger", "AUTO")
    assert status == 400, payload
    assert ctx.store.get_role_profile("h2p1", "stranger") is None
