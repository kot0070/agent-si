"""K08 user-requirement register: verbatim store plus PRESERVED audit (SPEC 0A).

The project requirement register keeps the user's requirements verbatim
and audits each requirement as PRESERVED / CHANGED / MISSING /
CONTRADICTED; any non-PRESERVED outcome blocks PASS. The state names
reuse the existing reference states of
:mod:`agent_si.context_keeper.register` (same strings, never redefined
here); frozen contract names from
:mod:`agent_si.context_keeper.interface` are never redefined here.
Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence


@dataclass(frozen=True)
class RequirementRow:
    """One user requirement kept verbatim (immutable)."""

    requirement_id: str
    text: str


@dataclass(frozen=True)
class RequirementAudit:
    """Per-requirement audit outcome plus the PASS-blocking flag.

    ``blocked`` mirrors ``LevelStartBundle.blocked``: True when any
    audited requirement is non-PRESERVED.
    """

    states: Dict[str, str]
    blocked: bool


class RequirementRegister:
    """Verbatim append-only user-requirement register (SPEC 0A)."""

    def __init__(self) -> None:
        self._by_id: Dict[str, RequirementRow] = {}
        self._order: List[str] = []

    def append(self, row: RequirementRow) -> RequirementRow:
        """Persist row verbatim; a duplicate id returns the stored row.

        History is append-only: a duplicate id never overwrites the
        stored row.
        """
        stored = self._by_id.get(row.requirement_id)
        if stored is not None:
            return stored
        self._by_id[row.requirement_id] = row
        self._order.append(row.requirement_id)
        return row

    def read(self, requirement_id: str) -> Optional[RequirementRow]:
        """Return the stored row for requirement_id, else None."""
        return self._by_id.get(requirement_id)

    def list_all(self) -> List[RequirementRow]:
        """Return every stored row in append order (history is kept)."""
        return [self._by_id[requirement_id] for requirement_id in self._order]


def audit_requirements(
    expected: Mapping[str, str],
    actual: Mapping[str, str],
    conflicting_ids: Sequence[str] = (),
    changed_ids: Sequence[str] = (),
) -> RequirementAudit:
    """Audit expected vs actual requirement texts (SPEC 0A states).

    Each expected requirement id maps to one of PRESERVED (actual text
    identical verbatim), CHANGED (actual text differs, or the id is
    flagged in changed_ids), MISSING (id absent from actual) or
    CONTRADICTED (id flagged in conflicting_ids). ``blocked`` is True
    when any requirement audited non-PRESERVED.
    """
    conflicting = set(conflicting_ids)
    changed = set(changed_ids)
    states: Dict[str, str] = {}
    for requirement_id, text in expected.items():
        if requirement_id in conflicting:
            states[requirement_id] = "CONTRADICTED"
        elif requirement_id in changed:
            states[requirement_id] = "CHANGED"
        elif requirement_id not in actual:
            states[requirement_id] = "MISSING"
        elif actual[requirement_id] != text:
            states[requirement_id] = "CHANGED"
        else:
            states[requirement_id] = "PRESERVED"
    blocked = any(state != "PRESERVED" for state in states.values())
    return RequirementAudit(states=states, blocked=blocked)
