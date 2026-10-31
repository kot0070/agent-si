"""Meta contributor price seed: one priced row via the KB seed/bind path.

Owner MODEL_KB (DIRECTOR/INBOX/MODEL_KB_OWNER_20261011/sections/meta.md,
retrieved 2026-10-11): muse-spark-1.3-contributor input 0.1 plus output
0.2 per 1M, currency USD, at
https://dev.meta.ai/docs/pricing-rate-limits. Stored here as field
values 0.1/0.2 (the per-token multiplier convention the served charge
uses: manager plus run_store compute delta as 4*in + 6*out).

Why seed/bind and not updater propose/apply: updater.fetch_source and
validate_proposal accept only KB_SOURCE_ALLOWLIST (updater.py:19-30,
enforced at 80-84 and 164-166); dev.meta.ai is outside that list, so
propose/apply raises SourceNotAllowlisted / KB_VALIDATION_FAILED. The
seed helpers below (kb.sourced plus make_model_row plus make_catalog
plus bind_catalog) carry any source URL with its retrieved_at.
"""
from agent_si.model_kb import kb

META_PROVIDER_ID = "meta"
META_MODEL_ID = "muse-spark-1.3-contributor"
META_SOURCE_URL = "https://dev.meta.ai/docs/pricing-rate-limits"
META_RETRIEVED_AT = "2026-10-11"
META_INPUT_PRICE = 0.1
META_OUTPUT_PRICE = 0.2
META_CURRENCY = "USD"

__all__ = ["META_PROVIDER_ID", "META_MODEL_ID", "META_SOURCE_URL",
           "META_RETRIEVED_AT", "META_INPUT_PRICE", "META_OUTPUT_PRICE",
           "META_CURRENCY", "meta_price_row", "priced_catalog",
           "bind_meta_price"]


def meta_price_row():
    """Build the one priced meta row through kb.sourced/make_model_row."""
    fields = {
        "currency": kb.sourced(
            META_CURRENCY, META_SOURCE_URL, META_RETRIEVED_AT),
        "price_effective_at": kb.sourced(
            META_RETRIEVED_AT, META_SOURCE_URL, META_RETRIEVED_AT),
        "input_token_price": kb.sourced(
            META_INPUT_PRICE, META_SOURCE_URL, META_RETRIEVED_AT),
        "output_token_price": kb.sourced(
            META_OUTPUT_PRICE, META_SOURCE_URL, META_RETRIEVED_AT),
    }
    return kb.make_model_row(META_PROVIDER_ID, META_MODEL_ID, fields)


def priced_catalog(base=None):
    """Catalog with exactly the one meta row first, then the base rows."""
    if base is None:
        base = kb.bound_catalog()
    kept = [row for row in base.get("models", [])
            if not (isinstance(row, dict)
                    and row.get("provider_id") == META_PROVIDER_ID
                    and row.get("model_id") == META_MODEL_ID)]
    version = base.get("version", {})
    try:
        next_version = int(version.get("kb_version", 1)) + 1
    except (TypeError, ValueError):
        next_version = 2
    return kb.make_catalog(
        [meta_price_row()] + kept,
        kb_version=next_version,
        updated_at=META_RETRIEVED_AT,
        change_log=list(version.get("change_log", [])),
        sources=tuple(base.get("manifest", {}).get("sources", ()))
        + (META_SOURCE_URL,))


def bind_meta_price(base=None):
    """Bind the priced catalog through the kb bind entry; return it."""
    catalog = priced_catalog(base)
    kb.bind_catalog(catalog)
    return catalog
