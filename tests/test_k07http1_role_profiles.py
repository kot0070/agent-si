# K07HTTP1 role-profile routing-store tests (RED first, then GREEN).
# Proves the 7 K07 DOUBLE rows' backend leg: GET plus PUT on the role path
# over the REAL handlers, with the session-token write guard, one row per
# role per project persisted in the JSON-file routing store (restart keeps
# rows, other project unaffected), and unknown roles refused, never stored.
# Handler level (the K02 header binding is carried by ctx.session_token;
# the URL query is never a token channel) plus mount level (PR.mount picks
# up the new PUT row with app.py untouched).
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
    rows = [(m, p, n) for m, p, n, _f in
            PR.ROUTES + PR._LEGACY_ROUTES]
    assert ("put", ROLE_PATH, "set_role_put") in rows
    fn = served_put()
    assert callable(fn)
    assert getattr(fn, "__name__", "") == "guarded_set_role_put"
    assert getattr(fn, "__wrapped__", None) is PR.set_role


def test_put_without_token_refused_401(tmp_path):
    ctx = make_ctx(tmp_path)
    status, payload = put_profile(ctx, "p1", "worker", "AUTO")
    assert status == 401, payload
    assert payload.get("code") == "CONTEXT_MISSING"
    assert ctx.role_table.get_profile("p1", "worker") is None


def test_put_query_only_token_ignored_and_refused_401(tmp_path):
    ctx = make_ctx(tmp_path)
    status, payload = served_put()(
        ctx, {"session_token": "query-only-token"},
        {"project_id": "p1", "role": "worker", "mode": "AUTO"})
    assert status == 401, payload
    assert ctx.role_table.get_profile("p1", "worker") is None


def test_put_then_get_roundtrip(tmp_path):
    ctx = make_ctx(tmp_path, session_token="tok-k07")
    status, payload = put_profile(
        ctx, "p1", "worker", "PINNED", "pa", "pa/a-1")
    assert status == 200, payload
    assert payload["ok"] is True
    # Backend shape: src/agent_si/backend/pools_routes.py:96 (_profile_payload).
    assert payload["profile"] == {
        "role": "worker", "project_id": "p1", "mode": "PINNED",
        "provider": "pa", "model": "pa/a-1", "binding": "DEFAULT",
        "version": 1}
    status, payload = served_get()(
        ctx, {"project_id": "p1", "role": "worker"}, None)
    assert status == 200, payload
    assert payload["profile"]["mode"] == "PINNED"
    assert payload["profile"]["provider"] == "pa"
    assert payload["profile"]["model"] == "pa/a-1"


def test_restart_keeps_rows_other_project_unaffected(tmp_path):
    ctx = make_ctx(tmp_path, session_token="tok-k07")
    status, _payload = put_profile(
        ctx, "p1", "worker", "PINNED", "pa", "pa/a-1")
    assert status == 200, _payload
    # Fresh ctx on the same store dir keeps rows (restart persistence).
    fresh = make_ctx(tmp_path, session_token="tok-k07")
    status, payload = served_get()(
        fresh, {"project_id": "p1", "role": "worker"}, None)
    assert status == 200, payload
    assert payload["profile"]["provider"] == "pa"
    # The other project is unaffected (no row leaks across projects).
    status, _payload = served_get()(
        fresh, {"project_id": "p2", "role": "worker"}, None)
    assert status == 404, _payload


def test_manager_pinned_persists_fixed_manager_fields(tmp_path):
    ctx = make_ctx(tmp_path, session_token="tok-k07")
    status, payload = put_profile(
        ctx, "p1", "manager", "PINNED", "pa", "pa/a-1")
    assert status == 200, payload
    assert payload["manager_profile"] == {
        "provider": "pa", "model": "pa/a-1", "version": 1}
    fresh = make_ctx(tmp_path, session_token="tok-k07")
    status, payload = served_get()(
        fresh, {"project_id": "p1", "role": "manager"}, None)
    assert status == 200, payload
    assert payload["profile"]["mode"] == "PINNED"
    assert payload["profile"]["provider"] == "pa"
    assert payload["profile"]["model"] == "pa/a-1"


def test_unknown_role_refused_never_stored(tmp_path):
    ctx = make_ctx(tmp_path, session_token="tok-k07")
    status, payload = put_profile(ctx, "p1", "stranger", "AUTO")
    assert status == 400, payload
    assert "unknown role" in payload.get("error", "")
    assert ctx.role_table.get_profile("p1", "stranger") is None
    assert ctx.store.get_role_profile("p1", "stranger") is None
    status, payload = served_get()(
        ctx, {"project_id": "p1", "role": "stranger"}, None)
    assert status == 400, payload


def test_mount_picks_up_put_row(tmp_path):
    ctx = make_ctx(tmp_path)

    class FakeApp:
        def __init__(self):
            self.gets = []
            self.posts = []
            self.puts = []

        def get(self, path):
            def deco(fn):
                self.gets.append(path)
                return fn
            return deco

        def post(self, path):
            def deco(fn):
                self.posts.append(path)
                return fn
            return deco

        def put(self, path):
            def deco(fn):
                self.puts.append(path)
                return fn
            return deco

    app = FakeApp()
    PR.mount(app, ctx)
    assert ROLE_PATH in app.puts
    assert ROLE_PATH in app.gets
