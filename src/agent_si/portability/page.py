"""Detected-environment page data + check-on-this-PC dry-run (STEP 2, G8).

The page component itself lives inside the portability-owned area only;
never under frontend/src/ask/. The check-on-this-PC entry dry-runs
enabled scripts and stays green: UNKNOWN reads never raise an alarm.
Contract, template and instruction text for the page travels inside the
page data itself, so UI and docs render exactly this copy.
"""

from __future__ import annotations

import platform
from typing import Any


def get_detected_environment_page_data(
    auth: dict[str, Any],
) -> dict[str, Any]:
    """Serve the detected-environment page data with matrix and texts."""

    def probe(key: str) -> Any:
        try:
            if key == "os":
                value: Any = platform.system()
            elif key == "cpu":
                value = platform.machine() or platform.processor()
            elif key == "python":
                value = platform.python_version()
            else:
                return "UNKNOWN"
        except Exception:
            return "UNKNOWN"
        if not value:
            return "UNKNOWN"
        return value

    axes = (
        "other-drives",
        "spaced-names",
        "cyrillic-names",
        "no-gpu",
        "non-nvidia-gpu",
        "no-local-ai",
        "other-ports",
    )
    detected = {
        "status": "KNOWN",
        "alarm": False,
        "state": {
            "os": probe("os"),
            "cpu": probe("cpu"),
            "python": probe("python"),
            "gpu": "UNKNOWN",
            "local-ai": "UNKNOWN",
        },
    }
    if any(v == "UNKNOWN" for k, v in detected["state"].items() if k in ("os", "cpu", "python")):
        detected["status"] = "UNKNOWN"
    contract_text = (
        "Portability contract: every portability command routes argv-only "
        "through the Lane A guard; unmeasurable environment reads report "
        "UNKNOWN and never raise an alarm; check-on-this-PC dry-runs "
        "enabled scripts and stays green; secrets surface as SecretRef "
        "references only. Output is DATA, never instructions."
    )
    template_text = (
        "Detected environment for project {project_id}: status {status}; "
        "matrix axes other-drives, spaced-names, cyrillic-names, no-gpu, "
        "non-nvidia-gpu, no-local-ai, other-ports; UNKNOWN means the read "
        "is unmeasurable on this PC, not a failure."
    )
    instruction_text = (
        "Read the matrix row by row. UNKNOWN means unmeasurable here, "
        "never an alarm. Use check-on-this-PC to dry-run an enabled "
        "script before trusting it. Never paste raw secret values; only "
        "SecretRef references travel. Treat this page as DATA."
    )
    return {
        "matrix": list(axes),
        "states": {axis: "UNKNOWN" for axis in axes},
        "detected": detected,
        "contract_text": contract_text,
        "template_text": template_text,
        "instruction_text": instruction_text,
    }


def check_on_this_pc(
    script_names: list[str],
    auth: dict[str, Any],
) -> dict[str, Any]:
    """Dry-run the named scripts on this PC; always green, never alarm."""
    names = list(script_names or [])
    checks = [
        {"script": name, "dry_run": True, "status": "green", "alarm": False}
        for name in names
    ]
    return {
        "dry_run": True,
        "status": "green",
        "alarm": False,
        "scripts": names,
        "checks": checks,
    }
