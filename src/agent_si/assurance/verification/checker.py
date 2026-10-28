"""K03 assurance lane verification checker: run output over grounded refs.

Frozen sources: 0C_ARCHITECTURE sec 1.3 (verification over own tool rows
plus files on disk shares one grounding module with audit); RUNPATH 0C
assurance order (verify, then audit, then finalize); K13_MANIFEST 21C
(missing evidence ref fails the criterion; deterministic scope ids;
frozen records), 17C (one deterministic path per failure class; infra
maps to VERIFICATION_INFRA_FAILURE), 40 (artifacts resolve through the
shared grounding entry).

``verify_run`` checks one run: every required evidence ref must resolve to
a matching ok tool row or to a real file under the run directory, and each
criterion artifact is grounded through the REAL shared grounding module
(never a second copy). Missing or unresolvable evidence fails the
criterion fail-closed, never a silent pass. Unreadable inputs give a
BLOCKED record carrying VERIFICATION_INFRA_FAILURE, never PASS. The
returned record binds project, task, run and contract hash so record-bound
finalization accepts it alongside the matching audit record.

Sibling import shape mirrors audit_coordinator: synthetic sys.modules name
first, plain package import as fallback, stdlib only at module level.
"""

from __future__ import annotations

import importlib
import itertools
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

#: Monotonic verification sequence per scope id (latest wins per scope).
_SCOPE_SEQUENCE: Dict[str, int] = {}

#: Monotonic counter for minted verification ids (never repeats).
_ID_SEQ = itertools.count(1)

#: String spellings that count as false for ok/required flags.
_FALSE_WORDS = frozenset(
    {
        "",
        "0",
        "false",
        "no",
        "off",
        "fail",
        "failed",
        "error",
        "none",
        "null",
    }
)


def _utcnow_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _grounding_module() -> Any:
    """Sibling grounding module by synthetic name, else package import."""
    mod = sys.modules.get("k03_assurance_grounding")
    if mod is not None:
        return mod
    try:
        return importlib.import_module("agent_si.assurance.grounding")
    except ImportError:
        return None


def _policies_module() -> Any:
    """Policies verification module: already loaded one, else import."""
    for mod in list(sys.modules.values()):
        if mod is None:
            continue
        if getattr(mod, "__name__", "") == __name__:
            continue
        if all(
            hasattr(mod, name)
            for name in (
                "VerificationRecord",
                "CriterionResult",
                "run_output_scope_id",
                "canonical_handling",
            )
        ):
            return mod
    try:
        return importlib.import_module("agent_si.policies.verification")
    except ImportError:
        return None


def _manifest() -> Any:
    """Frozen manifest enums (plain package import, both layouts)."""
    try:
        return importlib.import_module("iface.frozen_manifest").manifest
    except ImportError:
        return importlib.import_module("frozen_manifest").manifest


def _plain(item: Any, names: Tuple[str, ...]) -> Any:
    """Read one field from a plain record (mapping or attribute object)."""
    if isinstance(item, dict):
        for name in names:
            if name in item:
                return item[name]
        return None
    for name in names:
        if hasattr(item, name):
            return getattr(item, name)
    getter = getattr(item, "get", None)
    if callable(getter):
        for name in names:
            try:
                value = getter(name)
            except Exception:
                continue
            if value is not None:
                return value
    return None


def _truthy(value: Any) -> bool:
    """True only for positively true flags (fail-closed on anything else)."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in _FALSE_WORDS


def _require_id(label: str, value: Any) -> str:
    """Return the stripped id, or refuse with ValueError (no record)."""
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError("%s must be a non-blank string" % label)
    return text


def _refs_of(criterion: Any) -> Tuple[str, ...]:
    """Normalized evidence refs of one criterion (deduped, ordered)."""
    raw = _plain(criterion, ("evidence_refs", "evidence", "refs"))
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw.strip(),) if raw.strip() else ()
    try:
        items = tuple(raw)
    except TypeError:
        return ()
    return tuple(
        dict.fromkeys(s for s in (str(x).strip() for x in items) if s)
    )


def _required_of(criterion: Any) -> bool:
    """Whether the criterion requires evidence (default True, closed)."""
    raw = _plain(criterion, ("evidence_required",))
    if raw is None:
        return True
    return _truthy(raw)


def _method_of(criterion: Any) -> str:
    """Verification method label of one criterion (never blank)."""
    raw = _plain(criterion, ("verification_method", "method"))
    text = str(raw).strip() if raw is not None else ""
    return text or "grounded-evidence"


def _severity_of(policies: Any, criterion: Any) -> Any:
    """Severity of one criterion (unknown spellings read MEDIUM)."""
    raw = _plain(criterion, ("severity",))
    try:
        if raw is None:
            return policies.FailureSeverity.MEDIUM
        return policies.FailureSeverity(str(raw).strip().upper())
    except ValueError:
        return policies.FailureSeverity.MEDIUM


def _row_resolves(rows: Tuple[Any, ...], ref: str) -> bool:
    """True when a matching ok tool row names this evidence ref."""
    want = ref.strip()
    if not want:
        return False
    for row in rows:
        tool = _plain(row, ("tool",))
        if tool is None or not str(tool).strip():
            continue
        got = _plain(row, ("evidence_ref", "evidence", "ref"))
        if got is None or str(got).strip() != want:
            continue
        ok = _plain(row, ("ok",))
        if ok is None:
            ok = _plain(row, ("output",))
        if _truthy(ok):
            return True
    return False


def _file_resolves(project_dir: str, ref: str) -> bool:
    """True when ref is a real file contained in the project dir."""
    text = ref.strip()
    if not text:
        return False
    try:
        candidate = os.path.realpath(os.path.join(project_dir, text))
        base = os.path.realpath(project_dir)
    except (OSError, ValueError):
        return False
    if candidate != base and not candidate.startswith(base + os.sep):
        return False
    try:
        return os.path.isfile(candidate)
    except (OSError, ValueError):
        return False


def _ground_artifact(
    grounding_mod: Any,
    *,
    artifact_id: str,
    contract_hash: str,
    refs: Tuple[str, ...],
) -> Any:
    """Ground one criterion artifact through the shared grounding module."""
    port_cls = getattr(grounding_mod, "GroundingPort")
    request_cls = getattr(grounding_mod, "GroundingRequest")

    class _GroundedViaShared(port_cls):  # noqa: D106 -- thin real inherit
        pass

    port = _GroundedViaShared()
    return port.ground_artifact(
        request_cls(
            artifact_id=artifact_id,
            contract_hash=contract_hash,
            evidence_refs=tuple(refs),
        )
    )


def _criterion_eval(
    policies: Any,
    grounding_mod: Any,
    criterion: Any,
    *,
    ok_rows: Tuple[Any, ...],
    project_dir: str,
    contract_hash: str,
) -> Any:
    """Evaluate one criterion; missing evidence fails closed, never passes."""
    check = policies.CriterionVerificationResult
    fail_class = policies.VerificationFailureClass.IMPLEMENTATION_AC_DEFECT
    ac_id = str(_plain(criterion, ("ac_id",)) or "").strip()
    refs = _refs_of(criterion)
    method = _method_of(criterion)
    severity = _severity_of(policies, criterion)
    rid = "cr-%s" % (ac_id or "unknown")
    if not ac_id:
        return policies.CriterionResult(
            criterion_result_id=rid,
            ac_id="",
            result=check.FAIL,
            severity=severity,
            verification_method=method,
            evidence_refs=refs,
            failure_class=fail_class,
            notes="criterion without ac_id fails closed",
        )
    if _required_of(criterion) and not refs:
        return policies.CriterionResult(
            criterion_result_id=rid,
            ac_id=ac_id,
            result=check.FAIL,
            severity=severity,
            verification_method=method,
            evidence_refs=(),
            failure_class=fail_class,
            notes="empty evidence_refs on a required criterion fails",
        )
    missing = sorted(
        {
            ref
            for ref in refs
            if not (
                _row_resolves(ok_rows, ref)
                or _file_resolves(project_dir, ref)
            )
        }
    )
    if missing:
        return policies.CriterionResult(
            criterion_result_id=rid,
            ac_id=ac_id,
            result=check.FAIL,
            severity=severity,
            verification_method=method,
            evidence_refs=refs,
            failure_class=fail_class,
            notes="unresolvable evidence_refs: " + ",".join(missing),
        )
    try:
        _ground_artifact(
            grounding_mod,
            artifact_id=ac_id,
            contract_hash=contract_hash,
            refs=refs,
        )
    except Exception as exc:
        return policies.CriterionResult(
            criterion_result_id=rid,
            ac_id=ac_id,
            result=check.FAIL,
            severity=severity,
            verification_method=method,
            evidence_refs=refs,
            failure_class=fail_class,
            notes="shared grounding raised: %s" % type(exc).__name__,
        )
    return policies.CriterionResult(
        criterion_result_id=rid,
        ac_id=ac_id,
        result=check.PASS,
        severity=severity,
        verification_method=method,
        evidence_refs=refs,
        failure_class=None,
        notes="every evidence_ref resolved and grounded",
    )


def _blocked_result(
    policies: Any, criterion: Any, *, reason: str
) -> Any:
    """One BLOCKED criterion result echoing the declared refs."""
    ac_id = str(_plain(criterion, ("ac_id",)) or "").strip()
    return policies.CriterionResult(
        criterion_result_id="cr-%s" % (ac_id or "unknown"),
        ac_id=ac_id,
        result=policies.CriterionVerificationResult.BLOCKED,
        severity=_severity_of(policies, criterion),
        verification_method=_method_of(criterion),
        evidence_refs=_refs_of(criterion),
        failure_class=(
            policies.VerificationFailureClass.VERIFICATION_INFRA_FAILURE
        ),
        notes=reason,
    )


def _assemble(
    policies: Any,
    manifest_mod: Any,
    *,
    scope_id: str,
    verification_id: str,
    sequence: int,
    project_id: str,
    task_id: str,
    run_id: str,
    contract_hash: str,
    results: Tuple[Any, ...],
    overall: Any,
    failure_class: Any,
    started_at: str,
    ended_at: str,
) -> Any:
    """Build the frozen record; inputs are only read, never mutated."""
    union_refs = tuple(
        sorted({ref for item in results for ref in tuple(item.evidence_refs)})
    )
    union_ac = tuple(sorted({item.ac_id for item in results if item.ac_id}))
    return policies.VerificationRecord(
        verification_id=verification_id,
        verification_sequence=sequence,
        supersedes_verification_id=None,
        project_id=project_id,
        task_id=task_id,
        run_id=run_id,
        verification_scope_id=scope_id,
        verification_target_type=(
            policies.VerificationTargetType.RUN_OUTPUT
        ),
        contract_hash=contract_hash,
        criterion_results=tuple(results),
        result=overall,
        handling_disposition=policies.canonical_handling(overall),
        failure_class=failure_class,
        created_at=ended_at,
        started_at=started_at,
        ended_at=ended_at,
        evidence_refs=union_refs,
        artifact_refs=union_ac,
    )


def verify_run(
    *,
    project_dir,
    tool_rows,
    criteria,
    project_id,
    task_id,
    run_id,
    contract_hash,
    verification_id=None,
    verification_sequence=None,
):
    """Verify one run over its own tool rows plus files on disk.

    Every required evidence ref must resolve to a matching ok tool row or
    to a real file under ``project_dir``, and each criterion artifact is
    grounded through the shared grounding module. Missing evidence fails
    the criterion fail-closed. Unreadable ``project_dir``/``tool_rows``/
    ``criteria`` (or an unavailable shared grounding module) yields a
    BLOCKED record with VERIFICATION_INFRA_FAILURE, never PASS. Blank run
    ids or contract hash raise ValueError and yield no record.
    """
    project_id = _require_id("project_id", project_id)
    task_id = _require_id("task_id", task_id)
    run_id = _require_id("run_id", run_id)
    contract_hash = _require_id("contract_hash", contract_hash)
    policies = _policies_module()
    if policies is None:
        raise RuntimeError("agent_si.policies.verification is unavailable")
    manifest_mod = _manifest()
    scope_id = policies.run_output_scope_id(task_id, run_id, contract_hash)
    if verification_sequence is None:
        sequence = _SCOPE_SEQUENCE.get(scope_id, 0) + 1
    else:
        try:
            sequence = int(verification_sequence)
        except (TypeError, ValueError):
            raise ValueError("verification_sequence must be an int")
        if sequence < 1:
            raise ValueError("verification_sequence must be >= 1")
    _SCOPE_SEQUENCE[scope_id] = max(_SCOPE_SEQUENCE.get(scope_id, 0), sequence)
    vid = str(verification_id).strip() if verification_id is not None else ""
    if not vid:
        vid = "verification-%06d" % next(_ID_SEQ)
    started = _utcnow_iso()
    grounding_mod = _grounding_module()
    dir_text = ""
    try:
        if isinstance(project_dir, (str, os.PathLike)):
            dir_text = os.fspath(project_dir)
    except (OSError, ValueError, TypeError):
        dir_text = ""
    dir_ok = bool(dir_text)
    if dir_ok:
        try:
            dir_ok = os.path.isdir(dir_text)
            if dir_ok:
                with os.scandir(dir_text) as _probe:
                    pass
        except (OSError, ValueError):
            dir_ok = False
    rows_ok = isinstance(tool_rows, (list, tuple))
    crit_ok = isinstance(criteria, (list, tuple))
    if grounding_mod is None or not (dir_ok and rows_ok and crit_ok):
        ended = _utcnow_iso()
        if grounding_mod is None:
            reason = "shared grounding module unavailable"
        elif not dir_ok:
            reason = "project_dir unreadable"
        elif not rows_ok:
            reason = "tool_rows unreadable"
        else:
            reason = "criteria unreadable"
        blocked = (
            tuple(_blocked_result(policies, c, reason=reason) for c in criteria)
            if crit_ok
            else ()
        )
        overall = manifest_mod.VerificationResult.BLOCKED
        return _assemble(
            policies,
            manifest_mod,
            scope_id=scope_id,
            verification_id=vid,
            sequence=sequence,
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            contract_hash=contract_hash,
            results=blocked,
            overall=overall,
            failure_class=(
                policies.VerificationFailureClass.VERIFICATION_INFRA_FAILURE
            ),
            started_at=started,
            ended_at=ended,
        )
    ok_rows = tuple(tool_rows)
    results = tuple(
        _criterion_eval(
            policies,
            grounding_mod,
            criterion,
            ok_rows=ok_rows,
            project_dir=dir_text,
            contract_hash=contract_hash,
        )
        for criterion in criteria
    )
    ended = _utcnow_iso()
    values = [item.result.value for item in results]
    if any(value == "BLOCKED" for value in values):
        overall = manifest_mod.VerificationResult.BLOCKED
    elif any(value == "FAIL" for value in values):
        overall = manifest_mod.VerificationResult.FAIL
    else:
        overall = manifest_mod.VerificationResult.PASS
    if overall.value == "PASS":
        failure_class = None
    elif overall.value == "BLOCKED":
        failure_class = (
            policies.VerificationFailureClass.VERIFICATION_INFRA_FAILURE
        )
    else:
        failure_class = (
            policies.VerificationFailureClass.IMPLEMENTATION_AC_DEFECT
        )
    return _assemble(
        policies,
        manifest_mod,
        scope_id=scope_id,
        verification_id=vid,
        sequence=sequence,
        project_id=project_id,
        task_id=task_id,
        run_id=run_id,
        contract_hash=contract_hash,
        results=results,
        overall=overall,
        failure_class=failure_class,
        started_at=started,
        ended_at=ended,
    )


#: Entry points: logical name -> symbol in this file.
ENTRY_POINTS = {
    "verify_run": (
        "agent_si.assurance.verification.checker.verify_run"
    ),
}

__all__ = ["verify_run", "ENTRY_POINTS"]
