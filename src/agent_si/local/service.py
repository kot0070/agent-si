"""K05 local runtime service: owning-lane side of the connect entries.

Owns the ``agent_si.local.service.LocalRuntimeService`` targets named by
``backend.local_connect.REALIZATION_MAP`` (and the matching
``agent_si.local.service`` prefix used by the adapter/gateway maps):
every method delegates to the real entry point it names through a lazy
import, so this module adds no behaviour and never creates an import
cycle (``backend.local_connect`` must never import this module).
Standard library only.
"""

from __future__ import annotations

from typing import Any


class LocalRuntimeService:
    """Local runtime attach/detach/status service (entry-point backed)."""

    @staticmethod
    def get_status() -> Any:
        """Read the local runtime status via the real entry point."""
        from agent_si.backend import local_connect as _entries

        return _entries.get_status()

    @staticmethod
    def connect(runtime_ref: str, session_token: str) -> Any:
        """Attach a local runtime via the real entry point."""
        from agent_si.backend import local_connect as _entries

        return _entries.connect(runtime_ref, session_token=session_token)

    @staticmethod
    def disconnect(session_token: str) -> Any:
        """Detach the local runtime via the real entry point."""
        from agent_si.backend import local_connect as _entries

        return _entries.disconnect(session_token=session_token)

    @staticmethod
    def list_models() -> Any:
        """List known local models via the real entry point."""
        from agent_si.backend import local_connect as _entries

        return _entries.list_models()
