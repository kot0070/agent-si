"""In-app KB update: allowlisted fetch plus schema-validated proposal.

Fetched page text is data, never instructions: it is only ever parsed
as JSON data and validated field by field against the KB schema. This
module has no tools beyond fetch plus proposal building plus the
explicit user apply. Applying a proposal needs user_confirmed=True,
bumps the version, appends a change log entry, keeps source links, and
records the update cost through an injected CostCalculator port over a
PricingSnapshot (UNAVAILABLE cost is never written as zero).

CostCalculator port: cost_calculator(usage, pricing_snapshot) -> number.
MetricStore port: a plain dict keyed by usage ref for attach semantics.
"""
import copy
import json

from agent_si.model_kb import kb

KB_SOURCE_ALLOWLIST = (
    "https://platform.openai.com/docs",
    "https://docs.anthropic.com",
    "https://cloud.google.com/vertex-ai/docs",
    "https://docs.mistral.ai",
    "https://console.groq.com/docs",
    "https://console.openrouter.ai/docs",
    "https://docs.deepseek.com",
    "https://docs.x.ai",
    "https://ollama.com/docs",
    "https://lmstudio.ai/docs",
)


class KBUpdateError(ValueError):
    """Base error for every KB update failure."""


class SourceNotAllowlistedError(KBUpdateError):
    """Raised when a fetch URL is outside the allowlist."""


class ProposalRejectedError(KBUpdateError):
    """Raised when a proposal fails schema validation on apply."""


class ConfirmationRequiredError(KBUpdateError):
    """Raised when apply runs without explicit user confirmation."""


class KB_VALIDATION_FAILED(ProposalRejectedError):
    """Frozen sec6 code, raised literally on schema-validation failure."""


class KB_PROPOSAL_NOT_APPROVED(ConfirmationRequiredError):
    """Frozen sec6 code, raised literally without explicit approval."""


class MetricWriteError(KBUpdateError):
    """Raised when a MetricRecord breaks the K13 write rules."""


PRICE_VERSION_MUST_ADVANCE = "PRICE_VERSION_MUST_ADVANCE"


class PriceVersionError(KBUpdateError):
    """New prices refused as anything but a new snapshot version."""

    code = PRICE_VERSION_MUST_ADVANCE


class MetricState:
    MEASURED = "MEASURED"
    CALCULATED = "CALCULATED"
    ESTIMATED = "ESTIMATED"
    INFERRED = "INFERRED"
    UNAVAILABLE = "UNAVAILABLE"

    ALL = frozenset({MEASURED, CALCULATED, ESTIMATED, INFERRED, UNAVAILABLE})


def _allowlisted(url):
    return isinstance(url, str) and any(
        url == base or url.startswith(base + "/")
        for base in KB_SOURCE_ALLOWLIST)


def fetch_source(url, fetcher):
    """Fetch one KB source page; the fetcher is injected (fakes in tests)."""
    if not _allowlisted(url):
        raise SourceNotAllowlistedError(
            "source %r is outside the KB allowlist" % (url,))
    return fetcher(url)


def _parse_models_document(fetched_text):
    try:
        document = json.loads(fetched_text)
    except (ValueError, TypeError):
        return None, "fetched text is not JSON data"
    if not isinstance(document, dict) or not isinstance(
            document.get("models"), list):
        return None, "fetched text lacks a models list"
    return document["models"], ""


def propose_update(catalog, source_url, fetched_text, retrieved_at):
    """Build a schema-checked proposal diff; the catalog is not touched."""
    changes = []
    reasons = []
    entries, problem = _parse_models_document(fetched_text)
    if entries is None:
        return {"source_url": source_url, "retrieved_at": retrieved_at,
                "changes": [], "rejected": [],
                "reasons": [problem]}
    rejected = []
    known_rows = {(row.get("provider_id"), row.get("model_id")): row
                  for row in catalog.get("models", [])
                  if isinstance(row, dict)}
    for entry in entries:
        if not isinstance(entry, dict):
            rejected.append({"entry": entry,
                             "reason": "entry is not a dict"})
            continue
        provider_id = entry.get("provider_id")
        model_id = entry.get("model_id")
        fields = entry.get("fields")
        if not provider_id or not model_id or not isinstance(fields, dict):
            rejected.append({"entry": entry, "reason":
                             "entry needs provider_id, model_id, fields"})
            continue
        row = known_rows.get((provider_id, model_id))
        if row is None:
            rejected.append({"entry": entry, "reason":
                             "row %s/%s is not in the base"
                             % (provider_id, model_id)})
            continue
        for name, value in fields.items():
            if name not in kb.ROW_FIELD_NAMES:
                rejected.append({"entry": entry, "reason":
                                 "unknown field %r" % (name,)})
                continue
            old = row["fields"][name]["value"]
            if old == value:
                continue
            changes.append({"provider_id": provider_id,
                            "model_id": model_id,
                            "field": name,
                            "old": old,
                            "new": value,
                            "source": source_url,
                            "retrieved_at": retrieved_at})
    if not changes:
        reasons.append("no schema-valid field changes in fetched data")
    for item in rejected:
        reasons.append(str(item))
    return {"source_url": source_url, "retrieved_at": retrieved_at,
            "changes": changes, "rejected": rejected, "reasons": reasons}


def validate_proposal(catalog, proposal):
    """Return a list of proposal violations; [] means appliable."""
    errors = []
    if not isinstance(proposal, dict):
        return ["proposal is not a dict"]
    if not _allowlisted(proposal.get("source_url")):
        errors.append("proposal source %r is outside the allowlist"
                      % (proposal.get("source_url"),))
    if not proposal.get("retrieved_at"):
        errors.append("proposal lacks retrieved_at")
    changes = proposal.get("changes")
    if not isinstance(changes, list) or not changes:
        return errors + ["proposal carries no changes"]
    known_rows = {(row.get("provider_id"), row.get("model_id"))
                  for row in catalog.get("models", [])
                  if isinstance(row, dict)}
    for change in changes:
        if not isinstance(change, dict):
            errors.append("change is not a dict")
            continue
        pair = (change.get("provider_id"), change.get("model_id"))
        if pair not in known_rows:
            errors.append("change targets row %s/%s outside the base"
                          % pair)
        if change.get("field") not in kb.ROW_FIELD_NAMES:
            errors.append("change targets unknown field %r"
                          % (change.get("field"),))
        if not change.get("source") or not change.get("retrieved_at"):
            errors.append("change lacks source or retrieved_at")
    return errors


def write_metric_record(metric_id, project_id, task_id, run_id,
                        metric_name, value, unit, state, source,
                        recorded_at):
    """Build a K13 MetricRecord; missing write fields are rejected.

    An UNAVAILABLE metric with a zero value is rejected: unknown cost
    is never reported as zero.
    """
    if value is None or unit is None or state is None or source is None:
        raise MetricWriteError(
            "value, unit, state and source are required at write")
    if state not in MetricState.ALL:
        raise MetricWriteError("unknown metric state %r" % (state,))
    if state == MetricState.UNAVAILABLE and value == 0:
        raise MetricWriteError("UNAVAILABLE cost must never read zero")
    return {"metric_id": metric_id, "project_id": project_id,
            "task_id": task_id, "run_id": run_id,
            "metric_name": metric_name, "value": value, "unit": unit,
            "state": state, "source": source, "recorded_at": recorded_at}


def attach_metric_by_usage_ref(store, usage_ref, record):
    """Re-collection with an identical usage ref attaches, no duplicate."""
    if usage_ref in store:
        return store[usage_ref], False
    store[usage_ref] = record
    return record, True


def new_snapshot_version(snapshot, pricing_snapshot_id, created_at,
                         **overrides):
    """Corrections arrive as a new immutable snapshot version (ARCH-424).

    New prices are accepted only as a NEW version: a missing/unchanged id
    (silent in-place mutation path) and unknown price fields are refused.
    The input snapshot is never touched; the derived copy carries the new
    id, the new prices and the creation time.
    """
    current_id = snapshot.get("pricing_snapshot_id") \
        if isinstance(snapshot, dict) else None
    if not pricing_snapshot_id or pricing_snapshot_id == current_id:
        raise PriceVersionError(
            "new prices need a new pricing_snapshot_id, got %r "
            "[PRICE_VERSION_MUST_ADVANCE]" % (pricing_snapshot_id,))
    allowed = set(snapshot.keys()) if isinstance(snapshot, dict) else set()
    unknown = [name for name in overrides if name not in allowed]
    if unknown:
        raise PriceVersionError(
            "unknown snapshot price fields %r "
            "[PRICE_VERSION_MUST_ADVANCE]" % (sorted(unknown),))
    next_snapshot = copy.deepcopy(snapshot)
    next_snapshot.update(overrides)
    next_snapshot["pricing_snapshot_id"] = pricing_snapshot_id
    next_snapshot["created_at"] = created_at
    return next_snapshot


def compute_cost(cost_calculator, usage, pricing_snapshot):
    """Cost arrives only through the injected CostCalculator port."""
    if cost_calculator is None:
        raise KBUpdateError("no CostCalculator available for update cost")
    if pricing_snapshot is None:
        raise KBUpdateError("no PricingSnapshot available for update cost")
    return cost_calculator(usage, pricing_snapshot)


def _apply_changes(catalog, proposal):
    providers = []
    for change in proposal["changes"]:
        for row in catalog["models"]:
            if row.get("provider_id") == change["provider_id"] and \
                    row.get("model_id") == change["model_id"]:
                field = row["fields"][change["field"]]
                field["value"] = change["new"]
                field["source"] = change["source"]
                field["retrieved_at"] = change["retrieved_at"]
                links = row["fields"]["source_links"]
                if change["source"] not in links["value"]:
                    links["value"] = list(links["value"]) + [
                        change["source"]]
                    links["source"] = change["source"]
                    links["retrieved_at"] = change["retrieved_at"]
        if change["provider_id"] not in providers:
            providers.append(change["provider_id"])
    return sorted(providers)


def apply_proposal(catalog, proposal, user_confirmed=False,
                   cost_calculator=None, pricing_snapshot=None,
                   usage=None, usage_ref=None, metric_store=None,
                   project_id=None, task_id=None, run_id=None,
                   recorded_at=None):
    """Apply a validated proposal ONLY on explicit user confirmation.

    Returns {"catalog", "applied", "version", "cost_state", "metric"}.
    The input catalog dict is never mutated.
    """
    if user_confirmed is not True:
        raise KB_PROPOSAL_NOT_APPROVED(
            "KB_PROPOSAL_NOT_APPROVED: KB proposal apply needs "
            "explicit user confirmation")
    errors = validate_proposal(catalog, proposal)
    if errors:
        raise KB_VALIDATION_FAILED(
            "KB_VALIDATION_FAILED: proposal rejected: %s"
            % "; ".join(errors))
    updated = copy.deepcopy(catalog)
    providers = _apply_changes(updated, proposal)
    version = int(updated["version"].get("kb_version", 0)) + 1
    updated["version"]["kb_version"] = version
    updated["version"]["updated_at"] = proposal["retrieved_at"]
    cost_state = MetricState.UNAVAILABLE
    metric = None
    if cost_calculator is not None and pricing_snapshot is not None \
            and usage is not None:
        value = compute_cost(cost_calculator, usage, pricing_snapshot)
        metric = write_metric_record(
            metric_id="kb-update-%d" % version,
            project_id=project_id, task_id=task_id, run_id=run_id,
            metric_name="kb_update_cost", value=value,
            unit=pricing_snapshot.get("currency", "UNKNOWN"),
            state=MetricState.CALCULATED,
            source="pricing_snapshot:%s" % pricing_snapshot.get(
                "pricing_snapshot_id"),
            recorded_at=recorded_at or proposal["retrieved_at"])
        if metric_store is not None and usage_ref is not None:
            metric, _ = attach_metric_by_usage_ref(
                metric_store, usage_ref, metric)
        cost_state = MetricState.CALCULATED
    updated["version"]["change_log"] = list(
        updated["version"].get("change_log", [])) + [{
            "version": version,
            "at": proposal["retrieved_at"],
            "summary": "%d field change(s)" % len(proposal["changes"]),
            "source": proposal["source_url"],
            "providers": providers,
            "changes": copy.deepcopy(proposal["changes"]),
            "cost_state": cost_state}]
    check = kb.validate_catalog(updated)
    if check:
        raise KB_VALIDATION_FAILED(
            "KB_VALIDATION_FAILED: apply produced an invalid catalog: %s"
            % "; ".join(check))
    return {"catalog": updated, "applied": True, "version": version,
            "cost_state": cost_state, "metric": metric}


__all__ = ["KB_SOURCE_ALLOWLIST", "KBUpdateError",
           "SourceNotAllowlistedError", "ProposalRejectedError",
           "ConfirmationRequiredError", "KB_VALIDATION_FAILED",
           "KB_PROPOSAL_NOT_APPROVED", "MetricWriteError", "MetricState",
           "fetch_source", "propose_update", "validate_proposal",
           "write_metric_record", "attach_metric_by_usage_ref",
           "new_snapshot_version", "compute_cost", "apply_proposal"]
