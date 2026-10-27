"""Module-level provider facade functions (frozen K04 section 3.2 surface).

Thin delegation over
:class:`agent_si.providers.registry.provider_api.ProviderAPI`: every
function below carries the EXACT frozen name, parameter list and order
from ``src/agent_si/routing/interface.py`` (``descriptor, secret_ref`` /
``provider_id`` / ``only_evidenced`` / ``provider_instance`` /
``health``) with no extra parameters and no defaults, and forwards to
the matching :class:`ProviderAPI` method with real behavior (no
reimplementation, no placeholder data).

Model placement: ``register_provider`` passes ``descriptor`` and
``secret_ref`` straight through, so the model comes from inside the
descriptor mapping itself (``descriptor["model"]`` or
``descriptor.model``); the facade adds no ``model`` keyword because the
frozen signature has none.

Backing instance: callers with a provisioned stack call
:func:`configure` with their own :class:`ProviderAPI` (registry plus
real credential store, audit sink and usage probe). Without
:func:`configure` the functions fall back to a lazy in-memory default
built here from :class:`ProviderRegistry` plus a minimal ephemeral
credential store and audit sink (standard library only). The default
exists so the facade is usable standalone; its store entries are seeded
explicitly after provisioning, and :func:`remove_provider` surfaces
``CREDENTIAL_ENTRY_MISSING`` when the entry is absent, exactly like the
wired path. Standard library plus ``agent_si`` only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional

from .provider_api import ProviderAPI, ProviderContracts
from .registry import ProviderRegistry

if TYPE_CHECKING:
    from agent_si.routing.interface import SecretRef


class _MemoryCredentialStore:
    """Ephemeral credential-store stand-in for the lazy default backing.

    Entries are seeded explicitly after provisioning; ``has``/``delete``
    mirror the store port :class:`ProviderAPI` removes through.
    """

    def __init__(self) -> None:
        self._entries: dict = {}

    def seed(self, secret_id: str, payload: Any = "ephemeral-entry") -> None:
        self._entries[secret_id] = payload

    def has(self, secret_id: str) -> bool:
        return secret_id in self._entries

    def delete(self, secret_id: str) -> None:
        if secret_id not in self._entries:
            raise KeyError(secret_id)
        del self._entries[secret_id]


class _MemoryAuditSink:
    """Ephemeral audit sink for the lazy default backing."""

    def __init__(self) -> None:
        self.records: list = []

    def append(self, record: Any) -> None:
        self.records.append(dict(record))


_configured_api: ProviderAPI | None = None


def configure(api: ProviderAPI | None) -> ProviderAPI | None:
    """Bind the backing :class:`ProviderAPI` (pass None to reset to lazy).

    Returns the previously bound instance (None when the lazy default
    was in effect) so callers can restore it. The argument must expose
    the five delegated methods; anything else raises ValueError.
    """
    global _configured_api
    previous = _configured_api
    if api is None:
        _configured_api = None
        return previous
    for name in (
        "register_provider",
        "get_provider",
        "list_providers",
        "record_health",
        "remove_provider",
    ):
        if not callable(getattr(api, name, None)):
            raise ValueError(
                "configure needs a ProviderAPI with %r" % (name,)
            )
    _configured_api = api
    return previous


def _current() -> ProviderAPI:
    if _configured_api is not None:
        return _configured_api
    return ProviderAPI(
        ProviderRegistry(), _MemoryCredentialStore(), _MemoryAuditSink()
    )


def register_provider(descriptor: ProviderContracts,
                      secret_ref: SecretRef) -> ProviderContracts:
    """Key-only connect; the model travels inside the descriptor mapping."""
    return _current().register_provider(descriptor, secret_ref)


def get_provider(provider_id: str) -> Optional[ProviderContracts]:
    """Return the provider view, or None for an unknown id (exact match)."""
    return _current().get_provider(provider_id)


def list_providers(only_evidenced: bool) -> List[ProviderContracts]:
    """List provider views, stable-sorted; only evidenced when asked."""
    return _current().list_providers(only_evidenced)


def record_health(provider_id: str, provider_instance: Optional[str],
                  health: str) -> ProviderContracts:
    """Record per-instance health; the latest check wins."""
    return _current().record_health(provider_id, provider_instance, health)


def remove_provider(provider_id: str) -> None:
    """Remove the provider cleanly, including the store entry."""
    return _current().remove_provider(provider_id)


__all__ = [
    "ProviderContracts",
    "configure",
    "register_provider",
    "get_provider",
    "list_providers",
    "record_health",
    "remove_provider",
]
