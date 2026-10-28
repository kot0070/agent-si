"""K05 local-AI gateway interface (shapes only, no logic).

Frozen sources (read-only; 0C wins every clash):
RECORDS/day0/0C_ARCHITECTURE.md sec 6 (passive check before contact:
machine idle else skip with reason, never force, no user
benchmark/test running) and sec 12 (K05 owns src/agent_si/local/).
Other packages code against this module only; lane internals (names
starting with _) are never imported. Every function body is `...`
(no logic): real behavior lives in the owning lane module named
in REALIZATION_MAP. Standard library only.
"""

from __future__ import annotations

import itertools
import os
import threading
from dataclasses import dataclass


#: Passive check passed: machine idle, contact allowed.
GATEWAY_IDLE_REASON = "IDLE"

#: Passive check refused: a user benchmark or test run is active,
#: so the lane skips with reason instead of forcing contact.
GATEWAY_SKIP_REASONS = ("USER_BENCH_RUNNING", "USER_TEST_RUNNING")


@dataclass(frozen=True)
class PassiveCheckResult:
    allowed: bool
    reason: str


#: Env-declared active runs (set by the orchestrator while a user
#: bench/test run owns the machine; read at each check).
_BENCH_RUN_ENV = "AGENT_SI_BENCH_RUN_ID"
_TEST_RUN_ENV = "AGENT_SI_TEST_RUN_ID"

#: Serial one-model machine (0C sec 6): an idle verdict grants the slot
#: to the caller for its upcoming contact, so a later check sees a held
#: machine and skips with reason instead of forcing.
_ACTIVE_GRANT: str | None = None
_GRANT_SEQ = itertools.count(1)
_GRANT_LOCK = threading.Lock()


def passive_check() -> PassiveCheckResult:
    """Idle yields allowed with the idle reason; a running user bench/test run yields not-allowed with its skip reason; never forced."""
    if os.environ.get(_BENCH_RUN_ENV):
        return PassiveCheckResult(allowed=False, reason=GATEWAY_SKIP_REASONS[0])
    if os.environ.get(_TEST_RUN_ENV):
        return PassiveCheckResult(allowed=False, reason=GATEWAY_SKIP_REASONS[1])
    global _ACTIVE_GRANT
    with _GRANT_LOCK:
        if _ACTIVE_GRANT is not None:
            return PassiveCheckResult(allowed=False, reason=GATEWAY_SKIP_REASONS[0])
        _ACTIVE_GRANT = f"gateway-grant-{next(_GRANT_SEQ):06d}"
        return PassiveCheckResult(allowed=True, reason=GATEWAY_IDLE_REASON)


#: Frozen function name to owning lane implementation (dotted path).
REALIZATION_MAP = {
    "passive_check": "agent_si.local.service.GatewayService.passive_check",
}
