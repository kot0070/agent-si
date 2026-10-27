"""K05R3 M-EVID adapter-side rows: MEASURED is not ROUTING_ELIGIBLE, guards, arch rules.

Covers (adapter side, via the real adapter entry points only):
- SPEC 36: bare MEASURED tier never yields eligible=True; eligible only on
  routing-eligibility evidence (a structured store evidence ref carrying a
  MEASURED signal, or an explicit ROUTING_ELIGIBILITY stage marker) with an
  idle gateway; UNKNOWN never picked; PROXY/MEASURED alone ineligible.
- B0B-UNCOVERED_MVP_ACCEPT-175 (adapter side): no seeded MEASURED acceptance
  here; bare "measured" strings and seeded numeric literals never count as
  routing eligibility.
- B0B-UNCOVERED_MVP_ACCEPT-223 (adapter side): role-config fields are never
  accepted as task_class / model refs where they enter this module.
- SPEC 37 (adapter side, as applicable to this file): stdlib-only, no SQLite,
  external inputs validated by shape, originals never modified (pure entry
  points, frozen shapes).
- Frozen behaviours kept unchanged: lifecycle order/no-skips, NOT_CONFIGURED
  routing continues, explicit pin UNVERIFIED + zero measured, SPLIT atomic
  refs, REALIZATION_MAP names, verdict shape + signature.
"""

from __future__ import annotations

import dataclasses
import inspect
import sys
from pathlib import Path

import pytest

_WS_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_WS_SRC) not in sys.path:
    sys.path.insert(0, str(_WS_SRC))

from agent_si.local import adapter

_ADAPTER_SRC = Path(adapter.__file__).read_text(encoding="utf-8")

IDLE_GATEWAY = "gateway-state-idle"
BUSY_GATEWAY = "gateway-state-user-bench-running"

# Role-config field names (grounded in src/agent_si/local/config.py:
# EXPLICIT_CONFIG_FIELDS + LocalAIConfig fields + dotted settings.localAi
# view keys + their trailing segments). Never capability task classes.
_ROLE_CONFIG_FIELDS = [
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

_REFUSAL_CODE = "CAPABILITY_ROLE_CONFIG_AS_TASK_CLASS_REFUSED"


# --- SPEC 36: MEASURED is not ROUTING_ELIGIBLE (adapter side) ---


@pytest.mark.parametrize(
    "bare_ref",
    [
        "measured",
        "MEASURED",
        "  measured  ",
        "Measured",
        "proxy",
        "PROXY",
        "measured evidence only",
        "tier: MEASURED",
        "MEASURED tier label, no evidence ref",
    ],
)
def test_bare_tier_word_never_eligible(bare_ref):
    verdict = adapter.check_eligibility(bare_ref, IDLE_GATEWAY)
    assert verdict.eligible is False
    assert verdict.gateway_allowed is True
    assert "ROUTING_ELIGIB" in verdict.reason


@pytest.mark.parametrize(
    "proxy_ref",
    [
        "store-ref-proxy-2",
        "cap:proxy:notes:v9",
    ],
)
def test_proxy_evidence_alone_never_eligible(proxy_ref):
    verdict = adapter.check_eligibility(proxy_ref, IDLE_GATEWAY)
    assert verdict.eligible is False
    assert "ROUTING_ELIGIB" in verdict.reason


@pytest.mark.parametrize(
    "eligible_ref",
    [
        "store-ref-measured-1",
        "cap:bench-7:coding-measured:v1",
        "store-ref-measured-routing-eligibility-9",
        "ROUTING_ELIGIBILITY-measured-store-ref",
    ],
)
def test_routing_eligibility_evidence_eligible_when_gateway_idle(eligible_ref):
    verdict = adapter.check_eligibility(eligible_ref, IDLE_GATEWAY)
    assert verdict.eligible is True
    assert verdict.gateway_allowed is True
    assert isinstance(verdict.evidence_refs, tuple) and len(verdict.evidence_refs) > 0
    assert "store" in verdict.eligibility_source and "gateway" in verdict.eligibility_source


def test_unknown_tier_never_picked():
    verdict = adapter.check_eligibility("store-ref-with-only-unknown", IDLE_GATEWAY)
    assert verdict.eligible is False
    assert "UNKNOWN_TIER_INELIGIBLE" in verdict.reason


def test_busy_gateway_refuses_even_routing_eligible_evidence():
    verdict = adapter.check_eligibility("store-ref-measured-1", BUSY_GATEWAY)
    assert verdict.eligible is False
    assert verdict.gateway_allowed is False
    assert "GATEWAY_BUSY" in verdict.reason


def test_eligible_verdict_shape_and_signature_frozen():
    assert list(inspect.signature(adapter.check_eligibility).parameters) == [
        "capability_store_ref",
        "gateway_state_ref",
    ]
    assert dataclasses.fields(adapter.EligibilityVerdict)
    assert tuple(f.name for f in dataclasses.fields(adapter.EligibilityVerdict)) == (
        "eligible",
        "reason",
        "evidence_refs",
        "gateway_allowed",
        "eligibility_source",
    )


# --- B0B-UNCOVERED_MVP_ACCEPT-175 (adapter side): no seeded MEASURED here ---


@pytest.mark.parametrize("seeded", ["0.85", "sample_count=100", "0.9", "pass_rate 0.85/100"])
def test_seeded_numeric_literals_are_not_eligibility(seeded):
    verdict = adapter.check_eligibility(seeded, IDLE_GATEWAY)
    assert verdict.eligible is False


def test_adapter_source_carries_no_seeded_numbers():
    assert "0.85" not in _ADAPTER_SRC


# --- B0B-UNCOVERED_MVP_ACCEPT-223 (adapter side): role config is not task class ---


@pytest.mark.parametrize("field", _ROLE_CONFIG_FIELDS)
def test_role_config_field_refused_as_store_ref(field):
    with pytest.raises(Exception) as excinfo:
        adapter.check_eligibility(field, IDLE_GATEWAY)
    assert _REFUSAL_CODE in str(excinfo.value)


@pytest.mark.parametrize(
    "field",
    [
        "endpoint_url",
        "model_id",
        "permission_scope",
        "capability_evidence",
        "settings.localAi.title",
    ],
)
def test_role_config_field_refused_in_stable_ref_task_segment(field):
    ref = "cap:bench-7:%s:v1" % field
    with pytest.raises(Exception) as excinfo:
        adapter.check_eligibility(ref, IDLE_GATEWAY)
    assert _REFUSAL_CODE in str(excinfo.value)


@pytest.mark.parametrize("field", ["endpoint_url", "model_id", "needItNow"])
def test_role_config_field_refused_as_pin_model_ref(field):
    with pytest.raises(Exception) as excinfo:
        adapter.record_explicit_pin(field)
    assert _REFUSAL_CODE in str(excinfo.value)


def test_genuine_refs_and_pins_still_accepted():
    verdict = adapter.check_eligibility("store-ref-measured-1", IDLE_GATEWAY)
    assert verdict.eligible is True
    pin = adapter.record_explicit_pin("local-model-ref-1")
    assert pin.capability_evidence_refs == ("local-model-ref-1",)


# --- SPEC 37 (adapter side, as applicable): stdlib-only, originals untouched ---


def test_adapter_source_is_stdlib_only_no_sqlite():
    assert "sqlite" not in _ADAPTER_SRC.lower()
    assert "import sqlite3" not in _ADAPTER_SRC
    roots = set()
    for line in _ADAPTER_SRC.splitlines():
        stripped = line.strip()
        if stripped.startswith("import "):
            roots.add(stripped.split()[1].split(".")[0])
        elif stripped.startswith("from "):
            roots.add(stripped.split()[1].split(".")[0])
    assert roots <= {"__future__", "itertools", "os", "dataclasses", "enum"}


def test_adapter_entry_points_are_pure_and_frozen():
    verdict_one = adapter.check_eligibility("store-ref-measured-1", IDLE_GATEWAY)
    verdict_two = adapter.check_eligibility("store-ref-measured-1", IDLE_GATEWAY)
    assert verdict_one == verdict_two
    with pytest.raises(dataclasses.FrozenInstanceError):
        verdict_one.eligible = not verdict_one.eligible


def test_adapter_source_does_no_io_or_mutation():
    for token in ("open(", "socket", "urllib", "requests", "subprocess", "shutil",
                 "os.replace", "os.remove", "os.write"):
        assert token not in _ADAPTER_SRC


# --- Frozen behaviours kept ---


def test_lifecycle_order_and_no_skips_kept():
    assert [stage.value for stage in adapter.LifecycleStage] == [
        "SCAN",
        "DISCOVER",
        "IDENTIFY",
        "REGISTER",
        "PROBE",
        "BENCHMARK",
        "ROUTING_ELIGIBILITY",
    ]
    assert (
        adapter.advance_lifecycle(
            adapter.LifecycleStage.BENCHMARK,
            adapter.LifecycleStage.ROUTING_ELIGIBILITY,
        )
        is adapter.LifecycleStage.ROUTING_ELIGIBILITY
    )
    with pytest.raises(Exception) as excinfo:
        adapter.advance_lifecycle(adapter.LifecycleStage.SCAN, adapter.LifecycleStage.IDENTIFY)
    assert "LIFECYCLE_SKIP_REFUSED" in str(excinfo.value)


def test_not_configured_routing_continues_kept():
    assert adapter.routing_continues(adapter.STATUS_NOT_CONFIGURED) is True
    assert adapter.routing_continues("CONFIGURED") is False


def test_explicit_pin_unverified_zero_measured_kept():
    decision = adapter.record_explicit_pin("local-model-ref-1")
    assert decision.route == adapter.ROUTE_EXPLICIT_PIN
    assert decision.quality_basis == "UNVERIFIED_PIN"
    assert decision.measured_evidence_count == 0


def test_split_atomic_refs_kept():
    split = adapter.record_split_decision("draft-ref-9", "verify-ref-9", "draft-hash-9")
    assert (split.local_draft_ref, split.cloud_verify_ref) == ("draft-ref-9", "verify-ref-9")
    assert split.draft_hash == "draft-hash-9"
    with pytest.raises(ValueError):
        adapter.record_split_decision("", "verify-ref-9", "draft-hash-9")


def test_realization_map_names_kept():
    for name, target in adapter.REALIZATION_MAP.items():
        assert callable(getattr(adapter, name))
        assert target.startswith("agent_si.local.")
