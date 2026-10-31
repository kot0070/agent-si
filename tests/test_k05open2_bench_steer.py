"""K05OPEN2 bench-steer picker lane (M-P4-129): RED->GREEN proof.

The picker prefers the split (cloud vs local) supported by recorded bench
rows for the rule's case (rule_id == case_id) and honours deeper BenchLevels
(Standard beats Quick, Deep beats Standard). Within one level the majority
split wins; ties break by the latest row. Order without evidence is the
existing first-eligible order.

Bench input discipline: the REAL bench_runner store is used (real RunHandle /
RunProgress / BenchResultRow types, picker reads via the public
run_result_rows + list_run_ids). bench_runner exposes no public row writer,
so this fixture seeds the real in-memory store directly (test-only loopback
models) and the picker never writes it. Keys are distinctive and removed in
teardown, so no state leaks to other test files.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import copy

import pytest

from agent_si.local import bench_runner as _bench_runner
from agent_si.local.bench_protocol import (
    BenchLevel,
    BenchResultRow,
    HardwareProfile,
    ResultKind,
    build_result_row,
)
from agent_si.local.bench_runner import RunHandle, RunProgress
from agent_si.model_kb import SEED_CATALOG, bind_catalog, bound_catalog
from agent_si.model_kb import kb as _kb
from agent_si.model_kb import loader as _loader
from agent_si.model_kb.kb_reader import CatalogKbReader
from agent_si.providers.registry import ProviderRegistry
from agent_si.routing.picker import DOWN, PICKED, PickResult, pick

LOOPBACK = "http://127.0.0.1:9/v1"

_HW = HardwareProfile(gpu_vendor="CPU-only", gpu_model=None, vram_mb=None,
                      ram_mb=8192, cpu_only=True)


@pytest.fixture()
def reader():
    """Real CatalogKbReader over the real shipped seed catalog."""
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


def _seed_run(run_id, model_id, level):
    """Seed one run into the REAL bench store (fixture setup, test data)."""
    assert run_id not in _bench_runner._RUNS, "store polluted: %r" % run_id
    _bench_runner._RUNS[run_id] = RunHandle(
        run_id=run_id, model_id=model_id, level=level)
    _bench_runner._PROGRESS[run_id] = RunProgress(
        run_id=run_id, done_cases=0, total_cases=1, paused=False,
        stopped=True)
    _bench_runner._RUN_ROWS[run_id] = []


def _seed_row(run_id, case_id, model_id):
    """Append one real result row to a seeded run (fixture setup)."""
    assert run_id in _bench_runner._RUN_ROWS, "unknown seed run: %r" % run_id
    _bench_runner._RUN_ROWS[run_id].append(
        build_result_row(case_id, ResultKind.MEASURED, model_id, _HW))


@pytest.fixture()
def bench_store():
    """Seeded bench runs; teardown removes exactly the keys this file added."""
    added = []

    def _add(run_id, model_id, level):
        _seed_run(run_id, model_id, level)
        added.append(run_id)
        return run_id

    try:
        yield _add
    finally:
        for run_id in added:
            _bench_runner._RUNS.pop(run_id, None)
            _bench_runner._PROGRESS.pop(run_id, None)
            _bench_runner._RUN_ROWS.pop(run_id, None)


def _cloud_first_rule(rule_id, local_model, cloud_model):
    """Cloud candidate listed first: legacy first-eligible order picks cloud."""
    return {"rule_id": rule_id, "candidates": [
        {"script": "cloud-summarize", "parameters": {"depth": 1},
         "requires": {"provider_type": "cloud", "model": cloud_model}},
        {"script": "local-summarize", "parameters": {"depth": 1},
         "requires": {"provider_type": "local", "model": local_model}}]}


def test_bench_steer_prefers_supported_local_split(reader, bench_store):
    """(a) rows for the case support local: local wins over listed-first cloud."""
    local = _real_row("openai", "gpt-4o")
    cloud = _real_row("openai", "gpt-4o-mini")
    reg = _registry(local["model_id"], cloud["model_id"])
    bench_store("k05open2-steer-a", local["model_id"], BenchLevel.Quick)
    _seed_row("k05open2-steer-a", "steer-case-a", local["model_id"])
    res = pick(_cloud_first_rule("steer-case-a", local["model_id"],
                                 cloud["model_id"]), reg, reader)
    assert res.status == PICKED
    assert res.script == "local-summarize"
    assert res.model == local["model_id"]
    assert "bench" in res.reason


def test_bench_steer_deeper_level_overrides(reader, bench_store):
    """(b) one Standard row for local beats two Quick rows for cloud."""
    local = _real_row("openai", "gpt-4o")
    cloud = _real_row("openai", "gpt-4o-mini")
    reg = _registry(local["model_id"], cloud["model_id"])
    bench_store("k05open2-steer-bq", cloud["model_id"], BenchLevel.Quick)
    _seed_row("k05open2-steer-bq", "steer-case-b", cloud["model_id"])
    _seed_row("k05open2-steer-bq", "steer-case-b", cloud["model_id"])
    bench_store("k05open2-steer-bs", local["model_id"], BenchLevel.Standard)
    _seed_row("k05open2-steer-bs", "steer-case-b", local["model_id"])
    res = pick(_cloud_first_rule("steer-case-b", local["model_id"],
                                 cloud["model_id"]), reg, reader)
    assert res.status == PICKED
    assert res.script == "local-summarize"
    assert res.model == local["model_id"]
    assert "Standard" in res.reason


def test_bench_steer_same_level_majority_wins(reader, bench_store):
    """Same level: 2 cloud rows beat 1 local row even with local listed first."""
    local = _real_row("openai", "gpt-4o")
    cloud = _real_row("openai", "gpt-4o-mini")
    reg = _registry(local["model_id"], cloud["model_id"])
    bench_store("k05open2-steer-c", local["model_id"], BenchLevel.Quick)
    _seed_row("k05open2-steer-c", "steer-case-c", cloud["model_id"])
    _seed_row("k05open2-steer-c", "steer-case-c", cloud["model_id"])
    _seed_row("k05open2-steer-c", "steer-case-c", local["model_id"])
    rule = {"rule_id": "steer-case-c", "candidates": [
        {"script": "local-summarize", "parameters": {},
         "requires": {"provider_type": "local",
                      "model": local["model_id"]}},
        {"script": "cloud-summarize", "parameters": {},
         "requires": {"provider_type": "cloud",
                      "model": cloud["model_id"]}}]}
    res = pick(rule, reg, reader)
    assert res.status == PICKED
    assert res.script == "cloud-summarize"
    assert res.model == cloud["model_id"]


def test_bench_steer_same_level_tie_latest_wins(reader, bench_store):
    """Same level, 1-1 tie: the latest row's split (cloud) wins deterministically."""
    local = _real_row("openai", "gpt-4o")
    cloud = _real_row("openai", "gpt-4o-mini")
    reg = _registry(local["model_id"], cloud["model_id"])
    bench_store("k05open2-steer-d", local["model_id"], BenchLevel.Quick)
    _seed_row("k05open2-steer-d", "steer-case-d", local["model_id"])
    _seed_row("k05open2-steer-d", "steer-case-d", cloud["model_id"])
    rule = {"rule_id": "steer-case-d", "candidates": [
        {"script": "local-summarize", "parameters": {},
         "requires": {"provider_type": "local",
                      "model": local["model_id"]}},
        {"script": "cloud-summarize", "parameters": {},
         "requires": {"provider_type": "cloud",
                      "model": cloud["model_id"]}}]}
    first = pick(rule, reg, reader)
    second = pick(rule, reg, reader)
    assert first.status == PICKED
    assert first.script == "cloud-summarize"
    assert second.script == first.script
    assert second.reason == first.reason


def test_bench_steer_other_case_rows_do_not_steer(reader, bench_store):
    """Rows for another case leave the legacy first-eligible order alone."""
    local = _real_row("openai", "gpt-4o")
    cloud = _real_row("openai", "gpt-4o-mini")
    reg = _registry(local["model_id"], cloud["model_id"])
    bench_store("k05open2-steer-e", local["model_id"], BenchLevel.Deep)
    _seed_row("k05open2-steer-e", "steer-case-other", local["model_id"])
    res = pick(_cloud_first_rule("steer-case-e", local["model_id"],
                                 cloud["model_id"]), reg, reader)
    assert res.status == PICKED
    assert res.script == "cloud-summarize"
    assert "bench" not in res.reason
