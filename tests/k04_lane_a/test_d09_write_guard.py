# K04 D9 — USER-write session-token guard tests (one per write route).
# Token-less USER writes are refused 401/CONTEXT_MISSING (K13 route-guard
# family; 401 matches the provider lane's own token-less-delete refusal);
# reads need no token. With-token requests reach the real handlers.
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import pools_routes as PR
from agent_si.routing import kb_port as KB
from agent_si.routing import roles as RL
from agent_si.routing import store as ST

TOKEN = {"session_token": "ui-sess-1"}


class FakeKb(KB.KbReader):
    # FAKE-OF: agent_si.routing.kb_port.KbReader
    def __init__(self, facts):
        self._facts = dict(facts)

    def facts(self, provider, model):
        return self._facts.get((provider, model))

    def models(self, provider=None):
        return [f for (p, _m), f in self._facts.items()
                if provider is None or p == provider]


def make_facts(provider, model):
    return KB.KbModelFacts(
        provider=provider, model=model,
        task_fit={"coding": 0.9, "text": 0.9, "general": 0.9},
        strict_pass_rate=0.9, tolerant_pass_rate=0.9,
        sample_count=50, confidence=0.9, freshness="CURRENT",
        input_price=0.01, output_price=0.03,
        modalities=("text", "tools", "coding"), assessed_risk="LOW",
        fields_state="MEASURED", verified_static=False,
        source="fake", measured_at="2026-01-01T00:00:00+00:00",
        latency_ms=400.0)


def make_ctx(tmp_path):
    kb = FakeKb({("pa", "pa/a-1"): make_facts("pa", "pa/a-1")})
    return PR.RoutingCtx(store=ST.RoutingStore(str(tmp_path / "data")),
                         role_table=RL.RoleTable(), kb=kb)


def served_frozen(method, path):
    table = {(m.upper(), p): fn for m, p, _n, fn in PR.ROUTES}
    return table[(method.upper(), path)]


def served_legacy(method, path):
    return PR._DISPATCH[(method.lower(), path)]


def refused(status, payload):
    assert status == 401, payload
    assert payload.get("code") == "CONTEXT_MISSING", payload


def test_write_guard_put_role_pools(tmp_path):
    ctx = make_ctx(tmp_path)
    fn = served_frozen("PUT", "/api/v1/roles/pools")
    body = {"project_id": "p1", "role": "worker", "mode": "AUTO",
            "provider": None, "model": None, "pool": [], "strategy": "AUTO"}
    refused(*fn(ctx, {}, body))
    refused(*fn(ctx, TOKEN, body))
    ctx.session_token = "ui-sess-1"
    status, payload = fn(ctx, {}, body)
    assert status == 200, payload
    assert payload["profile"]["mode"] == "AUTO"


def test_write_guard_set_role(tmp_path):
    ctx = make_ctx(tmp_path)
    fn = served_legacy("post", "/api/v1/routing/role")
    body = {"project_id": "p1", "role": "worker", "mode": "PINNED",
            "provider": "pa", "model": "pa/a-1"}
    refused(*fn(ctx, {}, body))
    refused(*fn(ctx, TOKEN, body))
    ctx.session_token = "ui-sess-1"
    status, payload = fn(ctx, {}, body)
    assert status == 200, payload
    assert ctx.role_table.get_profile("p1", "worker").model == "pa/a-1"


def test_write_guard_post_pick(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.keymaps[("p1", "worker")] = {"k1": ("pa", "pa/a-1")}
    fn = served_legacy("post", "/api/v1/routing/pick")
    body = {"project_id": "p1", "role": "worker", "key": "k1"}
    refused(*fn(ctx, {}, body))
    refused(*fn(ctx, TOKEN, body))
    ctx.session_token = "ui-sess-1"
    status, payload = fn(ctx, {}, body)
    assert status == 200, payload
    assert payload["profile"]["mode"] == "PINNED"


def test_write_guard_post_decide(tmp_path):
    # PINNED with no stored profile: the handler should answer BLOCKED
    # without touching the frozen select facade. At HEAD both decide
    # branches are broken by the concurrent router/roles re-freeze, outside
    # this task's scope (no handler-logic changes): the PINNED branch
    # passes a stale table= kwarg (defect D9-3, A2 lane) and the generic
    # AUTO path passes stale select kwargs (defect D9-1, A2/router lanes).
    # This test pins guard behavior only (401 leg).
    ctx = make_ctx(tmp_path)
    fn = served_legacy("post", "/api/v1/routing/decide")
    body = {"project_id": "p1", "task_id": "t1", "run_id": "r1",
            "role": "worker", "mode": "PINNED",
            "candidates": [{"provider": "pa", "model": "pa/a-1"}]}
    refused(*fn(ctx, {}, body))
    refused(*fn(ctx, TOKEN, body))
    ctx.session_token = "ui-sess-1"
    status, payload = fn(ctx, {}, body)
    assert status == 200, payload
    assert payload["decision_id"], payload
    assert payload["status"] == "BLOCKED", payload


def test_write_guard_connect(tmp_path):
    ctx = make_ctx(tmp_path)
    fn = served_frozen("POST", "/api/v1/providers/connect")
    refused(*fn(ctx, {}, {}))
    refused(*fn(ctx, TOKEN, {}))
    ctx.session_token = "ui-sess-1"
    status, payload = fn(ctx, {}, {})
    assert status == 400, payload
    assert "preset_id" in payload["error"], payload


def test_write_guard_disconnect(tmp_path):
    ctx = make_ctx(tmp_path)
    fn = served_frozen("POST", "/api/v1/providers/{id}/disconnect")
    refused(*fn(ctx, {"id": "nope"}, {}))
    refused(*fn(ctx, dict(TOKEN, id="nope"), {}))
    ctx.session_token = "ui-sess-1"
    status, payload = fn(ctx, {"id": "nope"}, {})
    assert status == 404, payload


def test_write_guard_kb_apply(tmp_path):
    ctx = make_ctx(tmp_path)
    fn = served_frozen("POST", "/api/v1/kb/proposals/apply")
    body = {"proposal_id": "kb-prop-404", "approved_by_user": True}
    refused(*fn(ctx, {}, body))
    refused(*fn(ctx, TOKEN, body))
    ctx.session_token = "ui-sess-1"
    status, payload = fn(ctx, {}, body)
    assert status == 404, payload


def test_write_guard_ctx_bound_token(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.session_token = "bound-1"
    fn = served_frozen("PUT", "/api/v1/roles/pools")
    status, payload = fn(ctx, {}, {
        "project_id": "p1", "role": "worker", "mode": "AUTO",
        "provider": None, "model": None, "pool": [], "strategy": "AUTO"})
    assert status == 200, payload


def test_reads_need_no_token(tmp_path):
    ctx = make_ctx(tmp_path)
    status, _payload = served_frozen(
        "GET", "/api/v1/providers")(ctx, {}, None)
    assert status == 200
    status, _payload = served_frozen(
        "GET", "/api/v1/kb/status")(ctx, {}, None)
    assert status == 200
