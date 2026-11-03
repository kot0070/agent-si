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
import re

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
    "https://dev.meta.ai/docs",
)

#: Canonical own-docs base per staged provider (never a foreign URL).
#: Providers with no own allowlisted docs base have no entry here: their
#: proposal envelope is the shipped-copy marker below, never a
#: foreign provider's docs.
PROVIDER_DOCS = {
    "anthropic": "https://docs.anthropic.com",
    "deepseek": "https://docs.deepseek.com",
    "google": "https://cloud.google.com/vertex-ai/docs",
    "groq": "https://console.groq.com/docs",
    "local": "https://ollama.com/docs",
    "meta": "https://dev.meta.ai/docs",
    "mistral": "https://docs.mistral.ai",
    "openai": "https://platform.openai.com/docs",
    "xai": "https://docs.x.ai",
}

SHIPPED_COPY_PREFIX = "shipped copy from "


def shipped_copy_marker(retrieved_at):
    """Honest envelope for providers with no own allowlisted docs base."""
    return "%s%s" % (SHIPPED_COPY_PREFIX, retrieved_at)


def is_shipped_copy_source(source_url):
    """True only for the shipped-copy marker (never a URL)."""
    return isinstance(source_url, str) and source_url.startswith(
        SHIPPED_COPY_PREFIX)


def provider_source_url(provider_id, retrieved_at):
    """Envelope for one provider: own docs base or the shipped marker."""
    base = PROVIDER_DOCS.get(provider_id)
    if base and _allowlisted(base):
        return base
    return shipped_copy_marker(retrieved_at)


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


#: Instruction-like page text is data, never orders: a fetched string
#: value carrying one of these markers is dropped from proposals (the
#: row keeps its filed value). Narrow literal markers only, so filed
#: KB prose ("suited to ...", "watch out for ...") never trips them.
_INSTRUCTION_LIKE = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
               re.IGNORECASE),
    re.compile(r"disregard\s+.*instructions", re.IGNORECASE),
    re.compile(r"\byou\s+are\s+now\b", re.IGNORECASE),
    re.compile(r"<\s*script\b", re.IGNORECASE),
    re.compile(r"\bjailbreak\b", re.IGNORECASE),
    re.compile(r"\bexfiltrat\w*\b", re.IGNORECASE),
)


def _looks_instruction_like(value):
    """True when a string field value reads as instructions, not data."""
    if not isinstance(value, str):
        return False
    return any(mark.search(value) for mark in _INSTRUCTION_LIKE)


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


def _classify_field(known_rows, entry, provider_id, model_id, name,
                    value, source, retrieved_at):
    """Sort one (row, field, value) triple: change, added, skip, reject.

    Pairs outside the base stage as added-row fields (the connected-row
    update path); unknown field names are rejected; values already on
    file are skipped. Never raises, never invents a price.
    """
    if name not in kb.ROW_FIELD_NAMES:
        return ("rejected", {"entry": entry,
                             "reason": "unknown field %r" % (name,)})
    if _looks_instruction_like(value):
        return ("rejected", {"entry": entry,
                              "reason": "instruction-like text dropped"})
    row = known_rows.get((provider_id, model_id))
    if row is None:
        return ("added", {"provider_id": provider_id,
                          "model_id": model_id,
                          "field": name,
                          "new": value,
                          "source": source,
                          "retrieved_at": retrieved_at})
    try:
        old = row["fields"][name]["value"]
    except (KeyError, TypeError):
        old = kb.UNKNOWN
    if old == value:
        return ("skipped", None)
    return ("changed", {"provider_id": provider_id,
                        "model_id": model_id,
                        "field": name,
                        "old": old,
                        "new": value,
                        "source": source,
                        "retrieved_at": retrieved_at})


def _build_proposal(catalog, items, source_url, retrieved_at):
    """Assemble a proposal from normalized field items (data only).

    items carry (entry, provider_id, model_id, field, new, source,
    retrieved_at) tuples. Unknown pairs group into "added" row drafts
    (one per pair, full sourced-field mapping); the catalog is untouched.
    """
    changes = []
    reasons = []
    rejected = []
    added_by_pair = {}
    added_order = []
    known_rows = {(row.get("provider_id"), row.get("model_id")): row
                  for row in catalog.get("models", [])
                  if isinstance(row, dict)}
    for item in items:
        entry, provider_id, model_id, name, value, source, stamp = item
        kind, staged = _classify_field(
            known_rows, entry, provider_id, model_id, name, value,
            source, stamp)
        if kind == "changed":
            changes.append(staged)
        elif kind == "added":
            pair = (provider_id, model_id)
            if pair not in added_by_pair:
                added_by_pair[pair] = {
                    "provider_id": provider_id,
                    "model_id": model_id,
                    "fields": {},
                    "source": source_url,
                    "retrieved_at": retrieved_at}
                added_order.append(pair)
            added_by_pair[pair]["fields"][name] = {
                "value": value,
                "source": source,
                "retrieved_at": stamp}
        elif kind == "rejected":
            rejected.append(staged)
    added = [added_by_pair[pair] for pair in added_order]
    if not changes and not added:
        reasons.append("no schema-valid field changes in fetched data")
    for item in rejected:
        reasons.append(str(item))
    return {"source_url": source_url, "retrieved_at": retrieved_at,
            "changes": changes, "added": added,
            "rejected": rejected, "reasons": reasons}


def propose_update(catalog, source_url, fetched_text, retrieved_at):
    """Build a schema-checked proposal diff; the catalog is not touched.

    Entries for pairs outside the base stage as added rows (the
    connected-row update path) instead of rejecting; malformed entries
    and unknown field names are still rejected.
    """
    entries, problem = _parse_models_document(fetched_text)
    if entries is None:
        return {"source_url": source_url, "retrieved_at": retrieved_at,
                "changes": [], "added": [], "rejected": [],
                "reasons": [problem]}
    items = []
    pending_rejected = []
    for entry in entries:
        if not isinstance(entry, dict):
            pending_rejected.append({"entry": entry,
                                     "reason": "entry is not a dict"})
            continue
        provider_id = entry.get("provider_id")
        model_id = entry.get("model_id")
        fields = entry.get("fields")
        if not provider_id or not model_id or not isinstance(fields, dict):
            pending_rejected.append({"entry": entry, "reason":
                                     "entry needs provider_id, model_id, "
                                     "fields"})
            continue
        for name, value in fields.items():
            items.append((entry, provider_id, model_id, name, value,
                          source_url, retrieved_at))
    proposal = _build_proposal(catalog, items, source_url, retrieved_at)
    for item in pending_rejected:
        proposal["rejected"].append(item)
        proposal["reasons"].append(str(item))
    return proposal


def propose_from_field_data(catalog, entries, source_url, retrieved_at):
    """Build a proposal from explicit per-field entries (data only).

    entries carry provider_id, model_id and field plus new, with an
    optional per-entry source plus retrieved_at (each defaulting to the
    envelope source_url plus retrieved_at). Unknown pairs stage as
    added rows, so a connected provider missing from the base gains a
    sourced row; the catalog is not touched.
    """
    items = []
    pending_rejected = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            pending_rejected.append({"entry": entry,
                                     "reason": "entry is not a dict"})
            continue
        provider_id = entry.get("provider_id")
        model_id = entry.get("model_id")
        name = entry.get("field")
        if not provider_id or not model_id or not name:
            pending_rejected.append({"entry": entry, "reason":
                                     "entry needs provider_id, model_id, "
                                     "field"})
            continue
        items.append((entry, provider_id, model_id, name, entry.get("new"),
                      entry.get("source") or source_url,
                      entry.get("retrieved_at") or retrieved_at))
    proposal = _build_proposal(catalog, items, source_url, retrieved_at)
    for item in pending_rejected:
        proposal["rejected"].append(item)
        proposal["reasons"].append(str(item))
    return proposal


def validate_proposal(catalog, proposal):
    """Return a list of proposal violations; [] means appliable."""
    errors = []
    if not isinstance(proposal, dict):
        return ["proposal is not a dict"]
    if not _allowlisted(proposal.get("source_url")) and not \
            is_shipped_copy_source(proposal.get("source_url")):
        errors.append("proposal source %r is outside the allowlist"
                      % (proposal.get("source_url"),))
    if not proposal.get("retrieved_at"):
        errors.append("proposal lacks retrieved_at")
    changes = proposal.get("changes")
    added = proposal.get("added", [])
    if not isinstance(added, list):
        return errors + ["proposal added rows are not a list"]
    if (not isinstance(changes, list) or not changes) and not added:
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
    for item in added:
        if not isinstance(item, dict):
            errors.append("added row is not a dict")
            continue
        pair = (item.get("provider_id"), item.get("model_id"))
        if not pair[0] or not pair[1]:
            errors.append("added row needs provider_id and model_id")
        fields = item.get("fields")
        if not isinstance(fields, dict) or not fields:
            errors.append("added row %s/%s needs a non-empty fields mapping"
                          % pair)
            continue
        for name in fields:
            if name not in kb.ROW_FIELD_NAMES:
                errors.append("added row targets unknown field %r" % (name,))
        if not item.get("source") or not item.get("retrieved_at"):
            errors.append("added row %s/%s lacks source or retrieved_at"
                          % pair)
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


def find_leftover_keys(store):
    """List credential-store entry names only, never values.

    Safe leftover finder for the key-delete proof: returns the sorted
    entry names so a caller can show an entry is gone without ever
    reading a secret value. A store that cannot be listed reads
    as empty.
    """
    try:
        names = list(store)
    except Exception:
        return []
    found = []
    for name in names:
        if isinstance(name, str) and name and name not in found:
            found.append(name)
    return sorted(found)


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


def _note_source_links(row, source, retrieved_at):
    """Record one change source on a row's source_links (list-safe).

    Fresh UNKNOWN rows carry a scalar marker, never a list: wrap it
    instead of splitting it into characters.
    """
    if not source:
        return
    links = row["fields"]["source_links"]
    current = links["value"]
    if isinstance(current, list):
        values = list(current)
    elif current == kb.UNKNOWN or current is None:
        values = []
    else:
        values = [current]
    if source not in values:
        values.append(source)
    links["value"] = values
    links["source"] = source
    links["retrieved_at"] = retrieved_at


def _apply_added(catalog, proposal, providers):
    """Create (or merge) staged added rows; returns nothing.

    A pair already on file merges its staged fields instead of
    duplicating the row; staged per-field sources win, falling back to
    the entry envelope and then the proposal envelope.
    """
    index = {}
    for row in catalog["models"]:
        if isinstance(row, dict):
            index[(row.get("provider_id"), row.get("model_id"))] = row
    for item in proposal.get("added", []) or []:
        if not isinstance(item, dict):
            continue
        provider_id = item.get("provider_id")
        model_id = item.get("model_id")
        if not provider_id or not model_id:
            continue
        fields = item.get("fields")
        if not isinstance(fields, dict):
            fields = {}
        row = index.get((provider_id, model_id))
        if row is None:
            row = kb.make_model_row(provider_id, model_id)
            catalog["models"].append(row)
            index[(provider_id, model_id)] = row
        for name, triple in fields.items():
            if name not in kb.ROW_FIELD_NAMES:
                continue
            if isinstance(triple, dict) and "value" in triple:
                value = triple.get("value")
                source = (triple.get("source") or item.get("source")
                          or proposal.get("source_url"))
                stamp = (triple.get("retrieved_at")
                         or item.get("retrieved_at")
                         or proposal.get("retrieved_at"))
            else:
                value = triple
                source = item.get("source") or proposal.get("source_url")
                stamp = (item.get("retrieved_at")
                         or proposal.get("retrieved_at"))
            row["fields"][name] = {
                "value": value,
                "source": source or kb.UNKNOWN,
                "retrieved_at": stamp or kb.UNKNOWN}
        _note_source_links(
            row,
            item.get("source") or proposal.get("source_url"),
            item.get("retrieved_at") or proposal.get("retrieved_at"))
        if provider_id not in providers:
            providers.append(provider_id)


def _apply_changes(catalog, proposal):
    providers = []
    _apply_added(catalog, proposal, providers)
    for change in proposal["changes"]:
        for row in catalog["models"]:
            if row.get("provider_id") == change["provider_id"] and \
                    row.get("model_id") == change["model_id"]:
                field = row["fields"][change["field"]]
                field["value"] = change["new"]
                field["source"] = change["source"]
                field["retrieved_at"] = change["retrieved_at"]
                _note_source_links(row, change["source"],
                                   change["retrieved_at"])
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
    added_rows = [item for item in proposal.get("added", []) or []
                  if isinstance(item, dict)]
    if added_rows:
        summary = ("%d field change(s), %d new row(s)"
                   % (len(proposal["changes"]), len(added_rows)))
    else:
        summary = "%d field change(s)" % len(proposal["changes"])
    updated["version"]["change_log"] = list(
        updated["version"].get("change_log", [])) + [{
            "version": version,
            "at": proposal["retrieved_at"],
            "summary": summary,
            "source": proposal["source_url"],
            "providers": providers,
            "changes": copy.deepcopy(proposal["changes"]),
            "added": copy.deepcopy(added_rows),
            "cost_state": cost_state}]
    check = kb.validate_catalog(updated)
    if check:
        raise KB_VALIDATION_FAILED(
            "KB_VALIDATION_FAILED: apply produced an invalid catalog: %s"
            % "; ".join(check))
    return {"catalog": updated, "applied": True, "version": version,
            "cost_state": cost_state, "metric": metric,
            "added": len(added_rows)}


__all__ = ["KB_SOURCE_ALLOWLIST", "PROVIDER_DOCS", "KBUpdateError",
           "SourceNotAllowlistedError", "ProposalRejectedError",
           "ConfirmationRequiredError", "KB_VALIDATION_FAILED",
           "KB_PROPOSAL_NOT_APPROVED", "MetricWriteError", "MetricState",
           "fetch_source", "propose_update", "validate_proposal",
           "write_metric_record", "attach_metric_by_usage_ref",
           "find_leftover_keys", "provider_source_url",
           "shipped_copy_marker", "is_shipped_copy_source",
           "new_snapshot_version", "compute_cost", "apply_proposal",
           "propose_from_field_data"]
