"""K05R3 discover tests: DISCOVER-stage permission gate (B0B-UNCOVERED_BP05-29)."""
from __future__ import annotations

import importlib
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from agent_si.local import adapter  # noqa: E402
from agent_si.local import k05r3_discover as discover  # noqa: E402

_ALLOWED = "local-contact-allowed"


def test_permissionless_probing_refused():
    for missing in (None, "", "   "):
        with pytest.raises(discover.DiscoverError) as excinfo:
            discover.enter_discover(adapter.LifecycleStage.SCAN, missing)
        assert excinfo.value.code == discover.K05R3_DISCOVER_PERMISSION_REFUSED


def test_unlisted_scope_refused():
    with pytest.raises(discover.DiscoverError) as excinfo:
        discover.enter_discover(adapter.LifecycleStage.SCAN, "local-contact-denied")
    assert excinfo.value.code == discover.K05R3_DISCOVER_PERMISSION_REFUSED


def test_allowed_scope_admits_discover_only():
    grant = discover.enter_discover(adapter.LifecycleStage.SCAN, _ALLOWED)
    assert grant.stage is adapter.LifecycleStage.DISCOVER
    assert grant.stage == adapter.advance_lifecycle(
        adapter.LifecycleStage.SCAN, adapter.LifecycleStage.DISCOVER
    )
    assert grant.permission_scope == _ALLOWED
    assert grant.identity_state == "UNKNOWN"
    assert grant.grant_id.startswith("k05r3-discover-")


@pytest.mark.parametrize(
    "stage",
    [
        adapter.LifecycleStage.DISCOVER,
        adapter.LifecycleStage.IDENTIFY,
        adapter.LifecycleStage.PROBE,
        adapter.LifecycleStage.ROUTING_ELIGIBILITY,
    ],
)
def test_non_scan_stage_refused(stage):
    with pytest.raises(discover.DiscoverError) as excinfo:
        discover.enter_discover(stage, _ALLOWED)
    assert excinfo.value.code == discover.K05R3_DISCOVER_STAGE_REFUSED


def test_garbage_stage_refused():
    with pytest.raises(discover.DiscoverError) as excinfo:
        discover.enter_discover("SCAN", _ALLOWED)
    assert excinfo.value.code == discover.K05R3_DISCOVER_STAGE_REFUSED


def test_scan_allowlist_serves_one_level(tmp_path):
    target = tmp_path / "models"
    target.mkdir()
    (target / "b-model").write_text("x", encoding="utf-8")
    (target / "a-model").write_text("x", encoding="utf-8")
    got = discover.scan_roots([str(tmp_path)], str(target))
    assert got == ["a-model", "b-model"]


def test_scan_outside_allowlist_refused(tmp_path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    with pytest.raises(discover.DiscoverError) as excinfo:
        discover.scan_roots([str(tmp_path / "models")], str(outside))
    assert excinfo.value.code == discover.K05R3_DISCOVER_SCAN_REFUSED
    assert "allowlist" in str(excinfo.value)


def test_scan_forbidden_segment_refused(tmp_path):
    creds = tmp_path / "secrets"
    creds.mkdir()
    with pytest.raises(discover.DiscoverError) as excinfo:
        discover.scan_roots([str(tmp_path)], str(creds))
    assert excinfo.value.code == discover.K05R3_DISCOVER_SCAN_REFUSED


def test_scan_full_drive_and_non_dir_refused(tmp_path):
    with pytest.raises(discover.DiscoverError) as excinfo:
        discover.scan_roots([str(tmp_path)], os.path.splitdrive(str(tmp_path))[0] + os.sep)
    assert excinfo.value.code == discover.K05R3_DISCOVER_SCAN_REFUSED
    leaf = tmp_path / "leaf.txt"
    leaf.write_text("x", encoding="utf-8")
    with pytest.raises(discover.DiscoverError) as excinfo:
        discover.scan_roots([str(tmp_path)], str(leaf))
    assert excinfo.value.code == discover.K05R3_DISCOVER_SCAN_REFUSED
    with pytest.raises(discover.DiscoverError) as excinfo:
        discover.scan_roots([""], str(tmp_path))
    assert excinfo.value.code == discover.K05R3_DISCOVER_SCAN_REFUSED


def test_scan_symlink_refused(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "link"
    try:
        os.symlink(str(target), str(link))
    except OSError:
        pytest.skip("symlinks need a privilege this machine lacks")
    with pytest.raises(discover.DiscoverError) as excinfo:
        discover.scan_roots([str(tmp_path)], str(link))
    assert excinfo.value.code == discover.K05R3_DISCOVER_SCAN_REFUSED


def test_scan_changes_nothing(tmp_path):
    target = tmp_path / "models"
    target.mkdir()
    (target / "m").write_text("v", encoding="utf-8")
    before = sorted(p.name for p in target.iterdir())
    discover.scan_roots([str(tmp_path)], str(target))
    assert sorted(p.name for p in target.iterdir()) == before
    assert (target / "m").read_text(encoding="utf-8") == "v"


def test_discover_never_touches_sched_lane():
    bench_key = "agent_si.local.bench_runner"
    discover_key = "agent_si.local.k05r3_discover"
    saved = dict(sys.modules)
    sys.modules.pop(bench_key, None)
    sys.modules.pop(discover_key, None)
    try:
        importlib.import_module(discover_key)
        assert bench_key not in sys.modules
    finally:
        sys.modules.clear()
        sys.modules.update(saved)


def test_error_codes_new_module_only():
    assert tuple(discover.ERROR_CODES_K05R3_DISCOVER) == (
        "K05R3_DISCOVER_PERMISSION_REFUSED",
        "K05R3_DISCOVER_STAGE_REFUSED",
        "K05R3_DISCOVER_SCAN_REFUSED",
    )
