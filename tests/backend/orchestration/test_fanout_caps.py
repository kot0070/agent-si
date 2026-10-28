"""ROW32/M-P1-10/B0B-ARCH-755/762: fanout bounded by caps, excess queued
never dropped."""
import os
import sys

import pytest

sys.path.insert(
    0,
    os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
    ),
)

from agent_si.backend.orchestration.split import (
    MultiManagerSettings,
    fanout,
    split_package,
)


def make_settings(mode=True, cap=2, overlap=False):
    return MultiManagerSettings(
        multi_manager_mode=mode,
        max_parallel_managers=cap,
        overlap=overlap,
        integration_policy="merge",
        model_pool_per_manager={},
    )


def make_parts(tag, total, max_parts):
    return split_package(
        tag,
        f"{tag} goal",
        [f"artifact://{tag}/ctx-{i:03d}" for i in range(total)],
        max_parts,
    )


def test_cap_binds_active_rest_queued_row32():
    parts = make_parts("pkg-f-row32", 5, 5)
    running, queued = fanout(parts, make_settings(cap=2))
    assert len(running) == 2
    assert len(queued) == 3
    assert running + queued == parts


def test_queue_never_drops_m_p1_10():
    parts = make_parts("pkg-f-nodrop", 4, 4)
    running, queued = fanout(parts, make_settings(cap=1))
    assert len(running) + len(queued) == len(parts) == 4
    assert running + queued == parts


def test_positions_serial_order():
    parts = make_parts("pkg-f-order", 5, 5)
    running, queued = fanout(parts, make_settings(cap=2))
    assert running == parts[:2]
    assert queued == parts[2:]


def test_cap_above_parts_all_active():
    parts = make_parts("pkg-f-all", 2, 2)
    running, queued = fanout(parts, make_settings(cap=8))
    assert running == parts
    assert queued == []


def test_mode_off_single_running_b0b_arch_762():
    parts = make_parts("pkg-f-off", 3, 3)
    running, queued = fanout(parts, make_settings(mode=False, cap=8))
    assert running == parts[:1]
    assert queued == parts[1:]


def test_mode_off_single_part_stays_single():
    parts = make_parts("pkg-f-offone", 1, 1)
    running, queued = fanout(parts, make_settings(mode=False, cap=8))
    assert running == parts
    assert queued == []


@pytest.mark.parametrize("cap", [0, -1])
def test_cap_below_one_refused(cap):
    parts = make_parts(f"pkg-f-badcap-{cap}", 2, 2)
    with pytest.raises(ValueError):
        fanout(parts, make_settings(cap=cap))
    with pytest.raises(ValueError):
        fanout(parts, make_settings(mode=False, cap=cap))


def test_empty_parts_empty_queues():
    assert fanout([], make_settings()) == ([], [])
    assert fanout([], make_settings(mode=False)) == ([], [])


def test_overlap_flag_does_not_change_fanout_shape():
    parts = make_parts("pkg-f-flag", 4, 4)
    assert fanout(parts, make_settings(cap=2, overlap=False)) == fanout(
        parts, make_settings(cap=2, overlap=True)
    )


def test_capped_queue_positions_serial_order():
    from agent_si.backend.orchestration.split import capped_queue

    parts = make_parts("pkg-f-slots", 5, 5)
    slots = capped_queue(parts, make_settings(cap=2))
    assert [slot.position for slot in slots] == [0, 1, 2, 3, 4]
    assert [slot.part for slot in slots] == parts


def test_capped_queue_estimated_start_waves_by_cap():
    from agent_si.backend.orchestration.split import capped_queue

    parts = make_parts("pkg-f-waves", 5, 5)
    slots = capped_queue(parts, make_settings(cap=2), wall_time_s=10.0)
    assert [slot.estimated_start_s for slot in slots] == [0.0, 0.0, 10.0, 10.0, 20.0]


def test_capped_queue_matches_fanout_split():
    from agent_si.backend.orchestration.split import capped_queue

    parts = make_parts("pkg-f-match", 4, 4)
    settings = make_settings(cap=2)
    running, queued = fanout(parts, settings)
    slots = capped_queue(parts, settings)
    assert [slot.part for slot in slots[:2]] == running
    assert [slot.part for slot in slots[2:]] == queued


def test_capped_queue_mode_off_single_wave():
    from agent_si.backend.orchestration.split import capped_queue

    parts = make_parts("pkg-f-modeoff", 3, 3)
    slots = capped_queue(parts, make_settings(mode=False, cap=8), wall_time_s=5.0)
    assert [slot.estimated_start_s for slot in slots] == [0.0, 5.0, 10.0]


def test_capped_queue_never_drops():
    from agent_si.backend.orchestration.split import capped_queue

    parts = make_parts("pkg-f-nodrop", 4, 4)
    slots = capped_queue(parts, make_settings(cap=1))
    assert len(slots) == 4
    assert [slot.part for slot in slots] == parts


def test_capped_queue_bad_wall_time_refused():
    from agent_si.backend.orchestration.split import capped_queue

    parts = make_parts("pkg-f-badwall", 2, 2)
    with pytest.raises(ValueError):
        capped_queue(parts, make_settings(), wall_time_s=-1.0)
    with pytest.raises(ValueError):
        capped_queue(parts, make_settings(), wall_time_s=True)
