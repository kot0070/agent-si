"""K09-A instruction-guard, STEP2.

Stdlib only; no kb imports, so this module can never form an import cycle.
screen() matches INSTRUCTION_MARKERS as lowercase substrings and reports
the first hit as an evidence reference; None means the text is clean.
"""

from __future__ import annotations

import hashlib
import sys as _mod_sys
from typing import Optional

_mod_sys.modules.setdefault(
    "src." + __name__ if not __name__.startswith("src.") else __name__[4:],
    _mod_sys.modules[__name__],
)
"""Dual-harness identity: root-based (src.*) and src-based (agent_si.*)
imports resolve to this same module object."""

INSTRUCTION_MARKERS = (
    "ignore all previous instructions",
    "ignore previous instructions",
    "disregard all previous instructions",
    "disregard previous instructions",
    "escalate",
    "privilege escalation",
    "reveal system prompt",
)


def screen(text: str) -> Optional[str]:
    """Return "evidence:<sha1hex[:12]>" on marker hit, else None."""
    lowered = text.lower()
    for marker in INSTRUCTION_MARKERS:
        if marker in lowered:
            digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
            return "evidence:" + digest
    return None
