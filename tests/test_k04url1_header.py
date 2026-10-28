# K04URL1 M-HEADER: K04 USER routes read the UI session token ONLY from
# the x-ui-session-token header (+ server ctx binding). A query
# ?session_token never authenticates (refused, value unused, unlogged).
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import pools_routes as PR
from agent_si.routing import kb_port as KB
from agent_si.routing import roles as RL
from agent_si.routing import store as ST

APP_TOKEN = "mheader-app-token"
QUERY_ONLY_TOKEN = "user-query-only-token"


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


def make_ctx(tmp_path, *, session_token=None):
    kb = FakeKb({("pa", "pa/a-1"): make_facts("pa", "pa/a-1")})
    ctx = PR.RoutingCtx(store=ST.RoutingStore(str(tmp_path / "data")),
                        role_table=RL.RoleTable(), kb=kb)
    if session_token is not None:
        ctx.session_token = session_token
    return ctx


def served_frozen(method, path):
    table = {(m.upper(), p): fn for m, p, _n, fn in PR.ROUTES}
    return table[(method.upper(), path)]


def served_legacy(method, path):
    return PR._DISPATCH[(method.lower(), path)]


VALID_POOL_BODY = {"project_id": "p1", "role": "worker", "mode": "AUTO",
                   "provider": None, "model": None, "pool": [],
                   "strategy": "AUTO"}


def test_header_ctx_bound_accepted(tmp_path):
    ctx = make_ctx(tmp_path, session_token="hdr-ctx-1")
    fn = served_frozen("PUT", "/api/v1/roles/pools")
    status, payload = fn(ctx, {}, dict(VALID_POOL_BODY))
    assert status == 200, payload
    assert payload["profile"]["mode"] == "AUTO"


def test_query_only_refused_401(tmp_path):
    ctx = make_ctx(tmp_path)
    fn = served_frozen("PUT", "/api/v1/roles/pools")
    status, payload = fn(ctx, {"session_token": QUERY_ONLY_TOKEN},
                         dict(VALID_POOL_BODY))
    assert status == 401, payload
    assert payload.get("code") == "CONTEXT_MISSING", payload
    assert QUERY_ONLY_TOKEN not in str(payload), payload


def test_no_token_write_refused_401(tmp_path):
    ctx = make_ctx(tmp_path)
    fn = served_frozen("PUT", "/api/v1/roles/pools")
    status, payload = fn(ctx, {}, dict(VALID_POOL_BODY))
    assert status == 401, payload
    assert payload.get("code") == "CONTEXT_MISSING", payload


def test_legacy_query_only_refused_401(tmp_path):
    ctx = make_ctx(tmp_path)
    fn = served_legacy("post", "/api/v1/routing/role")
    body = {"project_id": "p1", "role": "worker", "mode": "PINNED",
            "provider": "pa", "model": "pa/a-1"}
    status, payload = fn(ctx, {"session_token": QUERY_ONLY_TOKEN}, body)
    assert status == 401, payload
    assert payload.get("code") == "CONTEXT_MISSING", payload
    assert QUERY_ONLY_TOKEN not in str(payload), payload


def make_client(tmp_path):
    from agent_si.backend.app import create_app
    import fastapi.testclient
    app = create_app({"store_dir": str(tmp_path / "appdata"),
                      "ui_session_token": APP_TOKEN})
    return fastapi.testclient.TestClient(app)


def test_app_query_only_refused_401(tmp_path):
    client = make_client(tmp_path)
    resp = client.put("/api/v1/roles/pools?session_token=" + QUERY_ONLY_TOKEN,
                      json=dict(VALID_POOL_BODY))
    assert resp.status_code == 401, resp.text
    assert QUERY_ONLY_TOKEN not in resp.text


def test_app_no_token_write_refused_401(tmp_path):
    client = make_client(tmp_path)
    resp = client.put("/api/v1/roles/pools", json=dict(VALID_POOL_BODY))
    assert resp.status_code == 401, resp.text


def test_app_header_bound_write_accepted_query_ignored(tmp_path):
    client = make_client(tmp_path)
    resp = client.put("/api/v1/roles/pools", json=dict(VALID_POOL_BODY),
                      headers={"x-actor": "ui-probe",
                               "x-ui-session-token": "ui-probe"})
    assert resp.status_code == 200, resp.text
    bad = client.put("/api/v1/roles/pools?session_token=" + QUERY_ONLY_TOKEN,
                     json=dict(VALID_POOL_BODY),
                     headers={"x-actor": "ui-probe"})
    assert bad.status_code in (401, 403), bad.text
    assert QUERY_ONLY_TOKEN not in bad.text
