"""K03 test-isolation guard (backend STEP1 loaders).

The STEP1 behaviour-contract modules in this directory load the real
``src/agent_si/assurance/*.py`` files under synthetic ``k03_assurance_*``
names in ``sys.modules`` (required: the sources use
``from __future__ import annotations`` with dataclasses, which resolves
string annotations through ``sys.modules``). Those entries must not leak
past this directory's tests: product
``src/agent_si/assurance/audit_coordinator.py::_records_module()`` (and
the ``verification/checker.py`` grounding lookup) prefers a
``k03_assurance_*`` entry over the real package import, so a leaked entry
redirects the served/coordinator audit store into the synthetic module's
registry while the K03 served tests assert on the real
``agent_si.assurance.audit_records`` registry (5 REDs on full runs:
test_k03mnt1_served x2, test_k03r3_assurance_coordinator x3).

Module-scoped teardown drops every ``k03_assurance_*`` name this
module's tests registered, after each module's tests finish. The
per-module ``_cache`` dicts are discarded with their modules, so later
modules re-load cleanly. Pre-existing entries (none expected) are kept.
"""

import sys

import pytest

_PREFIX = "k03_assurance_"


@pytest.fixture(scope="module", autouse=True)
def _drop_synthetic_assurance_modules():
    before = {k for k in sys.modules if k.startswith(_PREFIX)}
    yield
    for key in [
        k
        for k in sys.modules
        if k.startswith(_PREFIX) and k not in before
    ]:
        sys.modules.pop(key, None)
