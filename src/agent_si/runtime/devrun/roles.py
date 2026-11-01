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


def resolve_role(
    app: Any, project_id: str, role: str
) -> dict[str, Any]:
    """Resolve one role to provider+model+why; raise RoleUnbound.

    A missing profile, a non-PINNED/non-AUTO mode, or an AUTO pick
    with no candidate all end the run naming the role.
    """
    table = _role_table(app)
    factory = _factory(app)
    if table is not None:
        try:
            profile = table.get_profile(project_id, role)
        except Exception:
            profile = None
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
            elif mode == "AUTO":
                connected = _connected_providers(app, factory)
                try:
                    from agent_si.backend import routing_auto as _auto
                    pick = _auto.pick_auto(
                        _bound_catalog(), connected, "coding")
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
    raise RoleUnbound(
        "role %r has no provider: no usable profile" % (role,))


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
    """One model call: charge, ledger, budget-cap stop signal.

    Returns (response, over_cap): over_cap is True only when the
    call's own cost exceeds the remaining budget.
    """
    response = adapter.invoke(messages)
    usage = getattr(response, "usage", {}) or {}
    cost: Any = None
    try:
        from agent_si.runtime import manager as _manager
        cost = _manager._charge_budget_gate(
            str(project_id), str(resolution["provider"]),
            str(resolution["model"]), usage, str(run_id))
    except Exception:
        cost = None
    try:
        from agent_si.runtime.devrun import records as _records
        _records.ledger_add(
            record, role=resolution["role"],
            provider=str(resolution["provider"]),
            model=str(resolution["model"]),
            part=part, attempt=attempt, usage=usage, cost=cost)
    except Exception:
        pass
    over = _over_cap(
        app, project_id, str(resolution["provider"]),
        str(resolution["model"]), usage)
    return response, over


def new_identity(prefix: str) -> str:
    """One fresh run-scoped identity ref (producer or auditor)."""
    import uuid as _uuid

    return "%s-%s" % (prefix, _uuid.uuid4().hex)
