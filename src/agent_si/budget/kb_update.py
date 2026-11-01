"""KB provenance reads plus user-applied proposal applier (K04NEXT3 C2).

Budget-side seam for R-370: field_provenance surfaces every field's
source and retrieval date for one model row, with unsourced fields
marked UNKNOWN, never guessed. apply_proposal applies an already-built
proposal to a copy of the catalog only with explicit user approval, and
records the approval in the change log; without approval it raises.
The input catalog is read-only and never mutated.
"""
from __future__ import annotations

import copy
from collections.abc import Mapping

from agent_si.model_kb import kb as _kb
from agent_si.model_kb import loader as _loader


def field_provenance(catalog, provider_id, model_id):
    """Per-field {value, source, retrieved_at} plus the unsourced names."""
    bridged = _loader.bridge(catalog, provider_id, model_id)
    row = bridged["row"]
    if row is None:
        raise ValueError(
            "no KB row on file for %s/%s" % (provider_id, model_id))
    fields = {}
    unsourced = []
    for name, field in row["fields"].items():
        source = field.get("source") or _kb.UNKNOWN
        retrieved_at = field.get("retrieved_at") or _kb.UNKNOWN
        fields[name] = {"value": field.get("value"),
                        "source": source,
                        "retrieved_at": retrieved_at}
        if source == _kb.UNKNOWN or retrieved_at == _kb.UNKNOWN:
            unsourced.append(name)
    return {"provider_id": provider_id,
            "model_id": model_id,
            "kb_status": bridged["kb_status"],
            "fields": fields,
            "unsourced": sorted(unsourced)}


def apply_proposal(catalog, proposal, *, approved_by, applied_at):
    """Apply proposal changes to a catalog copy, with user approval.

    Every change carries provider_id, model_id, field and new plus its
    source and retrieval date. The version bumps by one and the change
    log records the proposal ref with who approved it and when.
    """
    if not (isinstance(approved_by, str) and approved_by.strip()):
        raise ValueError(
            "proposal applies only with explicit user approval "
            "(approved_by is required)")
    errors = _kb.validate_catalog(catalog)
    if errors:
        raise ValueError(
            "refusing to apply a proposal onto an invalid catalog: %s"
            % (errors,))
    if not isinstance(proposal, Mapping):
        raise ValueError("proposal must be a mapping with changes")
    proposal_ref = proposal.get("proposal_ref")
    changes = proposal.get("changes")
    if not (isinstance(proposal_ref, str) and proposal_ref.strip()):
        raise ValueError("proposal needs a non-empty proposal_ref")
    if not isinstance(changes, list) or not changes:
        raise ValueError("proposal needs a non-empty changes list")
    out = copy.deepcopy(catalog)
    index = {(row.get("provider_id"), row.get("model_id")): row
             for row in out.get("models", []) if isinstance(row, dict)}
    for change in changes:
        if not isinstance(change, Mapping):
            raise ValueError("proposal change must be a mapping: %r"
                             % (change,))
        pair = (change.get("provider_id"), change.get("model_id"))
        if pair not in index:
            raise ValueError(
                "proposal change targets a row outside the base: %s/%s"
                % pair)
        field = change.get("field")
        if field not in _kb.ROW_FIELD_NAMES:
            raise ValueError("proposal change targets unknown field %r"
                             % (field,))
        index[pair]["fields"][field] = {
            "value": change.get("new"),
            "source": change.get("source") or _kb.UNKNOWN,
            "retrieved_at": change.get("retrieved_at") or _kb.UNKNOWN,
        }
    version = out.get("version", {})
    out["version"] = dict(
        version, kb_version=int(version.get("kb_version", 0)) + 1,
        updated_at=applied_at,
        change_log=list(version.get("change_log", [])) + [{
            "proposal_ref": proposal_ref,
            "approved_by": approved_by,
            "applied_at": applied_at,
            "changes": len(changes),
        }])
    errors = _kb.validate_catalog(out)
    if errors:
        raise ValueError(
            "proposal application broke catalog validity: %s" % (errors,))
    return out
