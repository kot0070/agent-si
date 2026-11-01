"""K04H served proof: 8 PARTIAL-open model-KB rows served by the real seam.

Row map (row -> route -> test):
  M-R-MODEL-KB          kb.make_catalog/validate_catalog/bind_catalog/bound_catalog
                        -> test_k04h_model_kb_named_format_served
  M-R-LEFTOVER          updater.find_leftover_keys
                        -> test_k04h_leftover_key_finder_served
  M-R-SIMPLE            loader.candidates_for_auto/offer_one_click
                        -> test_k04h_simple_auto_run_served
  M-R-UX-13             kb_reader.CatalogKbReader.models + loader.lookup/bridge
                        -> test_k04h_model_store_search_groups_toggle_served
  B0B-UNCOVERED_ARCH-164  updater.write_metric_record/MetricState + apply_proposal
                        -> test_k04h_health_measured_vs_unavailable_served
  B0B-UNCOVERED_ARCH-527  loader.read_kb/resolve_exact_id + kb_reader.CatalogKbReader.facts
                        -> test_k04h_models_view_contracts_plus_health_served
  B0B-UNCOVERED_BP05-14   loader.bridge/resolve_pool/read_back
                        -> test_k04h_provider_registry_descriptors_health_usage_served
  B0B-BP07-44           loader.find_row + kb.to_pricing_snapshot
                        -> test_k04h_local_identity_verification_served

Every test drives REAL product code under src/agent_si/model_kb/.
Fixtures live only in this file. No product file is changed by this lane.
"""
import copy
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.model_kb import kb, kb_reader, loader, updater

DOC = "https://example.com/kb-doc"
DAY = "2026-10-01"
SRC_URL = "https://platform.openai.com/docs/models"


def _sourced_row(provider_id="openai", model_id="gpt-4o", values=None,
                 source=DOC, day=DAY):
    fields = {}
    for name in kb.ROW_FIELD_NAMES:
        if name == "source_links":
            fields[name] = kb.sourced([source], source, day)
        elif values and name in values:
            fields[name] = kb.sourced(values[name], source, day)
        else:
            fields[name] = kb.sourced("sample-%s" % name, source, day)
    return kb.make_model_row(provider_id, model_id, fields)


def _catalog(rows=None, version=3):
    if rows is None:
        rows = [_sourced_row()]
    return kb.make_catalog(rows, kb_version=version, updated_at=DAY)


def _snapshot(sid="snap-1", pid="openai", mid="gpt-4o"):
    return {
        "pricing_snapshot_id": sid, "provider_id": pid, "model_id": mid,
        "currency": "USD", "effective_at": DAY,
        "source": "https://example.com/prices",
        "input_token_price": 0.000005, "output_token_price": 0.000015,
        "cached_token_price": None, "reasoning_token_price": None,
        "request_price": None, "other_rules": [], "created_at": DAY,
        "hash": "abc123",
    }


def _bind(catalog):
    before = copy.deepcopy(kb.bound_catalog())
    kb.bind_catalog(catalog)
    return before


def _restore(before):
    kb.bind_catalog(before)


def test_k04h_model_kb_named_format_served():
    """M-R-MODEL-KB via kb.make_catalog/validate_catalog/bind_catalog."""
    rows = [_sourced_row("openai", "gpt-4o"),
            _sourced_row("openai", "gpt-4o-mini")]
    catalog = kb.make_catalog(rows, kb_version=3, updated_at=DAY)
    assert kb.KB_FORMAT_ID == "p17ub-kb/1"
    assert catalog["format"] == "p17ub-kb/1"
    assert set(catalog) == {"format", "manifest", "version", "models"}
    assert catalog["manifest"]["format"] == "p17ub-kb/1"
    assert catalog["version"]["kb_version"] == 3
    assert kb.validate_catalog(catalog) == []
    before = _bind(catalog)
    try:
        live = kb.bound_catalog()
        assert live["format"] == "p17ub-kb/1"
        assert len(live["models"]) == 2
    finally:
        _restore(before)


def test_k04h_leftover_key_finder_served():
    """M-R-LEFTOVER via updater.find_leftover_keys (names only, no values)."""
    store = {"own-key-a": "SECRET-A", "own-key-b": "SECRET-B"}
    assert updater.find_leftover_keys(store) == ["own-key-a", "own-key-b"]
    journal = []
    confirmed = "own-key-a"
    assert confirmed in updater.find_leftover_keys(store)
    del store[confirmed]
    journal.append({"deleted": confirmed, "at": DAY})
    assert updater.find_leftover_keys(store) == ["own-key-b"]
    assert journal == [{"deleted": "own-key-a", "at": DAY}]
    for name in updater.find_leftover_keys(store):
        assert "SECRET" not in name


def test_k04h_simple_auto_run_served():
    """M-R-SIMPLE via loader.candidates_for_auto/offer_one_click + reason."""
    rows = [
        _sourced_row("openai", "gpt-4o", {
            "modalities": "text", "tool_calling": "yes supported",
            "reasoning": "yes advanced", "best_for": "coding agents",
            "purpose": "software engineering", "cost_tier": "low"}),
        _sourced_row("other", "model-x", {
            "modalities": "text", "tool_calling": "yes supported",
            "reasoning": "yes advanced", "best_for": "coding agents",
            "purpose": "software engineering", "cost_tier": "low"}),
    ]
    catalog = _catalog(rows)
    auto = loader.candidates_for_auto(catalog, ["openai"])
    assert [c["model_id"] for c in auto["candidates"]] == ["gpt-4o"]
    assert auto["excluded_unconnected"] == ["other"]
    assert isinstance(auto["reason"], str) and auto["reason"]
    offer = loader.offer_one_click(catalog, ["openai"])
    assert offer["offer"]["model_id"] == "gpt-4o"
    assert offer["offer"]["connected"] is True
    assert isinstance(offer["reason"], str) and offer["reason"]


def test_k04h_model_store_search_groups_toggle_served():
    """M-R-UX-13 via kb_reader.models (groups) + loader.lookup/bridge."""
    rows = [_sourced_row("openai", "gpt-4o"),
            _sourced_row("openai", "gpt-4o-mini"),
            _sourced_row("other", "model-x")]
    before = _bind(_catalog(rows))
    try:
        group = kb_reader.CatalogKbReader().models(provider="openai")
        assert sorted(f.model for f in group) == ["gpt-4o", "gpt-4o-mini"]
        hit = loader.lookup(kb.bound_catalog(), "openai", "gpt-4o")
        assert hit["found"] is True
        assert hit["kb_status"] == loader.IN_BASE
        assert hit["row"]["model_id"] == "gpt-4o"
        miss = loader.lookup(kb.bound_catalog(), "openai", "no-such-model")
        assert miss["found"] is False
        assert miss["kb_status"] == loader.NOT_IN_BASE
        bridged = loader.bridge(
            kb.bound_catalog(), "openai", "gpt-4o",
            snapshots=[_snapshot()],
            local_tags={("openai", "gpt-4o"): ["local-tag"]})
        assert bridged["row"]["model_id"] == "gpt-4o"
        assert bridged["pricing_snapshot"]["pricing_snapshot_id"] == "snap-1"
        assert bridged["local_tags"] == ["local-tag"]
    finally:
        _restore(before)


def test_k04h_health_measured_vs_unavailable_served():
    """ARCH-164 via updater.write_metric_record + apply_proposal cost_state."""
    measured = updater.write_metric_record(
        "m-1", "p", "t", "r", "probe_ok", 12.5, "ms",
        updater.MetricState.MEASURED, "probe", DAY)
    assert measured["state"] == "MEASURED"
    assert measured["value"] == 12.5
    try:
        updater.write_metric_record(
            "m-2", "p", "t", "r", "probe_cost", 0, "USD",
            updater.MetricState.UNAVAILABLE, "probe", DAY)
        assert False, "UNAVAILABLE cost must never read zero"
    except updater.MetricWriteError:
        pass
    catalog = _catalog()
    fetched = json.dumps({"models": [{
        "provider_id": "openai", "model_id": "gpt-4o",
        "fields": {"purpose": "served purpose"}}]})
    proposal = updater.propose_update(catalog, SRC_URL, fetched, DAY)
    assert proposal["changes"], "fetched purpose differs from the sample"
    result = updater.apply_proposal(catalog, proposal, user_confirmed=True)
    assert result["cost_state"] == "UNAVAILABLE"
    assert result["metric"] is None
    assert result["version"] == 4


def test_k04h_models_view_contracts_plus_health_served():
    """ARCH-527 via loader.read_kb/resolve_exact_id + reader.facts."""
    rows = [_sourced_row("openai", "gpt-4o",
                         {"price_effective_at": "2026-10-01"})]
    before = _bind(_catalog(rows))
    try:
        contracts = loader.read_kb(["openai"])
        assert [(c["provider_id"], c["model_id"]) for c in contracts] == [
            ("openai", "gpt-4o")]
        assert set(contracts[0]) == {"provider_id", "model_id", "fields"}
        facts = kb_reader.CatalogKbReader().facts("openai", "gpt-4o")
        assert facts is not None
        assert facts.provider == "openai"
        assert facts.model == "gpt-4o"
        assert kb_reader.CatalogKbReader().facts("openai", "nope") is None
        contract, ref = loader.resolve_exact_id("gpt-4o")
        assert contract["provider_id"] == "openai"
        assert ref == "openai/gpt-4o@2026-10-01"
        try:
            loader.resolve_exact_id("no-such-model")
            assert False, "unknown id must raise LookupError"
        except LookupError:
            pass
    finally:
        _restore(before)


def test_k04h_provider_registry_descriptors_health_usage_served():
    """BP05-14 via loader.bridge/resolve_pool/read_back."""
    rows = [_sourced_row("openai", "gpt-4o"),
            _sourced_row("other", "model-x")]
    catalog = _catalog(rows)
    tags = {("openai", "gpt-4o"): ["local-present"]}
    bridged = loader.bridge(catalog, "openai", "gpt-4o",
                            snapshots=[_snapshot()], local_tags=tags)
    assert bridged["row"]["provider_id"] == "openai"
    assert bridged["row"]["model_id"] == "gpt-4o"
    assert bridged["pricing_snapshot"]["pricing_snapshot_id"] == "snap-1"
    assert bridged["local_tags"] == ["local-present"]
    assert bridged["kb_status"] == loader.IN_BASE
    pool = loader.resolve_pool(
        catalog,
        [{"provider_id": "openai", "model_id": "gpt-4o"},
         {"provider_id": "other", "model_id": "model-x"}],
        ["openai"], snapshots=[_snapshot()], local_tags=tags)
    by_id = {r["model_id"]: r for r in pool["resolutions"]}
    assert by_id["gpt-4o"]["connected"] is True
    assert by_id["gpt-4o"]["kb_status"] == loader.IN_BASE
    assert by_id["model-x"]["connected"] is False
    back = loader.read_back(catalog, "openai", "gpt-4o", ["openai"],
                            snapshots=[_snapshot()], local_tags=tags)
    assert back["mode"] == "PINNED"
    assert back["found"] is True
    assert back["connected"] is True


def test_k04h_local_identity_verification_served():
    """BP07-44 via loader.find_row (verbatim) + kb.to_pricing_snapshot."""
    catalog = _catalog([_sourced_row("openai", "gpt-4o")])
    assert loader.find_row(catalog, "openai", "gpt-4o")["model_id"] == "gpt-4o"
    assert loader.find_row(catalog, "openai", "GPT-4O") is None
    assert loader.find_row(catalog, "openai", " gpt-4o") is None
    assert loader.find_row(catalog, "other", "gpt-4o") is None
    bridged = loader.bridge(
        catalog, "openai", "gpt-4o",
        local_tags={("openai", "gpt-4o"): ["local-tag-v1"]})
    assert bridged["local_tags"] == ["local-tag-v1"]
    row = bridged["row"]
    snap_a = kb.to_pricing_snapshot(row, "snap-a", "probe", DAY)
    snap_b = kb.to_pricing_snapshot(row, "snap-a", "probe", DAY)
    assert snap_a["hash"] == snap_b["hash"]
    assert snap_a["provider_id"] == "openai"
    assert snap_a["model_id"] == "gpt-4o"
    assert snap_a["input_token_price"] is None
    assert set(snap_a) == set(kb.SNAPSHOT_FIELD_NAMES)
