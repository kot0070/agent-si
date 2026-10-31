# K04 Lane A2 — pool picker + pools_routes tests (RED first, then GREEN).
# Self-sufficient: portable sys.path bootstrap, no other coder's files needed.
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.routing import interface as IF
from agent_si.routing import types as T
from agent_si.routing import router as R
from agent_si.routing import roles as RL
from agent_si.routing import pools as P
from agent_si.routing import kb_port as KB
from agent_si.routing import telemetry_port as TP
from agent_si.routing import store as ST
from agent_si.backend import pools_routes as PR


class FakeKb(KB.KbReader):
    # FAKE-OF: agent_si.routing.kb_port.KbReader
    def __init__(self, facts):
        self._facts = dict(facts)

    def facts(self, provider, model):
        return self._facts.get((provider, model))

    def models(self, provider=None):
        return [f for (p, _m), f in self._facts.items()
                if provider is None or p == provider]


def make_facts(provider, model, *, fit=0.9, quality=0.9, price_in=0.01,
               price_out=0.03, modalities=("text", "tools", "coding"),
               risk="LOW", state="MEASURED", static=False, sample=50,
               conf=0.9, fresh="CURRENT", latency_ms=400.0):
    return KB.KbModelFacts(
        provider=provider, model=model,
        task_fit={"coding": fit, "text": fit, "general": fit},
        strict_pass_rate=quality, tolerant_pass_rate=quality,
        sample_count=sample, confidence=conf, freshness=fresh,
        input_price=price_in, output_price=price_out,
        modalities=modalities, assessed_risk=risk,
        fields_state=state, verified_static=static,
        source="fake", measured_at="2026-01-01T00:00:00+00:00",
        latency_ms=latency_ms)


def pol(**kw):
    d = dict(policy_id="rp-1", version=1,
             created_at="2026-01-01T00:00:00+00:00", hash="h",
             task_class="coding", risk_level="LOW",
             strict_min=1.0, tolerant_min=0.85, confidence_min=0.7,
             sample_min=20, freshness_requirement="CURRENT",
             local_allowed=True, split_allowed=True, cloud_required=False)
    d.update(kw)
    return T.RoutingPolicy(**d)


def opt(**kw):
    d = dict(policy_id="op-1", version=1,
             created_at="2026-01-01T00:00:00+00:00", hash="h",
             required_quality=0.8, max_risk="HIGH",
             weight_quality=1.0, weight_cost=1.0, weight_latency=1.0,
             weight_cloud_tokens=1.0, local_preference=False,
             deadline=None, budget_limit=None)
    d.update(kw)
    return T.OptimizationPolicy(**d)


def three_provider_kb():
    return FakeKb({
        ("pa", "pa/a-1"): make_facts("pa", "pa/a-1", fit=0.90, quality=0.92,
                                     price_in=0.010, price_out=0.030),
        ("pb", "pb/b-1"): make_facts("pb", "pb/b-1", fit=0.90, quality=0.91,
                                     price_in=0.005, price_out=0.015),
        ("pc", "pc/c-1"): make_facts("pc", "pc/c-1", fit=0.90, quality=0.93,
                                     price_in=0.020, price_out=0.060),
    })


CAPS = {"pa": ("text", "tools", "coding"),
        "pb": ("text", "tools", "coding"),
        "pc": ("text", "tools", "coding")}


def healthy():
    return ({"pa": "ONLINE", "pb": "ONLINE", "pc": "ONLINE"},
            {("pa", "pa/a-1"): "READY", ("pb", "pb/b-1"): "READY",
             ("pc", "pc/c-1"): "READY"})


def base_request(role, **kw):
    d = dict(project_id="p1", task_id="t1", run_id="r1", role=role,
             task_class="coding",
             required_capabilities=("text", "tools"),
             required_modalities=("text",),
             task_risk="LOW", routing_policy=pol(), optimization_policy=opt(),
             candidates=(), mode="AUTO")
    d.update(kw)
    return R.RoutingRequest(**d)


def make_deps(kb, store=None, emitter=None, ph=None, mhmap=None):
    phealth, mhealth = healthy()
    phealth = dict(phealth)
    mhealth = dict(mhealth)
    if ph is not None:
        phealth.update(ph)
    if mhmap is not None:
        mhealth.update(mhmap)
    return R.RoutingDeps(
        kb=kb,
        provider_health={p: T.ProviderHealth(provider=p, status=s)
                         for p, s in phealth.items()},
        model_health={k: T.ModelHealth(provider=k[0], model=k[1], status=s)
                      for k, s in mhealth.items()},
        provider_capabilities=dict(CAPS),
        resource_state={"eligible": True, "ref": "rs-1"},
        budget_state={"eligible": True, "ref": "bs-1"},
        store=store, emitter=emitter)


# ---------------------------------------------------------------- per-role

def test_per_role_pinned_pool_auto_route_as_set(tmp_path):
    kb = three_provider_kb()
    store = ST.RoutingStore(str(tmp_path / "data"))
    events = []
    emitter = TP.TelemetryEmitter()
    emitter.add_sink(events.append)
    table = RL.RoleTable()
    table.set_profile(T.RoleModelProfile(
        role="director", project_id="p1", mode="PINNED",
        provider="pa", model="pa/a-1", binding="DEFAULT", version=1, hash="h"))
    table.set_profile(T.RoleModelProfile(
        role="worker", project_id="p1", mode="AUTO",
        provider=None, model=None, binding="DEFAULT", version=1, hash="h"))
    pool = P.make_binding("manager", "p1", [
        P.PoolMember("pa", "pa/a-1", "primary"),
        P.PoolMember("pb", "pb/b-1", "fallback"),
        P.PoolMember("pc", "pc/c-1", "fallback"),
    ], strategy="FALLBACK_ORDER")
    store.save_pool(pool)
    audit_pool = P.make_binding("auditor", "p1", [
        P.PoolMember("pa", "pa/a-1", "primary"),
        P.PoolMember("pb", "pb/b-1", "fallback"),
        P.PoolMember("pc", "pc/c-1", "fallback"),
    ], strategy="AUTO")
    store.save_pool(audit_pool)

    deps = make_deps(kb, store=store, emitter=emitter)
    # director PINNED
    dres = table.resolve("p1", "director")
    assert (dres.provider, dres.model) == ("pa", "pa/a-1")
    out_d = R.decide_and_record(
        base_request("director", mode="PINNED",
                     pinned_provider="pa", pinned_model="pa/a-1",
                     candidates=(T.CandidateModel("pa", "pa/a-1"),)), deps)
    assert out_d.decision.selected_model == "pa/a-1"
    # manager pool FALLBACK_ORDER -> first healthy wins
    out_m = P.resolve_pool(pool, base_request("manager"), deps)
    assert out_m.decision.selected_model == "pa/a-1"
    assert [c["model"] for c in out_m.decision.fallback_chain] == ["pb/b-1", "pc/c-1"]
    # worker AUTO -> cheapest fitting (pb)
    out_w = R.decide_and_record(
        base_request("worker", candidates=(
            T.CandidateModel("pa", "pa/a-1"), T.CandidateModel("pb", "pb/b-1"),
            T.CandidateModel("pc", "pc/c-1"))), deps)
    assert out_w.decision.selected_model == "pb/b-1"
    # auditor AUTO excluding implementers -> differs from implementers
    out_a = R.decide_and_record(
        base_request("auditor",
                     candidates=(T.CandidateModel("pa", "pa/a-1"),
                                 T.CandidateModel("pb", "pb/b-1"),
                                 T.CandidateModel("pc", "pc/c-1")),
                     exclude_pairs=(("pb", "pb/b-1"),)), deps)
    assert out_a.decision.selected_provider != "pb"
    # bindings read back with declared use mode per member
    view = P.binding_view(store.get_pool("p1", "manager"))
    assert [(m["provider"], m["model"], m["use_mode"]) for m in view["members"]] == [
        ("pa", "pa/a-1", "primary"), ("pb", "pb/b-1", "fallback"),
        ("pc", "pc/c-1", "fallback")]
    assert all(e.get("reason") for e in events)


def test_fallback_order_skips_unhealthy_with_record(tmp_path):
    kb = three_provider_kb()
    store = ST.RoutingStore(str(tmp_path / "data"))
    pool = P.make_binding("worker", "p1", [
        P.PoolMember("pa", "pa/a-1", "primary"),
        P.PoolMember("pb", "pb/b-1", "fallback"),
    ], strategy="FALLBACK_ORDER")
    deps = make_deps(kb, store=store, mhmap={("pa", "pa/a-1"): "ERROR"})
    out = P.resolve_pool(pool, base_request("worker"), deps)
    assert out.decision.selected_model == "pb/b-1"
    assert "pa/a-1" in out.decision.reason


# ---------------------------------------------------------------- strategies

def test_each_strategy_routes_as_named(tmp_path):
    kb = FakeKb({
        ("pa", "pa/a-1"): make_facts("pa", "pa/a-1", fit=0.9, quality=0.92,
                                     price_in=0.010, price_out=0.030),
        ("pb", "pb/b-1"): make_facts("pb", "pb/b-1", fit=0.9, quality=0.91,
                                     price_in=0.005, price_out=0.015),
        ("lo", "lo/tiny"): make_facts("lo", "lo/tiny", fit=0.8, quality=0.60,
                                      price_in=0.0, price_out=0.0),
    })
    caps = dict(CAPS, lo=("text", "tools", "coding"))
    store = ST.RoutingStore(str(tmp_path / "data"))
    phealth = {"pa": "ONLINE", "pb": "ONLINE", "lo": "ONLINE"}
    mhealth = {("pa", "pa/a-1"): "READY", ("pb", "pb/b-1"): "READY",
               ("lo", "lo/tiny"): "READY"}
    deps = R.RoutingDeps(
        kb=kb,
        provider_health={p: T.ProviderHealth(provider=p, status=s)
                         for p, s in phealth.items()},
        model_health={k: T.ModelHealth(provider=k[0], model=k[1], status=s)
                      for k, s in mhealth.items()},
        provider_capabilities=caps,
        resource_state={"eligible": True, "ref": "rs-1"},
        budget_state={"eligible": True, "ref": "bs-1"},
        store=store, emitter=None)

    auto_pool = P.make_binding("worker", "p1", [
        P.PoolMember("pa", "pa/a-1", "primary"),
        P.PoolMember("pb", "pb/b-1", "fallback"),
    ], strategy="AUTO")
    out = P.resolve_pool(auto_pool, base_request("worker"), deps)
    assert out.decision.selected_model == "pb/b-1"
    assert out.decision.strategy == "AUTO"

    dd_pool = P.make_binding("director", "p1", [
        P.PoolMember("pa", "pa/a-1", "primary"),
        P.PoolMember("pb", "pb/b-1", "fallback"),
    ])  # default strategy when pool holds > 1 model
    assert dd_pool.strategy == "DIRECTOR_PER_TASK"
    blocked = P.resolve_pool(dd_pool, base_request("director"), deps)
    assert blocked.status == "BLOCKED"
    picked = P.resolve_pool(dd_pool, base_request(
        "director", director_pick_provider="pa",
        director_pick_model="pa/a-1"), deps)
    assert picked.decision.selected_model == "pa/a-1"

    split_pool = P.make_binding("worker", "p1", [
        P.PoolMember("lo", "lo/tiny", "draft", "local"),
        P.PoolMember("pa", "pa/a-1", "verify", "cloud"),
    ], strategy="SPLIT_PARALLEL")
    sout = P.resolve_pool(split_pool, base_request("worker"), deps)
    assert sout.decision.route == "SPLIT"
    assert sorted(a.stage for a in sout.assignments) == ["cloud_verify", "local_draft"]


def test_picker_payload_contains_no_raw_ids():
    kb = three_provider_kb()
    options, keymap = P.picker_options(
        "worker", kb.models(), purpose="coding")
    assert len(options) == 3
    raw = ["pa", "pb", "pc", "pa/a-1", "pb/b-1", "pc/c-1"]
    for o in options:
        blob = " ".join([o["key"], o["label"], o["description"]])
        for r in raw:
            assert r not in blob, (r, blob)
    assert set(keymap) == {o["key"] for o in options}
    assert keymap[options[0]["key"]] in (
        ("pa", "pa/a-1"), ("pb", "pb/b-1"), ("pc", "pc/c-1"))


# ---------------------------------------------------------------- WHY_THIS_MODEL replay

def test_why_replay_equals_snapshot_after_health_change(tmp_path):
    kb = three_provider_kb()
    store = ST.RoutingStore(str(tmp_path / "data"))
    deps = make_deps(kb, store=store)
    out = R.decide_and_record(
        base_request("worker", candidates=(
            T.CandidateModel("pa", "pa/a-1"), T.CandidateModel("pb", "pb/b-1"))),
        deps)
    did = out.decision.decision_id
    # Frozen why_replay triple: (RoutingDecision, [RoutingAssignment],
    # RoutingEvidenceSnapshot) reconstructed from persisted records only.
    before = store.why_replay(did)
    assert before is not None
    decision_b, assignments_b, snapshot_b = before
    assert isinstance(decision_b, T.RoutingDecision)
    assert isinstance(assignments_b, list)
    assert isinstance(snapshot_b, T.RoutingEvidenceSnapshot)
    # live health changes afterwards: winner goes OFFLINE
    deps2 = make_deps(kb, store=store, mhmap={("pa", "pa/a-1"): "OFFLINE"})
    assert deps2.model_health[("pa", "pa/a-1")].status == "OFFLINE"
    after = store.why_replay(did)
    assert after == before
    decision_a, _assignments_a, snapshot_a = after
    assert decision_a.decision_id == did
    assert decision_a.selected_model == out.decision.selected_model
    assert (snapshot_a.routing_snapshot_id
            == decision_a.routing_snapshot_id)


# ---------------------------------------------------------------- strongest suggestion

def test_strongest_suggestion_text_tools_coding_only():
    kb = FakeKb({
        ("pa", "pa/zeta-image"): make_facts(
            "pa", "pa/zeta-image", fit=0.99, quality=0.99,
            modalities=("image",)),
        ("pa", "pa/alpha-audio"): make_facts(
            "pa", "pa/alpha-audio", fit=0.99, quality=0.99,
            modalities=("audio",)),
        ("pa", "pa/embed-x"): make_facts(
            "pa", "pa/embed-x", fit=0.99, quality=0.99,
            modalities=("embedding",)),
        ("pa", "pa/mid-coder"): make_facts(
            "pa", "pa/mid-coder", fit=0.80, quality=0.85,
            modalities=("text", "tools", "coding")),
        ("pa", "pa/aaa-coder"): make_facts(
            "pa", "pa/aaa-coder", fit=0.80, quality=0.85,
            modalities=("text", "tools", "coding")),
    })
    best = P.suggest_strongest(kb, "pa", purpose="coding")
    assert best is not None
    assert best.model in ("pa/mid-coder", "pa/aaa-coder")  # never image/audio/embedding
    assert "image" not in best.modalities


# ---------------------------------------------------------------- routes: served handlers

def make_ctx(tmp_path, **over):
    kb = three_provider_kb()
    store = ST.RoutingStore(str(tmp_path / "data"))
    emitter = TP.TelemetryEmitter()
    table = RL.RoleTable()
    kw = dict(store=store, role_table=table, kb=kb,
              provider_health={p: T.ProviderHealth(provider=p, status="ONLINE")
                               for p in ("pa", "pb", "pc")},
              model_health={(p, m): T.ModelHealth(provider=p, model=m, status="READY")
                            for (p, m) in [("pa", "pa/a-1"), ("pb", "pb/b-1"),
                                           ("pc", "pc/c-1")]},
              provider_capabilities=dict(CAPS),
              resource_state={"eligible": True, "ref": "rs-1"},
              budget_state={"eligible": True, "ref": "bs-1"},
              emitter=emitter)
    kw.update(over)
    return PR.RoutingCtx(**kw)


def test_role_edits_persist_and_reflect(tmp_path):
    ctx = make_ctx(tmp_path)
    status, payload = PR.set_role(ctx, {}, {
        "project_id": "p1", "role": "worker", "mode": "PINNED",
        "provider": "pc", "model": "pc/c-1"})
    assert status == 200, payload
    status, payload = PR.get_role(ctx, {"role": "worker", "project_id": "p1"}, None)
    assert status == 200
    assert payload["profile"]["model"] == "pc/c-1"
    status, payload = PR.post_decide(ctx, {}, {
        "project_id": "p1", "task_id": "t1", "run_id": "r1", "role": "worker",
        "task_class": "coding",
        "candidates": [{"provider": "pa", "model": "pa/a-1"},
                       {"provider": "pc", "model": "pc/c-1"}]})
    assert status == 200
    assert payload["selected_model"] == "pc/c-1"
    assert payload["eligibility_source"] == "EXPLICIT_MODEL_PIN"


def test_raw_secrets_rejected(tmp_path):
    ctx = make_ctx(tmp_path)
    status, payload = PR.set_role(ctx, {}, {
        "project_id": "p1", "role": "worker", "mode": "PINNED",
        "provider": "pc", "model": "pc/c-1", "api_key": "sk-live-123"})
    assert status == 400


def test_picker_pick_roundtrip_no_raw_ids(tmp_path):
    ctx = make_ctx(tmp_path)
    status, payload = PR.get_picker(ctx, {"role": "worker", "project_id": "p1",
                                          "purpose": "coding"}, None)
    assert status == 200
    blob = str(payload)
    for r in ("pa/a-1", "pb/b-1", "pc/c-1"):
        assert r not in blob
    key = payload["options"][0]["key"]
    status, payload = PR.post_pick(ctx, {}, {
        "project_id": "p1", "role": "worker", "key": key})
    assert status == 200, payload
    status, payload = PR.get_bindings(ctx, {"role": "worker", "project_id": "p1"}, None)
    assert status == 200
    assert payload["profile"]["mode"] == "PINNED"


def test_why_endpoint_replays(tmp_path):
    ctx = make_ctx(tmp_path)
    status, payload = PR.post_decide(ctx, {}, {
        "project_id": "p1", "task_id": "t1", "run_id": "r1", "role": "worker",
        "task_class": "coding",
        "candidates": [{"provider": "pa", "model": "pa/a-1"},
                       {"provider": "pb", "model": "pb/b-1"}]})
    assert status == 200
    did = payload["decision_id"]
    status, payload = PR.get_why(ctx, {"decision_id": did}, None)
    assert status == 200
    assert payload["decision"]["decision_id"] == did
    assert payload["snapshot"]["routing_snapshot_id"] == payload["decision"]["routing_snapshot_id"]


def test_suggest_endpoint(tmp_path):
    ctx = make_ctx(tmp_path)
    status, payload = PR.get_suggest(ctx, {"provider": "pa", "purpose": "coding"}, None)
    assert status == 200
    assert payload["provider"] == "pa"
    assert payload["model"] == "pa/a-1"


def test_mount_registers_get_post_hosts(tmp_path):
    ctx = make_ctx(tmp_path)

    class FakeApp:
        # FAKE-OF: framework host app exposing .get/.post/.put registrars
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
    assert any("roles" in p for p in app.gets)
    assert any("decide" in p for p in app.posts)
    assert "/api/v1/roles/pools" in app.gets
    assert "/api/v1/roles/pools" in app.puts
    assert "/api/v1/routing/decision/{id}/why" in app.gets
    rows = [(m, p) for m, p, _n, _f in PR.ROUTES]
    assert ("get", "/api/v1/roles/pools") in rows
    assert ("put", "/api/v1/roles/pools") in rows
    assert ("get", "/api/v1/routing/decision/{id}/why") in rows
    assert all(isinstance(m, str) and m == m.lower() for m, _p in rows)
    assert all(len(entry) == 4 for entry in PR.ROUTES)


# ---------------------------------------------------------------- D14 facades

def test_set_get_role_pool_roundtrip_frozen_values(tmp_path):
    ctx = make_ctx(tmp_path)
    old = PR._DEFAULT_POOLS_CTX
    PR.bind_pools_ctx(ctx)
    try:
        profile = PR.set_role_pool(
            "p1", "worker", IF.RoleMode.pool, None, None,
            [{"provider_id": "pa", "model": "pa/a-1", "use_mode": "primary"},
             {"provider": "pb", "model": "pb/b-1", "use_mode": "fallback"},
             {"provider_id": "pc", "model_id": "pc/c-1"}],
            IF.PoolStrategy.FALLBACK_ORDER)
        assert isinstance(profile, T.RoleModelProfile)
        assert (profile.role, profile.mode) == ("worker", "pool")
        assert profile.provider is None and profile.model is None
        rows = PR.get_role_pools("p1")
        assert {r["role"] for r in rows} == set(T.ROLES)
        worker = next(r for r in rows if r["role"] == "worker")
        assert worker["project_id"] == "p1"
        assert worker["profile"]["mode"] == "pool"
        assert worker["binding"]["strategy"] == "FALLBACK_ORDER"
        assert [(m["provider"], m["model"], m["use_mode"])
                for m in worker["binding"]["members"]] == [
            ("pa", "pa/a-1", "primary"), ("pb", "pb/b-1", "fallback"),
            ("pc", "pc/c-1", "primary")]
        # plain strings round-trip too; ModelRef-shaped objects duck-typed
        import types as _stdlib_types
        member = _stdlib_types.SimpleNamespace(provider_id="pa",
                                               model="pa/a-1")
        PR.set_role_pool("p1", "manager", "PINNED", "pa", "pa/a-1",
                         [member], "AUTO")
        rows = PR.get_role_pools("p1")
        manager = next(r for r in rows if r["role"] == "manager")
        assert manager["profile"]["mode"] == "PINNED"
        assert manager["profile"]["provider"] == "pa"
        assert manager["binding"]["strategy"] == "AUTO"
    finally:
        PR._DEFAULT_POOLS_CTX = old


def test_set_role_pool_rejects_bad_values(tmp_path):
    ctx = make_ctx(tmp_path)
    good_pool = [{"provider": "pa", "model": "pa/a-1"}]
    old = PR._DEFAULT_POOLS_CTX
    PR.bind_pools_ctx(ctx)
    try:
        for bad in ({"mode": "MANUAL", "strategy": "AUTO"},
                    {"mode": "pool", "strategy": "ROUND_ROBIN"},
                    {"mode": "pool", "strategy": None},
                    {"mode": "pool", "strategy": "AUTO", "pool": []},
                    {"mode": "AUTO", "strategy": "AUTO",
                     "provider": "pa", "model": "pa/a-1"},
                    {"mode": "PINNED", "strategy": "AUTO",
                     "provider": None, "model": None},
                    {"role": "janitor", "mode": "pool", "strategy": "AUTO"}):
            try:
                PR.set_role_pool(
                    "p1", bad.get("role", "worker"), bad["mode"],
                    bad.get("provider"), bad.get("model"),
                    bad.get("pool", good_pool), bad["strategy"])
            except ValueError:
                pass
            else:
                raise AssertionError("accepted %r" % (bad,))
    finally:
        PR._DEFAULT_POOLS_CTX = old
    saved = PR.set_role_pool  # legacy: unbound ctx is a clear error
    old = PR._DEFAULT_POOLS_CTX
    PR._DEFAULT_POOLS_CTX = None
    try:
        try:
            saved("p1", "worker", "pool", None, None, good_pool, "AUTO")
        except RuntimeError as exc:
            assert "bind_pools_ctx" in str(exc)
        else:
            raise AssertionError("unbound ctx accepted")
    finally:
        PR._DEFAULT_POOLS_CTX = old


def test_bind_pools_ctx_default_serves_facades(tmp_path):
    ctx = make_ctx(tmp_path)
    old = PR._DEFAULT_POOLS_CTX
    PR.bind_pools_ctx(ctx)
    try:
        PR.set_role_pool("p1", "auditor", "pool", None, None,
                         [{"provider": "pb", "model": "pb/b-1"}], "AUTO")
        rows = PR.get_role_pools("p1")
        auditor = next(r for r in rows if r["role"] == "auditor")
        assert auditor["binding"]["strategy"] == "AUTO"
    finally:
        PR._DEFAULT_POOLS_CTX = old


# ------------------------------------------------- D9 roles/pools routes

def test_roles_pools_routes_list_put_roundtrip(tmp_path):
    ctx = make_ctx(tmp_path)
    status, payload = PR.put_role_pools(ctx, {}, {
        "project_id": "p1", "role": "worker", "mode": "pool",
        "provider": None, "model": None,
        "pool": [{"provider": "pa", "model": "pa/a-1",
                  "use_mode": "primary"},
                 {"provider": "pb", "model": "pb/b-1",
                  "use_mode": "fallback"}],
        "strategy": "FALLBACK_ORDER"})
    assert status == 200, payload
    assert payload["ok"] is True
    assert payload["profile"]["mode"] == "pool"
    assert payload["binding"]["strategy"] == "FALLBACK_ORDER"
    status, payload = PR.list_role_pools(ctx, {"project_id": "p1"}, None)
    assert status == 200
    assert set(payload) == {"roles"}
    worker = next(r for r in payload["roles"] if r["role"] == "worker")
    assert set(worker) == {"role", "mode", "provider", "model",
                           "pool", "strategy"}
    assert worker["mode"] == "pool"
    assert worker["strategy"] == "FALLBACK_ORDER"
    assert [(m["provider"], m["model"], m["use_mode"])
            for m in worker["pool"]] == [
        ("pa", "pa/a-1", "primary"), ("pb", "pb/b-1", "fallback")]


def test_roles_pools_put_rejects_bad_body(tmp_path):
    ctx = make_ctx(tmp_path)
    base = {"project_id": "p1", "role": "worker", "mode": "pool",
            "provider": None, "model": None,
            "pool": [{"provider": "pa", "model": "pa/a-1"}],
            "strategy": "AUTO"}
    status, _payload = PR.put_role_pools(
        ctx, {}, dict(base, api_key="[REDACTED]"))
    assert status == 400
    status, _payload = PR.put_role_pools(
        ctx, {}, dict(base, mode="MANUAL"))
    assert status == 400
    status, _payload = PR.put_role_pools(
        ctx, {}, dict(base, strategy="ROUND_ROBIN"))
    assert status == 400
    status, _payload = PR.put_role_pools(ctx, {}, dict(base, role="janitor"))
    assert status == 400


# ------------------------------------------------- D9 decision why route

def _decide_once(ctx):
    status, payload = PR.post_decide(ctx, {}, {
        "project_id": "p1", "task_id": "t1", "run_id": "r1", "role": "worker",
        "task_class": "coding",
        "candidates": [{"provider": "pa", "model": "pa/a-1"},
                       {"provider": "pb", "model": "pb/b-1"}]})
    assert status == 200, payload
    return payload["decision_id"]


def test_decision_why_route_200_and_meta(tmp_path):
    ctx = make_ctx(tmp_path)
    did = _decide_once(ctx)
    status, payload = PR.get_decision_why(
        ctx, {"decision_id": did}, None)
    assert status == 200
    assert payload["decision"]["decision_id"] == did
    assert (payload["snapshot"]["routing_snapshot_id"]
            == payload["decision"]["routing_snapshot_id"])
    assert payload["meta"]["routing_snapshot_id"] == \
        payload["decision"]["routing_snapshot_id"]
    # {id} path param arrives as id in query just the same
    status, payload = PR.get_decision_why(ctx, {"id": did}, None)
    assert status == 200
    assert payload["decision"]["decision_id"] == did


def test_decision_why_route_404_and_400(tmp_path):
    ctx = make_ctx(tmp_path)
    status, _payload = PR.get_decision_why(
        ctx, {"decision_id": "rd-missing"}, None)
    assert status == 404
    status, _payload = PR.get_decision_why(ctx, {}, None)
    assert status == 400


def test_decision_why_concrete_id_dispatch_mapping(tmp_path):
    # Template entry stays registered; concrete ids resolve through the
    # template-aware _DISPATCH mapping (no special-cased id).
    rows = [(m, p) for m, p, _n, _f in PR.ROUTES]
    assert ("get", "/api/v1/routing/decision/{id}/why") in rows
    assert ("get", "/api/v1/routing/decision/rd-1/why") in PR._DISPATCH
    assert ("get", "/api/v1/routing/decision/rd-xyz-9/why") in PR._DISPATCH
    assert PR._DISPATCH[("get", "/api/v1/routing/decision/rd-1/why")] \
        is PR.get_decision_why
    assert ("get", "/api/v1/routing/decision/why") not in PR._DISPATCH
    assert ("get", "/api/v1/routing/decision/rd-1/other") not in PR._DISPATCH


def test_decision_why_concrete_id_serves_end_to_end(tmp_path):
    # Concrete why URL routes end-to-end via serve(): 200 with the
    # triple bundle for a known id, 404 for an unknown id.
    import json as _json
    import urllib.request as _urlrequest
    import urllib.error as _urlerror
    ctx = make_ctx(tmp_path)
    did = _decide_once(ctx)
    server, thread, url = PR.serve(ctx, "127.0.0.1", 0)
    try:
        with _urlrequest.urlopen(
                "%s/api/v1/routing/decision/%s/why" % (url, did)) as resp:
            assert resp.status == 200
            payload = _json.loads(resp.read().decode("utf-8"))
        assert payload["decision"]["decision_id"] == did
        assert isinstance(payload["assignments"], list)
        assert (payload["snapshot"]["routing_snapshot_id"]
                == payload["decision"]["routing_snapshot_id"])
        assert payload["meta"]["routing_snapshot_id"] == \
            payload["decision"]["routing_snapshot_id"]
        try:
            _urlrequest.urlopen(
                "%s/api/v1/routing/decision/rd-missing/why" % url)
        except _urlerror.HTTPError as exc:
            assert exc.code == 404
        else:
            raise AssertionError("missing decision served 200")
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


class TripleStore:
    # FAKE-OF: agent_si.routing.store.RoutingStore (agreed why_replay triple shape)
    def __init__(self, real):
        self._real = real

    def why_replay(self, decision_id):
        bundle = self._real.why_replay(decision_id)
        if bundle is None:
            return None
        if isinstance(bundle, tuple):
            # Frozen store already returns the agreed triple; pass through.
            return bundle
        return (T.RoutingDecision(**bundle["decision"]),
                [T.RoutingAssignment(**row)
                 for row in bundle["assignments"]],
                T.RoutingEvidenceSnapshot(**bundle["snapshot"]))

    def get_meta(self, decision_id):
        return self._real.get_meta(decision_id)


def test_decision_why_route_serves_agreed_triple(tmp_path):
    ctx = make_ctx(tmp_path)
    did = _decide_once(ctx)
    ctx.store = TripleStore(ctx.store)
    status, payload = PR.get_decision_why(
        ctx, {"decision_id": did}, None)
    assert status == 200
    assert payload["decision"]["decision_id"] == did
    assert isinstance(payload["assignments"], list)
    assert (payload["snapshot"]["routing_snapshot_id"]
            == payload["decision"]["routing_snapshot_id"])
    assert payload["meta"]["routing_snapshot_id"] == \
        payload["decision"]["routing_snapshot_id"]
    status, _payload = PR.get_decision_why(
        ctx, {"decision_id": "rd-missing"}, None)
    assert status == 404


# ------------------------------------------------- 4-guard in the facade

def test_set_role_pool_facade_refuses_raw_secret(tmp_path):
    ctx = make_ctx(tmp_path)
    old = PR._DEFAULT_POOLS_CTX
    PR.bind_pools_ctx(ctx)
    try:
        try:
            PR.set_role_pool(
                "p1", "worker", "pool", None, None,
                [{"provider": "pa", "model": "pa/a-1", "use_mode": "primary"},
                 {"provider": "pb", "model": "pb/b-1",
                  "api_key": "[REDACTED]"}],
                "FALLBACK_ORDER")
        except ValueError as exc:
            assert "raw secret" in str(exc)
        else:
            raise AssertionError("facade accepted raw secret material")
    finally:
        PR._DEFAULT_POOLS_CTX = old
    # nothing persisted on refusal
    assert ctx.store.get_pool("p1", "worker") is None
    assert ctx.role_table.get_profile("p1", "worker") is None


def test_roles_pools_put_refuses_secret_member(tmp_path):
    ctx = make_ctx(tmp_path)
    status, payload = PR.put_role_pools(ctx, {}, {
        "project_id": "p1", "role": "worker", "mode": "pool",
        "provider": None, "model": None,
        "pool": [{"provider": "pa", "model": "pa/a-1"},
                 {"provider": "pb", "model": "pb/b-1",
                  "token": "[REDACTED]"}],
        "strategy": "FALLBACK_ORDER"})
    assert status == 400
    assert "raw secret" in payload["error"]
    assert ctx.store.get_pool("p1", "worker") is None


def test_set_role_pool_facade_rejects_legacy_strategy(tmp_path):
    ctx = make_ctx(tmp_path)
    old = PR._DEFAULT_POOLS_CTX
    PR.bind_pools_ctx(ctx)
    try:
        try:
            PR.set_role_pool(
                "p1", "worker", "pool", None, None,
                [{"provider": "pa", "model": "pa/a-1"}],
                "fallback_order")
        except ValueError as exc:
            assert "frozen" in str(exc)
        else:
            raise AssertionError("facade accepted a legacy strategy on write")
    finally:
        PR._DEFAULT_POOLS_CTX = old


# ------------------------------------------------- post_decide select wiring

def test_post_decide_select_path_records_once(tmp_path):
    events = []
    ctx = make_ctx(tmp_path)
    ctx.emitter.add_sink(events.append)
    status, payload = PR.post_decide(ctx, {}, {
        "project_id": "p1", "task_id": "t1", "run_id": "r1", "role": "worker",
        "task_class": "coding",
        "candidates": [{"provider": "pa", "model": "pa/a-1"},
                       {"provider": "pb", "model": "pb/b-1"}]})
    assert status == 200, payload
    assert set(payload) == {"status", "decision_id", "route", "strategy",
                            "selected_provider", "selected_model", "reason",
                            "eligibility_source", "capability_state",
                            "assignments", "fallback_chain"}
    assert payload["status"] != "BLOCKED"
    # wrapper already persisted + emitted: exactly one decision row, one event
    assert len(ctx.store._load_table("decisions")) == 1
    assert len(events) == 1
    triple = ctx.store.why_replay(payload["decision_id"])
    assert triple is not None
    decision, _assignments, _snapshot = triple
    assert decision.selected_model == payload["selected_model"]


def test_post_decide_select_blocked_shape(tmp_path):
    events = []
    ctx = make_ctx(tmp_path)
    ctx.emitter.add_sink(events.append)
    status, payload = PR.post_decide(ctx, {}, {
        "project_id": "p1", "task_id": "t1", "run_id": "r1", "role": "worker",
        "task_class": "coding", "candidates": []})
    assert status == 200, payload
    assert payload["status"] == "BLOCKED"
    assert set(payload) == {"status", "decision_id", "route", "strategy",
                            "selected_provider", "selected_model", "reason",
                            "eligibility_source", "capability_state",
                            "assignments", "fallback_chain"}
    assert payload["route"] == "BLOCKED"
    assert "NO_ELIGIBLE_CANDIDATE" in payload["reason"]
    # blocked outcome recorded once, like the old decide_and_record path
    assert len(ctx.store._load_table("decisions")) == 1
    assert len(events) == 1


def test_post_decide_pinned_boundary_no_profile(tmp_path):
    ctx = make_ctx(tmp_path)
    status, payload = PR.post_decide(ctx, {}, {
        "project_id": "p1", "task_id": "t1", "run_id": "r1", "role": "worker",
        "mode": "PINNED",
        "task_class": "coding",
        "candidates": [{"provider": "pa", "model": "pa/a-1"}]})
    assert status == 200, payload
    assert payload["status"] == "BLOCKED"
    assert "NO_PROFILE_BLOCKED" in payload["reason"]
    assert set(payload) == {"status", "decision_id", "route", "strategy",
                            "selected_provider", "selected_model", "reason",
                            "eligibility_source", "capability_state",
                            "assignments", "fallback_chain"}


def test_post_decide_pool_branch_uses_binding_strategy(tmp_path):
    ctx = make_ctx(tmp_path)
    old = PR._DEFAULT_POOLS_CTX
    PR.bind_pools_ctx(ctx)
    try:
        PR.set_role_pool(
            "p1", "worker", "pool", None, None,
            [{"provider": "pa", "model": "pa/a-1", "use_mode": "primary"},
             {"provider": "pb", "model": "pb/b-1", "use_mode": "fallback"}],
            "FALLBACK_ORDER")
        status, payload = PR.post_decide(ctx, {}, {
            "project_id": "p1", "task_id": "t1", "run_id": "r1", "role": "worker",
            "task_class": "coding"})
        assert status == 200, payload
        assert payload["selected_model"] == "pa/a-1"
        assert payload["strategy"] == "FALLBACK_ORDER"
    finally:
        PR._DEFAULT_POOLS_CTX = old


# ---------------------------------------------------------------- A2USE2 strategy behaviour

def test_a2use2_director_per_task_pick(tmp_path):
    ctx = make_ctx(tmp_path)
    old = PR._DEFAULT_POOLS_CTX
    PR.bind_pools_ctx(ctx)
    try:
        PR.set_role_pool(
            "p1", "director", "pool", None, None,
            [{"provider": "pa", "model": "pa/a-1", "use_mode": "primary"},
             {"provider": "pb", "model": "pb/b-1", "use_mode": "fallback"}],
            "DIRECTOR_PER_TASK")
    finally:
        PR._DEFAULT_POOLS_CTX = old
    rdeps = make_deps(three_provider_kb(), store=ctx.store)
    binding = ctx.store.get_pool("p1", "director")
    assert binding is not None
    blocked = P.resolve_pool(binding, base_request("director"), rdeps)
    assert blocked.status == "BLOCKED"
    assert T.STRATEGY_LABELS["DIRECTOR_PER_TASK"] in blocked.decision.reason
    picked = P.resolve_pool(binding, base_request(
        "director", director_pick_provider="pa",
        director_pick_model="pa/a-1"), rdeps)
    assert picked.decision.selected_model == "pa/a-1"
    assert picked.decision.strategy == "DIRECTOR_PER_TASK"
    # same behaviour through the public post_decide entry point
    status, payload = PR.post_decide(ctx, {}, {
        "project_id": "p1", "task_id": "t1", "run_id": "r1",
        "role": "director", "task_class": "coding",
        "director_pick_provider": "pa", "director_pick_model": "pa/a-1"})
    assert status == 200, payload
    assert payload["selected_model"] == "pa/a-1"
    assert payload["strategy"] == "DIRECTOR_PER_TASK"
    status, payload = PR.post_decide(ctx, {}, {
        "project_id": "p1", "task_id": "t1", "run_id": "r1",
        "role": "director", "task_class": "coding"})
    assert status == 200, payload
    assert payload["status"] == "BLOCKED"


def test_a2use2_auto_cheapest_fitting_wins(tmp_path):
    ctx = make_ctx(tmp_path)
    old = PR._DEFAULT_POOLS_CTX
    PR.bind_pools_ctx(ctx)
    try:
        PR.set_role_pool(
            "p1", "worker", "pool", None, None,
            [{"provider": "pa", "model": "pa/a-1", "use_mode": "primary"},
             {"provider": "pb", "model": "pb/b-1", "use_mode": "fallback"},
             {"provider": "pc", "model": "pc/c-1", "use_mode": "fallback"}],
            "AUTO")
    finally:
        PR._DEFAULT_POOLS_CTX = old
    rdeps = make_deps(three_provider_kb(), store=ctx.store)
    out = P.resolve_pool(ctx.store.get_pool("p1", "worker"),
                         base_request("worker"), rdeps)
    assert out.status == "ROUTED"
    assert out.decision.selected_model == "pb/b-1"
    assert out.decision.strategy == "AUTO"
    assert T.STRATEGY_LABELS["AUTO"] in out.decision.reason


def test_a2use2_fallback_order_first_healthy(tmp_path):
    ctx = make_ctx(tmp_path)
    old = PR._DEFAULT_POOLS_CTX
    PR.bind_pools_ctx(ctx)
    try:
        PR.set_role_pool(
            "p1", "manager", "pool", None, None,
            [{"provider": "pa", "model": "pa/a-1", "use_mode": "primary"},
             {"provider": "pb", "model": "pb/b-1", "use_mode": "fallback"},
             {"provider": "pc", "model": "pc/c-1", "use_mode": "fallback"}],
            "FALLBACK_ORDER")
    finally:
        PR._DEFAULT_POOLS_CTX = old
    rdeps = make_deps(three_provider_kb(), store=ctx.store,
                      mhmap={("pa", "pa/a-1"): "ERROR"})
    binding = ctx.store.get_pool("p1", "manager")
    out = P.resolve_pool(binding, base_request("manager"), rdeps)
    assert out.decision.selected_model == "pb/b-1"
    assert out.decision.strategy == "FALLBACK_ORDER"
    assert "pa/a-1" in out.decision.reason
    assert T.STRATEGY_LABELS["FALLBACK_ORDER"] in out.decision.reason
    # router-level wiring: decide_and_record honours the stored binding
    # for a pool-mode request on any role, not just worker
    routed = R.decide_and_record(
        base_request("manager", mode="pool"), rdeps)
    assert routed.decision.selected_model == "pb/b-1"
    assert routed.decision.strategy == "FALLBACK_ORDER"


def test_a2use2_split_parallel_spread(tmp_path):
    kb = FakeKb({
        ("pa", "pa/a-1"): make_facts("pa", "pa/a-1", fit=0.9, quality=0.92,
                                     price_in=0.010, price_out=0.030),
        ("pb", "pb/b-1"): make_facts("pb", "pb/b-1", fit=0.9, quality=0.91,
                                     price_in=0.005, price_out=0.015),
        ("lo", "lo/tiny"): make_facts("lo", "lo/tiny", fit=0.8, quality=0.60,
                                      price_in=0.0, price_out=0.0),
    })
    caps = dict(CAPS, lo=("text", "tools", "coding"))
    store = ST.RoutingStore(str(tmp_path / "data"))
    deps = R.RoutingDeps(
        kb=kb,
        provider_health={p: T.ProviderHealth(provider=p, status="ONLINE")
                         for p in ("pa", "pb", "lo")},
        model_health={k: T.ModelHealth(provider=k[0], model=k[1],
                                      status="READY")
                      for k in [("pa", "pa/a-1"), ("pb", "pb/b-1"),
                                ("lo", "lo/tiny")]},
        provider_capabilities=caps,
        resource_state={"eligible": True, "ref": "rs-1"},
        budget_state={"eligible": True, "ref": "bs-1"},
        store=store, emitter=None)
    binding = P.make_binding("worker", "p1", [
        P.PoolMember("lo", "lo/tiny", "draft", "local"),
        P.PoolMember("pa", "pa/a-1", "verify", "cloud"),
    ], strategy="SPLIT_PARALLEL")
    out = P.resolve_pool(binding, base_request("worker"), deps)
    assert out.decision.route == "SPLIT"
    assert out.decision.strategy == "SPLIT_PARALLEL"
    assert sorted(a.stage for a in out.assignments) == ["cloud_verify",
                                                        "local_draft"]
    assert (sorted((a.provider, a.model) for a in out.assignments)
            == [("lo", "lo/tiny"), ("pa", "pa/a-1")])


def test_a2use2_no_binding_is_auto(tmp_path):
    ctx = make_ctx(tmp_path)
    old_store, P._bound_pool_store = P._bound_pool_store, None
    old_ctx, PR._DEFAULT_POOLS_CTX = PR._DEFAULT_POOLS_CTX, None
    try:
        assert P.pick_pool_strategy("worker", "p1") == "AUTO"
        PR.bind_pools_ctx(ctx)
        try:
            PR.set_role_pool(
                "p1", "worker", "pool", None, None,
                [{"provider": "pa", "model": "pa/a-1", "use_mode": "primary"},
                 {"provider": "pb", "model": "pb/b-1", "use_mode": "fallback"}],
                "FALLBACK_ORDER")
        finally:
            PR._DEFAULT_POOLS_CTX = None
        # stored but unbound: still the no-binding default
        assert P.pick_pool_strategy("worker", "p1") == "AUTO"
        # module-level bound store serves the stored strategy
        P.bind_pool_store(ctx.store)
        assert P.pick_pool_strategy("worker", "p1") == "FALLBACK_ORDER"
        # backend default context serves it too once bound
        P.unbind_pool_store()
        PR.bind_pools_ctx(ctx)
        assert P.pick_pool_strategy("worker", "p1") == "FALLBACK_ORDER"
        # unknown role is rejected, never guessed
        try:
            P.pick_pool_strategy("janitor", "p1")
        except ValueError:
            pass
        else:
            raise AssertionError("unknown role accepted")
    finally:
        P._bound_pool_store = old_store
        PR._DEFAULT_POOLS_CTX = old_ctx


def test_a2use2_picker_options_carry_no_raw_ids():
    options, keymap = P.picker_options(
        "worker", three_provider_kb().models(), purpose="coding")
    assert len(options) == 3
    raw = ["pa", "pb", "pc", "pa/a-1", "pb/b-1", "pc/c-1"]
    for o in options:
        blob = " ".join([o["key"], o["label"], o["description"]])
        for r in raw:
            assert r not in blob, (r, blob)
    assert set(keymap) == {o["key"] for o in options}


def test_a2use2_strategy_label_in_telemetry_reason(tmp_path):
    events = []
    ctx = make_ctx(tmp_path)
    ctx.emitter.add_sink(events.append)
    old = PR._DEFAULT_POOLS_CTX
    PR.bind_pools_ctx(ctx)
    try:
        PR.set_role_pool(
            "p1", "worker", "pool", None, None,
            [{"provider": "pa", "model": "pa/a-1", "use_mode": "primary"},
             {"provider": "pb", "model": "pb/b-1", "use_mode": "fallback"}],
            "FALLBACK_ORDER")
    finally:
        PR._DEFAULT_POOLS_CTX = old
    status, payload = PR.post_decide(ctx, {}, {
        "project_id": "p1", "task_id": "t1", "run_id": "r1", "role": "worker",
        "task_class": "coding"})
    assert status == 200, payload
    assert payload["strategy"] == "FALLBACK_ORDER"
    assert len(events) == 1
    assert (T.STRATEGY_LABELS["FALLBACK_ORDER"] in events[0]["reason"])


# ------------------------------------------------- F3 HTTP parity: corrupt stored strategy

def test_f3_http_corrupt_stored_strategy_blocks_naming_it(tmp_path):
    # HTTP path: a raw corrupt stored strategy 'ROUND_ROBIN' (save_pool
    # rejects corrupt values, so written via a raw profiles-table row like
    # the facade F3 test) + pool-mode profile, through the REAL served
    # POST /api/v1/routing/decide entry over HTTP with a session token
    # -> http 200 BLOCKED naming "unknown pool strategy 'ROUND_ROBIN'",
    # with exactly one decision record persisted.
    import json as _json
    import urllib.request as _urlrequest
    ctx = make_ctx(tmp_path)
    ctx.session_token = "f3-http-probe-token"
    old = PR._DEFAULT_POOLS_CTX
    PR.bind_pools_ctx(ctx)
    try:
        PR.set_role_pool(
            "p1", "worker", "pool", None, None,
            [{"provider": "pa", "model": "pa/a-1", "use_mode": "primary"},
             {"provider": "pb", "model": "pb/b-1", "use_mode": "fallback"}],
            "FALLBACK_ORDER")
    finally:
        PR._DEFAULT_POOLS_CTX = old
    table = ctx.store._load_table("profiles")
    key = "p1\x00worker"
    row = dict(table["pools"][key])
    row["strategy"] = "ROUND_ROBIN"
    table["pools"][key] = row
    ctx.store._save_table("profiles", table)
    server, thread, url = PR.serve(ctx, "127.0.0.1", 0)
    try:
        raw = _json.dumps({
            "project_id": "p1", "task_id": "t1", "run_id": "r1",
            "role": "worker", "task_class": "coding"}).encode("utf-8")
        req = _urlrequest.Request(
            "%s/api/v1/routing/decide?session_token=f3-http-probe-token" % url,
            data=raw, headers={"Content-Type": "application/json"},
            method="POST")
        with _urlrequest.urlopen(req) as resp:
            assert resp.status == 200
            payload = _json.loads(resp.read().decode("utf-8"))
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
    assert payload["status"] == "BLOCKED"
    assert "unknown pool strategy 'ROUND_ROBIN'" in payload["reason"]
    assert len(ctx.store._load_table("decisions")) == 1
# ------------------------------------------------- ARCH-681 cost via CostCalculator

def test_a2use2_served_decide_cheapest_fitting_wins_no_leg_cost(tmp_path):
    # ARCH-681: the served cost path runs via CostCalculator only — no
    # direct cost arithmetic in pools/adapters legs. Served post_decide
    # over two fitting candidates picks the cheaper one with a priced
    # basis in the reason; legs.py carries no cost surface at all.
    ctx = make_ctx(tmp_path)
    status, payload = PR.post_decide(ctx, {}, {
        "project_id": "p1", "task_id": "t1", "run_id": "r1", "role": "worker",
        "task_class": "coding",
        "candidates": [{"provider": "pa", "model": "pa/a-1"},
                       {"provider": "pb", "model": "pb/b-1"}]})
    assert status == 200, payload
    assert payload["status"] == "ROUTED", payload
    assert payload["selected_model"] == "pb/b-1", payload
    assert "known prices" in payload["reason"], payload
    leg_src = os.path.join(
        _SRC, "agent_si", "providers", "adapters", "legs.py")
    with open(leg_src, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert "cost" not in text.lower(), \
        "legs.py must not do cost arithmetic (cost via CostCalculator only)"
