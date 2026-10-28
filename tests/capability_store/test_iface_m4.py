"""M4 STEP1 contract test: frozen capability_store surface (RED until impl).

Asserts the frozen names/signatures plus the own-prefix error-code
conditions. Fakes live in this file only; every fake carries FAKE-OF:.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

_WS_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_WS_SRC) not in sys.path:
    sys.path.insert(0, str(_WS_SRC))

from agent_si.capability_store import (
    ERROR_CODES_K05,
    NOT_CONFIGURED,
    CapabilityEvidenceRecord,
    CapabilityStore,
    CapabilityStoreError,
    EvidenceTier,
    FreshnessState,
    adapt_proxy_notes,
    get_evidence,
    import_measured_capability,
    require_current,
)

FAKE_MODEL_ID = "FAKE-OF: fixture model id"
FAKE_TASK_CLASS = "FAKE-OF: fixture task class"
FAKE_SOURCE_REF = "FAKE-OF: fixture benchmark source ref"
FAKE_DEST_REF = "FAKE-OF: fixture capability base dest ref"
# Convention under test: a dest_ref starting with "original:" addresses
# read-only original external data; the import path must refuse the write.
FAKE_ORIGINAL_DEST_REF = "FAKE-OF: fixture read-only original dest ref; original:model_kb/notes"
# Convention under test: an evidence_ref carrying a ":stale" backup marker
# addresses a versioned stale copy; serving it as current must be refused.
FAKE_STALE_REF = "FAKE-OF: fixture stale backup copy ref; backup:v3:stale"

FROZEN_EXPORTS = (
    "ERROR_CODES_K05",
    "NOT_CONFIGURED",
    "CapabilityEvidenceRecord",
    "CapabilityStore",
    "CapabilityStoreError",
    "EvidenceTier",
    "FreshnessState",
    "adapt_proxy_notes",
    "get_evidence",
    "import_measured_capability",
    "require_current",
)


def test_frozen_names_importable() -> None:
    import agent_si.capability_store as package

    for name in FROZEN_EXPORTS:
        assert hasattr(package, name), name


def test_evidence_tier_members() -> None:
    assert {member.value for member in EvidenceTier} == {"UNKNOWN", "PROXY", "MEASURED"}


def test_freshness_state_members() -> None:
    assert {member.value for member in FreshnessState} == {
        "CURRENT",
        "STALE",
        "INCOMPATIBLE",
        "UNKNOWN",
    }


def test_get_evidence_signature() -> None:
    assert list(inspect.signature(get_evidence).parameters) == ["model_id", "task_class"]


def test_require_current_signature() -> None:
    assert list(inspect.signature(require_current).parameters) == ["evidence_ref"]


def test_import_signatures() -> None:
    assert list(inspect.signature(import_measured_capability).parameters) == [
        "source_ref",
        "dest_ref",
    ]
    assert list(inspect.signature(adapt_proxy_notes).parameters) == [
        "source_ref",
        "dest_ref",
    ]


def test_not_configured_status_constant() -> None:
    assert NOT_CONFIGURED == "NOT_CONFIGURED"
    store = CapabilityStore(base_ref=None, status=NOT_CONFIGURED)
    assert store.status == NOT_CONFIGURED


def test_error_codes_own_prefix() -> None:
    assert set(ERROR_CODES_K05) == {
        "CAPABILITY_ORIGINAL_WRITE_REFUSED",
        "CAPABILITY_STALE_AS_CURRENT_REFUSED",
    }
    assert all(code.startswith("CAPABILITY_") for code in ERROR_CODES_K05)


def test_get_evidence_serves_row_with_ref() -> None:
    record = get_evidence(FAKE_MODEL_ID, FAKE_TASK_CLASS)
    assert record is not None
    assert isinstance(record, CapabilityEvidenceRecord)
    assert record.evidence_ref
    assert record.tier in (EvidenceTier.PROXY, EvidenceTier.MEASURED)


def test_branch_a_row_carries_numeric_evidence() -> None:
    record = get_evidence(FAKE_MODEL_ID, FAKE_TASK_CLASS)
    assert record is not None
    assert record.score is not None
    assert record.sample_count is not None
    assert record.confidence is not None


def test_original_write_attempt_refused() -> None:
    with pytest.raises(CapabilityStoreError) as excinfo:
        import_measured_capability(FAKE_SOURCE_REF, FAKE_ORIGINAL_DEST_REF)
    assert excinfo.value.code == "CAPABILITY_ORIGINAL_WRITE_REFUSED"


def test_stale_as_current_refused() -> None:
    with pytest.raises(CapabilityStoreError) as excinfo:
        require_current(FAKE_STALE_REF)
    assert excinfo.value.code == "CAPABILITY_STALE_AS_CURRENT_REFUSED"


def test_proxy_adapter_labels_notes_proxy_without_scores() -> None:
    record = adapt_proxy_notes(FAKE_SOURCE_REF, FAKE_DEST_REF)
    assert record is not None
    assert record.tier is EvidenceTier.PROXY
    assert record.score is None
    assert record.evidence_ref
