"""K03VER2 M-P3-120: four built-in test bases plus attached bases.

Every base carries one CODE, AI or HUMAN kind under the runner-library
contract. The four built-ins are frozen; user bases attach with an
explicit kind. No other lane owns these symbols.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from fastapi import HTTPException, Request

#: Exact shipped-preset model id (never retyped, never a second id).
MODEL_ID = "meta/muse-spark-1.3-contributor"

#: The four built-in test bases shipped with the catalog.
BUILTIN_TEST_BASES = (
    "base-code-fast",
    "base-code-full",
    "base-ai-judge",
    "base-human-operated",
)

#: Kind per built-in base, in the same order.
BUILTIN_BASE_KINDS = ("CODE", "CODE", "AI", "HUMAN")

#: Execution kinds every base (built-in or attached) must carry.
EXECUTION_KINDS = ("CODE", "AI", "HUMAN")

#: Frozen error-code names for this module (each pinned in its own test).
ERROR_CODES_TEST_BASES = (
    "UNKNOWN_TEST_BASE",
    "UNKNOWN_EXECUTION_KIND",
    "BASE_ALREADY_ATTACHED",
)


class TestBaseError(Exception):
    """Test-base failure carrying the frozen ``.code`` name."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TestBase:
    base_id: str
    kind: str
    origin: str


#: User-attached bases: base_id -> kind.
_ATTACHED_BASES: Dict[str, str] = {}


def list_bases() -> Tuple[TestBase, ...]:
    """All bases: the four built-ins first, then attached in attach order."""
    rows = [
        TestBase(base_id=base_id, kind=kind, origin="builtin")
        for base_id, kind in zip(BUILTIN_TEST_BASES, BUILTIN_BASE_KINDS)
    ]
    rows.extend(
        TestBase(base_id=base_id, kind=kind, origin="attached")
        for base_id, kind in _ATTACHED_BASES.items()
    )
    return tuple(rows)


def base_kind(base_id: str) -> str:
    """Kind for one base id; unknown ids are refused."""
    for known_id, kind in zip(BUILTIN_TEST_BASES, BUILTIN_BASE_KINDS):
        if base_id == known_id:
            return kind
    try:
        return _ATTACHED_BASES[base_id]
    except KeyError:
        raise TestBaseError(
            "UNKNOWN_TEST_BASE",
            "test base %r is not built-in or attached" % (base_id,),
        )


def attach_base(base_id: str, kind: str) -> TestBase:
    """Attach a user base with its CODE/AI/HUMAN kind."""
    if not isinstance(base_id, str) or not base_id.strip():
        raise TestBaseError(
            "UNKNOWN_TEST_BASE",
            "test base id must be a non-empty string",
        )
    if kind not in EXECUTION_KINDS:
        raise TestBaseError(
            "UNKNOWN_EXECUTION_KIND",
            "kind %r is not CODE, AI or HUMAN" % (kind,),
        )
    if base_id in BUILTIN_TEST_BASES or base_id in _ATTACHED_BASES:
        raise TestBaseError(
            "BASE_ALREADY_ATTACHED",
            "test base %r already exists" % (base_id,),
        )
    _ATTACHED_BASES[base_id] = kind
    return TestBase(base_id=base_id, kind=kind, origin="attached")


#: Entry points: logical name -> symbol in this module.
ENTRY_POINTS = {
    "list_bases": "list_bases",
    "base_kind": "base_kind",
    "attach_base": "attach_base",
}


def register_test_base_routes(app):
    """Mount the test-base surface; returns app."""

    def _fail(exc: Exception) -> HTTPException:
        if isinstance(exc, TestBaseError):
            return HTTPException(
                status_code=400, detail="%s: %s" % (exc.code, exc))
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

    @_bind("GET", "/api/v1/teststage/bases")
    async def _list(request: Request) -> dict:
        rows = list_bases()
        return {
            "bases": [
                {"base_id": row.base_id, "kind": row.kind,
                 "origin": row.origin}
                for row in rows
            ]
        }

    _list.__annotations__ = {"request": Request}

    @_bind("POST", "/api/v1/teststage/bases/attach")
    async def _attach(request: Request) -> dict:
        merged = await _body(request)
        try:
            row = attach_base(
                str(merged.get("base_id", "")),
                str(merged.get("kind", "")),
            )
        except Exception as exc:
            raise _fail(exc)
        return {"base_id": row.base_id, "kind": row.kind,
                "origin": row.origin}

    _attach.__annotations__ = {"request": Request}

    return app
