"""K03WIRE served test-stage rows (1317|200, 1318|201, 1425|M-P3-120,
1442|M-P4-154).

Every entry has the frozen shape ``(payload: dict) -> dict`` and
drives only the real product entries: the catalog
version/changelog/proposal flow, the runner contract, the four
built-in test bases and the global default-ON local-tests switch.
The module adds no product logic of its own; it only adapts HTTP
query payloads to the real entries and their results to plain JSON
dicts. Errors from the real entries keep their frozen signal codes
on the wire.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request

_CATALOG_VERSIONS_ROUTE = "/api/v1/teststage/catalog/versions"
_RUNNER_CONTRACT_ROUTE = "/api/v1/teststage/runner-contract"
_TEST_BASES_ROUTE = "/api/v1/teststage/test-bases"
_SETTINGS_DEFAULTS_ROUTE = "/api/v1/teststage/settings/defaults"


class _WireError(Exception):
    """Entry-level refusal carrying its HTTP status plus signal code."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def _utcnow() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _need_text(payload: dict[str, Any], name: str, what: str) -> str:
    """Return one required non-blank text field, else a loud 400."""
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise _WireError(400, "K03WIRE_FIELD_MISSING",
                         "k03wire needs a non-empty %s" % what)
    return value.strip()


def _need_int(payload: dict[str, Any], name: str, what: str) -> int:
    """Return one required int field, else a loud 400."""
    try:
        return int(str(payload.get(name, "")))
    except (TypeError, ValueError):
        raise _WireError(400, "K03WIRE_FIELD_INVALID",
                         "k03wire needs %s as an int" % what) from None


def _str_list(value: Any) -> list[str]:
    """Render one query/body field as a list of non-blank strings."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part for part in
                 (chunk.strip() for chunk in value.split(";")) if part]
        return parts
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value
                if str(item).strip()]
    return [str(value).strip()]


def _as_bool(value: Any) -> bool:
    """Render one query/body flag as a bool."""
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def k03wire_catalog_versions(payload: dict[str, Any]) -> dict[str, Any]:
    """Serve the catalog version/changelog/proposal flow over one GET lane."""
    from agent_si.test_runners import catalog_versions as _entries

    op = str(payload.get("op") or "read").strip().lower()
    if op == "record":
        row = _entries.record_version(
            _need_text(payload, "catalog_ref", "catalog_ref"),
            _need_int(payload, "version", "version"),
            _need_text(payload, "change_notes", "change_notes"),
            str(payload.get("recorded_at") or _utcnow()),
        )
        return {
            "catalog_ref": row.catalog_ref,
            "version": row.version,
            "change_notes": row.change_notes,
            "recorded_at": row.recorded_at,
        }
    if op == "propose":
        proposal = _entries.propose_catalog_update(
            _need_text(payload, "catalog_ref", "catalog_ref"),
            _need_int(payload, "from_version", "from_version"),
            _need_int(payload, "to_version", "to_version"),
            _str_list(payload.get("changes")),
            str(payload.get("proposed_at") or _utcnow()),
        )
        return _proposal_of(proposal)
    if op == "approve":
        proposal = _entries.approve_proposal(
            _need_text(payload, "proposal_id", "proposal_id"),
            _need_text(payload, "approver", "approver"),
            _as_bool(payload.get("approved", False)),
            str(payload.get("decided_at") or _utcnow()),
        )
        return _proposal_of(proposal)
    if op != "read":
        raise _WireError(400, "K03WIRE_OP_UNKNOWN",
                         "catalog versions op %r is not read/record/"
                         "propose/approve" % (payload.get("op"),))
    ref = _need_text(payload, "catalog_ref", "catalog_ref")
    try:
        current = _entries.current_version(ref)
    except _entries.CatalogVersionError:
        current = None
    rows = _entries.get_changelog(ref)
    return {
        "catalog_ref": ref,
        "current_version": None if current is None else {
            "catalog_ref": current.catalog_ref,
            "version": current.version,
            "change_notes": current.change_notes,
            "recorded_at": current.recorded_at,
        },
        "changelog": [
            {
                "catalog_ref": row.catalog_ref,
                "version": row.version,
                "change_notes": row.change_notes,
                "recorded_at": row.recorded_at,
            }
            for row in rows
        ],
    }


def _proposal_of(proposal: Any) -> dict[str, Any]:
    """Render one real catalog proposal as a plain JSON dict."""
    return {
        "proposal_id": proposal.proposal_id,
        "catalog_ref": proposal.catalog_ref,
        "from_version": proposal.from_version,
        "to_version": proposal.to_version,
        "changes": list(proposal.changes),
        "changelog": proposal.changelog,
        "status": proposal.status,
        "reviewed_by": proposal.reviewed_by,
    }


def k03wire_runner_contract(payload: dict[str, Any]) -> dict[str, Any]:
    """Serve the published runner contract over one GET lane."""
    from agent_si.test_runners import runner_contract as _entries

    op = str(payload.get("op") or "contract").strip().lower()
    if op == "approve":
        runner_id = _need_text(payload, "runner_id", "runner_id")
        approver = _need_text(payload, "approver", "approver")
        _entries.approve_user_runner(runner_id, approver)
        return {"runner_id": runner_id, "approved": True}
    if op == "run":
        profile = {
            "project_id": _need_text(payload, "project_id", "project_id"),
            "profile_name": str(payload.get("profile_name") or ""),
            "runtime": _need_text(payload, "runtime", "runtime"),
            "base_id": str(payload.get("base_id") or ""),
        }
        result = _entries.run_with_contract(
            profile,
            _need_text(payload, "test_id", "test_id"),
            _need_text(payload, "runner_id", "runner_id"),
        )
        return {
            "test_id": result.test_id,
            "status": result.status,
            "evidence_ref": result.evidence_ref,
            "runner_id": result.runner_id,
            "contract_version": result.contract_version,
        }
    if op != "contract":
        raise _WireError(400, "K03WIRE_OP_UNKNOWN",
                         "runner contract op %r is not contract/run/"
                         "approve" % (payload.get("op"),))
    return {
        "contract_version": _entries.RUNNER_CONTRACT_VERSION,
        "policy": "built-in runners always run; a user runner runs "
                  "only after its approval is recorded",
    }


def k03wire_test_bases(payload: dict[str, Any]) -> dict[str, Any]:
    """Serve the four built-in test bases with their CODE/AI/HUMAN kinds."""
    from agent_si.test_runners import test_bases as _entries
    from agent_si.test_runners import test_planner as _planner

    builtins = [row for row in _entries.list_bases()
                if row.origin == "builtin"]
    return {
        "builtins": [
            {"base_id": row.base_id, "kind": row.kind,
             "origin": row.origin}
            for row in builtins
        ],
        "count": len(builtins),
        "execution_kinds": list(_planner.EXECUTION_KINDS),
    }


def k03wire_settings_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    """Serve the global default-ON switch with the per-project value."""
    from agent_si.qa_catalog import qa_catalog as _catalog

    project_id = str(payload.get("project_id") or "global")
    global_default_on = bool(_catalog.local_tests_enabled(
        "k03wire-global-default-probe"))
    return {
        "project_id": project_id,
        "global_default_on": global_default_on,
        "enabled": bool(_catalog.local_tests_enabled(project_id)),
    }


def _refused(status: int, code: str, message: str) -> HTTPException:
    """Build one machine-readable refusal carrying its signal code."""
    return HTTPException(
        status_code=status, detail={"code": code, "message": message})


def _call(entry: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Run one entry; map the real errors to their HTTP refusals."""
    from agent_si.test_runners import catalog_versions as _versions
    from agent_si.test_runners import runner_contract as _contract
    from agent_si.test_runners import test_bases as _bases

    try:
        return entry(payload)
    except _WireError as exc:
        raise _refused(exc.status, exc.code, str(exc)) from None
    except (_versions.CatalogVersionError,
            _contract.RunnerContractError,
            _bases.TestBaseError) as exc:
        raise _refused(400, exc.code, str(exc)) from None
    except (ValueError, KeyError, TypeError) as exc:
        raise _refused(
            400, "K03WIRE_BAD_REQUEST", "%s: %s"
            % (type(exc).__name__, exc)) from None


def _bind(app: Any, method: str, path: str) -> Any:
    """Duck-type binder (same shape as the stage_runner mount)."""
    binder = None
    try:
        binder = app.get if method == "GET" else app.post
    except AttributeError:
        binder = None
    if binder is None:
        return app.route(path, methods=[method])
    return binder(path)


def register_k03wire_teststage_routes(app: Any) -> Any:
    """Mount the four K03WIRE test-stage routes; returns the app."""

    @_bind(app, "GET", _CATALOG_VERSIONS_ROUTE)
    async def _k03wire_catalog_versions(request: Request) -> dict[str, Any]:
        return _call(k03wire_catalog_versions, dict(request.query_params))

    _k03wire_catalog_versions.__annotations__ = {"request": Request}

    @_bind(app, "GET", _RUNNER_CONTRACT_ROUTE)
    async def _k03wire_runner_contract(request: Request) -> dict[str, Any]:
        return _call(k03wire_runner_contract, dict(request.query_params))

    _k03wire_runner_contract.__annotations__ = {"request": Request}

    @_bind(app, "GET", _TEST_BASES_ROUTE)
    async def _k03wire_test_bases(request: Request) -> dict[str, Any]:
        return _call(k03wire_test_bases, dict(request.query_params))

    _k03wire_test_bases.__annotations__ = {"request": Request}

    @_bind(app, "GET", _SETTINGS_DEFAULTS_ROUTE)
    async def _k03wire_settings_defaults(request: Request) -> dict[str, Any]:
        return _call(k03wire_settings_defaults, dict(request.query_params))

    _k03wire_settings_defaults.__annotations__ = {"request": Request}

    return app
