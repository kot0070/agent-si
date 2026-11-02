# K04 Lane A2 — pools/settings HTTP surface (pure handlers + mount + stdlib serve).
# Pure functions take (ctx, query, body) and return (status, payload), so the
# same handlers run behind any `.get`/`.post` host and behind the stdlib
# probe server. Never imports K02 `create_app`; mounts standalone.
"""Role profiles, pool picker, bindings, WHY_THIS_MODEL, decide endpoints."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict as _dc_asdict
from dataclasses import is_dataclass as _is_dc
from dataclasses import replace as _dc_replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from agent_si.routing import types as T
from agent_si.routing import router as R
from agent_si.routing import roles as RL
from agent_si.routing import pools as P
from agent_si.routing.telemetry_port import routing_event


# --------------------------------------------------------------------------
# Context

class RoutingCtx:
    """Server-side context: store, profiles, KB port, health views, emitter.

    session_token carries the K06 UI session handle when the host binds
    it server-side (reads ignore it); the URL query is never a token
    channel (see _served_token). The token never travels in
    the JSON body: secret-looking body fields stay refused by the
    raw-secret guards.
    """

    def __init__(self, *, store, role_table, kb,
                 provider_health: Mapping = None,
                 model_health: Mapping = None,
                 provider_capabilities: Mapping = None,
                 resource_state=None, budget_state=None,
                 emitter=None, manager_profile=None,
                 session_token=None) -> None:
        self.store = store
        self.role_table = role_table
        self.kb = kb
        self.session_token = session_token
        self.provider_health = dict(provider_health or {})
        self.model_health = dict(model_health or {})
        self.provider_capabilities = dict(provider_capabilities or {})
        self.resource_state = resource_state
        self.budget_state = budget_state
        self.emitter = emitter
        self.manager_profile = manager_profile
        self.keymaps: Dict[Tuple[str, str], Dict[str, Tuple[str, str]]] = {}

    def default_policy(self, task_class: str) -> T.RoutingPolicy:
        return T.RoutingPolicy(
            policy_id="ctx-default", version=1, created_at=T.utcnow(),
            hash="", task_class=task_class, risk_level="LOW",
            strict_min=1.0, tolerant_min=0.85, confidence_min=0.7,
            sample_min=20, freshness_requirement="CURRENT",
            local_allowed=True, split_allowed=True, cloud_required=False)

    def default_opt(self) -> T.OptimizationPolicy:
        return T.OptimizationPolicy(
            policy_id="ctx-default", version=1, created_at=T.utcnow(),
            hash="", required_quality=0.8, max_risk="HIGH",
            weight_quality=1.0, weight_cost=1.0, weight_latency=1.0,
            weight_cloud_tokens=1.0, local_preference=False,
            deadline=None, budget_limit=None)

    def deps(self, store=None, emitter=None) -> R.RoutingDeps:
        return R.RoutingDeps(
            kb=self.kb, provider_health=self.provider_health,
            model_health=self.model_health,
            provider_capabilities=self.provider_capabilities,
            resource_state=self.resource_state,
            budget_state=self.budget_state,
            manager_profile=self.manager_profile,
            store=self.store if store is None else store,
            emitter=self.emitter if emitter is None else emitter)


# --------------------------------------------------------------------------
# Helpers

def _q(query: Mapping, name: str, default=None):
    value = (query or {}).get(name, default)
    if isinstance(value, list):
        return value[0] if value else default
    return value


def _profile_payload(profile: T.RoleModelProfile) -> Dict[str, Any]:
    return {"role": profile.role, "project_id": profile.project_id,
            "mode": profile.mode, "provider": profile.provider,
            "model": profile.model, "binding": profile.binding,
            "version": profile.version}


SECRET_KEY_HINTS = ("secret", "api_key", "apikey", "token", "password",
                    "passwd", "credential", "private_key")


def _find_raw_secret(value: Any, path: str = "body"):
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(hint in lowered for hint in SECRET_KEY_HINTS):
                return "%s.%s" % (path, key)
            hit = _find_raw_secret(item, "%s.%s" % (path, key))
            if hit:
                return hit
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hit = _find_raw_secret(item, "%s[%d]" % (path, index))
            if hit:
                return hit
    return None


# --------------------------------------------------------------------------
# D14 facades: module-level pool binding access (ctx bound server-side).
# ctx carries role_table/store only, never raw secrets; the frozen
# (project_id, role, mode, provider, model, pool, strategy) params stay
# on the facade signatures so the strict contract test can compare them.

_DEFAULT_POOLS_CTX = None


def bind_pools_ctx(ctx):
    """Bind the default server-side context for the D14 facades.

    Accepts a RoutingCtx (or a mapping with role_table/store entries) and
    returns it unchanged. Facade calls that carry no role_table/store in
    their own ctx fall back to this binding.
    """
    global _DEFAULT_POOLS_CTX
    _DEFAULT_POOLS_CTX = ctx
    return ctx


def _pools_deps(ctx) -> Tuple[Any, Any]:
    """Resolve (role_table, store) from facade ctx or the bound default."""
    role_table = store = None
    if isinstance(ctx, Mapping):
        role_table = ctx.get("role_table")
        store = ctx.get("store")
    else:
        role_table = getattr(ctx, "role_table", None)
        store = getattr(ctx, "store", None)
    bound = _DEFAULT_POOLS_CTX
    if (role_table is None or store is None) and bound is not None:
        if isinstance(bound, Mapping):
            role_table = role_table or bound.get("role_table")
            store = store or bound.get("store")
        else:
            role_table = role_table or getattr(bound, "role_table", None)
            store = store or getattr(bound, "store", None)
    if role_table is None or store is None:
        raise RuntimeError(
            "pools context unbound: pass role_table/store in ctx "
            "or call bind_pools_ctx(ctx) with a RoutingCtx first")
    return role_table, store


def _frozen_value(value):
    """Unwrap a frozen enum member to its plain string value (duck-typed).

    The frozen interface module is never imported here (it stays a
    shape-only declaration); enum members are recognized by their
    ``value`` attribute only.
    """
    return getattr(value, "value", value)


def _normalize_mode(mode: Any) -> str:
    """Accept frozen RoleMode values (or their plain strings); reject rest."""
    text = _frozen_value(mode)
    if isinstance(text, str):
        lowered = text.lower()
        for canonical in T.ROLE_MODES:
            if lowered == canonical.lower():
                return canonical
    raise ValueError("unknown mode %r (PINNED|pool|AUTO)" % (mode,))


def _refuse_raw_secret(value: Any) -> None:
    """Reject raw secret material anywhere inside a facade input.

    Shared by the set_role_pool facade (direct callers) and the PUT
    handler (route callers): raises ValueError naming the offending
    path so the handler can translate it to the existing 400 shape.
    """
    hit = _find_raw_secret(value)
    if hit:
        raise ValueError(
            "raw secret material refused at %s "
            "(pass a SecretRef handle, never raw)" % hit)


def _normalize_strategy(strategy: Any) -> str:
    """Accept frozen PoolStrategy values (or their plain strings).

    Returns the frozen canonical name; the binding is stored frozen, so
    legacy persisted values (director_decides/auto/fallback_order/
    split_parallel) are rejected on WRITE (they migrate on store READ
    only, per the frozen contract).
    """
    text = _frozen_value(strategy)
    if isinstance(text, str):
        if text in T.POOL_STRATEGIES:
            return text
        if text in T.LEGACY_POOL_STRATEGIES:
            raise ValueError(
                "legacy strategy %r: writes take frozen values only "
                "(DIRECTOR_PER_TASK|AUTO|FALLBACK_ORDER|SPLIT_PARALLEL)"
                % (strategy,))
    raise ValueError(
        "unknown strategy %r "
        "(DIRECTOR_PER_TASK|AUTO|FALLBACK_ORDER|SPLIT_PARALLEL)" % (strategy,))


def _normalize_member(item: Any) -> P.PoolMember:
    """Accept a frozen ModelRef-shaped value or an equivalent mapping.

    Frozen ModelRef carries (provider_id, model) with no use mode; mappings
    may use provider_id/provider and model/model_id keys and may add
    use_mode and provider_type. Returns a pools.PoolMember.
    """
    if isinstance(item, P.PoolMember):
        return item
    if isinstance(item, Mapping):
        provider = item.get("provider_id", item.get("provider"))
        model = item.get("model", item.get("model_id"))
        use_mode = item.get("use_mode", "primary")
        provider_type = item.get("provider_type", "cloud")
    else:
        provider = getattr(item, "provider_id",
                           getattr(item, "provider", None))
        model = getattr(item, "model", getattr(item, "model_id", None))
        use_mode = getattr(item, "use_mode", "primary") or "primary"
        provider_type = getattr(item, "provider_type", "cloud") or "cloud"
    if not provider or not model:
        raise ValueError(
            "bad pool member %r: needs provider and model" % (item,))
    return P.PoolMember(provider, model, use_mode, provider_type)


def get_role_pools(project_id: str) -> List[RoleModelProfile]:
    """List stored role bindings for one project (D14 facade).

    Returns one record per frozen role with the same profile/binding
    material as the get_bindings payload (binding views carry the declared
    use mode per pool member), scoped by project_id. role_table/store come
    from ctx (or the bind_pools_ctx default); a clear error is raised when
    unbound.
    """
    role_table, store = _pools_deps(None)
    rows = []
    for role in T.ROLES:
        profile = role_table.get_profile(project_id, role)
        binding = store.get_pool(project_id, role)
        rows.append({
            "role": role,
            "project_id": project_id,
            "profile": _profile_payload(profile) if profile else None,
            "binding": P.binding_view(binding)
            if binding is not None else None,
        })
    return rows


def set_role_pool(project_id: str, role: str, mode: RoleMode,
                  provider: Optional[str], model: Optional[str],
                  pool: List[ModelRef],
                  strategy: PoolStrategy) -> RoleModelProfile:
    """Persist one role's pool binding (D14 facade).

    mode accepts frozen RoleMode values (or plain strings); strategy
    accepts frozen PoolStrategy values (or plain strings) and is validated
    before anything is persisted. pool accepts frozen ModelRef values (or
    equivalent mappings, see _normalize_member). Raw secret material
    anywhere in the inputs is refused (ValueError) before anything is
    persisted, so direct callers share the route's 4-guard. Returns the
    persisted RoleModelProfile.
    """
    role_table, store = _pools_deps(None)
    _refuse_raw_secret({"project_id": project_id, "role": role,
                        "mode": mode, "provider": provider,
                        "model": model, "pool": pool,
                        "strategy": strategy})
    if role not in T.ROLES:
        raise ValueError("unknown role %r" % (role,))
    norm_mode = _normalize_mode(mode)
    norm_strategy = _normalize_strategy(strategy)
    if norm_mode == "PINNED" and (not provider or not model):
        raise ValueError("PINNED needs provider and model")
    if norm_mode == "AUTO" and (provider or model):
        raise ValueError("AUTO holds no provider/model")
    members = [_normalize_member(item) for item in (pool or [])]
    if norm_mode == "pool" and not members:
        raise ValueError("pool mode needs at least one pool member")
    profile = T.RoleModelProfile(
        role=role, project_id=project_id, mode=norm_mode,
        provider=provider if norm_mode == "PINNED" else None,
        model=model if norm_mode == "PINNED" else None,
        binding="DEFAULT", version=1,
        hash=T.stable_hash({"role": role, "project": project_id,
                            "mode": norm_mode, "provider": provider,
                            "model": model, "strategy": norm_strategy}))
    role_table.set_profile(profile)
    if members:
        store.save_pool(P.make_binding(role, project_id, members,
                                       strategy=norm_strategy))
    return profile


# --------------------------------------------------------------------------
# Handlers: (ctx, query, body) -> (status, payload)

def list_roles(ctx: RoutingCtx, query, body) -> Tuple[int, Dict]:
    project_id = _q(query, "project_id", None)
    if not isinstance(project_id, str) or not project_id:
        return 400, {"error": "project_id required"}
    roles = []
    for role in T.ROLES:
        profile = ctx.role_table.get_profile(project_id, role)
        resolution = ctx.role_table.resolve(
            project_id, role, provider_health=ctx.provider_health,
            model_health=ctx.model_health)
        roles.append({
            "role": role,
            "mode": profile.mode if profile else None,
            "provider": profile.provider if profile else None,
            "model": profile.model if profile else None,
            "status": resolution.status,
            "reason": resolution.reason,
        })
    return 200, {"project_id": project_id, "roles": roles}


def get_role(ctx: RoutingCtx, query, body) -> Tuple[int, Dict]:
    project_id = _q(query, "project_id", None)
    if not isinstance(project_id, str) or not project_id:
        return 400, {"error": "project_id required"}
    role = _q(query, "role", None)
    if role not in T.ROLES:
        return 400, {"error": "unknown role %r" % (role,)}
    profile = ctx.role_table.get_profile(project_id, role)
    if profile is None:
        resolution = ctx.role_table.resolve(project_id, role)
        return 404, {"error": resolution.reason}
    payload = {"profile": _profile_payload(profile)}
    binding = ctx.store.get_pool(project_id, role) if ctx.store else None
    if binding is not None:
        payload["binding"] = P.binding_view(binding)
    return 200, payload


def set_role(ctx: RoutingCtx, query, body) -> Tuple[int, Dict]:
    body = body or {}
    hit = _find_raw_secret(body)
    if hit:
        return 400, {"error": "raw secret material refused at %s "
                              "(pass a SecretRef handle, never raw)" % hit}
    project_id = body.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        return 400, {"error": "project_id required"}
    role = body.get("role")
    mode = body.get("mode")
    if role not in T.ROLES:
        return 400, {"error": "unknown role %r" % (role,)}
    if mode not in T.ROLE_MODES:
        return 400, {"error": "unknown mode %r (PINNED|pool|AUTO)" % (mode,)}
    provider = body.get("provider")
    model = body.get("model")
    if mode == "PINNED" and (not provider or not model):
        return 400, {"error": "PINNED needs provider and model"}
    if mode in ("pool",) and not body.get("pool"):
        # pool mode without members: plain refusal, nothing stored
        # (an empty pool would only BLOCK later at resolve).
        return 400, {"error": "pool needs at least one member"}
    profile = T.RoleModelProfile(
        role=role, project_id=project_id, mode=mode,
        provider=provider if mode == "PINNED" else None,
        model=model if mode == "PINNED" else None,
        binding="DEFAULT", version=1,
        hash=T.stable_hash({"role": role, "project": project_id,
                            "mode": mode, "provider": provider,
                            "model": model}))
    ctx.role_table.set_profile(profile)
    payload: Dict[str, Any] = {"ok": True, "profile": _profile_payload(profile)}
    members = body.get("pool")
    if members:
        try:
            parsed = [P.PoolMember(m["provider"], m["model"],
                                   m.get("use_mode", "primary"),
                                   m.get("provider_type", "cloud"))
                      for m in members]
        except (KeyError, ValueError) as exc:
            return 400, {"error": "bad pool member: %s" % exc}
        binding = P.make_binding(role, project_id, parsed,
                                 strategy=body.get("strategy"))
        if ctx.store is not None:
            ctx.store.save_pool(binding)
        payload["binding"] = P.binding_view(binding)
    if role == "manager" and mode == "PINNED":
        manager = RL.make_default_manager_profile(provider, model)
        if ctx.store is not None:
            ctx.store.save_manager_profile(manager)
        ctx.manager_profile = manager
        payload["manager_profile"] = {"provider": manager.provider,
                                      "model": manager.model,
                                      "version": manager.version}
    if ctx.emitter is not None:
        ctx.emitter.emit(routing_event(
            project_id=project_id, task_id="-", run_id="-", role=role,
            event_type="role_edit",
            reason="role %s set to %s%s" % (
                role, mode,
                " %s/%s" % (provider, model) if mode == "PINNED" else ""),
            provider=provider if mode == "PINNED" else None,
            model=model if mode == "PINNED" else None))
    return 200, payload


def get_picker(ctx: RoutingCtx, query, body) -> Tuple[int, Dict]:
    project_id = _q(query, "project_id", None)
    if not isinstance(project_id, str) or not project_id:
        return 400, {"error": "project_id required"}
    role = _q(query, "role", None)
    purpose = _q(query, "purpose", "coding")
    if role not in T.ROLES:
        return 400, {"error": "unknown role %r" % (role,)}
    options, keymap = P.picker_options(role, ctx.kb.models(), purpose=purpose)
    ctx.keymaps[(project_id, role)] = keymap
    return 200, {"role": role, "project_id": project_id, "purpose": purpose,
                 "options": options}


def post_pick(ctx: RoutingCtx, query, body) -> Tuple[int, Dict]:
    body = body or {}
    project_id = body.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        return 400, {"error": "project_id required"}
    role = body.get("role")
    key = body.get("key")
    if role not in T.ROLES:
        return 400, {"error": "unknown role %r" % (role,)}
    keymap = ctx.keymaps.get((project_id, role), {})
    if key not in keymap:
        return 404, {"error": "unknown option key %r for role %r "
                              "(fetch the picker first)" % (key, role)}
    provider, model = keymap[key]
    profile = T.RoleModelProfile(
        role=role, project_id=project_id, mode="PINNED",
        provider=provider, model=model, binding="DEFAULT", version=1,
        hash=T.stable_hash({"role": role, "project": project_id,
                            "provider": provider, "model": model}))
    ctx.role_table.set_profile(profile)
    payload: Dict[str, Any] = {"ok": True, "profile": _profile_payload(profile)}
    if role == "manager":
        manager = RL.make_default_manager_profile(provider, model)
        if ctx.store is not None:
            ctx.store.save_manager_profile(manager)
        ctx.manager_profile = manager
    return 200, payload


def get_bindings(ctx: RoutingCtx, query, body) -> Tuple[int, Dict]:
    project_id = _q(query, "project_id", None)
    if not isinstance(project_id, str) or not project_id:
        return 400, {"error": "project_id required"}
    role = _q(query, "role", None)
    if role not in T.ROLES:
        return 400, {"error": "unknown role %r" % (role,)}
    profile = ctx.role_table.get_profile(project_id, role)
    payload: Dict[str, Any] = {
        "role": role, "project_id": project_id,
        "profile": _profile_payload(profile) if profile else None}
    binding = ctx.store.get_pool(project_id, role) if ctx.store else None
    if binding is None:
        payload["binding"] = None
        return 200, payload
    payload["binding"] = P.binding_view(binding)
    return 200, payload


def get_why(ctx: RoutingCtx, query, body) -> Tuple[int, Dict]:
    decision_id = _q(query, "decision_id", None)
    if not decision_id:
        return 400, {"error": "decision_id required"}
    bundle = ctx.store.why_replay(decision_id) if ctx.store else None
    if bundle is None:
        return 404, {"error": "no persisted decision %r" % (decision_id,)}
    if isinstance(bundle, tuple):
        # Frozen why_replay triple: (RoutingDecision, [RoutingAssignment],
        # RoutingEvidenceSnapshot); meta stays out (see store.get_meta).
        if len(bundle) != 3:
            return 500, {"error": "bad why bundle for %r" % (decision_id,)}
        decision, assignments, snapshot = bundle
        return 200, {"decision": _plain(decision),
                     "assignments": _plain(assignments),
                     "snapshot": _plain(snapshot)}
    return 200, bundle


def list_role_pools(ctx: RoutingCtx, query, body) -> Tuple[int, Dict]:
    project_id = _q(query, "project_id", None)
    if not isinstance(project_id, str) or not project_id:
        return 400, {"error": "project_id required"}
    # Internal caller: ctx mapped explicitly via the bound default, so the
    # facade call below carries exactly the frozen params.
    old = _DEFAULT_POOLS_CTX
    bind_pools_ctx(ctx)
    try:
        rows = get_role_pools(project_id)
    finally:
        bind_pools_ctx(old)
    roles = []
    for row in rows:
        profile = row["profile"] or {}
        binding = row["binding"] or {}
        roles.append({
            "role": row["role"],
            "mode": profile.get("mode"),
            "provider": profile.get("provider"),
            "model": profile.get("model"),
            "pool": binding.get("members", []),
            "strategy": binding.get("strategy"),
        })
    return 200, {"roles": roles}


def _enabled_allows(ctx: RoutingCtx, provider: Any,
                    model: Any) -> Optional[str]:
    """None when a (provider, model) pick is allowed, else the reason.

    The server's tick list is the routing truth: a provider with a stored
    tick list allows only its ticks (canonical compare, so ``meta/x``
    and ``x`` are one model). No stored tick lists anywhere means the
    legacy read: allowed.
    """
    if not provider or not model:
        return None
    state_dir = getattr(ctx, "model_state_dir", None)
    if not state_dir:
        return None
    pid = str(provider)
    enabled = _model_lists.load_enabled(state_dir, pid)
    if enabled is None:
        return None
    wanted = {_model_lists.canonical_model_id(pid, i) for i in enabled}
    if _model_lists.canonical_model_id(pid, model) in wanted:
        return None
    return ("model %r is not enabled for provider %r "
            "(tick it in the provider model list first)" % (model, pid))


def _member_provider_model(item: Any) -> Tuple[Any, Any]:
    if isinstance(item, Mapping):
        return (item.get("provider_id", item.get("provider")),
                item.get("model", item.get("model_id")))
    return (getattr(item, "provider_id", getattr(item, "provider", None)),
            getattr(item, "model", getattr(item, "model_id", None)))


def _chat_model_allowed(ctx: RoutingCtx, model_id: str) -> Optional[str]:
    """None when a chat model_id pick is allowed, else the reason.

    Same truth as above, across every provider with a stored tick list:
    allowed when some provider ticks it (canonical compare either with
    its own prefix or the model's own head).
    """
    state_dir = getattr(ctx, "model_state_dir", None)
    if not state_dir or not model_id:
        return None
    head = str(model_id).split("/", 1)[0]
    candidates = [head] if "/" in str(model_id) else []
    try:
        views = ctx.provider_facade.list_providers(False)
    except Exception:
        views = []
    for view in views or []:
        pid = getattr(view, "provider_id", "")
        if pid and pid not in candidates:
            candidates.append(pid)
    saw_state = False
    for pid in candidates:
        enabled = _model_lists.load_enabled(state_dir, pid)
        if enabled is None:
            continue
        saw_state = True
        wanted = {_model_lists.canonical_model_id(pid, i)
                  for i in enabled}
        if _model_lists.canonical_model_id(pid, model_id) in wanted:
            return None
    if not saw_state:
        return None
    return ("model %r is not enabled on any connected provider "
            "(tick it in the provider model list first)" % (model_id,))


def put_role_pools(ctx: RoutingCtx, query, body) -> Tuple[int, Dict]:
    # Thin adapter: the 4-guard (raw-secret refusal + mode/strategy
    # validation) lives in the set_role_pool facade; this handler only
    # translates its ValueError into the existing 400 shape.
    body = body or {}
    # Internal caller: ctx mapped explicitly via the bound default, so the
    # facade call below carries exactly the frozen params.
    old = _DEFAULT_POOLS_CTX
    bind_pools_ctx(ctx)
    try:
        try:
            _refuse_raw_secret(body)
            project_id = body.get("project_id")
            if not isinstance(project_id, str) or not project_id:
                return 400, {"error": "project_id required"}
            denied = _enabled_allows(
                ctx, body.get("provider"), body.get("model"))
            if denied is not None:
                return 400, {"error": "bad role pool: %s" % denied}
            for item in body.get("pool") or []:
                member_provider, member_model = _member_provider_model(
                    item)
                denied = _enabled_allows(
                    ctx, member_provider, member_model)
                if denied is not None:
                    return 400, {"error": "bad role pool: %s" % denied}
            profile = set_role_pool(
                project_id, body.get("role"),
                body.get("mode"), body.get("provider"), body.get("model"),
                body.get("pool"), body.get("strategy"))
        except (ValueError, KeyError, TypeError) as exc:
            return 400, {"error": "bad role pool: %s" % exc}
    finally:
        bind_pools_ctx(old)
    payload: Dict[str, Any] = {"ok": True,
                               "profile": _profile_payload(profile)}
    binding = (ctx.store.get_pool(profile.project_id, profile.role)
               if ctx.store else None)
    if binding is not None:
        payload["binding"] = P.binding_view(binding)
    return 200, payload


# --------------------------------------------------------------------------
# Chat-model save (K04P2-CHATSAVE, HD_VERDICT_PAGE_K04_2 plus ADDENDUM).
#
# PUT /api/v1/roles/chat-model persists one project's chat model pick.
# Token rule (ADDENDUM): the UI session token travels ONLY in the
# x-ui-session-token header through the K02 binding (ctx.session_token
# here); the URL query and the JSON body are never token channels, so a
# query-only token is refused with 401 exactly like a missing one. The
# old query-token guarded-write wrapper stays untouched on the old
# routes; this handler carries its own header-only guard instead.
#
# Persistence: the chat record lives in the "chat" section of the same
# profiles registry document the K04 store owns (store.py is frozen, so
# this lane reads/writes that section through the store's table API and
# changes no store shape). Registry read path: get_chat_record.
# K08 seam: journal-append (ctx.audit_sink.append) plus notify
# (ctx.emitter.emit) only; when either end is missing the save fails
# closed (500, nothing persisted) and no K08 file changes.

def get_chat_record(ctx: RoutingCtx, project_id: str) -> Optional[Dict[str, Any]]:
    """Read one project's saved chat model from the K04 registry.

    Returns {"project_id", "model_id"} or None when the registry holds
    no chat record for the project.
    """
    store = getattr(ctx, "store", None)
    if store is None:
        return None
    table = store._load_table("profiles")
    section = table.get("chat")
    if not isinstance(section, Mapping):
        return None
    row = section.get(project_id)
    if not isinstance(row, Mapping):
        return None
    model_id = row.get("model_id")
    if not (isinstance(model_id, str) and model_id):
        return None
    return {"project_id": project_id, "model_id": model_id}


def _save_chat_record(store, project_id: str, model_id: str) -> None:
    """Persist one project's chat model into the registry chat section."""
    table = store._load_table("profiles")
    section = table.get("chat")
    if not isinstance(section, dict):
        section = {}
        table["chat"] = section
    section[project_id] = {"project_id": project_id, "model_id": model_id}
    store._save_table("profiles", table)


def _chat_project_known(ctx: RoutingCtx, project_id: str) -> bool:
    """True when the K04 registry knows the project at all.

    Known means at least one frozen-role profile, one pool binding, or
    one chat record; anything else is an unknown project (404), never a
    hardcoded id list.
    """
    role_table = getattr(ctx, "role_table", None)
    if role_table is not None:
        for role in T.ROLES:
            if role_table.get_profile(project_id, role) is not None:
                return True
    store = getattr(ctx, "store", None)
    if store is not None:
        for role in T.ROLES:
            if store.get_pool(project_id, role) is not None:
                return True
        if get_chat_record(ctx, project_id) is not None:
            return True
    return False


def get_chat_model(ctx: RoutingCtx, query, body) -> Tuple[int, Dict]:
    """Read one project's saved chat model (GET /api/v1/roles/chat-model).

    Same project key as the PUT; answers 200 with the saved model_id or
    null when the registry holds no chat record. A read needs no token.
    """
    _ = body
    project_id = _q(query or {}, "project_id", None)
    if not (isinstance(project_id, str) and project_id.strip()):
        return 400, {"error": "project_id required"}
    record = get_chat_record(ctx, project_id)
    model_id = record["model_id"] if record is not None else None
    return 200, {"project_id": project_id, "model_id": model_id}


def put_chat_model(ctx: RoutingCtx, query, body) -> Tuple[int, Dict]:
    """Save one project's chat model (PUT /api/v1/roles/chat-model)."""
    _ = query
    token = getattr(ctx, "session_token", None)
    if isinstance(token, list):
        token = token[0] if token else None
    if not (isinstance(token, str) and token.strip()):
        return (401, {
            "error": "chat save refused: x-ui-session-token header missing "
                     "(the UI session token travels only in that header, "
                     "never in the URL query or the JSON body)",
            "code": _USER_WRITE_DENIED_CODE,
        })
    if not isinstance(body, Mapping):
        return 400, {"error": "chat save needs a JSON object body"}
    hit = _find_raw_secret(body)
    if hit:
        return 400, {"error": "raw secret material refused at %s "
                              "(pass a SecretRef handle, never raw)" % hit}
    if set(body.keys()) != {"project_id", "model_id"}:
        return 400, {"error": "chat save body holds exactly project_id "
                              "plus model_id"}
    project_id = body.get("project_id")
    model_id = body.get("model_id")
    if not (isinstance(project_id, str) and project_id.strip()) or not (
            isinstance(model_id, str) and model_id.strip()):
        return 400, {"error": "chat save needs non-empty project_id plus "
                              "model_id"}
    denied = _chat_model_allowed(ctx, model_id)
    if denied is not None:
        return 400, {"error": denied}
    if not _chat_project_known(ctx, project_id):
        return 404, {"error": "unknown project %r (no role profile, no pool "
                              "binding, no chat record)" % (project_id,)}
    store = getattr(ctx, "store", None)
    if store is None:
        return 500, {"error": "chat save refused: no K04 registry bound"}
    sink = getattr(ctx, "audit_sink", None)
    emitter = getattr(ctx, "emitter", None)
    if sink is None or not callable(getattr(sink, "append", None)) or \
            emitter is None or not callable(getattr(emitter, "emit", None)):
        return (500, {
            "error": "chat save refused: K08 seam DOWN (journal-append "
                     "plus notify unavailable; fail-closed, nothing "
                     "persisted)",
        })
    _save_chat_record(store, project_id, model_id)
    sink.append({"project_id": project_id, "model_id": model_id})
    emitter.emit(routing_event(
        project_id=project_id, task_id="-", run_id="-", role="chat",
        event_type="chat_model_save",
        reason="chat model for project %r set to %r"
               % (project_id, model_id),
        model=model_id))
    return 200, {"ok": True, "project_id": project_id,
                 "model_id": model_id}


def _plain(value):
    """Convert dataclass records (or nested mixes) to plain JSON data."""
    if _is_dc(value) and not isinstance(value, type):
        return _dc_asdict(value)
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def get_decision_why(ctx: RoutingCtx, query, body) -> Tuple[int, Dict]:
    decision_id = (_q(query, "decision_id", None)
                   or _q(query, "id", None))
    if not decision_id:
        return 400, {"error": "decision_id required"}
    store = ctx.store
    bundle = store.why_replay(decision_id) if store else None
    if bundle is None:
        return 404, {"error": "no persisted decision %r" % (decision_id,)}
    if isinstance(bundle, tuple):
        if len(bundle) != 3:
            return 500, {"error": "bad why bundle for %r" % (decision_id,)}
        decision, assignments, snapshot = bundle
        meta = (store.get_meta(decision_id)
                if hasattr(store, "get_meta") else None)
        return 200, {"decision": _plain(decision),
                     "assignments": _plain(assignments),
                     "snapshot": _plain(snapshot),
                     "meta": meta}
    payload = {"decision": bundle.get("decision"),
               "assignments": bundle.get("assignments"),
               "snapshot": bundle.get("snapshot"),
               "meta": bundle.get("meta")}
    if payload["meta"] is None and hasattr(store, "get_meta"):
        payload["meta"] = store.get_meta(decision_id)
    return 200, payload


def get_suggest(ctx: RoutingCtx, query, body) -> Tuple[int, Dict]:
    provider = _q(query, "provider", None)
    purpose = _q(query, "purpose", "coding")
    if not provider:
        return 400, {"error": "provider required"}
    best = P.suggest_strongest(ctx.kb, provider, purpose=purpose)
    if best is None:
        return 404, {"error": "no text/tools/coding model on file for %r"
                              % (provider,)}
    quality = best.strict_pass_rate
    return 200, {
        "provider": best.provider, "model": best.model, "purpose": purpose,
        "reason": "strongest %s model on %s: fit %s, measured quality %s, "
                  "%s (never image/audio/embedding, never alphabetical)"
                  % (purpose, provider, _num(best.fit_for(purpose)),
                     _num(quality),
                     "known prices" if best.has_known_price()
                     else "price unknown"),
    }


def _num(value) -> str:
    return "%.2f" % value if value is not None else "unknown"


def _decide_request(body, *, project_id, task_id, run_id, role,
                    task_class, policy, opt, candidates, profile, mode,
                    pinned_provider=None, pinned_model=None) -> R.RoutingRequest:
    """Full RoutingRequest for the pool/PINNED/blocked paths (fields unchanged)."""
    exclude_pairs = tuple(tuple(p) for p in body.get("exclude_pairs", []))
    if pinned_provider is None:
        pinned_provider = (body.get("pinned_provider")
                           or (profile.provider
                               if profile and mode == "PINNED" else None))
    if pinned_model is None:
        pinned_model = (body.get("pinned_model")
                        or (profile.model
                            if profile and mode == "PINNED" else None))
    return R.RoutingRequest(
        project_id=project_id, task_id=task_id, run_id=run_id, role=role,
        task_class=task_class, routing_policy=policy, optimization_policy=opt,
        candidates=tuple(candidates),
        required_capabilities=tuple(body.get("required_capabilities", ("text",))),
        required_modalities=tuple(body.get("required_modalities", ("text",))),
        task_risk=body.get("task_risk", "LOW"), mode=mode,
        pinned_provider=pinned_provider, pinned_model=pinned_model,
        override_provider=body.get("override_provider"),
        override_model=body.get("override_model"),
        excluded_models=tuple(body.get("excluded_models", ())),
        exclude_pairs=exclude_pairs,
        preferred_route=body.get("preferred_route"),
        preferred_strategy=body.get("preferred_strategy"),
        ranking=body.get("ranking", "optimal"),
        turn_cap=body.get("turn_cap"),
        director_pick_provider=body.get("director_pick_provider"),
        director_pick_model=body.get("director_pick_model"),
        subtask_id=body.get("subtask_id"), stage=body.get("stage"),
        manager_trigger=body.get("manager_trigger"),
        manager_trigger_ref=body.get("manager_trigger_ref"),
        tolerant_parser=bool(body.get("tolerant_parser", False)))


def _manager_bound(ctx: RoutingCtx, role):
    """ctx.manager_profile with a plain mapping converted (manager role)."""
    manager_profile = ctx.manager_profile
    if role == "manager" and isinstance(manager_profile, Mapping):
        try:
            return T.DefaultManagerProfile(**manager_profile)
        except TypeError:
            return None
    return manager_profile


def _role_deps(ctx: RoutingCtx, role) -> R.RoutingDeps:
    """RoutingDeps with the manager profile bound for the manager role."""
    deps = ctx.deps()
    return R.RoutingDeps(
        kb=deps.kb, provider_health=deps.provider_health,
        model_health=deps.model_health,
        provider_capabilities=deps.provider_capabilities,
        resource_state=deps.resource_state, budget_state=deps.budget_state,
        manager_profile=_manager_bound(ctx, role),
        store=deps.store, emitter=deps.emitter)


def _state_ref(state, default: str) -> str:
    if isinstance(state, Mapping):
        return state.get("ref", default)
    return getattr(state, "ref", None) or default


def _blocked_with_reason(request: R.RoutingRequest, deps: R.RoutingDeps,
                         reason: str) -> R.RoutingOutcome:
    """Blocked outcome carrying the frozen wrapper's genuine reason verbatim."""
    outcome = R.blocked_outcome(request, deps, (),
                                "post_decide: select blocked")
    decision = _dc_replace(outcome.decision, reason=reason)
    return R.RoutingOutcome(outcome.status, decision, outcome.assignments,
                            outcome.snapshot, outcome.trace)


def post_decide(ctx: RoutingCtx, query, body) -> Tuple[int, Dict]:
    body = body or {}
    project_id = body.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        return 400, {"error": "project_id required"}
    task_id = body.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        return 400, {"error": "task_id required"}
    run_id = body.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        return 400, {"error": "run_id required"}
    role = body.get("role", "worker")
    if role not in T.ROLES:
        return 400, {"error": "unknown role %r" % (role,)}
    task_class = body.get("task_class", "coding")
    policy_body = body.get("routing_policy")
    opt_body = body.get("optimization_policy")
    try:
        policy = (T.RoutingPolicy(**policy_body) if policy_body
                  else ctx.default_policy(task_class))
        opt = (T.OptimizationPolicy(**opt_body) if opt_body
               else ctx.default_opt())
    except (TypeError, ValueError) as exc:
        return 400, {"error": "bad policy: %s" % exc}

    raw_cands = body.get("candidates", [])
    candidates = []
    for item in raw_cands:
        try:
            candidates.append(T.CandidateModel(
                provider=item["provider"], model=item["model"],
                provider_instance=item.get("provider_instance"),
                provider_type=item.get("provider_type", "cloud"),
                is_mock=bool(item.get("is_mock", False))))
        except (KeyError, ValueError) as exc:
            return 400, {"error": "bad candidate: %s" % exc}

    profile = ctx.role_table.get_profile(project_id, role)
    mode = body.get("mode") or (profile.mode if profile else "AUTO")

    def base_request(**over) -> R.RoutingRequest:
        return _decide_request(
            body, project_id=project_id, task_id=task_id, run_id=run_id,
            role=role, task_class=task_class, policy=policy, opt=opt,
            candidates=candidates, profile=profile, mode=mode, **over)

    # Pool branch: the stored binding's strategy decides (resolve_pool);
    # the surfaced strategy comes from that same binding via _retag.
    if profile is not None and profile.mode == "pool" and ctx.store is not None:
        binding = ctx.store.get_pool(project_id, role)
        if binding is not None:
            request = base_request()
            outcome = P.resolve_pool(binding, request, _role_deps(ctx, role))
            _record(ctx, request, outcome)
            return _decide_payload(outcome)

    # PINNED branch: the single model comes from the frozen
    # resolve_role_model facade (ctx.role_table bound as its scope; the
    # call itself carries exactly the 2 frozen params); its
    # NO_PROFILE_BLOCKED raise becomes the existing BLOCKED outcome at
    # this HTTP boundary (shapes unchanged).
    if mode == "PINNED":
        RL.bind_role_table(ctx.role_table)
        try:
            try:
                ref = RL.resolve_role_model(role, project_id)
            except ValueError as exc:
                request = base_request()
                outcome = _blocked_with_reason(request, ctx.deps(), str(exc))
                _record(ctx, request, outcome)
                return _decide_payload(outcome)
        finally:
            RL.unbind_role_table()
        request = base_request(
            pinned_provider=body.get("pinned_provider") or ref.provider,
            pinned_model=body.get("pinned_model") or ref.model)
        outcome = R.decide_and_record(request, _role_deps(ctx, role))
        return _decide_payload(outcome)

    # Generic path: the frozen router.select wrapper. A request-scoped
    # registry is built from this request (policies/contracts keyed by
    # their ids; body candidates translated to CandidateView mappings;
    # body exclusions carried as rejected views) and bound as the
    # facade's scope; the call itself carries exactly the 6 frozen ref
    # params. The wrapper already persists + emits on success, so no
    # _record here (no double write); its ValueError becomes the
    # existing blocked-payload shape.
    request = base_request()
    excluded_names = set(body.get("excluded_models", ()))
    views: List[Dict[str, Any]] = [
        {"provider_id": item.provider, "model": item.model,
         "provider_instance": item.provider_instance}
        for item in candidates]
    for pair in body.get("exclude_pairs", []):
        try:
            prov, mod = tuple(pair)
        except (TypeError, ValueError):
            continue
        views.append({"provider_id": prov, "model": mod, "rejected": True})
    for item in candidates:
        if item.model in excluded_names:
            views.append({"provider_id": item.provider, "model": item.model,
                          "rejected": True})
    tc_ref = "tc:%s:%s:%s" % (project_id, task_id, run_id)
    R.bind_select_scope({
        "task_contracts": {tc_ref: {
            "project_id": project_id, "task_id": task_id,
            "run_id": run_id, "role": role, "task_class": task_class,
            "required_capabilities": tuple(
                body.get("required_capabilities", ("text",))),
            "required_modalities": tuple(
                body.get("required_modalities", ("text",))),
            "task_risk": body.get("task_risk", "LOW")}},
        "routing_policies": {policy.policy_id: policy},
        "optimization_policies": {opt.policy_id: opt},
        "kb": ctx.kb,
        "provider_health": ctx.provider_health,
        "model_health": ctx.model_health,
        "provider_capabilities": ctx.provider_capabilities,
        "resource_state": ctx.resource_state,
        "budget_state": ctx.budget_state,
        "store": ctx.store,
        "emitter": ctx.emitter,
        "manager_profile": _manager_bound(ctx, role),
    })
    try:
        try:
            outcome = R.select(
                tc_ref, views, policy.policy_id, opt.policy_id,
                _state_ref(ctx.budget_state, "bs:default"),
                _state_ref(ctx.resource_state, "rs:default"))
        except ValueError as exc:
            outcome = _blocked_with_reason(request, ctx.deps(), str(exc))
            _record(ctx, request, outcome)
            return _decide_payload(outcome)
    finally:
        R.unbind_select_scope()
    return _decide_payload(outcome)


def _record(ctx: RoutingCtx, request: R.RoutingRequest,
            outcome: R.RoutingOutcome) -> None:
    if ctx.store is not None:
        ctx.store.save_decision(outcome.decision, outcome.assignments,
                                outcome.snapshot, turn_cap=request.turn_cap)
    if ctx.emitter is not None:
        decision = outcome.decision
        ctx.emitter.emit(routing_event(
            project_id=request.project_id, task_id=request.task_id,
            run_id=request.run_id, role=request.role, route=decision.route,
            provider=decision.selected_provider, model=decision.selected_model,
            reason=decision.reason,
            routing_decision_ref=decision.decision_id,
            routing_snapshot_id=decision.routing_snapshot_id,
            mock=("mock: true" in decision.reason),
            capability_rule=decision.eligibility_source))


def _decide_payload(outcome: R.RoutingOutcome) -> Tuple[int, Dict]:
    decision = outcome.decision
    return 200, {
        "status": outcome.status,
        "decision_id": decision.decision_id,
        "route": decision.route,
        "strategy": decision.strategy,
        "selected_provider": decision.selected_provider,
        "selected_model": decision.selected_model,
        "reason": decision.reason,
        "eligibility_source": decision.eligibility_source,
        "capability_state": decision.capability_state,
        "assignments": [
            {"assignment_id": a.assignment_id, "role": a.role,
             "stage": a.stage, "route": a.route, "provider": a.provider,
             "model": a.model, "status": a.status}
            for a in outcome.assignments],
        "fallback_chain": list(decision.fallback_chain),
    }


def post_compensate(ctx, query, body) -> Tuple[int, Dict]:
    """Compensate a failed gate to RELEASED (ARCH-441, served entry).

    Delegates to the budget lane at call time: backend never imports
    budget at module level (no cycle, budget/__init__ docstring).
    """
    from agent_si.budget.routes import post_compensate as _impl
    return _impl(ctx, query, body)


def get_optimization_policy(ctx, query, body) -> Tuple[int, Dict]:
    """Serve the active OptimizationPolicy (ARCH-528 read leg).

    Returns required quality, the risk ceiling and the weights from the
    served context default (reads are open, no session token needed).
    """
    opt = ctx.default_opt()
    return 200, {
        "policy_id": opt.policy_id,
        "version": opt.version,
        "required_quality": opt.required_quality,
        "max_risk": opt.max_risk,
        "weights": {
            "weight_quality": opt.weight_quality,
            "weight_cost": opt.weight_cost,
            "weight_latency": opt.weight_latency,
            "weight_cloud_tokens": opt.weight_cloud_tokens,
        },
        "local_preference": opt.local_preference,
    }


def post_target_flow(ctx, query, body) -> Tuple[int, Dict]:
    """Load every role profile from TARGET_FLOW configuration (UID-17).

    All-or-nothing: a role without a configured entry refuses the whole
    load (no hard-coded role default), so partial configuration never
    stores partial defaults.
    """
    body = body if isinstance(body, Mapping) else {}
    project_id = body.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        return 400, {"error": "project_id required"}
    config = body.get("target_flow") or {}
    try:
        loaded = RL.load_target_flow(ctx.role_table, config,
                                     project_id=project_id)
    except RL.TargetFlowMissingError as exc:
        return 400, {"code": exc.code, "message": str(exc)}
    return 200, {"project_id": project_id, "loaded": loaded}


#: Refusal code when the L3 audit entry arrives without its decision ids.
L3_DECISION_IDS_REQUIRED = "L3_DECISION_IDS_REQUIRED"


def post_l3_audit(ctx, query, body) -> Tuple[int, Dict]:
    """Run an L3 independent audit on the separate provider path (168).

    The binding plus the key ref arrive in the body; the runner comes
    from the server-side ctx binding (production: the wired SDK runner).
    Validation legs (same provider, missing key) fail before anything
    runs; a missing runner is an honest 502, never a silent local pass.
    """
    from agent_si.sdk_adapter import sdk_adapter as _sa

    body = body if isinstance(body, Mapping) else {}
    key = body.get("key_ref")
    key_ref = None
    if isinstance(key, Mapping):
        try:
            key_ref = _sa.SecretRef(
                secret_id=str(key.get("secret_id") or ""),
                provider_id=str(key.get("provider_id") or ""),
                type=str(key.get("type") or ""),
                scope=str(key.get("scope") or ""),
                source=str(key.get("source") or ""),
                created_at=str(key.get("created_at") or ""),
                last_rotated_at=str(key.get("last_rotated_at") or ""))
        except TypeError:
            key_ref = None
    if key_ref is None or not key_ref.secret_id:
        key_ref = None
    missing_ids = [name for name, value in
                   (("decision_id", body.get("decision_id")),
                    ("project_id", body.get("project_id")),
                    ("task_id", body.get("task_id")),
                    ("run_id", body.get("run_id")))
                   if not isinstance(value, str) or not value]
    if missing_ids:
        return 400, {"code": L3_DECISION_IDS_REQUIRED,
                     "message": "l3 audit needs %s"
                                % (", ".join(missing_ids),)}
    decision = _sa.RoutingDecisionBinding(
        decision_id=str(body.get("decision_id")),
        project_id=str(body.get("project_id")),
        task_id=str(body.get("task_id")),
        run_id=str(body.get("run_id")),
        selected_provider=str(body.get("selected_provider") or ""),
        selected_model=str(body.get("selected_model") or ""))
    try:
        binding = _sa.bind_l3_audit(
            decision, l3_provider=str(body.get("l3_provider") or ""),
            l3_model=str(body.get("l3_model") or ""), key_ref=key_ref)
    except _sa.L3ProviderMustDifferError as exc:
        return 400, {"code": exc.code, "message": str(exc)}
    except _sa.L3KeyRefRequiredError as exc:
        return 400, {"code": exc.code, "message": str(exc)}
    runner = getattr(ctx, "l3_runner", None)
    adapter = _sa.OpenAIAgentsSDKAdapter(runner=runner)
    try:
        result = adapter.run_l3_audit(
            binding,
            input_ref=str(body.get("input_ref") or
                          "audit:%s:%s" % (binding.task_id, binding.run_id)),
            secret_ref=key_ref, runner=runner)
    except _sa.RunnerUnboundError as exc:
        return 502, {"code": exc.code, "message": str(exc)}
    return 200, {"provider": result.provider, "model": result.model,
                 "output_ref": result.output_ref,
                 "status": str(result.status),
                 "error_ref": result.error_ref}


# --------------------------------------------------------------------------
# Route table + mount + stdlib serve

ROUTES: Tuple[Tuple[str, str, str, Callable], ...] = (
    ("get", "/api/v1/routing/roles", "list_roles", list_roles),
    ("get", "/api/v1/routing/role", "get_role", get_role),
    ("post", "/api/v1/routing/role", "set_role", set_role),
    ("put", "/api/v1/routing/role", "set_role_put", set_role),
    ("get", "/api/v1/routing/picker", "get_picker", get_picker),
    ("post", "/api/v1/routing/pick", "post_pick", post_pick),
    ("get", "/api/v1/routing/bindings", "get_bindings", get_bindings),
    ("get", "/api/v1/routing/why", "get_why", get_why),
    ("get", "/api/v1/routing/suggest", "get_suggest", get_suggest),
    ("post", "/api/v1/routing/decide", "post_decide", post_decide),
    ("post", "/api/v1/budget/compensations", "post_compensate",
     post_compensate),
    ("get", "/api/v1/routing/optimization-policy",
     "get_optimization_policy", get_optimization_policy),
    ("post", "/api/v1/roles/target-flow", "post_target_flow",
     post_target_flow),
    ("post", "/api/v1/routing/l3-audit", "post_l3_audit", post_l3_audit),
    ("get", "/api/v1/roles/pools", "list_role_pools", list_role_pools),
    ("put", "/api/v1/roles/pools", "put_role_pools", put_role_pools),
    ("get", "/api/v1/routing/decision/{id}/why", "get_decision_why",
     get_decision_why),
)

def _match_template(template: str, path: str) -> Optional[Dict[str, str]]:
    """Match a concrete path against a {placeholder} template.

    Returns the captured segments keyed by placeholder name, or None
    when the segments differ.
    """
    t_segs = template.split("/")
    p_segs = path.split("/")
    if len(t_segs) != len(p_segs):
        return None
    params: Dict[str, str] = {}
    for t, p in zip(t_segs, p_segs):
        if t.startswith("{") and t.endswith("}"):
            params[t[1:-1]] = p
        elif t != p:
            return None
    return params


def _resolve_dispatch(method: str, path: str):
    """Resolve (method, path) to (handler, params), template-aware.

    Exact entries win; otherwise the first ROUTES template with the same
    method whose segments match wins, with {placeholders} captured. The
    why template's {id} is exposed as both "id" and "decision_id" so the
    handler's query lookup finds it.
    """
    key = (method, path)
    if key in _DISPATCH_BASE:
        return _DISPATCH_BASE[key], {}
    for tm, tp, _name, fn in ROUTES + _LEGACY_ROUTES:
        if tm != method:
            continue
        params = _match_template(tp, path)
        if params is not None:
            if "id" in params and "decision_id" not in params:
                params["decision_id"] = params["id"]
            return fn, params
    return None, {}


class _DispatchMap(dict):
    """dict of (method, path) -> handler with template-aware lookups.

    Exact entries are stored; template routes (e.g.
    /api/v1/routing/decision/{id}/why) also match concrete paths via
    __contains__/__getitem__/get so `("get", concrete) in _DISPATCH`
    holds and serve() routes concrete ids. Never special-cases an id.
    """

    def __contains__(self, key):
        if dict.__contains__(self, key):
            return True
        try:
            method, path = key
        except (TypeError, ValueError):
            return False
        fn, _params = _resolve_dispatch(method, path)
        return fn is not None

    def __getitem__(self, key):
        if dict.__contains__(self, key):
            return dict.__getitem__(self, key)
        method, path = key
        fn, _params = _resolve_dispatch(method, path)
        if fn is None:
            raise KeyError(key)
        return fn

    def get(self, key, default=None):
        if dict.__contains__(self, key):
            return dict.__getitem__(self, key)
        try:
            method, path = key
        except (TypeError, ValueError):
            return default
        fn, _params = _resolve_dispatch(method, path)
        return fn if fn is not None else default


_DISPATCH_BASE = {(method, path): fn for method, path, _name, fn in ROUTES}

_DISPATCH = _DispatchMap(_DISPATCH_BASE)

# Pre-freeze A2 routing rows stay served here (mount/serve/_DISPATCH)
# until the HD takes a removal decision; the D9 merge assigns them.
_LEGACY_ROUTES: Tuple[Tuple[str, str, str, Callable], ...] = ()


def mount(app, ctx: RoutingCtx):
    """Register every route on a `.get`/`.post` host (framework-agnostic).

    The host calls handlers as ``handler(query, body)`` where query is a
    string-keyed mapping and body is the parsed JSON object (or None).
    Returns the app for chaining.
    """
    for method, path, _name, fn in ROUTES + _LEGACY_ROUTES:
        registrar = getattr(app, method)

        def wrapper(query=None, body=None, _fn=fn):
            return _fn(ctx, query or {}, body)

        registrar(path)(wrapper)
    return app


def serve(ctx: RoutingCtx, host: str = "127.0.0.1", port: int = 0):
    """Start a stdlib HTTP server for probes; returns (server, thread, url)."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep probe output clean
            return None

        def _handle(self):
            parsed = urlparse(self.path)
            fn, params = _resolve_dispatch(self.command.lower(), parsed.path)
            if fn is None:
                self._send(404, {"error": "unknown route %s" % parsed.path})
                return
            query = {k: v[0] if len(v) == 1 else v
                     for k, v in parse_qs(parsed.query).items()}
            for k, v in params.items():
                query.setdefault(k, v)
            body = None
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                raw = self.rfile.read(length)
                if raw.strip():
                    try:
                        body = json.loads(raw.decode("utf-8"))
                    except ValueError:
                        self._send(400, {"error": "body is not JSON"})
                        return
            try:
                status, payload = fn(ctx, query, body)
            except Exception as exc:  # probes must see a 500, never a hang
                self._send(500, {"error": "%s: %s" % (type(exc).__name__, exc)})
                return
            self._send(status, payload)

        def _send(self, status: int, payload: Dict):
            data = json.dumps(payload, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._handle()

        def do_POST(self):
            self._handle()

        def do_PUT(self):
            self._handle()

    server = ThreadingHTTPServer((host, port), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
    thread.daemon = True
    thread.start()
    url = "http://%s:%d" % (host, server.server_address[1])
    return server, thread, url


# --------------------------------------------------------------------------
# D9 wiring: frozen section-4 surface (import-merge; B2 budget precedent).
#
# ROUTES is the frozen HTTP surface (the exact d09 set): the 5 provider
# rows (owned by providers/registry/provider_routes.py), the 2 KB rows
# (owned by backend/modelkb.py) and the budget row (owned by
# budget/routes.py, also merged by budget/__init__ on its own import) are
# merged into the served tables here at import, idempotently. Raw handler
# functions above are unchanged; the served tables hold thin wrappers
# (USER-write session guard + provider-ctx adaptation). serve()/mount()/
# _DISPATCH dispatch ROUTES + _LEGACY_ROUTES, so the pre-freeze A2 rows
# stay reachable until the HD takes a removal decision.
#
# Cycle note: backend imports only leaf route modules. provider_routes
# and modelkb never import backend (docstring-stated, verified); the
# budget gate is never imported (only budget.routes' row is referenced),
# so the backend never joins the budget cycle.

from agent_si.providers.registry import provider_routes as _provider_routes
from agent_si.providers.registry import provider_model_lists as _model_lists
from agent_si.backend import modelkb as _modelkb
from agent_si.budget.routes import BUDGET_ROUTES as _BUDGET_ROUTES

#: Served methods treated as USER writes (K04_INTERFACE section 4 guard).
_USER_WRITE_METHODS = ("post", "put", "delete")

#: Frozen refusal code for token-less USER writes (K13 frozen family).
_USER_WRITE_DENIED_CODE = "CONTEXT_MISSING"

_D9_MERGED = False


def _served_token(ctx, query, body):
    """Return the request's UI session token, or None when absent.

    The K06 UI session handle travels ONLY in the x-ui-session-token
    header through the server-side ctx binding
    (``session_token``/``ui_session_token``); reads ignore it. The
    URL query is never a token channel: a ``?session_token=...``
    value is refused (it is not read here, never used, never logged).
    The JSON body is deliberately not a token channel either:
    ``session_token`` is a secret-looking field and stays refused by
    the raw-secret guards.
    """
    _ = query
    _ = body
    for attr in ("session_token", "ui_session_token"):
        token = getattr(ctx, attr, None)
        if isinstance(token, str) and token.strip():
            return token
    return None


def _require_user_write_session(ctx, query, body):
    """K13 route-guard hook: USER writes check the UI session token first.

    Returns None when the request carries a session token, else the
    frozen (401, CONTEXT_MISSING) refusal (401 matches the provider
    lane's own token-less-delete refusal). Reads never call this.
    """
    if _served_token(ctx, query, body) is not None:
        return None
    return (401, {
        "error": "USER write refused: UI session token missing "
                 "(USER writes check the UI session token first; "
                 "reads need none)",
        "code": _USER_WRITE_DENIED_CODE,
    })


def _guarded_write(name, fn):
    """Serve a USER-write handler behind the session-token guard."""
    def wrapper(ctx, query, body):
        denial = _require_user_write_session(ctx, query, body)
        if denial is not None:
            return denial
        return fn(ctx, query or {}, body)
    wrapper.__name__ = "guarded_" + name
    wrapper.__wrapped__ = fn
    return wrapper


def _provider_models(ctx):
    """Derive provider-id -> model-id rows from the served ctx KB port.

    The provider lane's models port carries the KB rows when supplied;
    unknown shapes fall back to {} (the handlers then report the real
    empty-registry/404 behavior, never fake rows).
    """
    kb = getattr(ctx, "kb", None)
    if kb is None:
        return {}
    try:
        facts = kb.models()
    except Exception:
        return {}
    models: Dict[str, list] = {}
    for fact in facts or []:
        provider = getattr(fact, "provider", None)
        model = getattr(fact, "model", None)
        if isinstance(fact, Mapping):
            provider = fact.get("provider", provider)
            model = fact.get("model", model)
        if provider and model:
            models.setdefault(provider, []).append(model)
    return models


def _served_kb_rows() -> list:
    """Catalog rows with price fields for the provider-model merge."""
    try:
        rows = _modelkb.get_models([], None)
    except Exception:
        return []
    out = []
    for row in rows or []:
        if not isinstance(row, Mapping):
            continue
        out.append({"provider_id": row.get("provider_id"),
                    "model_id": row.get("model_id"),
                    "fields": row.get("fields") if isinstance(
                        row.get("fields"), Mapping) else {}})
    return out


def _provider_served(name, fn, *, write):
    """Serve a provider-lane handler on the pools-routes host ctx.

    Wiring (per the provider lane HANDOFF: host wiring stays with the
    pools routes owner): adapts the served RoutingCtx to the lane's
    ProviderCtx over the default facade, with USER writes guarded first.
    """
    def wrapper(ctx, query, body):
        if write:
            denial = _require_user_write_session(ctx, query, body)
            if denial is not None:
                return denial
        facade = getattr(ctx, "provider_facade", None)
        if facade is None:
            facade = _provider_routes._default_facade
        pctx = _provider_routes.ProviderCtx(
            facade=facade, models=_provider_models(ctx),
            credential_store=getattr(ctx, "credential_store", None),
            model_state_dir=getattr(ctx, "model_state_dir", None),
            kb_rows=_served_kb_rows())
        return fn(pctx, query or {}, body)
    wrapper.__name__ = "served_" + name
    wrapper.__wrapped__ = fn
    return wrapper


def _d9_merge():
    """Merge the frozen rows into the served tables (idempotent)."""
    global ROUTES, _LEGACY_ROUTES, _D9_MERGED
    if _D9_MERGED:
        return
    _D9_MERGED = True
    frozen = (
        ("get", "/api/v1/providers", "list_providers",
         _provider_served("list_providers",
                          _provider_routes.list_providers, write=False)),
        ("post", "/api/v1/providers/connect", "connect_provider",
         _provider_served("connect_provider",
                          _provider_routes.connect_provider, write=True)),
        ("post", "/api/v1/providers/{id}/disconnect", "disconnect_provider",
         _provider_served("disconnect_provider",
                          _provider_routes.disconnect_provider, write=True)),
        ("get", "/api/v1/providers/{id}/models", "provider_models",
         _provider_served("provider_models",
                          _provider_routes.provider_models, write=False)),
        ("post", "/api/v1/providers/{id}/models/refresh",
         "refresh_provider_models",
         _provider_served("refresh_provider_models",
                          _provider_routes.refresh_provider_models,
                          write=True)),
        ("put", "/api/v1/providers/{id}/models", "put_provider_models",
         _provider_served("put_provider_models",
                          _provider_routes.put_provider_models, write=True)),
        ("get", "/api/v1/chat/models", "chat_models",
         _provider_served("chat_models",
                          _provider_routes.chat_models, write=False)),
        ("get", "/api/v1/roles/pools", "list_role_pools", list_role_pools),
        ("put", "/api/v1/roles/pools", "put_role_pools",
         _guarded_write("put_role_pools", put_role_pools)),
        ("get", "/api/v1/routing/decision/{id}/why", "get_decision_why",
         get_decision_why),
        ("get", "/api/v1/budget", "get_budget", _BUDGET_ROUTES[0][3]),
        ("get", "/api/v1/kb/status", "kb_status", _modelkb.kb_status),
        ("post", "/api/v1/kb/proposals/apply", "kb_proposal_apply",
         _guarded_write("kb_proposal_apply", _modelkb.kb_proposal_apply)),
        ("put", "/api/v1/roles/chat-model", "put_chat_model",
         _guarded_write("put_chat_model", put_chat_model)),
        ("get", "/api/v1/roles/chat-model", "get_chat_model",
         get_chat_model),
    )
    frozen_keys = {(method.lower(), path) for method, path, _n, _f in frozen}
    legacy = []
    for method, path, name, fn in ROUTES:
        if (str(method).lower(), str(path)) in frozen_keys:
            continue
        if str(method).lower() in _USER_WRITE_METHODS:
            fn = _guarded_write(name, fn)
        legacy.append((method, path, name, fn))
    ROUTES = tuple(frozen)
    _LEGACY_ROUTES = tuple(legacy)
    served = ROUTES + _LEGACY_ROUTES
    _DISPATCH_BASE.clear()
    _DISPATCH_BASE.update(
        {(method, path): fn for method, path, _name, fn in served})
    _DISPATCH.clear()
    _DISPATCH.update(_DISPATCH_BASE)


_d9_merge()
