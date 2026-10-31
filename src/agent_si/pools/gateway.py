# K04NEXT2 K1 lane (CODER-1 Harrier) — pool-side provisioning-gateway guard.
"""Refuse inline key material on the pools side (row M-P4-149).

Row M-P4-149 reads, verbatim: "fakes only in-repo; the real store goes
through the provisioning gateway"
(``src/agent_si/providers/registry/provider_api.py`` LEFTOVER_RULES).
This guard enforces the same posture where pool bindings are built: a
member may carry id-only refs (provider, model, use mode), never inline
key material. The frozen inline-material field set mirrors
``RAW_INLINE_FIELD_NAMES`` in
``src/agent_si/providers/registry/contracts.py`` exactly, so the pools
side refuses the same fields the registry refuses. Standard library only:
no machine paths, no secrets, no vendor or model defaults.
"""

from __future__ import annotations

from collections.abc import Mapping

#: Row id this guard serves.
GATEWAY_RULE = "M-P4-149"

#: Frozen inline-material fields, verbatim from RAW_INLINE_FIELD_NAMES
#: (src/agent_si/providers/registry/contracts.py).
INLINE_SECRET_FIELD_NAMES = frozenset(
    {
        "api_key",
        "apikey",
        "api_secret",
        "secret_value",
        "client_secret",
        "access_token",
        "password",
        "authorization",
        "x-api-key",
    }
)

#: Nested ref mappings scanned one level down, like the registry does.
NESTED_REF_KEYS = ("secret_ref", "credential_ref")


def _refusal(fields) -> str:
    return ("pool member carries inline key material %s; in-repo runs "
            "use fakes only, the real store goes through the "
            "provisioning gateway [%s]" % (sorted(set(fields)),
                                           GATEWAY_RULE))


def _inline_fields(data: Mapping) -> list:
    found = [key for key in data if key in INLINE_SECRET_FIELD_NAMES]
    for nested_key in NESTED_REF_KEYS:
        nested = data.get(nested_key)
        if isinstance(nested, Mapping):
            found += [key for key in nested
                      if key in INLINE_SECRET_FIELD_NAMES]
    return found


def check_member_refs(member) -> None:
    """Accept an id-only pool member; refuse inline key material.

    Returns None when the member carries refs only. Raises ValueError
    naming M-P4-149 and the gateway when any inline secret field is
    present on the member or one level down in its ref mappings.
    """
    if isinstance(member, Mapping):
        data = member
    else:
        data = getattr(member, "__dict__", None)
        if data is None:
            data = {name: getattr(member, name)
                    for name in ("provider", "model", "use_mode",
                                 "provider_type")
                    if hasattr(member, name)}
    found = _inline_fields(data)
    if found:
        raise ValueError(_refusal(found))
    return None


def check_binding_refs(binding) -> int:
    """Accept a binding whose every member is ref-only; else refuse.

    Returns the checked member count. Accepts PoolBinding objects and
    stored binding dicts; raises the same M-P4-149 ValueError as
    :func:`check_member_refs` on the first dirty member.
    """
    if isinstance(binding, Mapping):
        members = binding.get("members", ()) or ()
    else:
        members = getattr(binding, "members", ()) or ()
    members = list(members)
    for member in members:
        check_member_refs(member)
    return len(members)
