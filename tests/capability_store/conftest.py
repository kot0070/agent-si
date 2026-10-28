"""K05R4 test-boundary import: labelled measurement data via the real path.

The session fixture below imports the FAKE-OF labelled measurement document
through the real public import path (`agent_si.capability_store`), so the
frozen read-path tests serve a genuinely imported MEASURED row. No product
seeding: every value lives in the labelled test-data document beside this
file, never in product code.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_WS_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_WS_SRC) not in sys.path:
    sys.path.insert(0, str(_WS_SRC))

DATA_FILE = Path(__file__).with_name("testdata_k05r4_evid.json")

# must match frozen test_iface_m4.py
FAKE_MODEL_ID = "FAKE-OF: fixture model id"
FAKE_TASK_CLASS = "FAKE-OF: fixture task class"


@pytest.fixture(scope="session", autouse=True)
def _import_k05r4_measured_evidence():
    """Import the labelled measurement row once per session; serve it."""
    from agent_si.capability_store import (
        EvidenceTier,
        get_evidence,
        import_measured_capability,
    )

    row = import_measured_capability(str(DATA_FILE), FAKE_TASK_CLASS)
    served = get_evidence(FAKE_MODEL_ID, FAKE_TASK_CLASS)
    assert served is not None
    assert served.evidence_ref
    assert served.tier is EvidenceTier.MEASURED
    assert served.score is not None
    assert served.sample_count is not None
    assert served.confidence is not None
    assert row is served
    return served
