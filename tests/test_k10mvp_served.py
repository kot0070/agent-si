"""K10MVP MVP verdict seam: binary verdict plus 3 host blockers, served test.

Rows:
  B0B-UNCOVERED_MVP_ACCEPT-209 | K10 | MVP verdict is binary ACCEPTED or
    NOT_ACCEPTED with explicit blockers.
  B0B-UNCOVERED_MVP_ACCEPT-210 | K10 | MVP_ACCEPTED equals ACCEPTED iff all
    acceptance items hold.
  B0B-UNCOVERED_MVP_ACCEPT-212 | K10 | MVP shortfall yields NOT_ACCEPTED
    with listed blockers.
  B0B-UNCOVERED_MVP_ACCEPT-214 | K10 | host blockers name missing
    permissions, auditor provider, and second provider.
  B0B-UNCOVERED_MVP_ACCEPT-215 | K10 | MVP is not attainable on a host until
    local permission, auditor provider, and a second real provider.

Lint cover (mode:regex): missing permissions, auditor provider,
second provider. Served: imports ONLY the product seam
(src/agent_si/k10_accept), no duplicated logic.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.k10_accept import (  # noqa: E402
    HOST_BLOCKERS,
    MVP_ACCEPTED,
    MVP_NOT_ACCEPTED,
    mvp_verdict,
)

ALL_HOLD_ITEMS = {"docker": True, "services": True, "powershell": True}


def _all_hosts():
    return {
        "local_permission": True,
        "auditor_provider": True,
        "second_real_provider": True,
    }


def test_209_mvp_verdict_is_binary_with_explicit_blockers():
    accepted = mvp_verdict(ALL_HOLD_ITEMS, **_all_hosts())
    assert accepted["verdict"] == "ACCEPTED", accepted
    assert accepted["verdict"] in ("ACCEPTED", "NOT_ACCEPTED"), accepted
    shortfall = mvp_verdict({"docker": False}, **_all_hosts())
    assert shortfall["verdict"] == "NOT_ACCEPTED", shortfall
    assert shortfall["verdict"] in ("ACCEPTED", "NOT_ACCEPTED"), shortfall
    assert isinstance(shortfall["blockers"], list) and shortfall["blockers"], shortfall
    assert all(isinstance(item, str) and item for item in shortfall["blockers"]), shortfall


def test_210_mvp_accepted_iff_all_items_hold():
    assert mvp_verdict(ALL_HOLD_ITEMS, **_all_hosts())["verdict"] == "ACCEPTED"
    one_false = dict(ALL_HOLD_ITEMS)
    one_false["services"] = False
    denied = mvp_verdict(one_false, **_all_hosts())
    assert denied["verdict"] == "NOT_ACCEPTED", denied
    assert "services" in denied["blockers"], denied


def test_212_mvp_shortfall_lists_blockers():
    shortfall = mvp_verdict({"docker": True, "services": False}, **_all_hosts())
    assert shortfall["verdict"] == "NOT_ACCEPTED", shortfall
    assert "services" in shortfall["blockers"], shortfall


def test_214_host_blockers_name_exact_three_strings():
    assert tuple(HOST_BLOCKERS) == (
        "missing local permission",
        "auditor provider",
        "second real provider",
    ), HOST_BLOCKERS
    assert MVP_ACCEPTED == "ACCEPTED", MVP_ACCEPTED
    assert MVP_NOT_ACCEPTED == "NOT_ACCEPTED", MVP_NOT_ACCEPTED


def test_215_host_without_each_requirement_is_not_accepted():
    expected = {
        "local_permission": "missing local permission",
        "auditor_provider": "auditor provider",
        "second_real_provider": "second real provider",
    }
    for flag, blocker in expected.items():
        hosts = _all_hosts()
        hosts[flag] = False
        result = mvp_verdict(ALL_HOLD_ITEMS, **hosts)
        assert result["verdict"] == "NOT_ACCEPTED", (flag, result)
        assert blocker in result["blockers"], (flag, result)
