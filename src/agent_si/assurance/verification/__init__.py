"""K03 assurance lane verification package: run-output checker.

Owns verification over the run's own tool rows plus files on disk, ahead
of audit and finalize. Every artifact resolves through the single shared
grounding module; this package defines no second copy. The entry point is
``checker.verify_run`` (also re-exported here as ``verify_run``).
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = ["checker", "verify_run"]


def __getattr__(name: str) -> Any:
    """Lazily load the checker on first attribute use (no hard import)."""
    if name in ("checker", "verify_run"):
        module = importlib.import_module(
            "agent_si.assurance.verification.checker"
        )
        if name == "checker":
            return module
        return module.verify_run
    raise AttributeError(
        "module %s has no attribute %s" % (__name__, name)
    )
