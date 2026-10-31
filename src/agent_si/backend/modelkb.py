"""Model KB route helper: thin production caller on the user path.

Read last-update state overall and per provider, trigger an update
(fetch plus proposal, never an apply), and apply a proposal only on
explicit user confirmation. All KB logic lives in model_kb; this
module only forwards the user-path calls.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from agent_si.model_kb import kb, loader, updater


def get_last_update_overall(catalog):
    """Overall last-update state from the catalog version record."""
    version = catalog.get("version", {})
    log = version.get("change_log", [])
    last = log[-1] if log else {}
    return {"kb_version": version.get("kb_version"),
            "updated_at": version.get("updated_at"),
            "total_changes": sum(len(item.get("changes", []))
                                 for item in log),
            "last_source": last.get("source")}


def get_last_update_per_provider(catalog):
    """Per-provider last-update state from models plus change log."""
    state = {}
    for row in catalog.get("models", []):
        provider = row.get("provider_id")
        state.setdefault(provider, {"models": 0, "last_change_at": None,
                                    "last_source": None})
        state[provider]["models"] += 1
    for item in catalog.get("version", {}).get("change_log", []):
        for provider in item.get("providers", []):
            if provider in state and (
                    state[provider]["last_change_at"] is None
                    or str(item.get("at", "")) >= str(
                        state[provider]["last_change_at"])):
                state[provider]["last_change_at"] = item.get("at")
                state[provider]["last_source"] = item.get("source")
    return state


def trigger_update(catalog, source_url, fetcher, retrieved_at):
    """Fetch a source page and return the proposal; never applies.

    The proposal is staged server-side (see stage_proposal) so the
    apply route can act on the exact text the user reviews.
    """
    fetched_text = updater.fetch_source(source_url, fetcher)
    proposal = updater.propose_update(catalog, source_url, fetched_text,
                                      retrieved_at)
    stage_proposal(proposal)
    return proposal


def apply_update(catalog, proposal, user_confirmed=False, **kwargs):
    """Apply a proposal only with explicit user confirmation."""
    result = updater.apply_proposal(catalog, proposal,
                                    user_confirmed=user_confirmed,
                                    **kwargs)
    catalog.clear()
    catalog.update(result["catalog"])
    return {"applied": result["applied"], "version": result["version"],
            "cost_state": result["cost_state"], "metric": result["metric"]}


def offer_one_click(catalog, connected_provider_ids,
                    snapshots=None, local_tags=None):
    """One-click offer; every choice rule lives in model_kb.loader."""
    return loader.offer_one_click(
        catalog, connected_provider_ids, snapshots=snapshots,
        local_tags=local_tags)


__all__ = ["get_last_update_overall", "get_last_update_per_provider",
           "trigger_update", "apply_update", "offer_one_click",
           "stage_proposal", "get_kb_status", "get_models",
           "apply_proposal", "kb_status", "kb_proposal_apply", "ROUTES",
           "mount"]


# --- server-side staged-proposal registry (D14-kb) -----------------------------

_STAGED_PROPOSALS = {}
_STAGED_COUNTER = 0
_STAGED_LOCK = threading.Lock()


def stage_proposal(proposal):
    """Stage a proposal for the user-confirm path; returns proposal_id.

    Stamps proposal["proposal_id"] and keeps the exact object the user
    reviews, so the apply route cannot act on different text.
    """
    global _STAGED_COUNTER
    with _STAGED_LOCK:
        _STAGED_COUNTER += 1
        proposal_id = "kb-prop-%d" % _STAGED_COUNTER
        proposal["proposal_id"] = proposal_id
        _STAGED_PROPOSALS[proposal_id] = proposal
    return proposal_id


# --- frozen D14-kb facades (exact frozen signatures) ---------------------------
#
# Verified with inspect against routing/interface.py stubs. They read the
# bound catalog (kb.bind_catalog / kb.bound_catalog, SEED_CATALOG until
# bound). All existing functions above keep their shape, so the owned
# tests keep passing unchanged.


def get_kb_status() -> Dict[str, Any]:
    """Frozen 3.7: last-update date overall plus per provider."""
    catalog = kb.bound_catalog()
    return {"overall": get_last_update_overall(catalog),
            "per_provider": get_last_update_per_provider(catalog)}


def get_models(provider_ids: List[str],
               query: Optional[str]) -> List[Dict[str, Any]]:
    """Frozen 3.7: model rows with checkbox state plus search.

    Every bound-catalog row is listed; "selected" is True when the
    row's provider is in provider_ids (checkbox state). query is a
    case-insensitive substring filter over "provider_id model_id";
    None or empty matches everything. Ids in the payload stay verbatim.
    """
    catalog = kb.bound_catalog()
    wanted = set(provider_ids or [])
    needle = query if isinstance(query, str) else ""
    needle = needle.strip().lower()
    rows = []
    for row in catalog.get("models", []):
        provider_id = row.get("provider_id")
        model_id = row.get("model_id")
        if needle and needle not in ("%s %s" % (provider_id,
                                                model_id)).lower():
            continue
        rows.append({"provider_id": provider_id,
                     "model_id": model_id,
                     "selected": provider_id in wanted,
                     "kb_status": loader.IN_BASE,
                     "fields": row.get("fields", {})})
    return rows


def apply_proposal(proposal_id: str,
                   approved_by_user: bool) -> Dict[str, Any]:
    """Frozen 3.7: applies a staged proposal only on explicit approval.

    Raises updater.ConfirmationRequiredError unless approved_by_user is
    True, KeyError for an unknown proposal_id. Applies against the
    bound catalog, rebinds the updated catalog, and drops the staged
    entry (one-shot: the id cannot be applied twice).
    """
    if approved_by_user is not True:
        raise updater.ConfirmationRequiredError(
            "KB proposal apply needs explicit user approval")
    try:
        proposal = _STAGED_PROPOSALS[proposal_id]
    except KeyError:
        raise KeyError("unknown proposal_id %r" % (proposal_id,))
    catalog = kb.bound_catalog()
    result = updater.apply_proposal(catalog, proposal, user_confirmed=True)
    kb.bind_catalog(result["catalog"])
    try:
        kb.persist_bound()
    except Exception:
        pass
    del _STAGED_PROPOSALS[proposal_id]
    return {"proposal_id": proposal_id, "applied": result["applied"],
            "version": result["version"],
            "cost_state": result["cost_state"], "metric": result["metric"]}


# --- D9-kb HTTP surface (pure handlers plus mount) -----------------------------
#
# Same shape as backend.pools_routes: handlers take (ctx, query, body)
# and return (status, payload); ctx is reserved for host wiring (the
# trigger-path fetcher), status/apply read the module registries above.
# Method names are lowercase because hosts expose `.get`/`.post` and
# stdlib dispatch lowercases the verb. NOTE: PR.ROUTES wiring
# (merging these paths into the served app) belongs to the pools-route
# owner; this module only defines the routes.


def kb_status(ctx, query, body):
    """GET /api/v1/kb/status: overall plus per-provider last-update."""
    return 200, get_kb_status()


def kb_proposal_apply(ctx, query, body):
    """POST /api/v1/kb/proposals/apply: staged proposal, approval only."""
    payload = body or {}
    try:
        return 200, apply_proposal(payload.get("proposal_id"),
                                   payload.get("approved_by_user", False))
    except updater.ConfirmationRequiredError as exc:
        return 400, {"error": str(exc),
                     "code": "KB_PROPOSAL_NOT_APPROVED"}
    except updater.ProposalRejectedError as exc:
        return 400, {"error": str(exc), "code": "KB_VALIDATION_FAILED"}
    except KeyError as exc:
        return 404, {"error": "unknown proposal_id: %s" % (
            exc.args[0] if exc.args else exc,)}


ROUTES = (
    ("get", "/api/v1/kb/status", "kb_status", kb_status),
    ("post", "/api/v1/kb/proposals/apply", "kb_proposal_apply",
     kb_proposal_apply),
)


def mount(app, ctx):
    """Register KB routes on a `.get`/`.post` host (framework-agnostic).

    Same shape as backend.pools_routes.mount: the host calls handlers
    as ``handler(query, body)`` where query is a string-keyed mapping
    and body is the parsed JSON object (or None). Returns the app for
    chaining.
    """
    for method, path, _name, fn in ROUTES:
        registrar = getattr(app, method)

        def wrapper(query=None, body=None, _fn=fn):
            return _fn(ctx, query or {}, body)

        registrar(path)(wrapper)
    return app
