"""Provider leg registry over the generic adapter (K04NEXT3 C2).

Adapters-side seam for M-P1-23 (generic adapters; one provider-specific
leg per provider: compat flag, chat path, route params, endpoint hint)
and R-369 (legs_for_provider returns the whole single-provider set).

The registry holds data only and is filled by explicit register_leg
calls, so no vendor id is built in anywhere (R-356). build_leg resolves
the provider's leg and constructs the matching adapter from base.py;
every id passes through verbatim and unknown ids raise.
"""
from __future__ import annotations

from agent_si.adapters import base as _base

_LEGS = {}


def clear_legs():
    """Empty the leg registry (test and reconfiguration path)."""
    _LEGS.clear()
    return []


def register_leg(provider_id, *, openai_compat, chat_path="/chat/completions",
                 route_params=None, endpoint_hint=""):
    """Add one provider-specific leg; explicit data, never a default."""
    if not (isinstance(provider_id, str) and provider_id.strip()):
        raise _base.AdapterSetupError(
            "register_leg needs an explicit provider_id",
            _base.SELECTION_REQUIRED)
    if provider_id in _LEGS:
        raise _base.AdapterSetupError(
            "leg for %r is already registered" % (provider_id,),
            "ADAPTER_LEG_CONFLICT")
    descriptor = {"provider_id": provider_id,
                  "openai_compat": bool(openai_compat),
                  "chat_path": chat_path,
                  "route_params": dict(route_params or {}),
                  "endpoint_hint": endpoint_hint}
    _LEGS[provider_id] = descriptor
    return dict(descriptor, route_params=dict(descriptor["route_params"]))


def catalog_legs():
    """One descriptor per registered leg, in registration order."""
    return [dict(descriptor,
                 route_params=dict(descriptor["route_params"]))
            for descriptor in _LEGS.values()]


def legs_for_provider(provider_id):
    """The leg set for one provider (single-provider mode reads this)."""
    try:
        descriptor = _LEGS[provider_id]
    except KeyError:
        raise _base.AdapterSetupError(
            "unknown provider_id %r; expected one of: %s"
            % (provider_id, ", ".join(sorted(_LEGS))),
            "ADAPTER_UNKNOWN_PROVIDER")
    return [dict(descriptor,
                 route_params=dict(descriptor["route_params"]))]


def build_leg(provider_id, model, secret_ref, transport=None, *,
              instance_id="default", base_url=None, backend_call=None,
              route_params=None):
    """Build the provider leg's adapter; ids pass through verbatim.

    provider_id and model are required positionals with no defaults
    (R-356). OpenAI-compatible legs build GenericAdapter over the
    injected transport; the remaining legs build FunctionBackedAdapter
    over the injected backend_call. Unknown ids raise instead of
    falling back to anything.
    """
    _base.require_explicit_selection(provider_id, model)
    try:
        leg = _LEGS[provider_id]
    except KeyError:
        raise _base.AdapterSetupError(
            "unknown provider_id %r; expected one of: %s"
            % (provider_id, ", ".join(sorted(_LEGS))),
            "ADAPTER_UNKNOWN_PROVIDER")
    params = dict(leg["route_params"]) if route_params is None \
        else dict(route_params)
    if leg["openai_compat"]:
        if not callable(transport):
            raise _base.AdapterSetupError(
                "leg %r needs a callable transport" % (provider_id,),
                _base.TRANSPORT_REQUIRED)
        return _base.GenericAdapter(
            provider_id, model, secret_ref, transport,
            instance_id=instance_id, chat_path=leg["chat_path"],
            base_url=base_url if base_url is not None
            else leg["endpoint_hint"],
            route_params=params)
    if not callable(backend_call):
        raise _base.AdapterSetupError(
            "leg %r needs a callable backend_call" % (provider_id,),
            _base.BACKEND_CALL_REQUIRED)
    return _base.FunctionBackedAdapter(
        provider_id, model, secret_ref, backend_call,
        instance_id=instance_id, route_params=params)


def describe_leg(adapter):
    """Transport descriptor data for a built leg adapter."""
    return adapter.transport_descriptor()
