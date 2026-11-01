"""K09-A knowledge-base registry, STEP2 (storage + validation layer).

Owns the attached-source store plus KB directory shape validation. The
retrieval lane calls this module; names and signatures here are frozen.

KB directory shape (validated by register): the directory at
``Path(source.kb_id)`` must be a dir holding a ``manifest.json`` file that
parses as a JSON dict, a purpose declaration (a ``purpose.txt`` file or a
``"purpose"`` key in the manifest), and at least one section.

Documented foreign-layout adapter (the ONE adapter): flat-md layout. A KB
dir with no ``sections/`` subfolder is accepted when ``*.md`` files live
directly at the top level of the KB dir (``manifest.json`` + purpose
declaration still required at top level). Section ids are the ``.md`` file
titles without suffix; ``section_text`` reads ``sections/<id>.md`` first,
then falls back to the flat ``<id>.md``.
"""

from __future__ import annotations

import re

import json
from pathlib import Path
from typing import Optional

try:
    from agent_si.kb.models import KnowledgeSource
except ImportError:
    from src.agent_si.kb.models import KnowledgeSource

import sys as _mod_sys

_mod_sys.modules.setdefault(
    "src." + __name__ if not __name__.startswith("src.") else __name__[4:],
    _mod_sys.modules[__name__],
)
"""Dual-harness identity: root-based (src.*) and src-based (agent_si.*)
imports resolve to this same module object, so the attached-source
store (_SOURCES) is shared whatever path the harness uses."""

_VALID_KINDS = ("LOCAL_CAPABILITY", "DEV_ROLE", "DEV_SHARED")

_SOURCES: dict[str, KnowledgeSource] = {}
_ENABLED: dict[tuple[str, Optional[str], str], bool] = {}


def register(source: KnowledgeSource) -> str:
    """Validate the KB dir shape at Path(source.kb_id) and store the source."""
    if source.kind not in _VALID_KINDS:
        raise ValueError(f"unknown kind: {source.kind!r}")
    kb_dir = Path(source.kb_id)
    if not kb_dir.is_dir():
        raise ValueError(f"kb dir missing: {source.kb_id!r}")
    try:
        manifest = json.loads((kb_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"manifest.json missing or not a JSON dict: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("manifest.json must parse as a JSON dict")
    purpose = manifest.get("purpose")
    purpose_ok = (kb_dir / "purpose.txt").is_file() or (
        isinstance(purpose, str) and purpose.strip() != ""
    )
    if not purpose_ok:
        raise ValueError("purpose missing: need purpose.txt or manifest 'purpose'")
    sections_dir = kb_dir / "sections"
    has_sections = sections_dir.is_dir() and any(
        p.is_file() for p in sections_dir.glob("*.md")
    )
    has_flat = any(p.is_file() for p in kb_dir.glob("*.md"))
    if not (has_sections or has_flat):
        raise ValueError("no sections: need sections/*.md or top-level *.md")
    _SOURCES[source.kb_id] = source
    return source.kb_id


def unregister(kb_id: str) -> None:
    """Remove a source; idempotent no-op if unknown."""
    _SOURCES.pop(kb_id, None)
    for key in [key for key in _ENABLED if key[2] == kb_id]:
        del _ENABLED[key]


# FXKBCHAT attach block: read-only scope view for explicit-kb chat.
def attached_source(kb_id: str) -> Optional[KnowledgeSource]:
    """Return the attached source for kb_id, or None when unattached."""
    return _SOURCES.get(kb_id)


def sources_for(
    project_id: str, role: Optional[str] = None
) -> list[KnowledgeSource]:
    """Attached entries for project_id visible to role."""
    result: list[KnowledgeSource] = []
    for source in _SOURCES.values():
        if source.project_id != project_id:
            continue
        if not (source.role is None or source.role == role):
            continue
        if not _ENABLED.get((project_id, role, source.kb_id), True):
            continue
        result.append(source)
    return result


def set_enabled(project_id: str, role: str, kb_id: str, enabled: bool) -> None:
    """Enable or disable one kb for one (project_id, role) pair."""
    _ENABLED[(project_id, role, kb_id)] = bool(enabled)


def is_attached(kb_id: str) -> bool:
    """True when kb_id is currently registered."""
    return kb_id in _SOURCES


def section_ids(kb_id: str) -> list[str]:
    """Section ids: manifest 'sections' list if present, else disk scan."""
    manifest: object = None
    try:
        manifest = json.loads((Path(kb_id) / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = None
    if isinstance(manifest, dict) and isinstance(manifest.get("sections"), list):
        return [str(s) for s in manifest["sections"]]
    kb_dir = Path(kb_id)
    sections_dir = kb_dir / "sections"
    names: list[str] = []
    if sections_dir.is_dir():
        names = sorted(p.stem for p in sections_dir.glob("*.md") if p.is_file())
    if not names and kb_dir.is_dir():
        names = sorted(p.stem for p in kb_dir.glob("*.md") if p.is_file())
    return names


def section_text(kb_id: str, section_id: str) -> str:
    """Section markdown; KeyError if unknown. Reads sections/ first, then flat."""
    kb_dir = Path(kb_id)
    for candidate in (
        kb_dir / "sections" / f"{section_id}.md",
        kb_dir / f"{section_id}.md",
    ):
        try:
            return candidate.read_text(encoding="utf-8")
        except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
            continue
    raise KeyError(section_id)


#: Question words that carry no content (never used as KB match terms).
_STOP_WORDS = frozenset({
    "what", "which", "where", "when", "does", "about", "with", "from", "that", "this",
    "have", "your", "there", "their", "will", "would", "could", "should", "tell",
    "please", "know", "give", "show", "into", "than", "then", "they", "them",
})


def _query_terms(query: str) -> list[str]:
    """Significant words of a user question (4+ letters/digits, lower case)."""
    return [w for w in re.findall(r"[0-9a-zЀ-ӿ]{4,}", query.lower())
            if w not in _STOP_WORDS]


def find_sections(kb_id: str, query: str) -> list[str]:
    """Section ids whose id or text contains the whole query or any of its
    significant words (case-insensitive). A chat question is never a verbatim
    substring of a section, so the whole-query test alone found nothing live
    (PART1DRIVE4 F11 01.11: "quokka beacon code?" missed "...beacon code is QUOKKA-7Z")."""
    if not query or not query.strip():
        return []
    needle = query.lower()
    terms = _query_terms(query)
    hits: list[str] = []
    for section_id in section_ids(kb_id):
        sid = section_id.lower()
        if needle in sid or any(term in sid for term in terms):
            hits.append(section_id)
            continue
        try:
            text = section_text(kb_id, section_id).lower()
        except KeyError:
            continue
        if needle in text or any(term in text for term in terms):
            hits.append(section_id)
    return hits
