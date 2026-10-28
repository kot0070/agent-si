import copy
import os
import sys

import pytest

sys.path.insert(
    0,
    os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
    ),
)

from agent_si.backend.orchestration import overlap as ov
from agent_si.backend.orchestration import split as sp
from agent_si.backend.orchestration.split import MultiManagerSettings


def settings(**extra):
    base = {
        "multi_manager_mode": True,
        "max_parallel_managers": 2,
        "overlap": True,
        "integration_policy": "merge",
        "model_pool_per_manager": {},
    }
    base.update(extra)
    return base


def fanout_settings(cfg):
    """Adapt a MultiMgr settings dict to the v2 home (split.fanout)."""
    return MultiManagerSettings(
        multi_manager_mode=cfg["multi_manager_mode"],
        max_parallel_managers=cfg["max_parallel_managers"],
        overlap=cfg["overlap"],
        integration_policy=cfg["integration_policy"],
        model_pool_per_manager=cfg["model_pool_per_manager"],
    )


def _mm_parts(tag, total):
    parts = []
    for idx in range(total):
        parts.append(
            {
                "package_id": f"{tag}-part-{idx:03d}",
                "contract_hash": f"{tag}-hash-{idx:03d}",
                "gate_verdict_ref": f"{tag}-gate-{idx:03d}",
                "audit_verdict_ref": f"{tag}-audit-{idx:03d}",
            }
        )
    return parts


@pytest.fixture(autouse=True)
def _clear_overlap_store():
    ov._clear_verdicts()
    yield
    ov._clear_verdicts()


def _store_pass(part):
    ov._record_gate_verdict(part["gate_verdict_ref"], "PASS")
    ov._record_audit_verdict(part["audit_verdict_ref"], "PASS")


def test_settings_frozen_keys():
    cfg = settings()
    assert cfg["multi_manager_mode"] is True
    assert cfg["max_parallel_managers"] == 2
    assert cfg["overlap"] is True
    assert cfg["integration_policy"] == "merge"
    assert cfg["model_pool_per_manager"] == {}


def test_validate_accepts_valid_settings():
    ok, reason = ov.validate_multi_manager_settings(settings())
    assert (ok, reason) == (True, "ok")


def test_mode_off_single_manager():
    parts = _mm_parts("pkg-mm-off", 3)
    running, queued = sp.fanout(
        parts, fanout_settings(settings(multi_manager_mode=False))
    )
    assert running == parts[:1]
    assert queued == parts[1:]
    assert running + queued == parts


def test_mode_off_single_part():
    parts = _mm_parts("pkg-mm-single", 1)
    running, queued = sp.fanout(
        parts, fanout_settings(settings(multi_manager_mode=False))
    )
    assert running == parts
    assert queued == []


def test_mode_off_ignores_capacity():
    parts = _mm_parts("pkg-mm-offcap", 4)
    running, queued = sp.fanout(
        parts,
        fanout_settings(settings(multi_manager_mode=False, max_parallel_managers=3)),
    )
    assert running == parts[:1]
    assert queued == parts[1:]


def test_over_capacity_queues_never_drops():
    # moved-caller proof: over-capacity fanout via the v2 home split.fanout.
    parts = _mm_parts("pkg-mm-overcap", 7)
    before = copy.deepcopy(parts)
    running, queued = sp.fanout(
        parts, fanout_settings(settings(max_parallel_managers=2))
    )
    assert running == parts[:2]
    assert queued == parts[2:]
    assert running + queued == parts
    assert parts == before


def test_capacity_one_serializes():
    parts = _mm_parts("pkg-mm-serial", 2)
    running, queued = sp.fanout(
        parts, fanout_settings(settings(max_parallel_managers=1))
    )
    assert running == parts[:1]
    assert queued == parts[1:]


def test_capacity_above_total_runs_all():
    parts = _mm_parts("pkg-mm-all", 2)
    running, queued = sp.fanout(
        parts, fanout_settings(settings(max_parallel_managers=5))
    )
    assert running == parts
    assert queued == []


def test_overlap_off_no_early_start_even_pass():
    parts = _mm_parts("pkg-mm-ovoff", 1)
    ref = parts[0]
    _store_pass(ref)
    assert ov.may_start_early(ref) is True
    cfg = settings(overlap=False)
    assert cfg["overlap"] is False
    assert ov.early_start_allowed(ref, False) is False
    assert ov.early_start_allowed(ref, settings=cfg) is False
    assert ov.early_start_allowed(ref, cfg) is False


def test_overlap_on_pass_allows_early_start():
    parts = _mm_parts("pkg-mm-ovon", 1)
    ref = parts[0]
    _store_pass(ref)
    assert ov.may_start_early(ref) is True
    assert ov.early_start_allowed(ref, True) is True
    assert ov.early_start_allowed(ref, settings=settings(overlap=True)) is True


def test_overlap_on_non_pass_refused():
    parts = _mm_parts("pkg-mm-ovbad", 1)
    ref = parts[0]
    ov._record_gate_verdict(ref["gate_verdict_ref"], "PASS")
    ov._record_audit_verdict(ref["audit_verdict_ref"], "REWORK")
    assert ov.may_start_early(ref) is False
    assert ov.early_start_allowed(ref, True) is False
    assert ov.early_start_allowed(ref, settings=settings(overlap=True)) is False


def test_invalid_settings_rejected():
    parts = _mm_parts("pkg-mm-badcap", 1)
    before = copy.deepcopy(parts)
    ok, reason = ov.validate_multi_manager_settings(
        settings(max_parallel_managers=0)
    )
    assert ok is False
    assert "max_parallel" in reason
    with pytest.raises(ValueError) as excinfo:
        sp.fanout(parts, fanout_settings(settings(max_parallel_managers=0)))
    assert "max_parallel" in str(excinfo.value)
    assert parts == before


def test_empty_policy_rejected():
    cfg = settings(integration_policy="")
    ok, reason = ov.validate_multi_manager_settings(cfg)
    assert ok is False
    assert "integration_policy" in reason
    # v2 home split.fanout gates cap/mode only: the split still covers all parts.
    parts = _mm_parts("pkg-mm-emptypol", 3)
    running, queued = sp.fanout(parts, fanout_settings(cfg))
    assert running == parts[:2]
    assert queued == parts[2:]
    assert running + queued == parts


def test_non_bool_mode_rejected():
    ok, _reason = ov.validate_multi_manager_settings(
        settings(multi_manager_mode="yes")
    )
    assert ok is False
    # v2 home split.fanout takes the settings object as-is: truthy mode
    # behaves as mode-on and nothing is dropped.
    parts = _mm_parts("pkg-mm-mode", 1)
    running, queued = sp.fanout(
        parts, fanout_settings(settings(multi_manager_mode="yes"))
    )
    assert running + queued == parts
    assert running == parts
    assert queued == []


def test_non_dict_settings_rejected():
    ok, _reason = ov.validate_multi_manager_settings(None)
    assert ok is False
    # v2 home split.fanout requires a settings object: None has no attributes.
    with pytest.raises(AttributeError):
        sp.fanout(_mm_parts("pkg-mm-none", 1), None)


def test_overlap_flag_carried_in_settings():
    assert settings(overlap=True)["overlap"] is True
    assert settings(overlap=False)["overlap"] is False
    assert settings()["overlap"] is True
