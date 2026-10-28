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
    attach_kb,
    detach_kb,
    list_kbs,
    manifest_lookup,
    read_section,
    record_hit,
    record_miss,
    record_web_fallback,
    retrieve,
    savings_report,
    set_role_kb_enabled,
)

__all__ = [
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
    "read_section",
    "record_hit",
    "record_miss",
    "record_web_fallback",
    "retrieve",
    "savings_report",
    "set_role_kb_enabled",
]
