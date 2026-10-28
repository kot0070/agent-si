"""K05R3 M-EVID store-side rows: real measurements only, guards, arch rules.

Covers (store-side, via the real store entry points):
- B0B-UNCOVERED_MVP_ACCEPT-175: no MEASURED row without a real import.
- B0B-UNCOVERED_MVP_ACCEPT-223: role-config fields refused as task_class.
- SPEC 37: no SQLite dep, stale never served as current, originals untouched.
- SPEC 36: MEASURED is not ROUTING_ELIGIBLE (data-only tier distinction).
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from agent_si.capability_store import store
from agent_si.capability_store.store import (
    CapabilityEvidenceRecord,
    CapabilityStoreError,
    EvidenceTier,
    FreshnessState,
    get_evidence,
    require_current,
)

_STORE_SRC = Path(store.__file__).read_text(encoding="utf-8")


def _fresh_model(prefix: str = "evid-model") -> str:
    return "%s-%s" % (prefix, uuid.uuid4().hex[:12])


def _measured_row(model_id: str, task_class: str) -> CapabilityEvidenceRecord:
    """One genuinely imported MEASURED row (test-owned fixture values)."""
    return CapabilityEvidenceRecord(
        model_id=model_id,
        task_class=task_class,
        tier=EvidenceTier.MEASURED,
        score=0.71,
        score_type="pass_rate",
        sample_count=17,
        confidence=0.62,
        benchmark_version="test-bench-v3",
        measured_at="2026-10-27T00:00:00+00:00",
        runtime="test-runtime",
        runtime_version="0.0-test",
        environment_fingerprint="test-pc-fingerprint",
        freshness_state=FreshnessState.CURRENT.value,
        evidence_ref="cap:%s:%s:v1" % (model_id, task_class),
        source="test-import",
    )


# --- B0B-UNCOVERED_MVP_ACCEPT-175: no MEASURED row without real measurement ---


def test_unknown_key_returns_no_row():
    model = _fresh_model()
    assert get_evidence(model, "coding-never-imported") is None


def test_unknown_key_registers_nothing():
    model = _fresh_model()
    assert get_evidence(model, "coding-no-side-effect") is None
    assert (model, "coding-no-side-effect") not in store._RECORDS


def test_seeded_default_helper_is_gone():
    assert not hasattr(store, "_default_measured_row")


def test_seeded_literals_gone_from_store_source():
    assert "0.85" not in _STORE_SRC
    assert "sample_count=100" not in _STORE_SRC
    assert "_default_measured_row" not in _STORE_SRC


def test_require_current_unknown_ref_is_refused_not_fabricated():
    model = _fresh_model()
    ref = "cap:%s:coding-unknown:v1" % model
    with pytest.raises(CapabilityStoreError) as exc_info:
        require_current(ref)
    assert exc_info.value.code == "CAPABILITY_UNKNOWN_EVIDENCE_REFUSED"
    assert exc_info.value.code.startswith("CAPABILITY_")
    assert get_evidence(model, "coding-unknown") is None


def test_require_current_garbage_ref_is_refused():
    with pytest.raises(CapabilityStoreError) as exc_info:
        require_current("not-a-stable-evidence-ref")
    assert exc_info.value.code == "CAPABILITY_UNKNOWN_EVIDENCE_REFUSED"


def test_imported_measured_row_is_served():
    model = _fresh_model()
    row = _measured_row(model, "coding-imported")
    store._register_row(row)
    assert get_evidence(model, "coding-imported") is row
    assert require_current(row.evidence_ref) is row


# --- B0B-UNCOVERED_MVP_ACCEPT-223: role config fields are not task classes ---

_ROLE_CONFIG_NAMES = [
    "endpoint_url",
    "model_id",
    "permission_scope",
    "local_only_mode",
    "project_key",
    "capability_evidence",
    "title",
    "purpose",
    "needItNow",
    "settings.localAi.title",
    "settings.localAi.purpose",
    "settings.localAi.needItNow",
]


@pytest.mark.parametrize("field", _ROLE_CONFIG_NAMES)
def test_role_config_field_refused_as_task_class(field):
    with pytest.raises(CapabilityStoreError) as exc_info:
        get_evidence(_fresh_model(), field)
    assert exc_info.value.code == "CAPABILITY_ROLE_CONFIG_AS_TASK_CLASS_REFUSED"
    assert exc_info.value.code.startswith("CAPABILITY_")


@pytest.mark.parametrize("field", _ROLE_CONFIG_NAMES)
def test_role_config_field_refused_in_stable_ref(field):
    ref = "cap:%s:%s:v1" % (_fresh_model(), field)
    with pytest.raises(CapabilityStoreError) as exc_info:
        require_current(ref)
    assert exc_info.value.code == "CAPABILITY_ROLE_CONFIG_AS_TASK_CLASS_REFUSED"


def test_genuine_task_class_still_accepted():
    assert get_evidence(_fresh_model(), "coding") is None


# --- SPEC 37: no SQLite dep, external analysis, original unmodified ---


def test_store_source_has_no_sqlite_dependency():
    assert "sqlite" not in _STORE_SRC.lower()


def test_store_imports_are_stdlib_and_future_only():
    assert "from dataclasses import" in _STORE_SRC
    assert "from enum import" in _STORE_SRC
    assert "from typing import" in _STORE_SRC
    assert "import sqlite3" not in _STORE_SRC
    assert "sqlite" not in _STORE_SRC.lower()


def test_stale_versioned_copy_never_served_as_current():
    with pytest.raises(CapabilityStoreError) as exc_info:
        require_current("cap:some-model:coding:v1:stale-2")
    assert exc_info.value.code == "CAPABILITY_STALE_AS_CURRENT_REFUSED"


def test_ref_only_registration_never_leaks_into_keyed_reads():
    model = _fresh_model()
    proxy = CapabilityEvidenceRecord(
        model_id=model,
        task_class="notes-versioned",
        tier=EvidenceTier.PROXY,
        score=None,
        score_type=None,
        sample_count=None,
        confidence=None,
        benchmark_version=None,
        measured_at=None,
        runtime=None,
        runtime_version=None,
        environment_fingerprint=None,
        freshness_state=FreshnessState.UNKNOWN.value,
        evidence_ref="cap:proxy:%s:notes:v9" % model,
        source="test-notes",
    )
    store._register_by_ref(proxy)
    assert get_evidence(model, "notes-versioned") is None
    assert require_current(proxy.evidence_ref) is proxy


def test_all_store_error_codes_keep_capability_prefix():
    assert store.ERROR_CODES_K05
    assert all(code.startswith("CAPABILITY_") for code in store.ERROR_CODES_K05)
    assert store.ERROR_CODES_K05_EXTENDED
    assert all(code.startswith("CAPABILITY_") for code in store.ERROR_CODES_K05_EXTENDED)
    assert set(store.ERROR_CODES_K05_EXTENDED) == {
        "CAPABILITY_UNKNOWN_EVIDENCE_REFUSED",
        "CAPABILITY_ROLE_CONFIG_AS_TASK_CLASS_REFUSED",
    }


# --- SPEC 36: MEASURED is not ROUTING_ELIGIBLE (data only, store side) ---


def test_tiers_are_distinct_data_values():
    assert {t.value for t in EvidenceTier} == {"UNKNOWN", "PROXY", "MEASURED"}
    assert EvidenceTier.MEASURED is not EvidenceTier.UNKNOWN
    assert EvidenceTier.MEASURED is not EvidenceTier.PROXY


def test_store_exposes_no_routing_eligibility_verdict():
    assert not hasattr(store, "check_eligibility")
    assert "ROUTING_ELIGIBLE" not in _STORE_SRC
    assert "eligible" not in _STORE_SRC.lower()


def test_measured_row_carries_tier_but_no_routing_mapping():
    model = _fresh_model()
    row = _measured_row(model, "coding-tier-check")
    store._register_row(row)
    served = get_evidence(model, "coding-tier-check")
    assert served is not None and served.tier is EvidenceTier.MEASURED
    assert not hasattr(served, "eligible")
    assert not hasattr(served, "routing_eligible")
