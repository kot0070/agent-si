"""FXDEVRUN roles: one adapter per role, every call on the ledger.

Pinned profiles resolve to the exact provider+model; AUTO roles pick
via routing_auto.pick_auto with the recorded why (task + price +
quality). A role with no provider ends the run with one terminal
event naming the role, never a silent substitute.
"""

from __future__ import annotations

from typing import Any


class RoleUnbound(RuntimeError):
    """One role names no provider; the run ends naming the role."""

    code: str = "DEVRUN_ROLE_UNBOUND"


class _BudgetOut(RuntimeError):
    """The run stops before the call: provider cap or hard limit."""

    code: str = "DEVRUN_BUDGET_STOP"


def _role_table(app: Any) -> Any:
    """The app's server-side role table, or None when absent."""
    try:
        ctx = getattr(getattr(app, "state", None), "k04_ctx", None)
        return getattr(ctx, "role_table", None)
    except Exception:
        return None


def _hierarchy_pinned(table: Any, project_id: str, role: str) -> tuple:
    """Pinned provider+model through the hierarchy seam (never copied)."""
    try:
        from agent_si.backend import hierarchy_routes as _routes
    except Exception:
        return (None, None)
    try:
        return _routes._pinned_identity(table, project_id, role)
    except Exception:
        return (None, None)


def _factory(app: Any) -> Any:
    """The adapter factory seam (tests inject per-role scripted fakes)."""
    try:
        return getattr(getattr(app, "state", None),
                       "devrun_adapter_factory", None)
    except Exception:
        return None


def _connected_providers(app: Any, factory: Any) -> list:
    """Connected provider ids: factory list, else evidenced facade ids."""
    if factory is not None:
        try:
            providers = factory.connected_providers()
            if providers:
                return [str(item) for item in providers]
        except Exception:
            pass
    try:
        ctx = getattr(getattr(app, "state", None), "k04_ctx", None)
        facade = getattr(ctx, "provider_facade", None)
        if facade is None:
            return []
        views = facade.list_providers(True)
        return [str(getattr(view, "provider_id", ""))
                for view in (views or ())
                if getattr(view, "evidenced", False)]
    except Exception:
        return []


def _bound_catalog() -> Any:
    """The real bound model catalog for AUTO picks."""
    from agent_si.model_kb import kb as _kb

    return _kb.bound_catalog()


def _pool_pick(
    app: Any, factory: Any, project_id: str, role: str
) -> tuple | None:
    """First enabled plus connected pool member, or None.

    Reads the stored binding through the existing pool store (the
    same read that migrates legacy strategies) and picks the first
    member that is enabled and connected; anything else leaves the
    run to end naming the role plus the pool.
    """
    try:
        ctx = getattr(getattr(app, "state", None), "k04_ctx", None)
        store = getattr(ctx, "store", None)
        if store is None:
            return None
        from agent_si.routing import pools as _pools

        binding = store.get_pool(project_id, role)
        if binding is None:
            return None
        view = _pools.binding_view(binding)
        members = list((view or {}).get("members", ()) or ())
    except Exception:
        return None
    try:
        connected = set(_connected_providers(app, factory))
    except Exception:
        connected = set()
    for member in members:
        try:
            if isinstance(member, dict):
                provider = str(member.get("provider") or "")
                model = str(member.get("model") or "")
                enabled = member.get("enabled", True)
            else:
                provider = str(getattr(member, "provider", "") or "")
                model = str(getattr(member, "model", "") or "")
                enabled = getattr(member, "enabled", True)
        except Exception:
            continue
        if not provider or not model:
            continue
        if enabled is False:
            continue
        if provider in connected:
            return (provider, model)
    return None


def _auto_pick(
    app: Any, factory: Any, role: str
) -> dict[str, Any]:
    """One AUTO resolution; RoleUnbound names the role on no candidate."""
    connected = _connected_providers(app, factory)
    try:
        from agent_si.backend import routing_auto as _auto

        pick = _auto.pick_auto(_bound_catalog(), connected, "coding")
    except Exception as exc:
        raise RoleUnbound(
            "role %r has no provider: AUTO pick failed: %s"
            % (role, exc)) from None
    return {
        "role": role, "mode": "AUTO",
        "provider": str(pick["manager"]),
        "model": str(pick["model"]),
        "why": dict(pick.get("why", {})),
    }


def resolve_role(
    app: Any, project_id: str, role: str
) -> dict[str, Any]:
    """Resolve one role to provider+model+why; raise RoleUnbound.

    A missing profile resolves the same as AUTO. Only a table
    failure or an AUTO pick with no candidate ends the run naming
    the role, as does a stored pool with no usable profile (which
    names the role plus the pool). PINNED is unchanged.
    """
    table = _role_table(app)
    factory = _factory(app)
    if table is None:
        raise RoleUnbound(
            "role %r has no provider: no role table" % (role,))
    try:
        profile = table.get_profile(project_id, role)
    except Exception as exc:
        raise RoleUnbound(
            "role %r has no provider: role table failed: %s"
            % (role, exc)) from None
    if profile is not None:
        mode = str(getattr(profile, "mode", "") or "")
        if mode == "PINNED":
            provider, model = _hierarchy_pinned(table, project_id, role)
            if provider and model:
                return {
                    "role": role, "mode": "PINNED",
                    "provider": str(provider), "model": str(model),
                    "why": {"mode": "PINNED",
                            "provider": str(provider),
                            "model": str(model)},
                }
            raise RoleUnbound(
                "role %r has no provider: PINNED names no model"
                % (role,))
        if mode == "pool":
            picked = _pool_pick(app, factory, project_id, role)
            if picked is None:
                raise RoleUnbound(
                    "role %r has no provider: pool has no usable profile"
                    % (role,))
            return {
                "role": role, "mode": "pool",
                "provider": str(picked[0]), "model": str(picked[1]),
                "why": {"mode": "pool",
                        "provider": str(picked[0]),
                        "model": str(picked[1])},
            }
        if mode != "AUTO":
            raise RoleUnbound(
                "role %r has no provider: unknown mode %r"
                % (role, mode))
    return _auto_pick(app, factory, role)


def build_adapter(app: Any, resolution: dict[str, Any]) -> Any:
    """One fresh adapter instance for one role call.

    The factory seam builds per-role instances (tests); otherwise a
    real leg is built for the resolved pair the way the chat bind
    does (never a mock outside the factory seam).
    """
    factory = _factory(app)
    if factory is not None:
        return factory(role=resolution["role"],
                       provider=resolution["provider"],
                       model=resolution["model"])
    provider = str(resolution["provider"])
    model = str(resolution["model"])
    try:
        ctx = getattr(getattr(app, "state", None), "k04_ctx", None)
        facade = getattr(ctx, "provider_facade", None)
        views = facade.list_providers(True) if facade is not None else []
    except Exception:
        views = []
    chosen = None
    for view in views or ():
        if str(getattr(view, "provider_id", "")) == provider:
            chosen = view
            break
    if chosen is None:
        raise RoleUnbound(
            "role %r has no provider: %r is not connected"
            % (resolution["role"], provider))
    try:
        secret_ref = getattr(chosen, "secret_ref", None)
        secret_mapping: dict[str, Any] = {}
        if secret_ref is not None:
            describe = getattr(secret_ref, "describe", None)
            described = None
            if callable(describe):
                try:
                    described = describe()
                except Exception:
                    described = None
            elif isinstance(secret_ref, dict):
                described = secret_ref
            if isinstance(described, dict):
                secret_mapping = {
                    key: value for key, value in described.items()
                    if key != "value"}
        base_url = getattr(chosen, "base_url", "") or ""
        instance_id = getattr(chosen, "instance_id", "") or "default"
        from agent_si.backend import chat_stream as _chat
        from agent_si.providers.adapters.legs import build_leg

        transport = _chat._gateway_transport(
            base_url, getattr(ctx, "credential_store", None),
            secret_mapping)
        return build_leg(provider, model, secret_mapping,
                         transport=transport,
                         instance_id=instance_id,
                         base_url=base_url or None)
    except RoleUnbound:
        raise
    except Exception as exc:
        raise RoleUnbound(
            "role %r has no provider: cannot build %r/%r: %s"
            % (resolution["role"], provider, model, exc)) from None


def _over_cap(
    app: Any, project_id: str, provider: str, model: str, usage: Any
) -> bool:
    """True when the just-charged call spent past the hard limit.

    Known price only: without a KB price nothing is invented and the
    run is never stopped for money. Compares the call's own cost
    against remaining (hard - spent - reserved).
    """
    try:
        from agent_si.runtime import manager as _manager
    except Exception:
        return False
    try:
        inp_price, out_price = _manager._kb_price_for_manager(
            provider, model)
    except Exception:
        return False
    if inp_price is None and out_price is None:
        return False
    try:
        tokens = dict(usage) if isinstance(usage, dict) else {}
    except Exception:
        return False

    def _num(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        return None

    inp = _num(tokens.get("input_tokens"))
    if inp is None:
        inp = _num(tokens.get("prompt_tokens"))
    outp = _num(tokens.get("output_tokens"))
    if outp is None:
        outp = _num(tokens.get("completion_tokens"))
    if inp is None and outp is None:
        return False
    try:
        from decimal import Decimal as _Dec
        cost = ((_Dec(str(inp_price or "0")) * _Dec(int(inp or 0))
                + _Dec(str(out_price or "0")) * _Dec(int(outp or 0)))
                / _Dec(1_000_000))
    except Exception:
        return False
    try:
        ctx = getattr(getattr(app, "state", None), "k04_ctx", None)
        gate = getattr(ctx, "budget_state", None)
        if gate is None:
            return False
        state = gate.get_state(str(project_id))
        remaining = (_Dec(str(state.hard_limit))
                     - _Dec(str(state.spent or "0"))
                     - _Dec(str(state.reserved or "0")))
    except Exception:
        return False
    return cost > remaining


def _cap_block(app: Any, project_id: str, provider: str) -> str | None:
    """Stop text when the provider cap or hard limit is reached.

    Reads the budget gate spending for the project: a set provider
    cap with spent at or above it (0.00 included) or project spent
    at or above the hard limit blocks the call before it runs. Any
    missing gate, project or figure leaves the call to run.
    """
    try:
        from decimal import Decimal as _Dec

        ctx = getattr(getattr(app, "state", None), "k04_ctx", None)
        gate = getattr(ctx, "budget_state", None)
        if gate is None:
            return None
        rows = gate.provider_spending(str(project_id))
    except Exception:
        return None
    try:
        from decimal import Decimal as _Dec

        row = (rows or {}).get(str(provider)) or {}
        cap = row.get("cap")
        spent = str(row.get("spent", "0") or "0")
        if cap is not None and _Dec(spent) >= _Dec(str(cap)):
            return ("budget stop: provider %s spent %s reached cap %s"
                    % (provider, spent, cap))
        try:
            state = gate.get_state(str(project_id))
        except Exception:
            return None
        if _Dec(str(state.spent or "0")) >= _Dec(str(state.hard_limit)):
            return ("budget stop: provider %s spent %s reached cap %s"
                    % (provider, spent, state.hard_limit))
    except Exception:
        return None
    return None


def _record_usage(app: Any, record: Any, project_id: str, run_id: str,
                  provider: str, model: str, usage: Any) -> None:
    """One telemetry row per call; never raises into the run."""
    try:
        from agent_si.telemetry import run_store as _store

        task_id = ""
        try:
            if isinstance(record, dict):
                task_id = str(record.get("task") or "")
            else:
                task_id = str(getattr(record, "task", "") or "")
        except Exception:
            task_id = ""
        _store.record_provider_usage(
            project_id=str(project_id), task_id=task_id,
            run_id=str(run_id), provider=str(provider),
            model=str(model), usage=usage)
    except Exception:
        pass


def invoke(
    app: Any,
    adapter: Any,
    resolution: dict[str, Any],
    messages: list,
    *,
    record: Any,
    project_id: str,
    run_id: str,
    part: Any = None,
    attempt: int = 0,
) -> Any:
    """One model call: charge with a per-call id, ledger, budget-cap stop.

    The charge id is the run id plus "-c" plus the ledger sequence
    number, so every call settles its own reservation; repeating the
    same call id is refused by the gate like any duplicate. The plain
    manager path is unchanged. Returns (response, over_cap): over_cap
    is True only when the call's own cost exceeds the remaining budget.
    A reached provider cap or hard limit raises _BudgetOut before call.
    """
    provider = str(resolution["provider"])
    model = str(resolution["model"])
    blocked = _cap_block(app, project_id, provider)
    if blocked is not None:
        raise _BudgetOut(blocked)
    response = adapter.invoke(messages)
    usage = getattr(response, "usage", {}) or {}
    cost: Any = None
    try:
        from agent_si.runtime import manager as _manager
        try:
            seq = len(record.get("ledger", []) or []) if isinstance(
                record, dict) else 0
        except Exception:
            seq = 0
        call_id = "%s-c%d" % (run_id, int(seq) + 1)
        cost = _manager._charge_budget_gate(
            str(project_id), provider, model, usage, str(call_id))
    except Exception:
        cost = None
    try:
        from agent_si.runtime.devrun import records as _records
        _records.ledger_add(
            record, role=resolution["role"],
            provider=provider, model=model,
            part=part, attempt=attempt, usage=usage, cost=cost)
    except Exception:
        pass
    _record_usage(app, record, project_id, run_id,
                  provider, model, usage)
    over = _over_cap(app, project_id, provider, model, usage)
    return response, over


def new_identity(prefix: str) -> str:
    """One fresh run-scoped identity ref (producer or auditor)."""
    import uuid as _uuid

    return "%s-%s" % (prefix, _uuid.uuid4().hex)
