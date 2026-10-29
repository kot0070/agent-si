"""K03VER2 row 200: catalog versions + changelog + proposal approval flow.

Versions are recorded per catalog ref with a required change note; every
record appends one changelog row. A review yields a separate proposal
carrying its own changelog text; the owner approves or rejects it, and an
approved proposal applies its version bump. No other lane owns these
symbols.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException, Request

#: Exact shipped-preset model id (never retyped, never a second id).
MODEL_ID = "meta/muse-spark-1.3-contributor"

#: Frozen error-code names for this module (each pinned in its own test).
ERROR_CODES_CATALOG_VERSIONS = (
    "CATALOG_VERSION_INVALID",
    "CHANGELOG_ENTRY_MISSING",
    "PROPOSAL_NOT_FOUND",
    "PROPOSAL_ALREADY_DECIDED",
)


class CatalogVersionError(Exception):
    """Version/proposal failure carrying the frozen ``.code`` name."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CatalogVersion:
    catalog_ref: str
    version: int
    change_notes: str
    recorded_at: str


@dataclass(frozen=True)
class ChangelogRow:
    catalog_ref: str
    version: int
    change_notes: str
    recorded_at: str


@dataclass(frozen=True)
class CatalogProposal:
    proposal_id: str
    catalog_ref: str
    from_version: int
    to_version: int
    changes: Tuple[str, ...]
    changelog: str
    status: str
    reviewed_by: Optional[str]


#: Current version per catalog ref.
_VERSIONS: Dict[str, CatalogVersion] = {}

#: Append-only changelog rows in recording order.
_CHANGELOG: List[ChangelogRow] = []

#: Proposals by id.
_PROPOSALS: Dict[str, CatalogProposal] = {}

#: Proposal sequence for unique ids.
_PROPOSAL_SEQ = [0]


def record_version(
    catalog_ref: str,
    version: int,
    change_notes: str,
    recorded_at: str,
) -> CatalogVersion:
    """Record a new catalog version with its change note."""
    if not isinstance(catalog_ref, str) or not catalog_ref.strip():
        raise CatalogVersionError(
            "CATALOG_VERSION_INVALID",
            "catalog ref must be a non-empty string",
        )
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise CatalogVersionError(
            "CATALOG_VERSION_INVALID",
            "version for %r must be a positive int" % (catalog_ref,),
        )
    if not isinstance(change_notes, str) or not change_notes.strip():
        raise CatalogVersionError(
            "CHANGELOG_ENTRY_MISSING",
            "version %d of %r carries no change note" % (version, catalog_ref),
        )
    current = _VERSIONS.get(catalog_ref)
    if current is not None and version <= current.version:
        raise CatalogVersionError(
            "CATALOG_VERSION_INVALID",
            "version %d does not advance %r past %d"
            % (version, catalog_ref, current.version),
        )
    recorded = CatalogVersion(
        catalog_ref=catalog_ref,
        version=version,
        change_notes=change_notes,
        recorded_at=recorded_at,
    )
    _VERSIONS[catalog_ref] = recorded
    _CHANGELOG.append(
        ChangelogRow(
            catalog_ref=catalog_ref,
            version=version,
            change_notes=change_notes,
            recorded_at=recorded_at,
        )
    )
    return recorded


def get_changelog(catalog_ref: str = "") -> Tuple[ChangelogRow, ...]:
    """Changelog rows, oldest first; filtered by ref when given."""
    if catalog_ref:
        return tuple(row for row in _CHANGELOG if row.catalog_ref == catalog_ref)
    return tuple(_CHANGELOG)


def current_version(catalog_ref: str) -> CatalogVersion:
    """Current version for one catalog ref."""
    try:
        return _VERSIONS[catalog_ref]
    except KeyError:
        raise CatalogVersionError(
            "CATALOG_VERSION_INVALID",
            "catalog ref %r has no recorded version" % (catalog_ref,),
        )


def propose_catalog_update(
    catalog_ref: str,
    from_version: int,
    to_version: int,
    changes: List[str],
    proposed_at: str,
) -> CatalogProposal:
    """Review output: a separate proposal with a changelog for approval."""
    if not isinstance(catalog_ref, str) or not catalog_ref.strip():
        raise CatalogVersionError(
            "CATALOG_VERSION_INVALID",
            "proposal catalog ref must be a non-empty string",
        )
    if to_version <= from_version:
        raise CatalogVersionError(
            "CATALOG_VERSION_INVALID",
            "proposal for %r must advance past %d" % (catalog_ref, from_version),
        )
    if not changes or not all(
        isinstance(item, str) and item.strip() for item in changes
    ):
        raise CatalogVersionError(
            "CHANGELOG_ENTRY_MISSING",
            "proposal for %r carries no changelog entries" % (catalog_ref,),
        )
    _PROPOSAL_SEQ[0] += 1
    proposal_id = "prop-%s-%d-to-%d-%d" % (
        catalog_ref, from_version, to_version, _PROPOSAL_SEQ[0],
    )
    changelog = "; ".join(item.strip() for item in changes)
    proposal = CatalogProposal(
        proposal_id=proposal_id,
        catalog_ref=catalog_ref,
        from_version=from_version,
        to_version=to_version,
        changes=tuple(changes),
        changelog=changelog,
        status="PENDING",
        reviewed_by=None,
    )
    _PROPOSALS[proposal_id] = proposal
    return proposal


def approve_proposal(
    proposal_id: str,
    approver: str,
    approved: bool,
    decided_at: str,
) -> CatalogProposal:
    """Owner decision on a proposal; approval applies the version bump."""
    proposal = _PROPOSALS.get(proposal_id)
    if proposal is None:
        raise CatalogVersionError(
            "PROPOSAL_NOT_FOUND",
            "proposal %r does not exist" % (proposal_id,),
        )
    if proposal.status != "PENDING":
        raise CatalogVersionError(
            "PROPOSAL_ALREADY_DECIDED",
            "proposal %r is already %s" % (proposal_id, proposal.status),
        )
    if not isinstance(approver, str) or not approver.strip():
        raise CatalogVersionError(
            "CATALOG_VERSION_INVALID",
            "proposal %r needs a named approver" % (proposal_id,),
        )
    status = "APPROVED" if approved else "REJECTED"
    decided = CatalogProposal(
        proposal_id=proposal.proposal_id,
        catalog_ref=proposal.catalog_ref,
        from_version=proposal.from_version,
        to_version=proposal.to_version,
        changes=proposal.changes,
        changelog=proposal.changelog,
        status=status,
        reviewed_by=approver,
    )
    _PROPOSALS[proposal_id] = decided
    if approved:
        record_version(
            proposal.catalog_ref,
            proposal.to_version,
            proposal.changelog,
            decided_at,
        )
    return decided


#: Entry points: logical name -> symbol in this module.
ENTRY_POINTS = {
    "record_version": "record_version",
    "get_changelog": "get_changelog",
    "current_version": "current_version",
    "propose_catalog_update": "propose_catalog_update",
    "approve_proposal": "approve_proposal",
}


def register_catalog_version_routes(app):
    """Mount the catalog version/changelog/proposal surface; returns app."""

    def _dump_version(row: CatalogVersion) -> dict:
        return {
            "catalog_ref": row.catalog_ref,
            "version": row.version,
            "change_notes": row.change_notes,
            "recorded_at": row.recorded_at,
        }

    def _dump_proposal(row: CatalogProposal) -> dict:
        return {
            "proposal_id": row.proposal_id,
            "catalog_ref": row.catalog_ref,
            "from_version": row.from_version,
            "to_version": row.to_version,
            "changes": list(row.changes),
            "changelog": row.changelog,
            "status": row.status,
            "reviewed_by": row.reviewed_by,
        }

    def _fail(exc: Exception) -> HTTPException:
        code = getattr(exc, "code", None)
        if isinstance(exc, CatalogVersionError):
            return HTTPException(status_code=400, detail="%s: %s" % (code, exc))
        if isinstance(exc, (KeyError, ValueError, TypeError)):
            return HTTPException(status_code=400, detail=str(exc))
        return HTTPException(status_code=500, detail=str(exc))

    async def _body(request: Request) -> dict:
        try:
            data = await request.json()
        except Exception:
            return {}
        merged = dict(request.query_params)
        if isinstance(data, dict):
            merged.update(data)
        return merged

    def _bind(method: str, path: str):
        binder = None
        try:
            binder = app.get if method == "GET" else app.post
        except AttributeError:
            binder = None
        if binder is None:
            return app.route(path, methods=[method])
        return binder(path)

    @_bind("POST", "/api/v1/teststage/catalog/versions/record")
    async def _record(request: Request) -> dict:
        merged = await _body(request)
        try:
            row = record_version(
                merged.get("catalog_ref", ""),
                int(merged.get("version", 0)),
                merged.get("change_notes", ""),
                str(merged.get("recorded_at", "")),
            )
        except Exception as exc:
            raise _fail(exc)
        return _dump_version(row)

    _record.__annotations__ = {"request": Request}

    @_bind("GET", "/api/v1/teststage/catalog/changelog")
    async def _changelog(request: Request) -> dict:
        merged = dict(request.query_params)
        rows = get_changelog(str(merged.get("catalog_ref", "")))
        return {
            "rows": [
                {
                    "catalog_ref": row.catalog_ref,
                    "version": row.version,
                    "change_notes": row.change_notes,
                    "recorded_at": row.recorded_at,
                }
                for row in rows
            ]
        }

    _changelog.__annotations__ = {"request": Request}

    @_bind("POST", "/api/v1/teststage/catalog/proposals")
    async def _propose(request: Request) -> dict:
        merged = await _body(request)
        try:
            changes = merged.get("changes", [])
            if isinstance(changes, str):
                changes = [changes]
            row = propose_catalog_update(
                merged.get("catalog_ref", ""),
                int(merged.get("from_version", 0)),
                int(merged.get("to_version", 0)),
                list(changes),
                str(merged.get("proposed_at", "")),
            )
        except Exception as exc:
            raise _fail(exc)
        return _dump_proposal(row)

    _propose.__annotations__ = {"request": Request}

    @_bind("POST", "/api/v1/teststage/catalog/proposals/approve")
    async def _approve(request: Request) -> dict:
        merged = await _body(request)
        try:
            raw = merged.get("approved", False)
            if isinstance(raw, str):
                approved = raw.strip().lower() in ("1", "true", "yes", "on")
            else:
                approved = bool(raw)
            row = approve_proposal(
                str(merged.get("proposal_id", "")),
                str(merged.get("approver", "")),
                approved,
                str(merged.get("decided_at", "")),
            )
        except Exception as exc:
            raise _fail(exc)
        return _dump_proposal(row)

    _approve.__annotations__ = {"request": Request}

    return app
