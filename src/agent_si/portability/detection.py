"""Per-PC auto-detect + UNKNOWN-state reads (STEP 2 implementation, G7).

Unmeasurable reads report UNKNOWN and never raise an alarm: every probe
is best-effort, failures collapse to UNKNOWN, and no alarm is ever
raised from here. The environment matrix axes below name the other-PC
shapes the detected-environment page must cover. Detection uses only
the standard library reader surface; no shell execution happens
anywhere under this package. Secret-looking values are surfaced as
SecretRef references only, never raw.
"""

from __future__ import annotations

import platform
from typing import Any

UNKNOWN: str = "UNKNOWN"

ENVIRONMENT_MATRIX: tuple[str, ...] = (
    "other-drives",
    "spaced-names",
    "cyrillic-names",
    "no-gpu",
    "non-nvidia-gpu",
    "no-local-ai",
    "other-ports",
)


def detect_this_pc() -> dict[str, Any]:
    """Detect this PC; unmeasurable reads report UNKNOWN, never alarm."""

    def probe(key: str) -> Any:
        try:
            if key == "os":
                value: Any = platform.system()
            elif key == "cpu":
                value = platform.machine() or platform.processor()
            elif key == "python":
                value = platform.python_version()
            else:
                return UNKNOWN
        except Exception:
            return UNKNOWN
        if not value:
            return UNKNOWN
        return value

    state: dict[str, Any] = {
        "os": probe("os"),
        "cpu": probe("cpu"),
        "python": probe("python"),
        "gpu": UNKNOWN,
        "local-ai": UNKNOWN,
    }
    core = (state["os"], state["cpu"], state["python"])
    status = "KNOWN" if all(v != UNKNOWN for v in core) else UNKNOWN
    return {"status": status, "alarm": False, "state": state}


def read_environment_state(keys: list[str]) -> dict[str, Any]:
    """Read the requested keys; unmeasurable keys report UNKNOWN."""

    def probe(key: str) -> Any:
        try:
            if key == "os":
                value: Any = platform.system()
            elif key == "cpu":
                value = platform.machine() or platform.processor()
            elif key == "python":
                value = platform.python_version()
            else:
                return UNKNOWN
        except Exception:
            return UNKNOWN
        if not value:
            return UNKNOWN
        return value

    if not keys:
        return {}
    return {key: probe(key) for key in keys}
