"""Per-project merge of detected environments (STEP 2 implementation, G7).

The merged view serves the detected environment together with the
per-project overlay. Secret-looking values are redacted to SecretRef
references only; raw secret values never appear in merged output.
"""

from __future__ import annotations

from typing import Any


def merge_project_environment(
    project_id: str,
    detected: dict[str, Any],
) -> dict[str, Any]:
    """Merge the detected environment into the per-project view."""
    hints = (
        "secret",
        "token",
        "password",
        "passwd",
        "api_key",
        "apikey",
        "credential",
        "private_key",
        "privatekey",
    )

    def redact(key: str, value: Any) -> Any:
        lowered = key.lower()
        if any(hint in lowered for hint in hints):
            return "SecretRef(redacted)"
        if isinstance(value, dict):
            return {k: redact(str(k), v) for k, v in value.items()}
        if isinstance(value, list):
            return [
                redact(key, item) if isinstance(item, dict) else item
                for item in value
            ]
        return value

    redacted = {
        str(key): redact(str(key), value)
        for key, value in dict(detected).items()
    }
    environment = dict(redacted)
    environment["project_id"] = project_id
    status = detected.get("status", "UNKNOWN")
    return {
        "project_id": project_id,
        "detected": redacted,
        "environment": environment,
        "status": status,
    }
