"""Shipped model knowledge base: named format p17ub-kb/1.

Every model row holds the Lane B field set; every field carries its
source URL plus retrieval date. A field without sourced evidence keeps
the literal "UNKNOWN" and is never guessed.

Layout of a catalog dict:
  {"format", "manifest", "version", "models"}
A model row dict:
  {"provider_id", "model_id", "fields": {name: sourced-field}}
A sourced field dict:
  {"value", "source", "retrieved_at"}
"""
import copy
import hashlib
import json
import os

KB_FORMAT_ID = "p17ub-kb/1"
KB_ID = "agent-si-model-kb"

ROW_FIELD_NAMES = (
    "purpose",
    "strengths",
    "weaknesses",
    "context_window",
    "max_output",
    "modalities",
    "tool_calling",
    "reasoning",
    "knowledge_cutoff",
    "currency",
    "price_effective_at",
    "input_token_price",
    "output_token_price",
    "cached_token_price",
    "reasoning_token_price",
    "request_price",
    "best_for",
    "avoid_for",
    "cost_tier",
    "role_notes",
    "source_links",
)

PRICE_FIELD_NAMES = (
    "currency",
    "price_effective_at",
    "input_token_price",
    "output_token_price",
    "cached_token_price",
    "reasoning_token_price",
    "request_price",
)

SNAPSHOT_FIELD_NAMES = (
    "pricing_snapshot_id",
    "provider_id",
    "model_id",
    "currency",
    "effective_at",
    "source",
    "input_token_price",
    "output_token_price",
    "cached_token_price",
    "reasoning_token_price",
    "request_price",
    "other_rules",
    "created_at",
    "hash",
)

UNKNOWN = "UNKNOWN"

KB_SCHEMA = {
    "format_id": KB_FORMAT_ID,
    "kb_id": KB_ID,
    "required_top": ("format", "manifest", "version", "models"),
    "required_row_keys": ("provider_id", "model_id", "fields"),
    "row_fields": ROW_FIELD_NAMES,
    "field_shape": ("value", "source", "retrieved_at"),
}

KB_MANIFEST = {
    "format": KB_FORMAT_ID,
    "kb_id": KB_ID,
    "sources": [],
    "note": "shipped catalog; per-field source plus date wins over "
            "this manifest; unsourced fields read UNKNOWN",
}

KB_VERSION = {
    "format": KB_FORMAT_ID,
    "kb_version": 0,
    "updated_at": UNKNOWN,
    "change_log": [],
}


def sourced(value=UNKNOWN, source=UNKNOWN, retrieved_at=UNKNOWN):
    """Build one sourced field dict."""
    return {"value": value, "source": source, "retrieved_at": retrieved_at}


def unknown_field():
    """Honest marker for a field with no sourced evidence."""
    return sourced()


def make_model_row(provider_id, model_id, fields=None):
    """Build a row; fields maps name to a sourced dict or a raw value.

    A raw value without provenance is stored as UNKNOWN, never taken
    at face value, so callers must pass sourced dicts for real data.
    """
    given = fields or {}
    row_fields = {}
    for name in ROW_FIELD_NAMES:
        item = given.get(name, None)
        if isinstance(item, dict) and set(item.keys()) == {
                "value", "source", "retrieved_at"}:
            row_fields[name] = {"value": item["value"],
                                "source": item["source"] or UNKNOWN,
                                "retrieved_at": (item["retrieved_at"]
                                                 or UNKNOWN)}
        else:
            row_fields[name] = unknown_field()
    return {"provider_id": provider_id, "model_id": model_id,
            "fields": row_fields}


def make_manifest(sources):
    manifest = copy.deepcopy(KB_MANIFEST)
    manifest["sources"] = list(sources)
    return manifest


def make_version(kb_version=1, updated_at=UNKNOWN, change_log=None):
    return {"format": KB_FORMAT_ID, "kb_version": kb_version,
            "updated_at": updated_at, "change_log": list(change_log or [])}


def make_catalog(models, kb_version=1, updated_at=UNKNOWN, change_log=None,
                sources=()):
    """Assemble a catalog dict; models is a list of row dicts."""
    return {"format": KB_FORMAT_ID,
            "manifest": make_manifest(sources),
            "version": make_version(kb_version, updated_at, change_log),
            "models": [copy.deepcopy(row) for row in models]}


def _field_errors(where, fields):
    errors = []
    for name in ROW_FIELD_NAMES:
        if name not in fields:
            errors.append("%s: missing field %r" % (where, name))
            continue
        field = fields[name]
        if not isinstance(field, dict) or set(field.keys()) != {
                "value", "source", "retrieved_at"}:
            errors.append("%s: field %r lacks source plus date shape"
                          % (where, name))
            continue
        if not field["source"] or not field["retrieved_at"]:
            errors.append("%s: field %r has empty source or date"
                          % (where, name))
    for name in fields:
        if name not in ROW_FIELD_NAMES:
            errors.append("%s: unknown field %r" % (where, name))
    return errors


def validate_row(row):
    """Return a list of schema violations; [] means the row is valid."""
    errors = []
    if not isinstance(row, dict):
        return ["row is not a dict"]
    for key in KB_SCHEMA["required_row_keys"]:
        if key not in row:
            errors.append("row missing %r" % key)
    if not isinstance(row.get("fields"), dict):
        return errors + ["row fields is not a dict"]
    where = "%s/%s" % (row.get("provider_id"), row.get("model_id"))
    return errors + _field_errors(where, row["fields"])


def validate_catalog(catalog):
    """Return a list of schema violations; [] means the catalog is valid."""
    if not isinstance(catalog, dict):
        return ["catalog is not a dict"]
    errors = []
    for key in KB_SCHEMA["required_top"]:
        if key not in catalog:
            errors.append("catalog missing %r" % key)
    if catalog.get("format") != KB_FORMAT_ID:
        errors.append("catalog format %r is not %r"
                      % (catalog.get("format"), KB_FORMAT_ID))
    models = catalog.get("models")
    if not isinstance(models, list):
        return errors + ["catalog models is not a list"]
    seen = set()
    for row in models:
        errors.extend(validate_row(row))
        if isinstance(row, dict):
            pair = (row.get("provider_id"), row.get("model_id"))
            if pair in seen:
                errors.append("duplicate row %s/%s" % pair)
            seen.add(pair)
    return errors


def _price_or_null(field):
    value = field["value"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _text_or_unknown(field):
    value = field["value"]
    if isinstance(value, str) and value:
        return value
    return UNKNOWN


def to_pricing_snapshot(row, pricing_snapshot_id, source, created_at):
    """Bridge one KB row to a K13 PricingSnapshot dict.

    Unknown prices stay null; the snapshot hash covers the price fields
    so historical cost reproduces from the referenced snapshot.
    """
    fields = row["fields"]
    effective = fields["price_effective_at"]["value"]
    if not isinstance(effective, str) or not effective:
        effective = UNKNOWN
    payload = {
        "pricing_snapshot_id": pricing_snapshot_id,
        "provider_id": row["provider_id"],
        "model_id": row["model_id"],
        "currency": _text_or_unknown(fields["currency"]),
        "effective_at": effective,
        "source": source,
        "input_token_price": _price_or_null(fields["input_token_price"]),
        "output_token_price": _price_or_null(fields["output_token_price"]),
        "cached_token_price": _price_or_null(
            fields["cached_token_price"]),
        "reasoning_token_price": _price_or_null(
            fields["reasoning_token_price"]),
        "request_price": _price_or_null(fields["request_price"]),
        "other_rules": [],
        "created_at": created_at,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"),
                   default=str).encode("utf-8")).hexdigest()
    payload["hash"] = digest
    assert set(payload.keys()) == set(SNAPSHOT_FIELD_NAMES)
    return payload


def save_catalog(catalog, path):
    """Write a validated catalog atomically with os.replace."""
    errors = validate_catalog(catalog)
    if errors:
        raise ValueError("refusing to save invalid catalog: %s" % errors)
    text = json.dumps(catalog, indent=2, sort_keys=True) + "\n"
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def load_catalog(path):
    """Load and schema-validate a catalog file."""
    with open(path, "r", encoding="utf-8") as handle:
        catalog = json.load(handle)
    errors = validate_catalog(catalog)
    if errors:
        raise ValueError("invalid catalog at %r: %s" % (path, errors))
    return catalog


def _seed_row(provider_id, model_id):
    return make_model_row(provider_id, model_id)


SEED_CATALOG = make_catalog(
    [_seed_row("openai", "gpt-4o"),
     _seed_row("openai", "gpt-4o-mini"),
     _seed_row("meta", "muse-spark-1.3-contributor"),
     _seed_row("anthropic", "claude-haiku-4-5")],
    kb_version=1,
    updated_at="2026-10-26",
    change_log=[{"version": 1, "at": "2026-10-26",
                 "summary": "shipped seed; spec fields UNKNOWN until a "
                            "sourced in-app update enriches them",
                 "source": "shipped-seed",
                 "providers": ["openai", "meta", "anthropic"],
                 "changes": [], "cost_state": "UNAVAILABLE"}],
    sources=[],
)


# --- server-side bound catalog (D8/D14-kb) -----------------------------------
#
# Zero-arg/one-arg KB facades (loader.read_kb, loader.resolve_exact_id,
# loader.propose_update, backend get_kb_status/get_models/apply_proposal)
# read through this registry instead of taking a catalog argument.
# Tests and choice-point code keep passing catalogs explicitly; only the
# frozen facades use the binding.

_BOUND_CATALOG = None


def bind_catalog(catalog):
    """Bind the server-side catalog every KB facade reads through.

    Invalid catalogs are refused. The input is deep-copied, so later
    caller mutation cannot corrupt the bound copy.
    """
    errors = validate_catalog(catalog)
    if errors:
        raise ValueError("refusing to bind invalid catalog: %s" % errors)
    global _BOUND_CATALOG
    _BOUND_CATALOG = copy.deepcopy(catalog)
    return _BOUND_CATALOG


def bound_catalog():
    """Return the bound catalog, or SEED_CATALOG when nothing is bound.

    The live object is returned (never a copy): readers must not mutate
    it; replace it through bind_catalog.
    """
    if _BOUND_CATALOG is None:
        return SEED_CATALOG
    return _BOUND_CATALOG


_KB_PERSIST_FILENAME = "kb_catalog.json"
_PERSIST_DIR = None


def set_persist_dir(store_dir):
    """Set the KB persist dir (app store); None disables persistence."""
    global _PERSIST_DIR
    _PERSIST_DIR = str(store_dir) if store_dir else None
    return _PERSIST_DIR


def persist_path():
    """Persisted catalog path, or None when persistence is disabled."""
    if not _PERSIST_DIR:
        return None
    return os.path.join(_PERSIST_DIR, _KB_PERSIST_FILENAME)


def persist_bound():
    """Save the bound catalog to the persist path (never raises)."""
    path = persist_path()
    if not path:
        return None
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    save_catalog(bound_catalog(), path)
    return path


def load_persisted():
    """Bind the persisted catalog when present; None when absent/invalid.

    Seed backfill: a persisted catalog that lacks a shipped seed row
    gains it (UNKNOWN fields) at load; rows already present are never
    overwritten, and the backfilled catalog is saved back.
    """
    path = persist_path()
    if not path:
        return None
    catalog = load_catalog(path)
    known = {(row.get("provider_id"), row.get("model_id"))
             for row in catalog.get("models", [])
             if isinstance(row, dict)}
    missing = [copy.deepcopy(row)
               for row in SEED_CATALOG.get("models", [])
               if (row.get("provider_id"), row.get("model_id")) not in known]
    if not missing:
        return bind_catalog(catalog)
    catalog["models"].extend(missing)
    errors = validate_catalog(catalog)
    if errors:
        raise ValueError("invalid catalog at %r: %s" % (path, errors))
    bound = bind_catalog(catalog)
    try:
        persist_bound()
    except Exception:
        pass
    return bound
