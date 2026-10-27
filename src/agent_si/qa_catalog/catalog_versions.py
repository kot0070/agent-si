"""K03 catalog lane STEP2: versions plus change log plus proposals.

A catalog review yields a separate proposal with a change log for the
owner's approval; newer versions are imported, never edited in place.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

#: Frozen error-code names for this module (each pinned in its own test).
ERROR_CODES_VERSIONS = (
    "PROPOSAL_NOT_APPROVED",
    "UNKNOWN_PROPOSAL",
    "UNKNOWN_BASE_VERSION",
)


class VersionsError(Exception):
    """Version failure carrying the frozen ``.code`` name."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CatalogVersion:
    catalog_ref: str
    version: int
    catalog_hash: str
    created_at: str
    supersedes_version: Optional[int]


@dataclass(frozen=True)
class ChangelogEntry:
    catalog_ref: str
    version: int
    change: str
    changed_at: str
    changed_by: str


@dataclass(frozen=True)
class CatalogProposal:
    proposal_id: str
    catalog_ref: str
    base_version: int
    changes: Tuple[str, ...]
    change_log: Tuple[str, ...]
    status: str
    proposed_by_model: str


_SEED_REF = "catalog-frozen-v1"
_SEED_AT = "2026-10-26T00:00:00Z"


def _catalog_hash(catalog_ref: str, version: int) -> str:
    return hashlib.sha256(
        ("%s:v%d" % (catalog_ref, version)).encode("utf-8")
    ).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_CURRENT: Dict[str, CatalogVersion] = {
    _SEED_REF: CatalogVersion(
        catalog_ref=_SEED_REF,
        version=1,
        catalog_hash=_catalog_hash(_SEED_REF, 1),
        created_at=_SEED_AT,
        supersedes_version=None,
    ),
}

_KNOWN_HASHES: Dict[str, Dict[int, str]] = {
    _SEED_REF: {1: _catalog_hash(_SEED_REF, 1)},
}

_CHANGELOG: Dict[str, List[ChangelogEntry]] = {
    _SEED_REF: [
        ChangelogEntry(
            catalog_ref=_SEED_REF,
            version=1,
            change="initial frozen catalog",
            changed_at=_SEED_AT,
            changed_by="owner",
        )
    ],
}

_PROPOSALS: Dict[str, CatalogProposal] = {}
_APPLIED: set = set()
_PROPOSAL_SEQ = [0]


def current_version(catalog_ref: str) -> CatalogVersion:
    """Return the active catalog version for a ref."""
    try:
        return _CURRENT[catalog_ref]
    except KeyError:
        raise VersionsError(
            "UNKNOWN_BASE_VERSION",
            "no known base version for catalog ref %r" % catalog_ref,
        )


def propose_update(
    catalog_ref: str,
    base_version: int,
    draft_changes: List[str],
    updated_by_model: str,
) -> CatalogProposal:
    """Propose a catalog change set; review yields a separate proposal."""
    if catalog_ref not in _KNOWN_HASHES:
        raise VersionsError(
            "UNKNOWN_BASE_VERSION",
            "no known base version for catalog ref %r" % catalog_ref,
        )
    if base_version not in _KNOWN_HASHES[catalog_ref]:
        raise VersionsError(
            "UNKNOWN_BASE_VERSION",
            "unknown base version %r for catalog ref %r"
            % (base_version, catalog_ref),
        )
    _PROPOSAL_SEQ[0] += 1
    proposal_id = "proposal-%s-v%d-%03d" % (
        catalog_ref,
        base_version,
        _PROPOSAL_SEQ[0],
    )
    proposal = CatalogProposal(
        proposal_id=proposal_id,
        catalog_ref=catalog_ref,
        base_version=base_version,
        changes=tuple(draft_changes),
        change_log=tuple(draft_changes),
        status="PENDING_REVIEW",
        proposed_by_model=updated_by_model,
    )
    _PROPOSALS[proposal_id] = proposal
    return proposal


def apply_proposal(proposal_id: str, approved_by_user: bool) -> CatalogVersion:
    """Apply a proposal only on explicit owner approval; else refused."""
    try:
        proposal = _PROPOSALS[proposal_id]
    except KeyError:
        raise VersionsError(
            "UNKNOWN_PROPOSAL", "unknown proposal %r" % proposal_id
        )
    if not approved_by_user:
        raise VersionsError(
            "PROPOSAL_NOT_APPROVED",
            "proposal %r needs explicit owner approval" % proposal_id,
        )
    if proposal_id in _APPLIED:
        return _CURRENT[proposal.catalog_ref]
    new_version_number = max(
        _CURRENT[proposal.catalog_ref].version, proposal.base_version
    ) + 1
    new_hash = _catalog_hash(proposal.catalog_ref, new_version_number)
    _KNOWN_HASHES[proposal.catalog_ref][new_version_number] = new_hash
    applied = CatalogVersion(
        catalog_ref=proposal.catalog_ref,
        version=new_version_number,
        catalog_hash=new_hash,
        created_at=_utc_now(),
        supersedes_version=_CURRENT[proposal.catalog_ref].version,
    )
    _CURRENT[proposal.catalog_ref] = applied
    log = _CHANGELOG.setdefault(proposal.catalog_ref, [])
    for change in proposal.changes:
        log.append(
            ChangelogEntry(
                catalog_ref=proposal.catalog_ref,
                version=new_version_number,
                change=change,
                changed_at=applied.created_at,
                changed_by="owner",
            )
        )
    _APPLIED.add(proposal_id)
    return applied


def import_newer_version(catalog_ref: str, version: int) -> CatalogVersion:
    """Import a newer catalog version; unknown versions are refused."""
    known = _KNOWN_HASHES.get(catalog_ref, {})
    if version not in known:
        raise VersionsError(
            "UNKNOWN_BASE_VERSION",
            "unknown version %r for catalog ref %r" % (version, catalog_ref),
        )
    current = _CURRENT[catalog_ref]
    if version <= current.version:
        return CatalogVersion(
            catalog_ref=catalog_ref,
            version=version,
            catalog_hash=known[version],
            created_at=current.created_at,
            supersedes_version=version - 1 if version > 1 else None,
        )
    imported = CatalogVersion(
        catalog_ref=catalog_ref,
        version=version,
        catalog_hash=known[version],
        created_at=_utc_now(),
        supersedes_version=current.version,
    )
    _CURRENT[catalog_ref] = imported
    return imported


def get_changelog(catalog_ref: str) -> List[ChangelogEntry]:
    """Change log for a catalog ref, oldest entry first."""
    return list(_CHANGELOG.get(catalog_ref, []))


#: Entry points: logical name -> symbol in this module.
ENTRY_POINTS = {
    "current_version": "current_version",
    "propose_update": "propose_update",
    "apply_proposal": "apply_proposal",
    "import_newer_version": "import_newer_version",
    "get_changelog": "get_changelog",
}
