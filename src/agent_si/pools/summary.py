# K04 pools-side seam helpers (plain-language pool surface).
"""Plain-language pool summaries over stored bindings.

Standard library only. No machine paths, no secrets, no vendor or model
defaults. Legacy persisted strategies migrate through the frozen
vocabulary; unknown values surface as readable words, never raw codes.
"""

from __future__ import annotations

from collections.abc import Mapping

from agent_si.routing import types as T


def strategy_label(strategy) -> str:
    """Plain-language label for one pool strategy value.

    Frozen strategies map through STRATEGY_LABELS; legacy persisted
    values migrate first; anything else renders as readable words so
    the picker never shows a raw code.
    """
    raw = getattr(strategy, "value", strategy)
    canonical = T.migrate_pool_strategy(raw)
    label = T.STRATEGY_LABELS.get(canonical)
    if label is not None:
        return label
    text = "" if canonical is None else str(canonical)
    return text.replace("_", " ").strip().title() if text else ""


def _member_use_modes(members) -> list:
    """Sorted unique use modes across binding members."""
    modes = set()
    for member in members:
        if isinstance(member, Mapping):
            modes.add(member.get("use_mode") or "primary")
        else:
            modes.add(getattr(member, "use_mode", None) or "primary")
    return sorted(modes)


def _member_providers(members) -> list:
    """Sorted unique provider ids across binding members."""
    providers = set()
    for member in members:
        if isinstance(member, Mapping):
            provider = member.get("provider")
        else:
            provider = getattr(member, "provider", None)
        if provider:
            providers.add(provider)
    return sorted(providers)


def binding_summary(binding) -> dict | None:
    """Plain-language summary of one pool binding (object or stored dict).

    Returns None for a missing binding (a PINNED role holds no pool
    binding); otherwise the role, project, frozen strategy, its label,
    member count, sorted use modes, sorted providers, and a one-line
    sentence the picker surface can quote verbatim.
    """
    if binding is None:
        return None
    if isinstance(binding, Mapping):
        role = binding.get("role")
        project_id = binding.get("project_id")
        strategy = T.migrate_pool_strategy(binding.get("strategy"))
        members = binding.get("members", ()) or ()
    else:
        role = binding.role
        project_id = binding.project_id
        strategy = T.migrate_pool_strategy(binding.strategy)
        members = binding.members or ()
    members = list(members)
    label = strategy_label(strategy)
    use_modes = _member_use_modes(members)
    providers = _member_providers(members)
    count = len(members)
    plural = "" if count == 1 else "s"
    modes = ", ".join(use_modes) if use_modes else "no members"
    sentence = (f"{role} pool holds {count} model{plural} "
                  f"({modes}) under {label or strategy}")
    return {
        "role": role,
        "project_id": project_id,
        "strategy": strategy,
        "strategy_label": label,
        "member_count": count,
        "use_modes": use_modes,
        "providers": providers,
        "sentence": sentence,
    }
