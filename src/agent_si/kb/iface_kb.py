"""K09-A knowledge-base interface, STEP1 (signatures only).

FROZEN-IFACE-K09-v1: type and function names are frozen, do not rename.
Every function body is the literal Ellipsis; STEP2 implements behaviour.
KB directory shape: manifest.json + sections/*.md + purpose declaration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

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


def attach_kb(source: KnowledgeSource) -> str:
    ...


def detach_kb(kb_id: str) -> None:
    ...


def list_kbs(project_id: str, role: Optional[str] = None) -> list[KnowledgeSource]:
    ...


def set_role_kb_enabled(project_id: str, role: str, kb_id: str, enabled: bool) -> None:
    ...


def retrieve(
    query: str,
    project_id: str,
    role: str,
    policy: Optional[RetrievalPolicy] = None,
) -> tuple[list[KnowledgeChunk], dict[str, Any]]:
    ...


def manifest_lookup(kb_id: str, query: str) -> list[str]:
    ...


def read_section(kb_id: str, section_id: str) -> KnowledgeChunk:
    ...


def record_hit(role: str, agent: str, tokens: int, cost: float) -> None:
    ...


def record_miss(role: str, agent: str, tokens: int, cost: float) -> None:
    ...


def record_web_fallback(role: str, agent: str, tokens: int, cost: float) -> None:
    ...


def savings_report() -> dict[str, Any]:
    ...
