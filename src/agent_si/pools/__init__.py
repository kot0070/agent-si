# K04 pools package — canonical pools-side import surface for the
# pools/routing lane (serves the R-311/R-332/R-339 pools-side seams).
"""Pool bindings, strategies, picker and plain-language summaries.

This package is the pools-side authority used by the served pools routes:
binding construction and the frozen strategy vocabulary live in
:mod:`agent_si.routing.pools`; the plain-language summary helpers live in
:mod:`agent_si.pools.summary`. Standard library only: no machine paths,
no secrets, no vendor or model defaults.
"""

from __future__ import annotations

from agent_si.pools.summary import binding_summary, strategy_label
from agent_si.routing.pools import (
    PoolBinding,
    PoolMember,
    bind_pool_store,
    binding_view,
    default_strategy_for,
    guided_strategy_levels,
    make_binding,
    pick_pool_strategy,
    picker_options,
    resolve_pool,
    suggest_strongest,
    unbind_pool_store,
)

__all__ = [
    "PoolBinding",
    "PoolMember",
    "bind_pool_store",
    "binding_summary",
    "binding_view",
    "default_strategy_for",
    "guided_strategy_levels",
    "make_binding",
    "pick_pool_strategy",
    "picker_options",
    "resolve_pool",
    "strategy_label",
    "suggest_strongest",
    "unbind_pool_store",
]
