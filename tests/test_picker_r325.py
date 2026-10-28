"""K04 R-325: rule-driven script picker behaviour tests (REAL inputs only).

The picker chooses a script plus parameters per rule from the live
ProviderRegistry plus the real bound-catalog KB rows. No canned product
code: provider/model ids come from real bound-catalog seed rows, the
registry is a real ProviderRegistry, and facts come from
CatalogKbReader over the real bound catalog.
"""

import copy
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from agent_si.model_kb import SEED_CATALOG, bind_catalog, bound_catalog
from agent_si.model_kb import kb as _kb
from agent_si.model_kb import loader as _loader
from agent_si.model_kb.kb_reader import CatalogKbReader
from agent_si.providers.registry import ProviderRegistry
from agent_si.routing.picker import DOWN, PICKED, PickResult, pick, run_rule

LOOPBACK = "http://127.0.0.1:9/v1"


@pytest.fixture()
def reader():
    """Real CatalogKbReader over the real shipped seed catalog.

    Binds the real SEED_CATALOG for the test and restores whatever was
    bound before, so no global state leaks between test files.
    """
    saved = copy.deepcopy(_kb.bound_catalog())
    bind_catalog(SEED_CATALOG)
    try:
        yield CatalogKbReader()
    finally:
        bind_catalog(saved)


def _real_row(provider_id, model_id):
    """One real bound-catalog row; rules are built from these rows."""
    row = _loader.find_row(bound_catalog(), provider_id, model_id)
    assert row is not None, "real seed row missing: %s/%s" % (
        provider_id, model_id)
    return row


def _registry(local_model, cloud_model):
    """Real registry with one routing-eligible local plus one cloud."""
    reg = ProviderRegistry()
    reg.register_instance({
        "provider": "openai",
        "model": local_model,
        "instance_id": "local-1",
        "provider_type": "local",
        "base_url": LOOPBACK,
        "credential_ref": {"secret_id": "ref-local-1",
                           "provider_id": "openai"},
    })
    reg.register_instance({
        "provider": "openai",
        "model": cloud_model,
        "instance_id": "default",
        "provider_type": "cloud",
        "base_url": LOOPBACK,
        "credential_ref": {"secret_id": "ref-cloud-1",
                           "provider_id": "openai"},
    })
    reg.record_credential_evidence("openai", "local-1", "fake-probe-local")
    reg.record_credential_evidence("openai", "default", "fake-probe-cloud")
    reg.record_health("openai", "local-1", "ONLINE")
    reg.record_health("openai", "default", "ONLINE")
    return reg


def test_pick_per_rule_local_picks_local_script_verbatim(reader):
    local = _real_row("openai", "gpt-4o")
    cloud = _real_row("openai", "gpt-4o-mini")
    reg = _registry(local["model_id"], cloud["model_id"])
    rule = {"rule_id": "watch-local", "candidates": [
        {"script": "local-summarize",
         "parameters": {"depth": 2, "format": "text"},
         "requires": {"provider_type": "local",
                      "model": local["model_id"]}}]}
    res = pick(rule, reg, reader)
    assert isinstance(res, PickResult)
    assert res.status == PICKED == "PICKED"
    assert res.rule_id == "watch-local"
    assert res.script == "local-summarize"
    assert res.parameters == {"depth": 2, "format": "text"}
    assert res.provider_id == "openai"
    assert res.model == local["model_id"]


def test_ordered_candidates_fall_through_to_later_eligible(reader):
    local = _real_row("openai", "gpt-4o")
    cloud = _real_row("openai", "gpt-4o-mini")
    reg = _registry(local["model_id"], cloud["model_id"])
    rule = {"rule_id": "watch-fallback", "candidates": [
        {"script": "never-picked",
         "parameters": {},
         "requires": {"capability": "text"}},
        {"script": "local-summarize",
         "parameters": {"depth": 1},
         "requires": {"provider_type": "local"}}]}
    res = pick(rule, reg, reader)
    assert res.status == PICKED
    assert res.script == "local-summarize"
    assert res.parameters == {"depth": 1}


def test_none_eligible_gives_down_and_seam_never_called(reader):
    local = _real_row("openai", "gpt-4o")
    cloud = _real_row("openai", "gpt-4o-mini")
    reg = _registry(local["model_id"], cloud["model_id"])
    rule = {"rule_id": "watch-empty", "candidates": [
        {"script": "nope", "parameters": {},
         "requires": {"capability": "text"}}]}
    res = pick(rule, reg, reader)
    assert res.status == DOWN == "DOWN"
    assert res.script is None
    assert res.parameters == {}
    assert res.provider_id is None
    assert res.model is None
    journal_calls = []
    notify_calls = []
    res2 = run_rule(rule, reg, reader,
                    journal_append=journal_calls.append,
                    notify=notify_calls.append)
    assert res2.status == DOWN
    assert journal_calls == []
    assert notify_calls == []


def test_raising_journal_seam_gives_down_naming_it(reader):
    local = _real_row("openai", "gpt-4o")
    cloud = _real_row("openai", "gpt-4o-mini")
    reg = _registry(local["model_id"], cloud["model_id"])
    rule = {"rule_id": "watch-seam", "candidates": [
        {"script": "local-summarize", "parameters": {},
         "requires": {"provider_type": "local"}}]}

    def _boom(entry):
        raise RuntimeError("fake journal outage")

    notify_calls = []
    res = run_rule(rule, reg, reader, journal_append=_boom,
                   notify=notify_calls.append)
    assert res.status == DOWN
    assert "journal_append" in res.reason
    assert notify_calls == []


def test_raising_notify_seam_gives_down_naming_it(reader):
    local = _real_row("openai", "gpt-4o")
    cloud = _real_row("openai", "gpt-4o-mini")
    reg = _registry(local["model_id"], cloud["model_id"])
    rule = {"rule_id": "watch-seam", "candidates": [
        {"script": "local-summarize", "parameters": {},
         "requires": {"provider_type": "local"}}]}

    def _boom(payload):
        raise RuntimeError("fake notify outage")

    journal_calls = []
    res = run_rule(rule, reg, reader,
                   journal_append=journal_calls.append, notify=_boom)
    assert res.status == DOWN
    assert "notify" in res.reason
    assert len(journal_calls) == 1


def test_forbidden_parameter_key_fails_candidate(reader):
    local = _real_row("openai", "gpt-4o")
    cloud = _real_row("openai", "gpt-4o-mini")
    reg = _registry(local["model_id"], cloud["model_id"])
    rule = {"rule_id": "watch-token", "candidates": [
        {"script": "local-summarize",
         "parameters": {"session_token": "fake-secret-value"},
         "requires": {"provider_type": "local"}},
        {"script": "api-key-script",
         "parameters": {"api_key": "fake-secret-value"},
         "requires": {"provider_type": "local"}}]}
    res = pick(rule, reg, reader)
    assert res.status == DOWN
    assert res.script is None
    assert "fake-secret-value" not in res.reason


def test_unknown_keys_error(reader):
    local = _real_row("openai", "gpt-4o")
    cloud = _real_row("openai", "gpt-4o-mini")
    reg = _registry(local["model_id"], cloud["model_id"])
    base = {"script": "s", "parameters": {},
            "requires": {"provider_type": "local"}}
    with pytest.raises(ValueError):
        pick({"rule_id": "r", "candidates": [dict(
            base, requires={"bogus": 1})]}, reg, reader)
    with pytest.raises(ValueError):
        pick({"rule_id": "r", "candidates": [dict(base, extra=1)]},
             reg, reader)
    with pytest.raises(ValueError):
        pick({"rule_id": "r", "candidates": [base], "extra": 1},
             reg, reader)
    with pytest.raises(ValueError):
        pick({"rule_id": "", "candidates": [base]}, reg, reader)
    with pytest.raises(ValueError):
        pick({"rule_id": "r", "candidates": []}, reg, reader)
    with pytest.raises(ValueError):
        pick({"rule_id": "r", "candidates": [{"script": ""}]},
             reg, reader)


def test_picked_calls_journal_and_notify_exactly_once(reader):
    local = _real_row("openai", "gpt-4o")
    cloud = _real_row("openai", "gpt-4o-mini")
    reg = _registry(local["model_id"], cloud["model_id"])
    rule = {"rule_id": "watch-local", "candidates": [
        {"script": "local-summarize",
         "parameters": {"depth": 2},
         "requires": {"provider_type": "local",
                      "model": local["model_id"]}}]}
    journal_calls = []
    notify_calls = []
    res = run_rule(rule, reg, reader,
                   journal_append=journal_calls.append,
                   notify=notify_calls.append)
    assert res.status == PICKED
    assert len(journal_calls) == 1
    assert len(notify_calls) == 1
    entry = journal_calls[0]
    assert set(entry) == {"rule_id", "status", "script", "provider_id",
                          "model", "parameters", "reason"}
    assert entry["rule_id"] == "watch-local"
    assert entry["status"] == PICKED
    assert entry["script"] == "local-summarize"
    assert entry["provider_id"] == "openai"
    assert entry["model"] == local["model_id"]
    assert entry["parameters"] == {"depth": 2}
    payload = notify_calls[0]
    assert set(payload) == {"rule_id", "status", "script", "provider_id",
                            "model", "reason"}
    assert payload["rule_id"] == "watch-local"
    assert payload["script"] == "local-summarize"
