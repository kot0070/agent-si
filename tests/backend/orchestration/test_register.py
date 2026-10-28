"""ROW33 / M-P1-15: served part register rows plus status filter and update."""
import os
import sys

import pytest

sys.path.insert(
    0,
    os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
    ),
)

from agent_si.backend.orchestration.parts import (
    PartRow,
    list_parts,
    register_part,
    update_status,
)


def make_row(scope, agent="agent-1", deliverable=None, status="QUEUED"):
    return PartRow(
        agent=agent,
        scope=scope,
        deliverable=deliverable or f"artifact://pkg/{scope}",
        status=status,
    )


def scoped_rows(prefix, status=None):
    rows = list_parts(status)
    scopes = [row.scope for row in rows]
    assert scopes == sorted(scopes)
    return [row for row in rows if row.scope.startswith(prefix)]


def test_row33_register_list_roundtrip():
    prefix = "row33-"
    rows = [make_row(prefix + "0002"), make_row(prefix + "0001", agent="agent-2")]
    for row in rows:
        out = register_part(row)
        assert (out.agent, out.scope, out.deliverable, out.status) == (
            row.agent, row.scope, row.deliverable, row.status,
        )
    got = scoped_rows(prefix)
    assert [row.scope for row in got] == sorted(row.scope for row in rows)
    by_scope = {row.scope: row for row in got}
    assert by_scope[prefix + "0001"].agent == "agent-2"
    assert all(row.deliverable.startswith("artifact://") for row in got)
    assert all(row.status == "QUEUED" for row in got)


def test_default_status_queued():
    row = PartRow(agent="agent-d", scope="def-0001", deliverable="artifact://pkg/def-0001")
    assert row.status == "QUEUED"


def test_m_p1_15_status_filter():
    prefix = "mp115-"
    register_part(make_row(prefix + "0001"))
    register_part(make_row(prefix + "0002"))
    update_status(prefix + "0002", "RUNNING")
    assert {row.scope for row in scoped_rows(prefix, "QUEUED")} == {prefix + "0001"}
    assert {row.scope for row in scoped_rows(prefix, "RUNNING")} == {prefix + "0002"}
    assert all(row.status == "QUEUED" for row in list_parts("QUEUED"))


def test_register_duplicate_scope_refused():
    register_part(make_row("dup-0001"))
    with pytest.raises(ValueError):
        register_part(make_row("dup-0001", agent="agent-2"))


def test_blank_fields_rejected():
    with pytest.raises(ValueError):
        PartRow(agent="  ", scope="blank-0001", deliverable="artifact://pkg/blank-0001")
    with pytest.raises(ValueError):
        PartRow(agent="a", scope="   ", deliverable="artifact://pkg/blank-0002")
    with pytest.raises(ValueError):
        PartRow(agent="a", scope="blank-0003", deliverable="  ")


def test_inline_deliverable_rejected():
    with pytest.raises(ValueError):
        PartRow(agent="a", scope="inline-0001", deliverable="inline-bytes-not-a-ref")


def test_unknown_status_rejected():
    with pytest.raises(ValueError):
        PartRow(
            agent="a",
            scope="unk-0001",
            deliverable="artifact://pkg/unk-0001",
            status="NOPE",
        )
    with pytest.raises(ValueError):
        list_parts("NOPE")  # type: ignore[arg-type]
    register_part(make_row("unk-0002"))
    with pytest.raises(ValueError):
        update_status("unk-0002", "NOPE")  # type: ignore[arg-type]


def test_unknown_part_key_error():
    with pytest.raises(KeyError):
        update_status("no-such-scope-0001", "RUNNING")


def test_update_status_changes_served_row():
    register_part(make_row("upd-0001"))
    out = update_status("upd-0001", "ACCEPTED")
    assert out.status == "ACCEPTED"
    got = [row for row in list_parts(None) if row.scope == "upd-0001"]
    assert len(got) == 1 and got[0].status == "ACCEPTED"
    assert [row for row in list_parts("ACCEPTED") if row.scope == "upd-0001"]


def test_b0b_arch_distinct_scopes():
    register_part(make_row("b0b-arch-456-0001"))
    register_part(make_row("b0b-arch-766-0001"))
    got = [
        row
        for row in list_parts(None)
        if row.scope in ("b0b-arch-456-0001", "b0b-arch-766-0001")
    ]
    assert sorted(row.scope for row in got) == [
        "b0b-arch-456-0001",
        "b0b-arch-766-0001",
    ]


def test_served_rows_are_copies():
    out = register_part(make_row("copy-0001"))
    out.status = "REJECTED"
    out.agent = "mutated"
    got = next(row for row in list_parts(None) if row.scope == "copy-0001")
    assert (got.agent, got.status) == ("agent-1", "QUEUED")
    updated = update_status("copy-0001", "RETURNED")
    updated.status = "BLOCKED"
    again = next(row for row in list_parts(None) if row.scope == "copy-0001")
    assert again.status == "RETURNED"


def test_partstore_register_close_gate_rule():
    from agent_si.backend.orchestration.gates import (
        GATE_NOT_PASSED,
        GateAuditLog,
    )
    from agent_si.backend.orchestration.gates import close_part as gates_close_part
    from agent_si.backend.orchestration.parts import (
        PartRecord,
        PartStore,
    )

    store = PartStore()
    out = store.register(
        PartRecord(
            part_id="pkg-r-1:part-000",
            package_id="pkg-r-1",
            contract_hash="ch-r",
            agent="agent-1",
            scope="slice",
            deliverable_ref="artifact://pkg-r-1/part-000",
        )
    )
    assert out.part_id == "pkg-r-1:part-000"
    log = GateAuditLog()
    gate = log.serve_gate("pkg-r-1:part-000", "PASS")
    with pytest.raises(GATE_NOT_PASSED):
        gates_close_part(
            {
                "package_id": "pkg-r-1",
                "contract_hash": "ch-r",
                "gate_verdict_ref": gate.gate_id,
                "audit_verdict_ref": "audit:unknown-r1",
            }
        )
    with pytest.raises(GATE_NOT_PASSED):
        gates_close_part(
            {
                "package_id": "pkg-r-1",
                "contract_hash": "ch-r",
                "gate_verdict_ref": "gate:unknown-r1",
                "audit_verdict_ref": "audit:unknown-r1",
            }
        )
    with pytest.raises(ValueError):
        store.register(
            PartRecord(
                part_id="pkg-r-1:part-000",
                package_id="pkg-r-1",
                contract_hash="ch-r",
                agent="agent-1",
                scope="slice",
                deliverable_ref="artifact://pkg-r-1/part-000",
            )
        )


def test_partstore_close_returns_frozen_ref_shape():
    from agent_si.backend.orchestration.gates import GateAuditLog
    from agent_si.backend.orchestration.gates import close_part as gates_close_part
    from agent_si.backend.orchestration.parts import PartRecord, PartStore

    store = PartStore()
    stored = store.register(
        PartRecord(
            part_id="pkg-r-2:part-000",
            package_id="pkg-r-2",
            contract_hash="ch-r2",
            agent="agent-1",
            scope="slice",
            deliverable_ref="artifact://pkg-r-2/part-000",
        )
    )
    assert (stored.package_id, stored.contract_hash) == ("pkg-r-2", "ch-r2")
    log = GateAuditLog()
    gate = log.serve_gate("pkg-r-2:part-000", "PASS")
    audit = log.serve_audit(
        "pkg-r-2:part-000", "PASS", "auditor-r2", ("producer-r2",), True
    )
    verdict = gates_close_part(
        {
            "package_id": "pkg-r-2",
            "contract_hash": "ch-r2",
            "gate_verdict_ref": gate.gate_id,
            "audit_verdict_ref": audit.audit_id,
        }
    )
    assert set(verdict) == {
        "package_id",
        "gate",
        "audit",
        "decided_at",
        "evidence_refs",
    }
    assert (verdict["package_id"], verdict["gate"], verdict["audit"]) == (
        "pkg-r-2",
        "PASS",
        "PASS",
    )
    assert verdict["evidence_refs"] == [gate.gate_id, audit.audit_id]


def test_partstore_bad_verdicts_refused_at_record():
    from agent_si.backend.orchestration.parts import PartRecord, PartStore

    store = PartStore()
    store.register(
        PartRecord(
            part_id="pkg-r-3:part-000",
            package_id="pkg-r-3",
            contract_hash="ch",
            agent="agent-1",
            scope="slice",
            deliverable_ref="artifact://pkg-r-3/part-000",
        )
    )
    with pytest.raises(ValueError):
        store.record_gate_verdict("pkg-r-3:part-000", "MAYBE", "gate:x")
    with pytest.raises(ValueError):
        store.record_audit_verdict("pkg-r-3:part-000", "MAYBE", "audit:x")
    with pytest.raises(KeyError):
        store.record_gate_verdict("pkg-r-3:missing", "PASS", "gate:x")


def test_partrecord_inline_deliverable_rejected():
    from agent_si.backend.orchestration.parts import PartRecord

    with pytest.raises(ValueError):
        PartRecord(
            part_id="p",
            package_id="pkg",
            contract_hash="ch",
            agent="a",
            scope="s",
            deliverable_ref="inline-bytes",
        )


def test_ledger_row_frozen_shape_m_p1_17():
    import dataclasses

    from agent_si.backend.orchestration.parts import LedgerRow, PackageLedger

    row = LedgerRow(package_id="pkg-l-1", agents=2, peak_concurrency=2, wall_time_s=3)
    assert {f.name for f in dataclasses.fields(row)} == {
        "package_id",
        "agents",
        "peak_concurrency",
        "wall_time_s",
    }
    assert row.wall_time_s == 3.0 and isinstance(row.wall_time_s, float)
    ledger = PackageLedger()
    ledger.record_row("pkg-l-1", 2, 2, 3.0)
    assert ledger.package_ids() == ["pkg-l-1"]
    with pytest.raises(ValueError):
        LedgerRow(
            package_id="pkg-l-1", agents=True, peak_concurrency=1, wall_time_s=1.0
        )
    with pytest.raises(ValueError):
        LedgerRow(package_id="pkg-l-1", agents=1, peak_concurrency=-1, wall_time_s=1.0)
    with pytest.raises(ValueError):
        LedgerRow(package_id="pkg-l-1", agents=1, peak_concurrency=1, wall_time_s=-0.5)


def test_package_report_nudge_and_no_auto_push():
    from agent_si.backend.orchestration.parts import PackageLedger, package_report

    ledger = PackageLedger()
    ledger.record_row("pkg-l-2", 3, 2, 12.5)
    report = package_report(ledger, "pkg-l-2", "pkg-l-3")
    assert report["row"] == {
        "package_id": "pkg-l-2",
        "agents": 3,
        "peak_concurrency": 2,
        "wall_time_s": 12.5,
    }
    assert "pkg-l-2" in report["nudge"] and "pkg-l-3" in report["nudge"]
    assert report["auto_push"] is False
    plain = package_report(ledger, "pkg-l-2")
    assert "pkg-l-2" in plain["nudge"] and plain["auto_push"] is False
    with pytest.raises(KeyError):
        package_report(ledger, "pkg-l-missing")


def test_ledger_hot_write_roundtrip(tmp_path):
    from agent_si.backend.orchestration.parts import (
        PackageLedger,
        load_ledger,
        package_report,
        persist_ledger,
    )

    ledger = PackageLedger()
    ledger.record_row("pkg-l-4", 2, 2, 4.0)
    ledger.record_row("pkg-l-5", 1, 1, 1.5)
    path = str(tmp_path / "ledger.json")
    persist_ledger(path, ledger)
    loaded = load_ledger(path)
    assert loaded.package_ids() == ["pkg-l-4", "pkg-l-5"]
    assert package_report(loaded, "pkg-l-4")["row"]["wall_time_s"] == 4.0
    assert package_report(loaded, "pkg-l-5", "pkg-l-6")["auto_push"] is False


def test_teamcard_and_decision_shapes_in_parts():
    import dataclasses

    from agent_si.backend.orchestration.parts import (
        ApplyOutcome,
        DecisionLog,
        DecisionRow,
        TeamCard,
    )

    card = TeamCard(
        provider="p",
        model="meta/muse-spark-1.3-contributor",
        model_kb_facts={"part-size-vs-model": "small parts run cheap"},
        budget_left={"units": 5},
        limits={"max_parts": 2},
    )
    assert {f.name for f in dataclasses.fields(card)} == {
        "provider",
        "model",
        "model_kb_facts",
        "budget_left",
        "limits",
    }
    with pytest.raises(ValueError):
        TeamCard(
            provider="p",
            model="other-model",
            model_kb_facts={},
            budget_left={},
            limits={},
        )
    log = DecisionLog()
    first = log.append("scope-a", "do x", "because y", "director-1", "t")
    second = log.append("scope-a", "do z", "because w", "director-1", "t")
    assert isinstance(first, DecisionRow)
    assert (first.decision_id, second.decision_id) == ("scope-a-0001", "scope-a-0002")
    assert {f.name for f in dataclasses.fields(first)} == {
        "decision_id",
        "scope",
        "statement",
        "reason",
        "authority",
        "created_at",
    }
    outcome = ApplyOutcome(accepted=True, reason="applied", row=first)
    assert outcome.row is first and outcome.surfaced == ""
