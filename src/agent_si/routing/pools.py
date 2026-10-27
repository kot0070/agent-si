# K04 Lane A2 — plain-language pool strategies + guided picker + suggestions.
# Strategies: Director decides per task (default when the pool holds more
# than one model), Auto, Fallback order, Split/parallel. The picker never
# exposes raw ids: options carry opaque keys, resolved server-side.
"""Pool bindings, strategy resolution, picker, strongest-model suggestion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Tuple

from . import types as T
from .kb_port import KbModelFacts, KbReader, is_text_code_candidate
from .router import RoutingDeps, RoutingOutcome, RoutingRequest
from . import router as R


@dataclass(frozen=True)
class PoolMember:
    provider: str
    model: str  # exact model id, verbatim (server-side only, never in picker)
    use_mode: str = "primary"  # primary | fallback | draft | verify | parallel
    provider_type: str = "cloud"  # cloud | local

    def __post_init__(self):
        T.check_enum("use_mode", self.use_mode, T.POOL_USE_MODES)
        if self.provider_type not in ("cloud", "local"):
            raise ValueError("invalid provider_type: %r" % (self.provider_type,))


@dataclass(frozen=True)
class PoolBinding:
    role: str
    project_id: str
    strategy: str
    members: tuple
    version: int = 1

    def __post_init__(self):
        if self.role not in T.ROLES:
            raise ValueError("invalid role: %r" % (self.role,))
        T.check_enum("strategy", self.strategy, T.POOL_STRATEGIES)
        if not self.members:
            raise ValueError("pool binding needs at least one member")


def default_strategy_for(member_count: int) -> str:
    """Director decides per task when the pool holds more than one model."""
    return "DIRECTOR_PER_TASK" if member_count > 1 else "AUTO"


def make_binding(role: str, project_id: str, members,
                 strategy: Optional[str] = None, version: int = 1) -> PoolBinding:
    """Build a binding; frozen strategy, defaulting per member count."""
    members = tuple(members)
    if strategy is None:
        strategy = default_strategy_for(len(members))
    return PoolBinding(role=role, project_id=project_id, strategy=strategy,
                       members=members, version=version)


def binding_view(binding) -> Dict:
    """Stored binding read back with the declared use mode per member."""
    if isinstance(binding, Mapping):
        members = binding.get("members", ())
        strategy = T.migrate_pool_strategy(binding.get("strategy"))
        return {
            "role": binding.get("role"),
            "project_id": binding.get("project_id"),
            "strategy": strategy,
            "strategy_label": T.STRATEGY_LABELS.get(strategy, ""),
            "version": binding.get("version", 1),
            "members": [{"provider": m.get("provider"), "model": m.get("model"),
                         "use_mode": m.get("use_mode", "primary"),
                         "provider_type": m.get("provider_type", "cloud")}
                        for m in members],
        }
    strategy = T.migrate_pool_strategy(binding.strategy)
    return {
        "role": binding.role,
        "project_id": binding.project_id,
        "strategy": strategy,
        "strategy_label": T.STRATEGY_LABELS[strategy],
        "version": binding.version,
        "members": [{"provider": m.provider, "model": m.model,
                     "use_mode": m.use_mode, "provider_type": m.provider_type}
                    for m in binding.members],
    }


# --------------------------------------------------------------------------
# Guided picker (no raw ids in options)

def picker_options(role: str, facts_list: List[KbModelFacts],
                   purpose: str = "coding") -> Tuple[List[Dict[str, str]], Dict[str, Tuple[str, str]]]:
    """Guided options with opaque keys; raw ids stay server-side in keymap.

    Options are ordered by fit then measured quality then known prices,
    never alphabetically.
    """
    cands = [f for f in (facts_list or [])
             if purpose == "vision" or is_text_code_candidate(f)]

    def rank(f: KbModelFacts):
        fit = f.fit_for(purpose)
        quality = f.strict_pass_rate
        return ((fit if fit is not None else -1.0) * -1.0,
                (quality if quality is not None else -1.0) * -1.0,
                0 if f.has_known_price() else 1)

    ordered = sorted(cands, key=rank)
    options: List[Dict[str, str]] = []
    keymap: Dict[str, Tuple[str, str]] = {}
    for index, facts in enumerate(ordered):
        key = "opt-%d" % (index + 1)
        keymap[key] = (facts.provider, facts.model)
        fit = facts.fit_for(purpose)
        quality = facts.strict_pass_rate
        price_note = ("known prices" if facts.has_known_price()
                      else "price unknown (counts as expensive)")
        locality = "local" if "local" in set(facts.modalities or ()) else "cloud"
        options.append({
            "key": key,
            "label": "Option %d — %s model for %s" % (index + 1, locality, purpose),
            "description": ("fit %s for %s; measured quality %s; %s; "
                            "evidence %s"
                            % (_num(fit), purpose, _num(quality), price_note,
                               facts.fields_state)),
        })
    return options, keymap


def _num(value) -> str:
    return "%.2f" % value if value is not None else "unknown"


# --------------------------------------------------------------------------
# Strongest text/tools/coding suggestion (row 255)

def suggest_strongest(kb: KbReader, provider: str,
                      purpose: str = "coding") -> Optional[KbModelFacts]:
    """Strongest text/tools/coding model for a provider from the KB.

    Never image/audio/embedding models, never alphabetical: ties break by
    measured quality, then known prices, then KB order.
    """
    cands = [f for f in kb.models(provider)
             if purpose == "vision" or is_text_code_candidate(f)]
    if not cands:
        return None

    def rank(item):
        index, facts = item
        fit = facts.fit_for(purpose)
        quality = facts.strict_pass_rate
        return ((fit if fit is not None else -1.0) * -1.0,
                (quality if quality is not None else -1.0) * -1.0,
                0 if facts.has_known_price() else 1,
                index)

    ordered = sorted(enumerate(cands), key=rank)
    return ordered[0][1]


# --------------------------------------------------------------------------
# Strategy resolution

def _member_candidates(binding) -> List:
    from .types import CandidateModel
    members = binding.members if hasattr(binding, "members") else binding.get("members", ())
    out = []
    for m in members:
        if isinstance(m, Mapping):
            out.append(CandidateModel(
                provider=m["provider"], model=m["model"],
                provider_type=m.get("provider_type", "cloud")))
        else:
            out.append(CandidateModel(
                provider=m.provider, model=m.model,
                provider_type=getattr(m, "provider_type", "cloud")))
    return out


def _retag(outcome: RoutingOutcome, strategy: str, note: str) -> RoutingOutcome:
    decision = outcome.decision
    try:
        from dataclasses import replace as _replace
        decision = _replace(decision, strategy=strategy,
                            reason="%s; %s" % (note, decision.reason))
    except Exception:
        pass
    return RoutingOutcome(outcome.status, decision, outcome.assignments,
                          outcome.snapshot, outcome.trace)


def resolve_pool(binding, request: RoutingRequest,
                 deps: RoutingDeps, strategy=None) -> RoutingOutcome:
    """Route one role through its pool binding per the named strategy.

    strategy overrides the binding's stored value when given: the router
    passes the pick_pool_strategy facade result so every level select
    routes by the stored-binding read. None keeps the binding's own
    strategy. Either value migrates via T.migrate_pool_strategy; an
    unknown value blocks naming it.
    """
    if strategy is None:
        raw = (binding.strategy if hasattr(binding, "strategy")
               else binding.get("strategy"))
    else:
        raw = strategy
    strategy = T.migrate_pool_strategy(getattr(raw, "value", raw))
    members = _member_candidates(binding)
    base = request

    if strategy == "DIRECTOR_PER_TASK":
        provider = base.director_pick_provider
        model = base.director_pick_model
        if not provider or not model:
            return R.blocked_outcome(
                base, deps, (),
                "NO_ELIGIBLE_CANDIDATE: Director decides per task: no "
                "Director pick recorded for this task (pool holds %d "
                "models)" % len(members))
        match = [c for c in members if (c.provider, c.model) == (provider, model)]
        if not match:
            return R.blocked_outcome(
                base, deps, (),
                "NO_ELIGIBLE_CANDIDATE: Director pick %s/%s is not a pool "
                "member" % (provider, model))
        sub = _replace_request(base, candidates=tuple(match),
                               preferred_strategy="DIRECTOR_PER_TASK")
        return _retag(R._select_impl(sub, deps), "DIRECTOR_PER_TASK",
                      "pool strategy=Director decides per task")

    if strategy == "AUTO":
        sub = _replace_request(base, candidates=tuple(members),
                               preferred_strategy="AUTO")
        return _retag(R._select_impl(sub, deps), "AUTO", "pool strategy=Auto")

    if strategy == "FALLBACK_ORDER":
        sub = _replace_request(base, candidates=tuple(members),
                               ranking="listed",
                               preferred_strategy="FALLBACK_ORDER")
        return _retag(R._select_impl(sub, deps), "FALLBACK_ORDER",
                      "pool strategy=Fallback order")

    if strategy == "SPLIT_PARALLEL":
        locals_ = [c for c in members if c.provider_type == "local"]
        clouds = [c for c in members if c.provider_type != "local"]
        policy = base.routing_policy
        if locals_ and clouds and policy.split_allowed:
            sub = _replace_request(
                base, candidates=tuple(members), preferred_route="SPLIT",
                preferred_strategy="LOCAL_DRAFT_CLOUD_FINAL")
            return _retag(R._select_impl(sub, deps), "SPLIT_PARALLEL",
                          "pool strategy=Split/parallel")
        sub = _replace_request(base, candidates=tuple(members),
                               preferred_route="PARALLEL",
                               preferred_strategy="PARALLEL_COMPARE")
        return _retag(R._select_impl(sub, deps), "SPLIT_PARALLEL",
                      "pool strategy=Split/parallel")

    return R.blocked_outcome(base, deps, (),
                             "unknown pool strategy %r" % (strategy,))


def _replace_request(request: RoutingRequest, **changes) -> RoutingRequest:
    from dataclasses import replace as _replace
    return _replace(request, **changes)


def _safe_len(value):
    """len(value), or None when the value is not sized."""
    try:
        return len(value)
    except TypeError:
        return None


def _binding_key(binding):
    """(project_id, role) for a PoolBinding object or stored-binding dict."""
    if hasattr(binding, "project_id"):
        return (binding.project_id, binding.role)
    if isinstance(binding, Mapping):
        return (binding.get("project_id"), binding.get("role"))
    return (None, None)


def _binding_member_count(binding) -> int:
    members = (binding.members if hasattr(binding, "members")
               else binding.get("members", ()))
    return _safe_len(members) or 0


def _matching_binding(bindings, role: str, project_id: str):
    """The binding for (project_id, role): single binding used as-is, or
    the matching entry of a bindings list (None when no entry matches)."""
    if bindings is None:
        return None
    if isinstance(bindings, (list, tuple)):
        for candidate in bindings:
            if _binding_key(candidate) == (project_id, role):
                return candidate
        return None
    return bindings


# --------------------------------------------------------------------------
# Stored-strategy facade (frozen params, server-side resolution)

_bound_pool_store = None


def bind_pool_store(store):
    """Bind the server-side pool store for pick_pool_strategy.

    Returns the store unchanged. The facade falls back to the backend
    default context (bind_pools_ctx) when no store is bound here, and to
    AUTO when neither is available.
    """
    global _bound_pool_store
    _bound_pool_store = store
    return store


def unbind_pool_store():
    """Clear the bound pool store (tests/finally)."""
    global _bound_pool_store
    _bound_pool_store = None


def _lookup_stored_binding(role: str, project_id: str):
    """Stored binding for (project_id, role), or None when unresolvable."""
    store = _bound_pool_store
    if store is None:
        try:
            from agent_si.backend import pools_routes as _backend
            bound = getattr(_backend, "_DEFAULT_POOLS_CTX", None)
            if bound is None:
                return None
            if isinstance(bound, Mapping):
                store = bound.get("store")
            else:
                store = getattr(bound, "store", None)
        except Exception:
            return None
    if store is None:
        return None
    get_pool = getattr(store, "get_pool", None)
    if get_pool is None:
        return None
    try:
        return get_pool(project_id, role)
    except Exception:
        return None


def pick_pool_strategy(role: str, project_id: str) -> str:
    """Frozen facade: the plain-language pool strategy for a role.

    Frozen params only (no **ctx): the stored binding written by
    set_role_pool / PUT /api/v1/roles/pools is resolved through the
    module-level bound store (bind_pool_store) or, failing that, the
    backend default context (bind_pools_ctx), with AUTO when no stored
    binding resolves. A stored binding whose strategy is outside the
    frozen vocabulary falls back to the member-count default. Legacy persisted
    values migrate via T.migrate_pool_strategy; anything outside the
    frozen POOL_STRATEGIES falls back to AUTO. Picker options and
    telemetry carry strategy labels only, never raw pool ids.
    """
    if role not in T.ROLES:
        raise ValueError("invalid role: %r" % (role,))
    binding = _lookup_stored_binding(role, project_id)
    if binding is None:
        return "AUTO"
    if hasattr(binding, "strategy"):
        raw = binding.strategy
    elif isinstance(binding, Mapping):
        raw = binding.get("strategy")
    else:
        return "AUTO"
    strategy = T.migrate_pool_strategy(getattr(raw, "value", raw))
    if strategy in T.POOL_STRATEGIES:
        return strategy
    return default_strategy_for(_binding_member_count(binding))
