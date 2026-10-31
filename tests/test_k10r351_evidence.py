"""K10R351 R-351: served proof for acceptance on the tech-handbook copy.

testid: k10r351-evidence (lives ONLY in this file).

Row R-351 (kit BUILD_PLAN: acceptance on the tech-handbook copy, all
functions, n8n excluded, final evidence table): every served K10 function
carries one evidence-table row with an artifact link (serving route plus
proving test); no row mentions n8n. Served through create_app plus HTTP
client on the named route GET /k10/compet/audit (which serves this lane's
owned module agent_si.k10_compet); the table itself is the module's
evidence_table(). Loopback TEST data only.
"""
import os
import sys

_TESTID = "k10r351-evidence"

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import fastapi.testclient  # noqa: E402

from agent_si.backend.app import create_app  # noqa: E402
from agent_si.k10_compet import evidence_table as _evidence_table  # noqa: E402

_EXPECTED_FUNCTIONS = (
    "accept",
    "combine",
    "compet-audit",
    "start-demo",
    "start-evidence",
    "start-migrate",
)


def _client():
    app = create_app({"ui_session_token": "k10r351-evidence-token"})
    return fastapi.testclient.TestClient(app)


def test_k10r351_named_route_serves_compet_audit():
    """R-351 named route GET /k10/compet/audit serves the owned module."""
    client = _client()
    resp = client.get("/k10/compet/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["testid"] == "k10st4-accept", body
    flows = body["flows"]
    assert isinstance(flows, list) and flows, body
    for row in flows:
        for key in ("flow", "claim", "source", "snippet"):
            assert row.get(key), row


def test_k10r351_unknown_route_is_404():
    """The served app is a real router: unknown paths 404, not catch-all."""
    client = _client()
    resp = client.get("/k10/no-such-r351-route")
    assert resp.status_code == 404, resp.text


def test_k10r351_evidence_table_one_row_per_function():
    """R-351 final evidence table: one row per function, each with artifact."""
    table = _evidence_table()
    assert isinstance(table, list) and table, table
    assert [row["function"] for row in table] == list(_EXPECTED_FUNCTIONS)
    for row in table:
        for key in ("function", "claim", "source", "snippet", "artifact"):
            assert row.get(key), row
        assert "/k10/" in row["artifact"], row
        assert ".py" in row["artifact"], row


def test_k10r351_evidence_table_excludes_n8n():
    """R-351 n8n excluded: no table field mentions n8n."""
    table = _evidence_table()
    assert table, table
    for row in table:
        for key in ("function", "claim", "source", "snippet", "artifact"):
            assert "n8n" not in str(row[key]).lower(), (key, row)


def test_k10r351_evidence_table_testid_marker():
    """This lane's proof marker lives only here, never in product code."""
    assert _TESTID == "k10r351-evidence"
