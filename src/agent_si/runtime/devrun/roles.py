"""FXDEVRUN roles: one adapter per role, every call on the ledger.

Pinned profiles resolve to the exact provider+model; AUTO roles pick
via routing_auto.pick_auto with the recorded why (task + price +
quality). A role with no provider ends the run with one terminal
event naming the role, never a silent substitute.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Any


class RoleUnbound(RuntimeError):
    """One role names no provider; the run ends naming the role."""

    code: str = "DEVRUN_ROLE_UNBOUND"


class _BudgetOut(RuntimeError):
    """The run stops before the call: provider cap or hard limit."""

    code: str = "DEVRUN_BUDGET_STOP"


class ModelTimeout(RuntimeError):
    """A model call exceeded its bounded timeout; the attempt continues."""

    code: str = "DEVRUN_MODEL_TIMEOUT"


class ModelStopped(RuntimeError):
    """A model call was stopped while waiting; the run unwinds."""

    code: str = "DEVRUN_MODEL_STOPPED"


class ProviderUnreachable(RuntimeError):
    """A provider call failed by connection/5xx after bounded retries.

    The engine converts this to a paused run (never a silent provider
    switch): the outage was already signalled once for the run.
    """

    code: str = "DEVRUN_PROVIDER_UNREACHABLE"


#: Bounded provider attempts before the outage signal: the first
#: try plus one retry (a dead connection fails fast, and tests stay
#: fast). Retries reuse invoke_timed, so its waiting line still fires
#: on a slow second try.
_OUTAGE_ATTEMPTS = 2


def _is_outage_error(exc: BaseException) -> bool:
    """True for connection/5xx failures (never timeouts or stops)."""
    if isinstance(exc, (ModelStopped, ModelTimeout)):
        return False
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    try:
        text = str(exc or "").lower()
    except Exception:
        return False
    if not text:
        return False
    markers = (
        "connection refused", "connection reset", "connection aborted",
        "connection error", "failed to connect", "could not connect",
        "unreachable", "network is unreachable", "broken pipe",
        "bad gateway", "service unavailable", "gateway timeout",
        "internal server error", " 500", " 502", " 503", " 504",
        "(500)", "(502)", "(503)", "(504)", " 5xx", "status 500",
        "status 502", "status 503", "status 504",
    )
    return any(marker in text for marker in markers)


#: Default per-call model timeout in seconds (bounded by the max).
_CALL_TIMEOUT_S = 300.0

#: Upper bound for any per-call model timeout in seconds.
_CALL_TIMEOUT_MAX = 900.0

#: Quiet waiting notice: first after this many seconds, then every this
#: many seconds while one call is still running.
_WAIT_FIRST_S = 20.0
_WAIT_EVERY_S = 30.0


def _clamp_timeout(value: Any) -> float:
    """Bound one per-call timeout to [1, _CALL_TIMEOUT_MAX] seconds."""
    if value is None:
        return float(_CALL_TIMEOUT_S)
    try:
        clamped = float(value)
    except (TypeError, ValueError):
        return float(_CALL_TIMEOUT_S)
    return min(max(clamped, 1.0), float(_CALL_TIMEOUT_MAX))


def _clean_outage_text(exc: BaseException) -> str:
    """User-safe outage detail: no class names, no "internal" word.

    Strips a leading ``XxxError:`` class prefix and neutralises the
    "internal server error" phrase; the full class-qualified error goes
    to the log in _signal_outage_once, never to the user line.
    """
    try:
        text = str(exc or "").strip()
    except Exception:
        text = ""
    if not text:
        return "no response"
    text = re.sub(r"^[A-Za-z_][\w.]*Error\s*:\s*", "", text).strip()
    text = re.sub(r"(?i)\binternal server error\b", "server error", text)
    return text or "no response"


def _signal_outage_once(app: Any, record: Any, project_id: str,
                         provider: str, exc: BaseException) -> None:
    """Signal one provider outage for the run (first failure only).

    Uses the watcher's stop-and-report signal (real stop-all lane plus
    one OUTAGE_SIGNAL row); its own dedupe replays repeats. A flag on
    the run record keeps it to once per run. Never raises.
    """
    try:
        if isinstance(record, dict) and record.get("outage_signalled"):
            return
    except Exception:
        return
    try:
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "provider outage signalled: project=%s provider=%s error=%s: %s",
            project_id, provider, type(exc).__name__, exc)
    except Exception:
        pass
    try:
        from agent_si.watcher import outage as _outage

        _outage.signal_outage(
            str(project_id), str(provider),
            "provider %s unreachable: %s" % (provider, exc))
    except Exception:
        pass
    try:
        if isinstance(record, dict):
            record["outage_signalled"] = str(provider)
    except Exception:
        pass


def waiting_line(role: str, elapsed_s: float) -> str:
    """One quiet chat status line for a still-running model call."""
    return "Waiting for the model: %s, %d s" % (
        str(role), int(max(0, elapsed_s)))


def invoke_timed(adapter: Any, messages: list, *,
                 timeout_s: Any = None,
                 first_notice_s: Any = None,
                 notice_every_s: Any = None,
                 tick_s: float = 0.2,
                 stop_seen: Any = None,
                 on_waiting: Any = None) -> Any:
    """Run one adapter.invoke off the stream thread with a bounded wait.

    The call runs in a daemon thread; this thread waits in slices so a
    stop is honoured at once (never the full timeout) and a quiet
    waiting notice fires after first_notice_s seconds and then every
    notice_every_s seconds. A stop raises ModelStopped; an expired
    bound raises ModelTimeout; an adapter failure re-raises unchanged.
    """
    limit = _clamp_timeout(timeout_s)
    try:
        first = float(first_notice_s
                      if first_notice_s is not None else _WAIT_FIRST_S)
    except (TypeError, ValueError):
        first = float(_WAIT_FIRST_S)
    try:
        every = float(notice_every_s
                      if notice_every_s is not None else _WAIT_EVERY_S)
    except (TypeError, ValueError):
        every = float(_WAIT_EVERY_S)
    try:
        tick = max(0.05, float(tick_s))
    except (TypeError, ValueError):
        tick = 0.2
    box: dict[str, Any] = {}

    def _target() -> None:
        try:
            box["response"] = adapter.invoke(messages)
        except BaseException as exc:  # noqa: BLE001 -- re-raised below
            box["error"] = exc

    worker = threading.Thread(target=_target, daemon=True,
                              name="devrun-model-call")
    worker.start()
    start = time.monotonic()
    noticed = False
    last_notice = 0.0
    while True:
        worker.join(timeout=tick)
        if not worker.is_alive():
            break
        if stop_seen is not None:
            try:
                stopped = bool(stop_seen())
            except Exception:
                stopped = False
            if stopped:
                raise ModelStopped("model call stopped")
        elapsed = time.monotonic() - start
        if elapsed >= limit:
            raise ModelTimeout(
                "model call timed out after %d s" % (int(limit),))
        if on_waiting is not None and elapsed >= first and (
                not noticed or elapsed - last_notice >= every):
            noticed = True
            last_notice = elapsed
            try:
                on_waiting(elapsed)
            except Exception:
                pass
    if "error" in box:
        raise box["error"]
    return box.get("response")


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


def _facade_first_model(app: Any, provider: str) -> str | None:
    """First model id the facade holds for one provider, or None.

    Reads the provider facade's own connect-time model rows verbatim
    (provider prefix stripped the way the chat bind does); never
    invented, never a KB read. A connected provider's models are
    enabled by connection, so the first stored row is the fallback.
    """
    try:
        ctx = getattr(getattr(app, "state", None), "k04_ctx", None)
        facade = getattr(ctx, "provider_facade", None)
        if facade is None:
            return None
        providers = getattr(facade, "_providers", None)
        if not isinstance(providers, dict):
            return None
        record = providers.get(provider)
        if not isinstance(record, dict):
            return None
        models_map = record.get("models", {})
        if not isinstance(models_map, dict):
            return None
        for value in models_map.values():
            text = str(value or "")
            if not text:
                continue
            if "/" in text:
                head, _, tail = text.partition("/")
                if head == provider and tail:
                    text = tail
            if text:
                return text
    except Exception:
        return None
    return None


def _auto_pick(
    app: Any, factory: Any, role: str
) -> dict[str, Any]:
    """One AUTO resolution; RoleUnbound names the role on no candidate.

    A pick blocked only because no connected provider holds a KB row
    falls back to that provider's first enabled facade model (honest
    why, UNKNOWN price until the user runs Update); any other block
    stays a run-failed line naming the role.
    """
    connected = _connected_providers(app, factory)
    try:
        from agent_si.backend import routing_auto as _auto

        pick = _auto.pick_auto(_bound_catalog(), connected, "coding")
    except Exception as exc:
        try:
            from agent_si.backend import routing_auto as _blocked

            no_kb_row = (isinstance(exc, _blocked.AutoBlocked)
                         and "connected providers hold no KB rows"
                         in str(exc))
        except Exception:
            no_kb_row = False
        if no_kb_row:
            for provider in connected or []:
                model = _facade_first_model(app, provider)
                if model:
                    return {
                        "role": role, "mode": "AUTO",
                        "provider": str(provider),
                        "model": str(model),
                        "why": {
                            "connected": list(connected or []),
                            "task_type": "coding",
                            "reason": "no KB row: first enabled model "
                                      "of the connected provider"},
                    }
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
                  provider: str, model: str, usage: Any,
                  role: Any = None, cost: Any = None) -> None:
    """One telemetry row per call (with role), plus metered-call log; never raises."""
    try:
        task_id = ""
        try:
            if isinstance(record, dict):
                task_id = str(record.get("task") or "")
            else:
                task_id = str(getattr(record, "task", "") or "")
        except Exception:
            task_id = ""
        try:
            from agent_si.telemetry import run_store as _store

            _store.record_provider_usage(
                project_id=str(project_id), task_id=task_id,
                run_id=str(run_id), provider=str(provider),
                model=str(model), usage=usage,
                role=str(role) if isinstance(role, str) and role else None)
        except Exception:
            pass
        try:
            _METERED_CALLS.append({
                "project_id": str(project_id), "task_id": task_id,
                "run_id": str(run_id), "role": str(role or "devrun"),
                "provider": str(provider), "model": str(model),
                "cost": cost,
            })
        except Exception:
            pass
    except Exception:
        pass


#: Every metered model call this process settled (role confirmation
#: surface for the chat and AI-test entries, which carry no devrun
#: ledger row). Appended only; never raises; probe isolation reads a
#: snapshot via metered_calls.
_METERED_CALLS: list = []


def metered_calls() -> tuple:
    """Snapshot of every metered call settled so far (oldest first)."""
    return tuple(_METERED_CALLS)


def admit_role_call(gate: Any, *, project_id: str, task_id: str,
                    run_id: str, role: str, provider_id: str) -> None:
    """Admit one named-role model call before it runs (HE19-1 shared).

    The same admission every metered entry shares: a zero-amount
    reserve under ``admit-<run>-<role>`` that raises the gate's own
    BudgetBlockedError when the provider cap or hard limit is already
    reached, so the provider is never invoked past a hard cap. A
    missing gate allows the call (the post-call charge still reports
    UNAVAILABLE); any other gate failure also allows it.
    """
    from agent_si.runtime import manager as _manager

    _manager.admit_budget_call(
        gate, str(project_id), str(provider_id), str(task_id),
        str(run_id), "admit-%s-%s" % (str(run_id), str(role)))


def settle_role_call(*, project_id: str, task_id: str, run_id: str,
                     role: str, provider_id: str, model: str,
                     usage: Any) -> Any:
    """Telemetry plus charge for one named-role model call (HE19-1 shared).

    Records the provider usage row, settles the spend through the
    budget gate, and logs the call (with its role) on metered_calls.
    Never raises; returns the charged cost (None when unknown).
    """
    provider = str(provider_id)
    name = str(model)
    try:
        from agent_si.telemetry import run_store as _store

        _store.record_provider_usage(
            project_id=str(project_id), task_id=str(task_id),
            run_id=str(run_id), provider=provider,
            model=name, usage=usage)
    except Exception:
        pass
    cost: Any = None
    try:
        from agent_si.runtime import manager as _manager

        cost = _manager._charge_budget_gate(
            str(project_id), provider, name, usage, str(run_id))
    except Exception:
        cost = None
    try:
        _METERED_CALLS.append({
            "project_id": str(project_id), "task_id": str(task_id),
            "run_id": str(run_id), "role": str(role),
            "provider": provider, "model": name, "cost": cost,
        })
    except Exception:
        pass
    return cost


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
    lock: Any = None,
    timeout_s: Any = None,
    first_notice_s: Any = None,
    notice_every_s: Any = None,
    tick_s: float = 0.2,
    stop_seen: Any = None,
    on_waiting: Any = None,
) -> Any:
    """One model call: charge with a per-call id, ledger, budget-cap stop.

    The charge id is the run id plus "-c" plus the ledger sequence
    number, so every call settles its own reservation; repeating the
    same call id is refused by the gate like any duplicate (int B4,
    per-call billing). The plain manager path is unchanged. Returns
    (response, over_cap): over_cap is True only when the call's own
    cost exceeds the remaining budget. A reached provider cap or hard
    limit raises _BudgetOut before call. The model call always runs
    outside any lock; the whole post-call block (charge, ledger,
    telemetry, over-cap) runs as one unit under the given lock, so
    two parts never interleave a charge (A1). The call itself runs
    off the stream thread with a bounded timeout (default 300 s): a
    stop raises ModelStopped at once, an expired bound raises
    ModelTimeout and the attempt continues. Callers that need the
    row they wrote (never the ledger tail) use invoke_owned.
    """
    response, over, _row = invoke_owned(
        app, adapter, resolution, messages, record=record,
        project_id=project_id, run_id=run_id, part=part,
        attempt=attempt, lock=lock, timeout_s=timeout_s,
        first_notice_s=first_notice_s, notice_every_s=notice_every_s,
        tick_s=tick_s, stop_seen=stop_seen, on_waiting=on_waiting)
    return response, over


def invoke_owned(
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
    lock: Any = None,
    timeout_s: Any = None,
    first_notice_s: Any = None,
    notice_every_s: Any = None,
    tick_s: float = 0.2,
    stop_seen: Any = None,
    on_waiting: Any = None,
) -> Any:
    """Same as invoke, plus the ledger row this call wrote.

    Returns (response, over_cap, ledger_row) for the A2 own-row rule.
    The charge id is the run id plus "-c" plus the ledger sequence
    number, so every call settles its own reservation; repeating the
    same call id is refused by the gate like any duplicate. The plain
    manager path is unchanged. Returns (response, over_cap,
    ledger_row): over_cap is True only when the call's own cost
    exceeds the remaining budget. A reached provider cap or hard
    limit raises _BudgetOut before call. The call itself runs off the
    stream thread with a bounded timeout (default 300 s): a stop
    raises ModelStopped at once, an expired bound raises ModelTimeout
    and the attempt continues.
    """
    provider = str(resolution["provider"])
    model = str(resolution["model"])
    blocked = _cap_block(app, project_id, provider)
    if blocked is not None:
        raise _BudgetOut(blocked)
    try:
        from agent_si.budget.gate import BudgetBlockedError as _AdmitBlocked

        ctx = getattr(getattr(app, "state", None), "k04_ctx", None)
        try:
            task_name = str(record.get("task") if isinstance(
                record, dict) else "")
        except Exception:
            task_name = ""
        admit_role_call(
            getattr(ctx, "budget_state", None), project_id=str(project_id),
            task_id=task_name, run_id=str(run_id),
            role=str(resolution.get("role", "devrun")), provider_id=provider)
    except _BudgetOut:
        raise
    except _AdmitBlocked as _admit_exc:
        raise _BudgetOut(str(_admit_exc)) from None
    except Exception:
        pass
    _missing: Any = object()
    response: Any = _missing
    failures: list[BaseException] = []
    for _try in range(max(1, int(_OUTAGE_ATTEMPTS))):
        try:
            response = invoke_timed(
                adapter, messages, timeout_s=timeout_s,
                first_notice_s=first_notice_s,
                notice_every_s=notice_every_s,
                tick_s=tick_s, stop_seen=stop_seen,
                on_waiting=on_waiting)
            break
        except (ModelStopped, ModelTimeout):
            raise
        except Exception as exc:
            if not _is_outage_error(exc):
                raise
            failures.append(exc)
    if response is _missing:
        last = failures[-1] if failures else RuntimeError("no response")
        _signal_outage_once(app, record, project_id, provider, last)
        raise ProviderUnreachable(
            "provider %s unreachable after %d tries: %s"
            % (provider, _OUTAGE_ATTEMPTS, _clean_outage_text(last)))
    usage = getattr(response, "usage", {}) or {}

    # FXPARALLEL BEGIN charge-lock: post-call block as one unit.
    def _charge_locked() -> Any:
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
        row: Any = {}
        try:
            from agent_si.runtime.devrun import records as _records
            row = _records.ledger_add(
                record, role=resolution["role"],
                provider=provider, model=model,
                part=part, attempt=attempt, usage=usage, cost=cost)
        except Exception:
            pass
        _record_usage(app, record, project_id, run_id,
                      provider, model, usage,
                      role=resolution.get("role")
                      if isinstance(resolution, dict) else None,
                      cost=cost)
        over = _over_cap(app, project_id, provider, model, usage)
        return row, over

    if lock is not None:
        with lock:
            row, over = _charge_locked()
    else:
        row, over = _charge_locked()
    # FXPARALLEL END charge-lock.
    return response, over, row


def new_identity(prefix: str) -> str:
    """One fresh run-scoped identity ref (producer or auditor)."""
    import uuid as _uuid

    return "%s-%s" % (prefix, _uuid.uuid4().hex)
