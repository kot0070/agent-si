"""Portability error codes for the Lane B portability prefix.

Defines the six PORT_* string constants, one per failure condition
(unknown environment, guard denial, unknown or disabled runner,
unavailable merge, unknown command), collected in ERROR_CODES.
"""

from __future__ import annotations

PORT_UNKNOWN_ENVIRONMENT: str = "PORT_UNKNOWN_ENVIRONMENT"
PORT_GUARD_DENIED: str = "PORT_GUARD_DENIED"
PORT_RUNNER_UNKNOWN: str = "PORT_RUNNER_UNKNOWN"
PORT_RUNNER_NOT_ENABLED: str = "PORT_RUNNER_NOT_ENABLED"
PORT_MERGE_UNAVAILABLE: str = "PORT_MERGE_UNAVAILABLE"
PORT_COMMAND_UNKNOWN: str = "PORT_COMMAND_UNKNOWN"

ERROR_CODES: tuple[str, ...] = (
    PORT_UNKNOWN_ENVIRONMENT,
    PORT_GUARD_DENIED,
    PORT_RUNNER_UNKNOWN,
    PORT_RUNNER_NOT_ENABLED,
    PORT_MERGE_UNAVAILABLE,
    PORT_COMMAND_UNKNOWN,
)
