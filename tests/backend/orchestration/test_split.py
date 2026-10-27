import os, sys; sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__),"..","..","..","src")))
"""ROW93/ROW100 frozen sect. 3: split N disjoint parts, bounded per-part context."""

from hashlib import sha256
from math import ceil

import pytest

from agent_si.backend.orchestration import split as split_mod
from agent_si.backend.orchestration.split import (
    PartRef,
    SCOPE_OVERLAP,
    split_package,
    validate_disjoint,
)


def make_refs(tag, n):
    return [f"artifact://{tag}/scope-{i:03d}" for i in range(n)]


def expected_hash(package_id, goal):
    return sha256((package_id + "\0" + goal).encode("utf-8")).hexdigest()


def scopes_of(parts):
    return [split_mod._GATE_SCOPES[p.gate_verdict_ref] for p in parts]


def test_n_disjoint_parts_cover_all_refs_no_dup_row93():
    refs = make_refs("pkg-s-row93", 6)
    parts = split_package("pkg-s-row93", "row93 goal", refs, 3)
    assert len(parts) == min(3, len(refs)) == 3
    scopes = scopes_of(parts)
    assert all(len(s) > 0 for s in scopes)
    union = set().union(*scopes)
    assert union == set(refs)
    assert sum(len(s) for s in scopes) == len(refs)
    assert validate_disjoint(parts) is None


def test_n_capped_by_ref_count():
    refs = make_refs("pkg-s-cap", 2)
    parts = split_package("pkg-s-cap", "cap goal", refs, 5)
    assert len(parts) == 2
    union = set().union(*scopes_of(parts))
    assert union == set(refs)
    assert validate_disjoint(parts) is None


def test_single_part_covers_all_refs():
    refs = make_refs("pkg-s-one", 4)
    parts = split_package("pkg-s-one", "one goal", refs, 1)
    assert len(parts) == 1
    assert set(scopes_of(parts)[0]) == set(refs)
    assert validate_disjoint(parts) is None


@pytest.mark.parametrize("max_parts", [0, -1, -10])
def test_max_parts_below_one_refused(max_parts):
    with pytest.raises(ValueError):
        split_package("pkg-s-badcap", "goal", make_refs("pkg-s-badcap", 3), max_parts)


def test_empty_refs_refused():
    with pytest.raises(ValueError):
        split_package("pkg-s-empty", "goal", [], 2)


@pytest.mark.parametrize("package_id", ["", "   "])
def test_blank_package_id_refused(package_id):
    with pytest.raises(ValueError):
        split_package(package_id, "goal", make_refs("pkg-s-badid", 2), 2)


@pytest.mark.parametrize("goal", ["", "   "])
def test_blank_goal_refused(goal):
    with pytest.raises(ValueError):
        split_package("pkg-s-badgoal", goal, make_refs("pkg-s-badgoal", 2), 2)


@pytest.mark.parametrize(
    "total,max_parts",
    [(6, 3), (7, 3), (5, 5), (5, 2), (4, 3), (9, 4), (3, 10)],
)
def test_chunk_sizes_differ_by_at_most_one_and_bound_row100(total, max_parts):
    tag = f"pkg-s-row100-{total}-{max_parts}"
    refs = make_refs(tag, total)
    parts = split_package(tag, "row100 goal", refs, max_parts)
    count = min(max_parts, total)
    assert len(parts) == count
    bound = ceil(total / count)
    sizes = [len(s) for s in scopes_of(parts)]
    assert all(size <= bound for size in sizes)
    assert max(sizes) - min(sizes) <= 1
    union = set().union(*scopes_of(parts))
    assert union == set(refs)


def test_contract_hash_identical_for_all_parts_of_one_split():
    tag = "pkg-s-hash"
    parts = split_package(tag, "hash goal", make_refs(tag, 5), 3)
    assert len({p.contract_hash for p in parts}) == 1
    assert parts[0].contract_hash == expected_hash(tag, "hash goal")


def test_verdict_refs_unique_per_part_format():
    tag = "pkg-s-refs"
    parts = split_package(tag, "refs goal", make_refs(tag, 4), 4)
    gates = [p.gate_verdict_ref for p in parts]
    audits = [p.audit_verdict_ref for p in parts]
    assert gates == [f"gate:{tag}:part-{i:03d}" for i in range(4)]
    assert audits == [f"audit:{tag}:part-{i:03d}" for i in range(4)]
    assert len(set(gates)) == 4
    assert len(set(audits)) == 4


def test_registry_records_issuance_per_part():
    tag = "pkg-s-reg"
    refs = make_refs(tag, 3)
    parts = split_package(tag, "reg goal", refs, 3)
    recorded = [split_mod._GATE_SCOPES[p.gate_verdict_ref] for p in parts]
    assert all(isinstance(s, frozenset) for s in recorded)
    assert set().union(*recorded) == set(refs)


def test_parts_carry_package_id():
    tag = "pkg-s-pid"
    parts = split_package(tag, "pid goal", make_refs(tag, 2), 2)
    assert all(p.package_id == tag for p in parts)
    assert all(isinstance(p, PartRef) for p in parts)


def test_shared_ref_across_splits_raises_scope_overlap():
    shared = "artifact://shared/scope-000"
    left = split_package(
        "pkg-s-overlap-a", "goal a", [shared, "artifact://a/scope-001"], 2
    )
    right = split_package(
        "pkg-s-overlap-b", "goal b", [shared, "artifact://b/scope-001"], 2
    )
    with pytest.raises(SCOPE_OVERLAP) as exc:
        validate_disjoint(left + right)
    assert shared in str(exc.value)


def test_duplicate_ref_twice_raises_scope_overlap():
    parts = split_package("pkg-s-dup", "dup goal", make_refs("pkg-s-dup", 2), 2)
    with pytest.raises(SCOPE_OVERLAP):
        validate_disjoint([parts[0], parts[0]])


def test_unknown_ref_raises_value_error():
    ghost = PartRef(
        package_id="pkg-s-ghost",
        contract_hash="deadbeef",
        gate_verdict_ref="gate:pkg-s-ghost:part-999",
        audit_verdict_ref="audit:pkg-s-ghost:part-999",
    )
    with pytest.raises(ValueError):
        validate_disjoint([ghost])


def test_distinct_scopes_b0b_rows():
    tag = "pkg-s-distinct"
    parts = split_package(tag, "distinct goal", make_refs(tag, 6), 3)
    scopes = scopes_of(parts)
    for first in range(len(scopes)):
        for second in range(first + 1, len(scopes)):
            assert scopes[first] != scopes[second]
            assert not (scopes[first] & scopes[second])


def test_decomposition_small_part_uses_cheap_fact_r301():
    from agent_si.backend.orchestration.split import (
        FACT_CHEAP_SMALL_PARTS,
        FACT_PART_SIZE_VS_MODEL,
        KNOWN_FACTS,
        record_decomposition,
    )

    record = record_decomposition("pkg-s-r301:part-000", 3)
    assert record.record_id == "decomp-pkg-s-r301:part-000"
    assert record.route == "cheap-small-part"
    assert record.facts_used == [FACT_PART_SIZE_VS_MODEL, FACT_CHEAP_SMALL_PARTS]
    assert set(record.facts_used) <= set(KNOWN_FACTS)
    assert record.artifact_ref == "ARTIFACT_REF:pkg-s-r301:part-000/decomposition"
    assert record.reason and all(ord(ch) < 128 for ch in record.reason)


def test_decomposition_large_part_routes_long_context():
    from agent_si.backend.orchestration.split import (
        FACT_LONG_CONTEXT_ROUTING,
        FACT_PART_SIZE_VS_MODEL,
        record_decomposition,
    )

    record = record_decomposition("pkg-s-r301:part-001", 100)
    assert record.route == "long-context"
    assert record.facts_used == [FACT_PART_SIZE_VS_MODEL, FACT_LONG_CONTEXT_ROUTING]


def test_decomposition_mid_part_stays_standard():
    from agent_si.backend.orchestration.split import (
        FACT_PART_SIZE_VS_MODEL,
        record_decomposition,
    )

    record = record_decomposition("pkg-s-r301:part-002", 20)
    assert record.route == "standard"
    assert record.facts_used == [FACT_PART_SIZE_VS_MODEL]


def test_decomposition_bad_size_refused():
    from agent_si.backend.orchestration.split import record_decomposition

    with pytest.raises(ValueError):
        record_decomposition("pkg-s-r301:part-003", -1)
    with pytest.raises(ValueError):
        record_decomposition("  ", 3)


def test_teamcard_frozen_shape_and_model_id():
    import dataclasses

    from agent_si.backend.orchestration.split import MODEL_ID, TeamCard

    assert MODEL_ID == "meta/muse-spark-1.3-contributor"
    card = TeamCard(
        provider="p",
        model="meta/muse-spark-1.3-contributor",
        model_kb_facts={"part-size-vs-model": "small parts run cheap"},
        budget_left={"units": 10},
        limits={"max_parts": 4},
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


def test_shared_refs_artifact_or_secret_only():
    from agent_si.backend.orchestration.split import is_shared_ref, make_secret_ref

    assert is_shared_ref("artifact://pkg/ref-000") is True
    assert is_shared_ref("ARTIFACT_REF:pkg/hierarchy") is True
    assert is_shared_ref(make_secret_ref("budget-store")) is True
    assert is_shared_ref("raw-secret-value") is False
    assert is_shared_ref("inline-bytes") is False
    assert is_shared_ref({"other": "x"}) is False
    assert is_shared_ref(None) is False


def test_raw_secret_context_ref_refused():
    with pytest.raises(ValueError):
        split_package(
            "pkg-s-secret", "goal", ["artifact://pkg-s-secret/ok", "raw-secret"], 2
        )


def test_secret_ref_context_ref_accepted():
    from agent_si.backend.orchestration.split import make_secret_ref

    parts = split_package(
        "pkg-s-sref",
        "goal",
        ["artifact://pkg-s-sref/ok", make_secret_ref("budget-store")],
        2,
    )
    assert len(parts) == 2
    assert validate_disjoint(parts) is None


def test_corrections_hash_deterministic_arch705():
    from agent_si.backend.orchestration.split import corrections_hash

    channel = [{"actor": "user", "text": "pause after step two"}]
    assert corrections_hash(channel) == corrections_hash(list(channel))
    assert corrections_hash([]) != corrections_hash(channel)


def test_corrections_issuance_check():
    from agent_si.backend.orchestration.split import (
        corrections_hash,
        issued_corrections_hash,
    )

    channel = [{"actor": "user", "text": "re-split part two"}]
    parts = split_package(
        "pkg-s-arch705",
        "goal",
        make_refs("pkg-s-arch705", 2),
        2,
        corrections=channel,
    )
    assert len(parts) == 2
    assert issued_corrections_hash("pkg-s-arch705") == corrections_hash(channel)
    with pytest.raises(ValueError):
        split_package(
            "pkg-s-arch705-stale",
            "goal",
            make_refs("pkg-s-arch705-stale", 2),
            2,
            corrections=channel,
            expected_corrections_hash="deadbeef",
        )
    ok = split_package(
        "pkg-s-arch705-fresh",
        "goal",
        make_refs("pkg-s-arch705-fresh", 2),
        2,
        corrections=channel,
        expected_corrections_hash=corrections_hash(channel),
    )
    assert len(ok) == 2


def test_hot_write_and_decomposition_roundtrip(tmp_path):
    from agent_si.backend.orchestration.split import (
        hot_write_text,
        load_decompositions,
        persist_decompositions,
        record_decomposition,
    )

    target = str(tmp_path / "split.txt")
    hot_write_text(target, "served\n")
    with open(target, encoding="utf-8") as handle:
        assert handle.read() == "served\n"
    records = [
        record_decomposition("pkg-s-hw:part-000", 3),
        record_decomposition("pkg-s-hw:part-001", 100),
    ]
    report = str(tmp_path / "decomp.json")
    persist_decompositions(report, records)
    loaded = load_decompositions(report)
    assert [r.record_id for r in loaded] == [r.record_id for r in records]
    assert [r.facts_used for r in loaded] == [r.facts_used for r in records]
    assert [r.artifact_ref for r in loaded] == [r.artifact_ref for r in records]
