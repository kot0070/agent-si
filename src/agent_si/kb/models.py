"""K09-A retrieval-lane models, STEP2.

Holds the frozen KB surface types (KnowledgeSource, KnowledgeChunk,
RetrievalPolicy and the three errors) so product code imports types from
this module and never from the frozen interface module. SectionTouch
records one served section read; new_section_log builds the fresh
per-retrieve section log; count_tokens is the exact token metric
(whitespace-separated word count).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

import sys as _mod_sys

_mod_sys.modules.setdefault(
    "src." + __name__ if not __name__.startswith("src.") else __name__[4:],
    _mod_sys.modules[__name__],
)
"""Dual-harness identity: root-based (src.*) and src-based (agent_si.*)
imports resolve to this same module object, so isinstance checks agree."""

KbKind = Literal["LOCAL_CAPABILITY", "DEV_ROLE", "DEV_SHARED"]


@dataclass
class KnowledgeSource:
    kb_id: str
    kind: KbKind
    project_id: str
    role: Optional[str]
    purpose: str
    read_only: bool = True


@dataclass
class KnowledgeChunk:
    kb_id: str
    section_id: str
    text: str
    tokens: int
    instruction_status: str = "DATA_ONLY"
    citation: str = ""


@dataclass(kw_only=True)
class RetrievalPolicy:
    kb_first: bool = True
    web_second_allowed: bool


class ManifestRequiredError(Exception):
    ...


class WholeKbReadRefused(Exception):
    ...


class InstructionBlockedError(Exception):
    ...


@dataclass
class SectionTouch:
    kb_id: str
    section_id: str
    tokens: int


def new_section_log() -> dict[str, Any]:
    """Return a fresh per-retrieve section log."""
    return {"touches": [], "token_cost": 0}


def count_tokens(text: str) -> int:
    """Count tokens as the exact whitespace-separated word count."""
    return len(text.split())
