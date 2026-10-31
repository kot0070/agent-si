"""K09-A knowledge-base package surface, STEP2.

Re-exports the frozen public names from the implementation homes so
callers can import them from src.agent_si.kb directly. Only implementation
modules are imported here, never the frozen interface module.
"""

from .models import (
    InstructionBlockedError,
    KnowledgeChunk,
    KnowledgeSource,
    ManifestRequiredError,
    RetrievalPolicy,
    WholeKbReadRefused,
)
from .retriever import (
    HANDOFF_INLINE_TOKEN_LIMIT,
    attach_kb,
    detach_kb,
    list_kbs,
    manifest_lookup,
    package_handoff,
    read_section,
    record_hit,
    record_miss,
    record_web_fallback,
    resolve_handoff,
    retrieve,
    retrieve_handoff,
    savings_report,
    set_role_kb_enabled,
)

__all__ = [
    "HANDOFF_INLINE_TOKEN_LIMIT",
    "InstructionBlockedError",
    "KnowledgeChunk",
    "KnowledgeSource",
    "ManifestRequiredError",
    "RetrievalPolicy",
    "WholeKbReadRefused",
    "attach_kb",
    "detach_kb",
    "list_kbs",
    "manifest_lookup",
    "package_handoff",
    "read_section",
    "record_hit",
    "record_miss",
    "record_web_fallback",
    "resolve_handoff",
    "retrieve",
    "retrieve_handoff",
    "savings_report",
    "set_role_kb_enabled",
]
