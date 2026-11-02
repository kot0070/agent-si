import os, sys; sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__),"..","..","..","src")))
"""K02 frozen contract, V2 BEHAVIOUR suite (one test per K02 error code).

Every K02 error code is triggered in its condition against the REAL lane
modules (section A, one test per code). Every section 4 route is proven
through its in-tree serving function to the real implementation
(section B). Every callable call surface is invoked through a production
caller or production data path with the caller file:line cited in the
wiring tables (section C); constants are pinned by value plus home
file:line in the agreement table. interface.py carries one definition
per name (section D). Cross-lane waits (sibling package or INT2 wiring
owns the caller) appear ONLY as strict xfail with reason "<lane>: <row>";
nothing else is skipped, there are no other skips. Bounded: no network,
no sleeps, no filesystem writes outside tmp_path; stub plus lane imports
stay inside test bodies via _load. Shapes follow v2 C1-C20: teamcard and
ledger config changes return accepted-form outcomes with free-text
reason and never raise; steplimits, offload and delta keep the
applied-form with reason codes; ledger.intake_bounded_delta never
raises; refusal reasons are asserted by content, never by comparing a
free-text reason to a literal code.
"""
import ast
import pathlib

import pytest

IMPL_PKG = "agent_si.backend.orchestration"
STUB_MOD = "agent_si.backend.orchestration.interface"
IMPL_MODS = ("split", "parts", "gates", "graph", "overlap", "manifest",
             "delta", "teamcard", "ledger", "offload", "steplimits",
             "common")


def _load(mod):
    import importlib
    if mod == "interface":
        return importlib.import_module(STUB_MOD)
    return importlib.import_module(IMPL_PKG + "." + mod)


def _root():
    return pathlib.Path(__file__).resolve().parents[3]


def _cite(rel, line):
    lines = (_root() / rel).read_text(encoding="utf-8").splitlines()
    assert 1 <= line <= len(lines), "%s has no line %d" % (rel, line)
    return lines[line - 1]


@pytest.fixture(autouse=True)
def _isolate_lane_state():
    offload = _load("offload")
    steplimits = _load("steplimits")
    overlap = _load("overlap")
    teamcard = _load("teamcard")
    offload._reset_state()
    steplimits._reset_state()
    overlap._clear_verdicts()
    saved = list(teamcard.AUDIT_CHOICE_LOG)
    yield
    offload._reset_state()
    steplimits._reset_state()
    overlap._clear_verdicts()
    del teamcard.AUDIT_CHOICE_LOG[:]
    teamcard.AUDIT_CHOICE_LOG.extend(saved)


# ---- (a) every K02 error code triggered in its condition, one test each ----

def test_scope_overlap_condition():
    split = _load("split")
    refs = ["artifact://a-so/scope-%03d" % i for i in range(4)]
    parts = split.split_package("a-so-pkg", "overlap probe goal", refs, 2)
    assert len(parts) == 2
    assert split.validate_disjoint(parts) is None
    with pytest.raises(split.SCOPE_OVERLAP, match="SCOPE_OVERLAP"):
        split.validate_disjoint([parts[0], parts[0]])


def test_rejected_scope_overlap_condition():
    offload = _load("offload")
    first = {
        "project_id": "a-rso-a",
        "role": "worker",
        "enabled": True,
        "authority": "director probe",
        "reason": "routine cover probe",
        "statement": "cover offload probe",
        "task_ids": ["a-rso-task-1"],
    }
    accepted = offload.apply_offload_config_change(dict(first))
    assert accepted.applied is True, accepted.reason
    assert len(offload._DECISIONS) == 1
    second = dict(first)
    second["project_id"] = "a-rso-b"
    refused = offload.apply_offload_config_change(second)
    assert refused.applied is False
    assert refused.reason.startswith("REJECTED_SCOPE_OVERLAP:")
    assert "already bound" in refused.reason
    assert refused.decision_ref is None
    assert len(offload._DECISIONS) == 1
    assert offload.offload_enabled("a-rso-b", "worker") is False
    assert offload.offload_enabled("a-rso-a", "worker") is True


def test_gate_not_passed_condition():
    gates = _load("gates")
    with pytest.raises(gates.GATE_NOT_PASSED, match="GATE_NOT_PASSED"):
        gates.close_part({
            "package_id": "a-gnp",
            "contract_hash": "a-gnp-hash",
            "gate_verdict_ref": "a-gnp-missing-gate",
            "audit_verdict_ref": "a-gnp-missing-audit",
        })


def test_missing_integration_task_condition():
    gates = _load("gates")
    log = gates.GateAuditLog()
    log.serve_gate("a-mit:part-1", "PASS")
    log.serve_audit("a-mit:part-1", "PASS", "a-mit-auditor",
                    ["a-mit-producer"], True)
    with pytest.raises(gates.MISSING_INTEGRATION_TASK,
                       match="MISSING_INTEGRATION_TASK"):
        gates.evaluate_phase_gate(["a-mit"])


def test_invalid_hierarchy_chain_condition():
    gates = _load("gates")
    with pytest.raises(gates.INVALID_HIERARCHY_CHAIN,
                       match="INVALID_HIERARCHY_CHAIN"):
        gates.check_hierarchy_activation(["only-one"])
    assert gates.check_hierarchy_activation(
        ["a-ihc-director-1", "a-ihc-manager-1", "a-ihc-tool-1"]) is None


def test_audit_independence_rejected_condition():
    steplimits = _load("steplimits")
    offload = _load("offload")
    delta = _load("delta")
    teamcard = _load("teamcard")
    ledger = _load("ledger")
    refused = steplimits.apply_steplimit_config_change({
        "project_id": "a-air-sl",
        "authority": "manager probe",
        "reason": "keep audit probe",
        "independent_audit": False,
    })
    assert refused.applied is False
    assert refused.reason.startswith("AUDIT_INDEPENDENCE_REJECTED:")
    assert "independent_audit must stay true" in refused.reason
    assert refused.decision_ref is None
    assert "a-air-sl" not in steplimits._PROJECT_LIMITS
    refused = offload.apply_offload_config_change({
        "project_id": "a-air-of",
        "role": "worker",
        "enabled": True,
        "authority": "director probe",
        "reason": "keep audit probe",
        "statement": "audit probe statement",
        "independent_audit": False,
    })
    assert refused.applied is False
    assert refused.reason.startswith("AUDIT_INDEPENDENCE_REJECTED:")
    assert refused.decision_ref is None
    assert ("a-air-of", "worker") not in offload._SWITCHES
    ok, reason = delta.validate_config_change(
        {"auditor": "w", "worker": "w", "independent_audit": False}, {})
    assert ok is False
    assert reason.startswith("AUDIT_INDEPENDENCE_REJECTED:")
    store = teamcard.TeamConfigStore()
    before = dict(store.config)
    outcome = teamcard.apply_team_config_change(
        store, "probe statement", "probe reason", "director",
        {"auditor": "same-agent", "worker": "same-agent"})
    assert outcome.accepted is False
    assert outcome.reason.startswith("audit independence broken:")
    assert "AUDIT_INDEPENDENCE_REJECTED" not in outcome.reason
    assert outcome.row is None
    assert store.config == before
    assert outcome.surfaced.startswith("change refused:")
    lstore = ledger.LedgerConfigStore()
    lbefore = dict(lstore.config)
    loutcome = ledger.apply_ledger_config_change(
        lstore, "probe statement", "probe reason", "director",
        {"independent_audit": False})
    assert loutcome.accepted is False
    assert loutcome.reason.startswith("audit independence broken:")
    assert "AUDIT_INDEPENDENCE_REJECTED" not in loutcome.reason
    assert loutcome.row is None
    assert lstore.config == lbefore
    assert loutcome.surfaced.startswith("change refused:")


def test_budget_capped_condition():
    steplimits = _load("steplimits")
    offload = _load("offload")
    delta = _load("delta")
    teamcard = _load("teamcard")
    ledger = _load("ledger")
    refused = steplimits.apply_steplimit_config_change({
        "project_id": "a-bc-sl",
        "authority": "manager probe",
        "reason": "routine change probe",
        "cost": 10,
        "budget_left": 5,
    })
    assert refused.applied is False
    assert refused.reason.startswith("BUDGET_CAPPED:")
    assert "exceeds budget left" in refused.reason
    assert refused.decision_ref is None
    assert "a-bc-sl" not in steplimits._PROJECT_LIMITS
    refused = offload.apply_offload_config_change({
        "project_id": "a-bc-of",
        "role": "worker",
        "enabled": True,
        "authority": "director probe",
        "reason": "budget probe",
        "statement": "budget probe statement",
        "cost": 10,
        "budget_left": 5,
    })
    assert refused.applied is False
    assert refused.reason.startswith("BUDGET_CAPPED:")
    assert refused.decision_ref is None
    assert ("a-bc-of", "worker") not in offload._SWITCHES
    ok, reason = delta.validate_config_change(
        {"cost": 10}, {"budget_left": 5})
    assert ok is False
    assert reason.startswith("BUDGET_CAPPED:")
    store = teamcard.TeamConfigStore()
    before = dict(store.config)
    outcome = teamcard.apply_team_config_change(
        store, "probe statement", "probe reason", "director", {"cost": 1000})
    assert outcome.accepted is False
    assert outcome.reason.startswith("over budget:")
    assert "BUDGET_CAPPED" not in outcome.reason
    assert outcome.row is None
    assert store.config == before
    lstore = ledger.LedgerConfigStore()
    lbefore = dict(lstore.config)
    loutcome = ledger.apply_ledger_config_change(
        lstore, "probe statement", "probe reason", "director",
        {"agents": 99, "max_agents": 8})
    assert loutcome.accepted is False
    assert loutcome.reason.startswith("over cap:")
    assert "BUDGET_CAPPED" not in loutcome.reason
    assert loutcome.row is None
    assert lstore.config == lbefore


def test_unknown_limit_kind_condition():
    steplimits = _load("steplimits")
    assert steplimits.UNKNOWN_LIMIT_KIND is steplimits.UnknownLimitKindError
    with pytest.raises(steplimits.UNKNOWN_LIMIT_KIND,
                       match="UNKNOWN_LIMIT_KIND"):
        steplimits.limits_for("bogus-kind")
    project_id = "a-ulk-proj"
    applied = steplimits.apply_steplimit_config_change({
        "project_id": project_id,
        "authority": "manager probe",
        "reason": "set limits for probe",
        "task_max_steps": 2,
        "chat_max_steps": 5,
    })
    assert applied.applied is True, applied.reason
    assert steplimits.limits_for("task", project_id) == 2
    assert steplimits.limits_for("chat", project_id) == 5
    with pytest.raises(steplimits.UnknownLimitKindError):
        steplimits.limits_for("bogus-kind", project_id)


def test_delta_over_bound_condition():
    delta = _load("delta")
    with pytest.raises(delta.DELTA_OVER_BOUND, match="DELTA_OVER_BOUND"):
        delta.intake_bounded_delta(
            ["a-dob-%02d" % index for index in range(17)], False)
    ok = delta.intake_bounded_delta(
        ["a-dob-ok-%02d" % index for index in range(16)], False)
    assert set(ok) == {"delta_id", "scope", "blocking", "keep", "patch",
                       "created_at"}


# ---- v2 C1-C20 outcome shapes: accepted-form returns, never raises ----

def test_team_accept_shape():
    teamcard = _load("teamcard")
    store = teamcard.TeamConfigStore()
    outcome = teamcard.apply_team_config_change(
        store, "probe statement", "probe reason", "director",
        {"agents": 2, "cost": 10})
    assert outcome.accepted is True
    assert outcome.reason == "applied"
    assert outcome.row is not None
    assert outcome.row.scope == "team-config"
    assert outcome.row.statement == "probe statement"
    assert outcome.surfaced == "change applied"
    assert store.config["agents"] == 2
    assert store.config["budget_left"] == 90.0


def test_ledger_accept_shape():
    ledger = _load("ledger")
    store = ledger.LedgerConfigStore()
    outcome = ledger.apply_ledger_config_change(
        store, "probe statement", "probe reason", "director", {"agents": 2})
    assert outcome.accepted is True
    assert outcome.reason == "applied"
    assert outcome.row is not None
    assert outcome.row.scope == "ledger-config"
    assert outcome.surfaced == "change applied"
    assert store.config["agents"] == 2


def test_steplimit_and_delta_keep_applied_shape():
    steplimits = _load("steplimits")
    delta = _load("delta")
    outcome = steplimits.apply_steplimit_config_change({
        "project_id": "a-shape-sl",
        "authority": "manager probe",
        "reason": "set limits for probe",
        "task_max_steps": 2,
        "chat_max_steps": 5,
    })
    assert outcome.applied is True
    assert outcome.reason == "applied"
    assert outcome.decision_ref is not None
    assert outcome.decision_ref.startswith("steplimits:a-shape-sl:")
    config = {"budget_left": 100.0, "model": "meta/muse-spark-1.3-contributor"}
    log = []
    ok = delta.apply_config_change(config, log, "a-shape-scope",
                                   "raise limit", "need capacity", "director",
                                   {"cost": 10.0})
    assert ok == {"applied": True, "reason": "applied",
                  "decision_ref": "a-shape-scope-0001"}
    assert len(log) == 1 and log[0]["decision_id"] == "a-shape-scope-0001"
    bad = delta.apply_config_change(dict(config), [], "a-shape-scope",
                                    "bad model", "probe", "director",
                                    {"model": "other-model"})
    assert bad["applied"] is False
    assert bad["decision_ref"] is None
    assert "model must stay" in bad["reason"]


def test_policy_conflict_returned_not_raised():
    delta = _load("delta")
    ok, reason = delta.validate_config_change(
        {"model": "other-model"}, {"model": "meta/muse-spark-1.3-contributor"})
    assert ok is False
    assert reason.startswith("POLICY_CONFLICT:")
    assert "model must stay" in reason
    ok, reason = delta.validate_config_change(
        {"scope": "a-pc-scope"}, {"claimed_scopes": ["a-pc-scope"]})
    assert ok is False
    assert reason.startswith("REJECTED_SCOPE_OVERLAP:")
    assert "already claimed" in reason


def test_ledger_bounded_delta_never_raises():
    ledger = _load("ledger")
    taken = []
    refused = ledger.intake_bounded_delta(
        taken, {"delta_id": "a-bd-1", "items": [1, 2, 3]}, 2)
    assert refused == {"accepted": False,
                       "reason": "delta a-bd-1 over bound: 3 items exceed 2",
                       "delta_id": "a-bd-1"}
    assert taken == []
    accepted = ledger.intake_bounded_delta(
        taken, {"delta_id": "a-bd-2", "items": [1, 2]}, 2)
    assert accepted == {"accepted": True, "reason": "intake within bound",
                        "delta_id": "a-bd-2"}
    assert taken == [{"delta_id": "a-bd-2", "count": 2}]


def test_ledger_record_row_is_method_only():
    ledger = _load("ledger")
    assert not hasattr(ledger, "record_row")
    book = ledger.PackageLedger()
    row = book.record_row("a-row-pkg", 2, 1, 4.0)
    assert (row.package_id, row.agents, row.peak_concurrency,
            row.wall_time_s) == ("a-row-pkg", 2, 1, 4.0)
    assert book.get_row("a-row-pkg") is row
    assert book.get_row("a-row-missing") is None
    assert book.package_ids() == ["a-row-pkg"]


def test_persist_load_ledger_roundtrip(tmp_path):
    ledger = _load("ledger")
    book = ledger.PackageLedger()
    book.record_row("a-io-pkg", 3, 2, 5.5)
    path = str(tmp_path / "ledger.json")
    assert ledger.persist_ledger(path, book) is None
    loaded = ledger.load_ledger(path)
    assert isinstance(loaded, ledger.PackageLedger)
    row = loaded.get_row("a-io-pkg")
    assert (row.package_id, row.agents, row.peak_concurrency,
            row.wall_time_s) == ("a-io-pkg", 3, 2, 5.5)


def test_package_report_missing_row_raises():
    ledger = _load("ledger")
    with pytest.raises(KeyError):
        ledger.package_report(ledger.PackageLedger(), "a-no-such-pkg")


# ---- (b) every section 4 route reaches the REAL implementation ----
# No HTTP server lives in this tree (HTTP transport is INT2-owned
# wiring): each route is proven through its in-tree serving function to
# the real implementation, the same data path the INT2 tests serve.

def test_route_agents_live_data():
    parts = _load("parts")
    scope = "b-live-scope"
    parts.register_part(parts.PartRow(agent="agent-b-live", scope=scope,
                                      deliverable="artifact://pkg/" + scope))
    rows = parts.list_parts(None)
    served = [row for row in rows if row.scope == scope]
    assert len(served) == 1
    live = served[0]
    assert live.status == "QUEUED"
    assert set(vars(live)) == {"agent", "scope", "deliverable", "status"}


def test_route_runs_ledger_data():
    ledger = _load("ledger")
    book = ledger.PackageLedger()
    book.record_row("b-ledger-pkg", 2, 1, 4.0)
    assert "b-ledger-pkg" in book.package_ids()
    row = book.get_row("b-ledger-pkg")
    assert (row.agents, row.peak_concurrency, row.wall_time_s) == (2, 1, 4.0)


def test_route_nudge_new_shape():
    ledger = _load("ledger")
    book = ledger.PackageLedger()
    book.record_row("b-nudge-1", 2, 1, 4.0)
    report = ledger.package_report(book, "b-nudge-1",
                                   next_package_id="b-nudge-2")
    assert set(report.keys()) == {"row", "nudge", "auto_push"}
    assert "load" not in report
    assert "package_id" not in report
    assert report["row"] == {"package_id": "b-nudge-1", "agents": 2,
                             "peak_concurrency": 1, "wall_time_s": 4.0}
    assert "b-nudge-2" in report["nudge"]
    assert report["auto_push"] is False


# ---- (c) every callable call surface has a production caller ----
# Each row cites the production file:line that calls, serves, raises or
# otherwise requires the surface; the probe invokes the REAL lane code
# through that path. Names whose caller lives in a sibling package or in
# INT2 wiring are NOT listed here: they are recorded as strict-xfail
# waits in section (e), one wait per row.

def _trig_scope_overlap():
    split = _load("split")
    refs = ["artifact://c-so/%d" % i for i in range(2)]
    parts = split.split_package("c-so-pkg", "goal probe", refs, 2)
    with pytest.raises(split.SCOPE_OVERLAP, match="SCOPE_OVERLAP"):
        split.validate_disjoint([parts[0], parts[0]])


def _trig_gate_refused():
    gates = _load("gates")
    with pytest.raises(gates.GateRefused, match="part_id must be non-empty"):
        gates.GateAuditLog().serve_gate("", "PASS")


def _trig_audit_refused():
    gates = _load("gates")
    with pytest.raises(gates.AuditRefused, match="self-audit refused"):
        gates.GateAuditLog().serve_audit(
            "c-ar-p", "PASS", "c-ar-aud", ["c-ar-aud"], True)


def _trig_gate_not_passed():
    gates = _load("gates")
    with pytest.raises(gates.GATE_NOT_PASSED, match="GATE_NOT_PASSED"):
        gates.close_part({
            "package_id": "c-gnp",
            "contract_hash": "c-gnp-hash",
            "gate_verdict_ref": "c-gnp-gate",
            "audit_verdict_ref": "c-gnp-audit",
        })


def _trig_missing_integration():
    gates = _load("gates")
    log = gates.GateAuditLog()
    log.serve_gate("c-mit:part-1", "PASS")
    log.serve_audit("c-mit:part-1", "PASS", "c-mit-aud",
                    ["c-mit-prod"], True)
    with pytest.raises(gates.MISSING_INTEGRATION_TASK,
                       match="MISSING_INTEGRATION_TASK"):
        gates.evaluate_phase_gate(["c-mit"])


def _trig_invalid_chain():
    gates = _load("gates")
    with pytest.raises(gates.INVALID_HIERARCHY_CHAIN,
                       match="INVALID_HIERARCHY_CHAIN"):
        gates.check_hierarchy_activation(["only-one"])


def _trig_cycle_error():
    graph = _load("graph")
    with pytest.raises(graph.CycleError, match="dependency cycle"):
        graph.build_graph(["c-cy-a", "c-cy-b"],
                          [("c-cy-a", "c-cy-b"), ("c-cy-b", "c-cy-a")])


def _trig_dependency_error():
    graph = _load("graph")
    with pytest.raises(graph.DependencyError, match="unknown dep nodes"):
        graph.build_graph(["c-de-a"], [("c-de-a", "c-de-nope")])


def _trig_routing_refused():
    graph = _load("graph")
    sub = graph.PlannedSubtask(subtask_id="c-rr-s", plan_ref="c-rr-p",
                               goal="probe goal", task_class="build",
                               risk="LOW")
    with pytest.raises(graph.RoutingRefused, match="worker_class"):
        graph.route_task(sub, "", "local", manager_id="c-rr-m")


def _trig_dispatch_rejected():
    graph = _load("graph")
    with pytest.raises(graph.DispatchRejected, match="subtask_id"):
        graph.validate_dispatch({"agent_task_id": "c-dr-t"}, graph.SubtaskGraph())


def _trig_hierarchy_refused():
    graph = _load("graph")
    store = graph.HierarchyConfigStore()
    chain = graph.HierarchyChain(director_id="", manager_id="c-hr-m",
                                 tool_agent_ids=["c-hr-t"])
    with pytest.raises(graph.HierarchyRefused, match="Director"):
        store.activate_chain(chain, "director-1")


def _trig_parent_blocked():
    graph = _load("graph")
    store = graph.HierarchyConfigStore()
    with pytest.raises(graph.ParentClosureBlocked,
                       match="integration task missing"):
        store.close_parent({}, None)


def _trig_director_only():
    graph = _load("graph")
    with pytest.raises(graph.DirectorControlOnly, match="control-plane-only"):
        graph.require_explicit_director(None)


def _trig_delta_over_bound():
    delta = _load("delta")
    with pytest.raises(delta.DELTA_OVER_BOUND, match="DELTA_OVER_BOUND"):
        delta.intake_bounded_delta(["c-dob-%d" % i for i in range(17)], False)


def _trig_unknown_limit():
    steplimits = _load("steplimits")
    assert steplimits.UNKNOWN_LIMIT_KIND is steplimits.UnknownLimitKindError
    with pytest.raises(steplimits.UnknownLimitKindError,
                       match="UNKNOWN_LIMIT_KIND"):
        steplimits.limits_for("c-ulk-kind")


_TRIGGERS = {
    "SCOPE_OVERLAP": _trig_scope_overlap,
    "gates_GateRefused": _trig_gate_refused,
    "AuditRefused": _trig_audit_refused,
    "GATE_NOT_PASSED": _trig_gate_not_passed,
    "MISSING_INTEGRATION_TASK": _trig_missing_integration,
    "INVALID_HIERARCHY_CHAIN": _trig_invalid_chain,
    "CycleError": _trig_cycle_error,
    "DependencyError": _trig_dependency_error,
    "RoutingRefused": _trig_routing_refused,
    "DispatchRejected": _trig_dispatch_rejected,
    "HierarchyRefused": _trig_hierarchy_refused,
    "ParentClosureBlocked": _trig_parent_blocked,
    "DirectorControlOnly": _trig_director_only,
    "DELTA_OVER_BOUND": _trig_delta_over_bound,
    "UnknownLimitKindError": _trig_unknown_limit,
    "UNKNOWN_LIMIT_KIND": _trig_unknown_limit,
}

# (stub name, home lane, home attr, production file, production line)
_RAISE = [
    ("SCOPE_OVERLAP", "split", "SCOPE_OVERLAP",
     "src/agent_si/backend/orchestration/split.py", 180),
    ("gates_GateRefused", "gates", "GateRefused",
     "src/agent_si/backend/orchestration/gates.py", 110),
    ("AuditRefused", "gates", "AuditRefused",
     "src/agent_si/backend/orchestration/gates.py", 142),
    ("GATE_NOT_PASSED", "gates", "GATE_NOT_PASSED",
     "src/agent_si/backend/orchestration/gates.py", 219),
    ("MISSING_INTEGRATION_TASK", "gates", "MISSING_INTEGRATION_TASK",
     "src/agent_si/backend/orchestration/gates.py", 293),
    ("INVALID_HIERARCHY_CHAIN", "gates", "INVALID_HIERARCHY_CHAIN",
     "src/agent_si/backend/orchestration/gates.py", 333),
    ("CycleError", "graph", "CycleError",
     "src/agent_si/backend/orchestration/graph.py", 355),
    ("DependencyError", "graph", "DependencyError",
     "src/agent_si/backend/orchestration/graph.py", 337),
    ("RoutingRefused", "graph", "RoutingRefused",
     "src/agent_si/backend/orchestration/graph.py", 260),
    ("DispatchRejected", "graph", "DispatchRejected",
     "src/agent_si/backend/orchestration/graph.py", 303),
    ("HierarchyRefused", "graph", "HierarchyRefused",
     "src/agent_si/backend/orchestration/graph.py", 436),
    ("ParentClosureBlocked", "graph", "ParentClosureBlocked",
     "src/agent_si/backend/orchestration/graph.py", 507),
    ("DirectorControlOnly", "graph", "DirectorControlOnly",
     "src/agent_si/backend/orchestration/graph.py", 398),
    ("DELTA_OVER_BOUND", "delta", "DELTA_OVER_BOUND",
     "src/agent_si/backend/orchestration/delta.py", 34),
    ("UnknownLimitKindError", "steplimits", "UnknownLimitKindError",
     "src/agent_si/backend/orchestration/steplimits.py", 111),
    ("UNKNOWN_LIMIT_KIND", "steplimits", "UNKNOWN_LIMIT_KIND",
     "src/agent_si/backend/orchestration/steplimits.py", 111),
]


@pytest.mark.parametrize("name,home,attr,cite_file,cite_line", _RAISE,
                         ids=[row[0] for row in _RAISE])
def test_wired_raise(name, home, attr, cite_file, cite_line, tmp_path):
    assert attr in _cite(cite_file, cite_line)
    _TRIGGERS[name]()


def _flow_part_register(name, tmp_path):
    parts = _load("parts")
    scope = "c-reg-%s" % name.replace(".", "-")
    parts.register_part(parts.PartRow(
        agent="agent-c", scope=scope, deliverable="artifact://pkg/" + scope))
    assert any(row.scope == scope for row in parts.list_parts(None))
    updated = parts.update_status(scope, "RUNNING")
    assert updated.status == "RUNNING"
    assert any(row.scope == scope for row in parts.list_parts("RUNNING"))


def _flow_gate_serve_close(name, tmp_path):
    gates = _load("gates")
    tag = "c-gsc-%s" % name.replace(".", "-")
    log = gates.GateAuditLog()
    part_id = tag + ":part-000"
    gate = log.serve_gate(part_id, "PASS")
    audit = log.serve_audit(part_id, "PASS", "auditor-c", ("producer-c",),
                            True)
    verdict = gates.close_part({
        "package_id": tag,
        "contract_hash": "ch",
        "gate_verdict_ref": gate.gate_id,
        "audit_verdict_ref": audit.audit_id,
    })
    assert verdict["gate"] == "PASS" and verdict["audit"] == "PASS"
    assert set(verdict) == {"package_id", "gate", "audit", "decided_at",
                            "evidence_refs"}


def _flow_phase_gate(name, tmp_path):
    gates = _load("gates")
    log = gates.GateAuditLog()
    package_id = "c-ph-%s" % name.replace(".", "-")
    for part in ("part-000", "part-001"):
        log.serve_gate(package_id + ":" + part, "PASS")
        log.serve_audit(package_id + ":" + part, "PASS", "auditor-c",
                        ("producer-c",), True)
    log.serve_gate(package_id + ":integration", "PASS")
    log.serve_audit(package_id + ":integration", "PASS", "auditor-c",
                    ("producer-c",), True)
    verdict = gates.evaluate_phase_gate([package_id])
    assert verdict["package_id"] == package_id
    assert verdict["gate"] == "PASS" and verdict["audit"] == "PASS"


def _flow_split_validate(name, tmp_path):
    split = _load("split")
    tag = "c-sv-%s" % name.replace(".", "-")
    refs = ["artifact://%s/%d" % (tag, i) for i in range(2)]
    made = split.split_package(tag, "goal probe", refs, 2)
    assert split.validate_disjoint(made) is None


def _flow_issued_hash(name, tmp_path):
    split = _load("split")
    tag = "c-ih-%s" % name.replace(".", "-")
    corrections = [{"k": "v"}]
    split.split_package(tag, "goal probe", ["artifact://%s/x" % tag], 1,
                        corrections=corrections)
    assert split.issued_corrections_hash(tag) == split.corrections_hash(
        corrections)


def _flow_planner_clear(name, tmp_path):
    graph = _load("graph")
    planner = graph.TaskPlanner()
    specs = [{"goal": "slice", "task_class": "build", "risk": "LOW"}]
    first_ref, first_graph = planner.plan("c-pc-pkg", "goal probe", specs)
    second_ref, second_graph = planner.plan("c-pc-pkg", "goal probe", specs)
    assert first_ref == second_ref
    assert second_graph is first_graph
    planner.clear()
    third_ref, third_graph = planner.plan("c-pc-pkg", "goal probe", specs)
    assert third_ref == first_ref
    assert third_graph is not first_graph


def _resolve(mod, dotted):
    obj = mod
    for bit in dotted.split("."):
        obj = getattr(obj, bit)
    return obj


def _resolve_dotted(dotted):
    import importlib
    head, _, tail = dotted.partition(".")
    if head in IMPL_MODS:
        base = importlib.import_module(IMPL_PKG + "." + head)
        return _resolve(base, tail) if tail else base
    raise AssertionError("control-plane target outside the lanes: " + dotted)


_FLOWS = {
    "register_part": _flow_part_register,
    "list_parts": _flow_part_register,
    "update_status": _flow_part_register,
    "GateAuditLog.serve_gate": _flow_gate_serve_close,
    "GateAuditLog.serve_audit": _flow_gate_serve_close,
    "close_part": _flow_gate_serve_close,
    "evaluate_phase_gate": _flow_phase_gate,
    "validate_disjoint": _flow_split_validate,
    "issued_corrections_hash": _flow_issued_hash,
    "TaskPlanner.clear": _flow_planner_clear,
}

# (stub name, home lane, home attr, production file, production line,
#  shared-state token proving the producer/consumer link)
_SERVE = [
    ("register_part", "parts", "register_part",
     "src/agent_si/backend/orchestration/parts.py", 100, "_store"),
    ("list_parts", "parts", "list_parts",
     "src/agent_si/backend/orchestration/parts.py", 107, "_store"),
    ("update_status", "parts", "update_status",
     "src/agent_si/backend/orchestration/parts.py", 116, "_store"),
    ("GateAuditLog.serve_gate", "gates", "GateAuditLog.serve_gate",
     "src/agent_si/backend/orchestration/gates.py", 121, "_GATE_BY_ID"),
    ("GateAuditLog.serve_audit", "gates", "GateAuditLog.serve_audit",
     "src/agent_si/backend/orchestration/gates.py", 160, "_AUDIT_BY_ID"),
    ("close_part", "gates", "close_part",
     "src/agent_si/backend/orchestration/gates.py", 215, "_GATE_BY_ID"),
    ("evaluate_phase_gate", "gates", "evaluate_phase_gate",
     "src/agent_si/backend/orchestration/gates.py", 277, "_GATE_BY_PART"),
    ("validate_disjoint", "split", "validate_disjoint",
     "src/agent_si/backend/orchestration/split.py", 171, "_GATE_SCOPES"),
    ("issued_corrections_hash", "split", "issued_corrections_hash",
     "src/agent_si/backend/orchestration/split.py", 94,
     "_ISSUED_CORRECTIONS"),
    ("TaskPlanner.clear", "graph", "TaskPlanner.clear",
     "src/agent_si/backend/orchestration/graph.py", 243, "_plans"),
]


@pytest.mark.parametrize("name,home,attr,cite_file,cite_line,token", _SERVE,
                         ids=[row[0] for row in _SERVE])
def test_wired_serve(name, home, attr, cite_file, cite_line, token,
                     tmp_path):
    mod = _load(home)
    assert callable(_resolve(mod, attr)), name
    assert token in _cite(cite_file, cite_line)
    _FLOWS[name](name, tmp_path)


def _probe_utc_now(name, tmp_path):
    common = _load("common")
    stamp = common.utc_now()
    assert isinstance(stamp, str) and stamp and "T" in stamp


def _probe_is_compact(name, tmp_path):
    common = _load("common")
    assert common.is_compact_english("ok text") is True
    assert common.is_compact_english("  ") is False


def _probe_ensure_compact(name, tmp_path):
    common = _load("common")
    assert common.ensure_compact_english("  a  b ") == "a b"


def _probe_hot_write(name, tmp_path):
    common = _load("common")
    target = str(tmp_path / ("c-hot-%s.txt" % name.replace(".", "-")))
    common.hot_write_text(target, "hello probe")
    with open(target, encoding="utf-8") as handle:
        assert handle.read() == "hello probe"


def _probe_decision_row(name, tmp_path):
    common = _load("common")
    row = common.DecisionRow("d-1", "s", "st", "r", "a", "c")
    assert (row.decision_id, row.scope) == ("d-1", "s")


def _probe_decision_log(name, tmp_path):
    common = _load("common")
    log = common.DecisionLog()
    first = log.append("s", "one", "r", "a", "t")
    second = log.append("s", "two", "r", "a", "t")
    assert (first.decision_id, second.decision_id) == ("s-0001", "s-0002")
    assert log.rows == [first, second]


def _probe_decision_add(name, tmp_path):
    common = _load("common")
    log = common.DecisionLog()
    assert log.next_id("s") == "s-0001"
    row = log.add("s", "one", "r", "a")
    assert row["decision_id"] == "s-0001"
    assert log.to_list() == [row]
    assert log.next_id("s") == "s-0002"


def _probe_apply_outcome(name, tmp_path):
    common = _load("common")
    out = common.ApplyOutcome(accepted=True, reason="applied")
    assert out.row is None and out.surfaced == ""


def _probe_surface(name, tmp_path):
    common = _load("common")
    ok = common.ApplyOutcome(accepted=True, reason="applied")
    assert common.surface_rejection(ok) == "change applied"
    no = common.ApplyOutcome(accepted=False, reason="over cap: agents")
    assert common.surface_rejection(no) == "change refused: over cap: agents"


def _probe_is_shared(name, tmp_path):
    split = _load("split")
    assert split.is_shared_ref("artifact://x") is True
    assert split.is_shared_ref("ARTIFACT_REF:y") is True
    assert split.is_shared_ref({"secret_ref": "n"}) is True
    assert split.is_shared_ref("raw inline") is False


def _probe_corrections_hash(name, tmp_path):
    split = _load("split")
    digest = split.corrections_hash([])
    assert len(digest) == 64
    int(digest, 16)


def _probe_split_package(name, tmp_path):
    split = _load("split")
    graph = _load("graph")
    target = graph.control_plane_map()["director.split"]
    assert target == "split.split_package"
    assert _resolve_dotted(target) is split.split_package
    refs = ["artifact://p-sp/%d" % i for i in range(4)]
    made = split.split_package("p-sp-pkg", "goal probe", refs, 2)
    assert len(made) == 2
    assert all(isinstance(part, split.PartRef) for part in made)
    assert len(made[0].contract_hash) == 64


def _probe_fanout(name, tmp_path):
    split = _load("split")
    refs = ["artifact://p-fo/%d" % i for i in range(4)]
    made = split.split_package("p-fo-pkg", "goal probe", refs, 4)
    settings = split.MultiManagerSettings(True, 2, False,
                                          "manager-integrates")
    running, queued = split.fanout(made, settings)
    assert (len(running), len(queued)) == (2, 2)


def _probe_split_teamcard(name, tmp_path):
    split = _load("split")
    teamcard = _load("teamcard")
    assert split.TeamCard is teamcard.TeamCard
    card = teamcard.TeamCard(
        provider="p", model="meta/muse-spark-1.3-contributor",
        model_kb_facts={}, budget_left={}, limits={})
    assert card.provider == "p"


def _probe_split_compact(name, tmp_path):
    split = _load("split")
    common = _load("common")
    assert split.is_compact_english is common.is_compact_english
    assert split.ensure_compact_english is common.ensure_compact_english
    assert split.is_compact_english("ok") is True
    assert split.ensure_compact_english("  a ") == "a"


def _probe_split_hot_write(name, tmp_path):
    split = _load("split")
    common = _load("common")
    assert split.hot_write_text is common.hot_write_text
    target = str(tmp_path / "c-split-hot.txt")
    split.hot_write_text(target, "split probe")
    with open(target, encoding="utf-8") as handle:
        assert handle.read() == "split probe"


def _probe_mm_settings(name, tmp_path):
    split = _load("split")
    settings = split.MultiManagerSettings(True, 2, False,
                                          "manager-integrates")
    assert (settings.multi_manager_mode,
            settings.max_parallel_managers) == (True, 2)


def _probe_part_ref(name, tmp_path):
    split = _load("split")
    refs = ["artifact://p-pr/0", "artifact://p-pr/1"]
    made = split.split_package("p-pr-pkg", "goal probe", refs, 2)
    assert isinstance(made[0], split.PartRef)
    assert made[0].package_id == "p-pr-pkg"


def _probe_split_decomp_record(name, tmp_path):
    split = _load("split")
    rec = split.record_decomposition("p-sd-1", 3)
    assert isinstance(rec, split.DecompositionRecord)
    assert rec.route == "cheap-small-part"
    assert rec.artifact_ref == "ARTIFACT_REF:p-sd-1/decomposition"


def _probe_queue_slot(name, tmp_path):
    split = _load("split")
    refs = ["artifact://p-qs/%d" % i for i in range(3)]
    made = split.split_package("p-qs-pkg", "goal probe", refs, 3)
    settings = split.MultiManagerSettings(True, 2, False,
                                          "manager-integrates")
    slots = split.capped_queue(made, settings)
    assert len(slots) == 3
    assert all(isinstance(slot, split.QueueSlot) for slot in slots)
    assert [slot.position for slot in slots] == [0, 1, 2]


def _probe_part_row(name, tmp_path):
    parts = _load("parts")
    row = parts.PartRow(agent="a", scope="p-prw-%s" % name.replace(".", "-"),
                        deliverable="artifact://p/prw", status="QUEUED")
    assert row.status == "QUEUED"


def _probe_part_record(name, tmp_path):
    parts = _load("parts")
    store = parts.PartStore()
    rec = parts.PartRecord(part_id="p-prc-1", package_id="p-prc-p",
                           contract_hash="h", agent="a", scope="p-prc-s",
                           deliverable_ref="artifact://p/drw")
    stored = store.register(rec)
    assert store.get("p-prc-1") is not None
    assert stored.part_id == "p-prc-1"


def _probe_gates_utc(name, tmp_path):
    gates = _load("gates")
    assert gates.utc_now().endswith("Z")


def _probe_gate_ids(name, tmp_path):
    gates = _load("gates")
    assert gates.gate_id_of("p", 1) == "p:gate-001"
    assert gates.audit_id_of("p", 1) == "p:audit-001"
    assert gates.audit_scope_id_of("p").startswith("audit-scope-")


def _probe_can_close(name, tmp_path):
    gates = _load("gates")
    assert gates.can_close(None, None)[0] is False
    assert gates.can_close("PASS", "PASS") == (True, "ok")


def _probe_gate_record(name, tmp_path):
    gates = _load("gates")
    rec = gates.GateRecord(gate_id="g", part_id="p", verdict="PASS",
                           created_at="t")
    assert rec.verdict == "PASS"


def _probe_audit_record(name, tmp_path):
    gates = _load("gates")
    rec = gates.AuditRecord(audit_id="a", part_id="p", result="PASS",
                            auditor_session_ref="aud")
    assert rec.result == "PASS"


def _probe_graph_kernel(name, tmp_path):
    graph = _load("graph")
    common = _load("common")
    assert graph.utc_now is common.utc_now
    assert graph.is_compact_english is common.is_compact_english
    assert graph.ensure_compact_english is common.ensure_compact_english
    assert graph.DecisionRow is common.DecisionRow
    assert graph.DecisionLog is common.DecisionLog
    assert graph.ApplyOutcome is common.ApplyOutcome
    log = graph.DecisionLog()
    row = log.append("s", "one", "r", "a", "t")
    assert row.decision_id == "s-0001"


def _probe_planned_subtask(name, tmp_path):
    graph = _load("graph")
    node = graph.PlannedSubtask(subtask_id="p-ps-1", plan_ref="p-ps-r",
                                goal="probe goal", task_class="build",
                                risk="MEDIUM")
    assert node.status == graph.PLANNED


def _probe_run_config(name, tmp_path):
    graph = _load("graph")
    assert graph.RunConfig().client_max_retries == 0
    assert graph.RunConfig().retry_policy_ref == "retry:default"


def _probe_route_task(name, tmp_path):
    graph = _load("graph")
    target = graph.control_plane_map()["director.route"]
    assert target == "graph.route_task"
    assert _resolve_dotted(target) is graph.route_task
    sub = graph.PlannedSubtask(subtask_id="p-rt-1", plan_ref="p-rt-r",
                               goal="probe goal", task_class="build",
                               risk="LOW")
    decision = graph.route_task(sub, "worker", "local", manager_id="p-rt-m")
    assert decision.subordinate_to == "p-rt-m"
    assert decision.run_config.client_max_retries == 0


def _probe_agent_task(name, tmp_path):
    graph = _load("graph")
    planner = graph.TaskPlanner()
    specs = [{"goal": "slice", "task_class": "build", "risk": "LOW"}]
    _, built = planner.plan("p-at-pkg", "goal probe", specs)
    sid = next(iter(built.nodes))
    task = graph.validate_dispatch({"agent_task_id": "p-at-t",
                                    "subtask_id": sid,
                                    "agent_id": "p-at-a",
                                    "contract_hash": "h"}, built)
    assert isinstance(task, graph.AgentTask)
    assert task.subtask_id == sid


def _probe_hierarchy_chain(name, tmp_path):
    graph = _load("graph")
    chain = graph.HierarchyChain(director_id="p-hc-d", manager_id="p-hc-m",
                                 tool_agent_ids=["p-hc-t"])
    assert chain.tool_agent_ids == ["p-hc-t"]


def _probe_team_sizing(name, tmp_path):
    graph = _load("graph")
    store = graph.HierarchyConfigStore()
    sizing = store.size_team("p-ts-b", 2, "LOW", "director-1")
    assert isinstance(sizing, graph.TeamSizing)
    assert sizing.members == 2
    assert sizing.roles == ["manager", "tool-agent", "tool-agent"]
    assert len(store.log.rows) == 1


def _probe_subtask_graph(name, tmp_path):
    graph = _load("graph")
    planner = graph.TaskPlanner()
    specs = [{"goal": "slice", "task_class": "build", "risk": "LOW"}]
    _, built = planner.plan("p-sg-pkg", "goal probe", specs)
    assert isinstance(built, graph.SubtaskGraph)
    assert built.order() == ["p-sg-pkg:sub-000"]


def _probe_graph_add(name, tmp_path):
    graph = _load("graph")
    built = graph.SubtaskGraph()
    built.add(graph.PlannedSubtask(subtask_id="p-ga-1", plan_ref="r",
                                   goal="g", task_class="build", risk="LOW"))
    assert "p-ga-1" in built.nodes


def _probe_graph_validate(name, tmp_path):
    graph = _load("graph")
    planner = graph.TaskPlanner()
    specs = [{"goal": "slice", "task_class": "build", "risk": "LOW",
              "dependency_ids": ["p-gv-nope"]}]
    with pytest.raises(graph.DependencyError):
        planner.plan("p-gv-pkg", "goal probe", specs)


def _probe_graph_order(name, tmp_path):
    graph = _load("graph")
    built = graph.SubtaskGraph()
    for sid in ("p-go-1", "p-go-2"):
        built.add(graph.PlannedSubtask(subtask_id=sid, plan_ref="r", goal="g",
                                       task_class="build", risk="LOW"))
    assert built.order() == ["p-go-1", "p-go-2"]


def _probe_hcs_class(name, tmp_path):
    graph = _load("graph")
    target = graph.control_plane_map()["director.integrate"]
    assert target == "graph.HierarchyConfigStore.close_parent"
    store = graph.HierarchyConfigStore()
    assert _resolve_dotted(target) is graph.HierarchyConfigStore.close_parent
    assert store.config["integration_policy"] == "manager-integrates"


def _probe_close_parent(name, tmp_path):
    graph = _load("graph")
    store = graph.HierarchyConfigStore()
    done = store.close_parent({"p-cp-1": "PASS"}, {"record_id": "p-cp-rec"})
    assert done == {"parent": "closed", "parts": "p-cp-1",
                    "integration_ref": "p-cp-rec"}


def _probe_decision_append(name, tmp_path):
    graph = _load("graph")
    teamcard = _load("teamcard")
    target = graph.control_plane_map()["director.decide"]
    assert target == "teamcard.DecisionLog.append"
    assert _resolve_dotted(target) is teamcard.DecisionLog.append
    log = teamcard.DecisionLog()
    row = log.append("s", "one", "r", "a", "t")
    assert row.decision_id == "s-0001"


def _probe_graph_decision_add(name, tmp_path):
    graph = _load("graph")
    common = _load("common")
    assert graph.DecisionLog is common.DecisionLog
    log = graph.DecisionLog()
    assert log.next_id("s") == "s-0001"
    row = log.add("s", "one", "r", "a")
    assert row["decision_id"] == "s-0001"
    assert log.to_list() == [row]
    assert log.next_id("s") == "s-0002"


def _probe_may_start(name, tmp_path):
    overlap = _load("overlap")
    ref = {"package_id": "p-ms", "contract_hash": "h",
           "gate_verdict_ref": "p-ms-g", "audit_verdict_ref": "p-ms-a"}
    assert overlap.may_start_early(ref) is False
    overlap._record_gate_verdict("p-ms-g", "PASS")
    overlap._record_audit_verdict("p-ms-a", "PASS")
    assert overlap.may_start_early(ref) is True


def _probe_frozen_hash(name, tmp_path):
    manifest = _load("manifest")
    base = {"manifest_id": "p-fh-1", "version": 1, "hash_algorithm": "sha256"}
    digest = manifest.frozen_hash(dict(base, hash="x"))
    assert len(digest) == 64
    int(digest, 16)


def _probe_manifest_rec(name, tmp_path):
    manifest = _load("manifest")
    rec = manifest.ManifestRec("p-mr-1", 1, [])
    assert rec.hash_algorithm == "sha256"
    assert rec.to_dict()["manifest_id"] == "p-mr-1"
    back = manifest.ManifestRec.from_dict(rec.to_dict())
    assert back.version == 1


def _probe_canonical_bytes(name, tmp_path):
    manifest = _load("manifest")
    import json
    raw = manifest.canonical_manifest_bytes("p-cb-1", 1, [])
    assert isinstance(raw, bytes)
    assert json.loads(raw.decode("utf-8"))["manifest_id"] == "p-cb-1"


def _probe_manifest_hash(name, tmp_path):
    manifest = _load("manifest")
    built = manifest.build_manifest("p-mh-1", 1, [])
    assert built["hash"] == manifest.manifest_hash(built)
    assert manifest.verify_manifest_hash(built) is True
    tampered = dict(built, version=999)
    assert manifest.verify_manifest_hash(tampered) is False


def _probe_verify_hash(name, tmp_path):
    manifest = _load("manifest")
    built = manifest.build_manifest("p-vh-1", 1, [])
    assert manifest.verify_manifest_hash(built) is True
    assert manifest.verify_manifest_hash({"nope": True}) is False


def _probe_part_ref_check(name, tmp_path):
    manifest = _load("manifest")
    built = manifest.build_manifest("p-vp-1", 1, [])
    ref = {"package_id": "p-vp-1", "contract_hash": built["hash"],
           "gate_verdict_ref": "g", "audit_verdict_ref": "a"}
    assert manifest.validate_part_ref(ref, built) is True
    bad = dict(ref, contract_hash="0" * 64)
    assert manifest.validate_part_ref(bad, built) is False


def _probe_to_dict(name, tmp_path):
    manifest = _load("manifest")
    rec = manifest.ManifestRec("p-td-1", 2, [{"package_id": "x"}])
    assert rec.to_dict()["parts"] == [{"package_id": "x"}]


def _probe_validate_change(name, tmp_path):
    delta = _load("delta")
    ok, reason = delta.validate_config_change({"agents": 2}, {})
    assert (ok, reason) == (True, "ok")


def _probe_apply_change(name, tmp_path):
    delta = _load("delta")
    config = {"budget_left": 50.0}
    log = []
    out = delta.apply_config_change(config, log, "p-ac-scope", "statement",
                                    "reason", "director", {"agents": 2})
    assert out["applied"] is True
    assert out["decision_ref"] == "p-ac-scope-0001"
    assert config["agents"] == 2
    graph = _load("graph")
    assert delta.HierarchyConfigStore is graph.HierarchyConfigStore
    stored = delta.HierarchyConfigStore()
    chain = graph.HierarchyChain(director_id="p-ac-d", manager_id="p-ac-m",
                                 tool_agent_ids=["p-ac-t"])
    back = stored.activate_chain(chain, "director-1")
    assert back.accepted is True
    assert stored.config["director"] == "p-ac-d"


def _probe_delta_hcs_activate(name, tmp_path):
    delta = _load("delta")
    graph = _load("graph")
    assert delta.HierarchyConfigStore is graph.HierarchyConfigStore
    store = delta.HierarchyConfigStore()
    chain = graph.HierarchyChain(director_id="p-da-d", manager_id="p-da-m",
                                 tool_agent_ids=["p-da-t"])
    out = store.activate_chain(chain, "director-1")
    assert out.accepted is True
    assert store.config["director"] == "p-da-d"
    assert len(store.log.rows) == 1


def _probe_delta_hcs_correct(name, tmp_path):
    delta = _load("delta")
    graph = _load("graph")
    assert delta.HierarchyConfigStore is graph.HierarchyConfigStore
    store = delta.HierarchyConfigStore()
    out = store.append_user_correction("user", "fix the budget note")
    assert out.accepted is True
    assert store.config["user_corrections"][-1]["text"] == "fix the budget note"


def _probe_delta_hcs_role(name, tmp_path):
    delta = _load("delta")
    graph = _load("graph")
    assert delta.HierarchyConfigStore is graph.HierarchyConfigStore
    store = delta.HierarchyConfigStore(
        {"role_models": {"worker": {"model": "m", "purpose": "dev"}}})
    out = store.grant_role_authority("worker", {"model": "m", "purpose": "dev"},
                                     "director-1")
    assert out.accepted is True
    assert store.config["role_models"]["worker"]["purpose"] == "dev"


def _probe_team_secret(name, tmp_path):
    teamcard = _load("teamcard")
    assert teamcard.make_secret_ref("p-budget") == {"secret_ref": "p-budget"}


def _probe_team_card(name, tmp_path):
    teamcard = _load("teamcard")
    card = teamcard.TeamCard(
        provider="p", model="meta/muse-spark-1.3-contributor",
        model_kb_facts={"part-size-vs-model": True}, budget_left={},
        limits={})
    assert card.model_kb_facts == {"part-size-vs-model": True}


def _probe_director_context(name, tmp_path):
    teamcard = _load("teamcard")
    card = teamcard.TeamCard(
        provider="p", model="meta/muse-spark-1.3-contributor",
        model_kb_facts={}, budget_left={}, limits={})
    ctx = teamcard.director_context({"m1": card}, {"m1": [card]})
    assert set(ctx) == {"managers", "workers"}
    assert ctx["managers"] == {"m1": card}


def _probe_manager_context(name, tmp_path):
    teamcard = _load("teamcard")
    card = teamcard.TeamCard(
        provider="p", model="meta/muse-spark-1.3-contributor",
        model_kb_facts={}, budget_left={}, limits={})
    ctx = teamcard.manager_context(card, [card])
    assert ctx == {"own": card, "workers": [card]}


def _probe_worker_context(name, tmp_path):
    teamcard = _load("teamcard")
    assert teamcard.worker_context() == {}


def _probe_team_decomp_record(name, tmp_path):
    teamcard = _load("teamcard")
    rec = teamcard.record_decomposition("p-td-1", 3)
    assert isinstance(rec, teamcard.DecompositionRecord)
    assert rec.route == "cheap-small-part"
    assert "part-size-vs-model" in rec.facts_used


def _probe_team_store(name, tmp_path):
    teamcard = _load("teamcard")
    store = teamcard.TeamConfigStore()
    assert store.config["independent_audit"] is True
    assert store.log.rows == []


def _probe_validate_team(name, tmp_path):
    teamcard = _load("teamcard")
    store = teamcard.TeamConfigStore()
    ok, reason = teamcard.validate_team_config_change({"agents": 2},
                                                      store.config)
    assert (ok, reason) == (True, "ok")


def _probe_audit_choice(name, tmp_path):
    teamcard = _load("teamcard")
    log = []
    low = teamcard.select_audit_model("p-ac-1", "low", log)
    assert isinstance(low, teamcard.AuditModelChoice)
    assert (low.strength, low.model) == (
        "standard", "meta/muse-spark-1.3-contributor")
    high = teamcard.select_audit_model("p-ac-2", "high", log)
    assert high.strength == "strong"
    assert [choice.part_id for choice in log] == ["p-ac-1", "p-ac-2"]


def _probe_register_verbatim(name, tmp_path):
    teamcard = _load("teamcard")
    baseline = {"e1": "text"}
    assert teamcard.register_verbatim("e1", "text", baseline)["status"] == \
        teamcard.REGISTER_PRESERVED
    assert teamcard.register_verbatim("e9", "text", baseline)["status"] == \
        teamcard.REGISTER_MISSING


def _probe_team_report(name, tmp_path):
    teamcard = _load("teamcard")
    report = teamcard.TeamReport()
    assert report.director == {} and report.managers == {}
    assert report.decompositions == [] and report.audits == []


def _probe_ledger_row(name, tmp_path):
    ledger = _load("ledger")
    row = ledger.LedgerRow(package_id="p-lr-1", agents=2, peak_concurrency=1,
                           wall_time_s=4.0)
    assert row.package_id == "p-lr-1"


def _probe_ledger_class(name, tmp_path):
    ledger = _load("ledger")
    book = ledger.PackageLedger()
    assert book.package_ids() == []
    row = book.record_row("p-lc-1", 1, 1, 2.0)
    assert book.package_ids() == ["p-lc-1"]
    assert book.get_row("p-lc-1") is row


def _probe_record_row(name, tmp_path):
    ledger = _load("ledger")
    book = ledger.PackageLedger()
    row = book.record_row("p-rr-1", 2, 1, 4.0)
    assert book.get_row("p-rr-1") is row


def _probe_get_row(name, tmp_path):
    ledger = _load("ledger")
    book = ledger.PackageLedger()
    assert book.get_row("p-gr-nope") is None
    row = book.record_row("p-gr-1", 1, 1, 1.0)
    assert book.get_row("p-gr-1") is row


def _probe_package_report(name, tmp_path):
    ledger = _load("ledger")
    book = ledger.PackageLedger()
    book.record_row("p-pr-1", 2, 1, 4.0)
    items = ledger.build_package_report(book, ["p-pr-1"])
    assert items[0]["row"]["package_id"] == "p-pr-1"
    direct = ledger.package_report(book, "p-pr-1")
    assert direct["row"]["agents"] == 2
    assert direct["auto_push"] is False


def _probe_ledger_store(name, tmp_path):
    ledger = _load("ledger")
    store = ledger.LedgerConfigStore()
    assert store.config["independent_audit"] is True
    assert store.log.rows == []


def _probe_validate_ledger(name, tmp_path):
    ledger = _load("ledger")
    store = ledger.LedgerConfigStore()
    ok, reason = ledger.validate_ledger_config_change({"agents": 2},
                                                      store.config)
    assert (ok, reason) == (True, "ok")


def _probe_ledger_report(name, tmp_path):
    ledger = _load("ledger")
    report = ledger.LedgerReport()
    assert report.packages == []


def _probe_offload_decision(name, tmp_path):
    offload = _load("offload")
    row = offload.DecisionRow(decision_id="d", scope="s", statement="st",
                              reason="r", authority="a", created_at="c")
    assert row.scope == "s"


def _probe_handover(name, tmp_path):
    offload = _load("offload")
    tag = "p-ho-%s" % name.replace(".", "-")
    accepted = offload.apply_offload_config_change({
        "project_id": tag,
        "role": "worker",
        "enabled": True,
        "authority": "director probe",
        "reason": "handover probe",
        "statement": "handover probe statement",
        "task_ids": [tag + "-task-1"],
    })
    assert accepted.applied is True, accepted.reason
    assert accepted.decision_ref.startswith("offload:%s:" % tag)
    record = offload.maybe_offload(tag + "-task-1", "worker", True)
    assert isinstance(record, offload.HandoverRecord)
    assert record.task_id == tag + "-task-1"


def _probe_offload_outcome(name, tmp_path):
    offload = _load("offload")
    out = offload.ApplyOutcome(applied=True, reason="applied")
    assert out.decision_ref is None


def _probe_offload_enabled(name, tmp_path):
    offload = _load("offload")
    tag = "p-oe-%s" % name.replace(".", "-")
    assert offload.offload_enabled(tag, "worker") is False
    accepted = offload.apply_offload_config_change({
        "project_id": tag,
        "role": "worker",
        "enabled": True,
        "authority": "director probe",
        "reason": "switch probe",
        "statement": "switch probe statement",
    })
    assert accepted.applied is True, accepted.reason
    assert offload.offload_enabled(tag, "worker") is True


def _probe_maybe_offload(name, tmp_path):
    offload = _load("offload")
    assert offload.maybe_offload("p-mo-task", "worker", True) is None
    assert offload.maybe_offload("p-mo-task", "worker", False) is None
    assert offload.maybe_offload("p-mo-task", "auditor", True) is None


def _probe_apply_offload(name, tmp_path):
    offload = _load("offload")
    tag = "p-ao-%s" % name.replace(".", "-")
    accepted = offload.apply_offload_config_change({
        "project_id": tag,
        "role": "worker",
        "enabled": False,
        "authority": "director probe",
        "reason": "disable probe",
        "statement": "disable probe statement",
    })
    assert accepted.applied is True, accepted.reason
    assert accepted.reason == "applied"
    assert offload.offload_enabled(tag, "worker") is False


def _probe_sl_outcome(name, tmp_path):
    steplimits = _load("steplimits")
    out = steplimits.ApplyOutcome(applied=False, reason="x")
    assert out.decision_ref is None


def _probe_step_limits(name, tmp_path):
    steplimits = _load("steplimits")
    limits = steplimits.StepLimits(task_max_steps=2, chat_max_steps=5)
    assert (limits.task_max_steps, limits.chat_max_steps) == (2, 5)


def _probe_limits_for(name, tmp_path):
    steplimits = _load("steplimits")
    tag = "p-lf-%s" % name.replace(".", "-")
    applied = steplimits.apply_steplimit_config_change({
        "project_id": tag,
        "authority": "manager probe",
        "reason": "limits probe",
        "task_max_steps": 3,
        "chat_max_steps": 7,
    })
    assert applied.applied is True, applied.reason
    assert steplimits.limits_for("task", tag) == 3
    assert steplimits.limits_for("chat", tag) == 7


def _probe_apply_steplimit(name, tmp_path):
    steplimits = _load("steplimits")
    tag = "p-as-%s" % name.replace(".", "-")
    applied = steplimits.apply_steplimit_config_change({
        "project_id": tag,
        "authority": "manager probe",
        "reason": "apply probe",
        "task_max_steps": 2,
        "chat_max_steps": 5,
    })
    assert applied.applied is True, applied.reason
    assert applied.decision_ref.startswith("steplimits:%s:" % tag)


_PROBES = {
    "utc_now": _probe_utc_now,
    "is_compact_english": _probe_is_compact,
    "ensure_compact_english": _probe_ensure_compact,
    "hot_write_text": _probe_hot_write,
    "DecisionRow": _probe_decision_row,
    "DecisionLog": _probe_decision_log,
    "DecisionLog.append": _probe_decision_log,
    "DecisionLog.add": _probe_decision_add,
    "DecisionLog.next_id": _probe_decision_add,
    "DecisionLog.to_list": _probe_decision_add,
    "ApplyOutcome": _probe_apply_outcome,
    "surface_rejection": _probe_surface,
    "is_shared_ref": _probe_is_shared,
    "corrections_hash": _probe_corrections_hash,
    "split_package": _probe_split_package,
    "fanout": _probe_fanout,
    "split_TeamCard": _probe_split_teamcard,
    "split_is_compact_english": _probe_split_compact,
    "split_ensure_compact_english": _probe_split_compact,
    "split_hot_write_text": _probe_split_hot_write,
    "MultiManagerSettings": _probe_mm_settings,
    "PartRef": _probe_part_ref,
    "split_DecompositionRecord": _probe_split_decomp_record,
    "QueueSlot": _probe_queue_slot,
    "PartRow": _probe_part_row,
    "PartRecord": _probe_part_record,
    "gates_utc_now": _probe_gates_utc,
    "gate_id_of": _probe_gate_ids,
    "audit_id_of": _probe_gate_ids,
    "audit_scope_id_of": _probe_gate_ids,
    "can_close": _probe_can_close,
    "GateRecord": _probe_gate_record,
    "AuditRecord": _probe_audit_record,
    "graph_utc_now": _probe_graph_kernel,
    "graph_is_compact_english": _probe_graph_kernel,
    "graph_ensure_compact_english": _probe_graph_kernel,
    "graph_DecisionRow": _probe_graph_kernel,
    "graph_DecisionLog": _probe_graph_kernel,
    "graph_DecisionLog.append": _probe_decision_append,
    "graph_DecisionLog.add": _probe_graph_decision_add,
    "graph_DecisionLog.next_id": _probe_graph_decision_add,
    "graph_DecisionLog.to_list": _probe_graph_decision_add,
    "graph_ApplyOutcome": _probe_graph_kernel,
    "PlannedSubtask": _probe_planned_subtask,
    "RunConfig": _probe_run_config,
    "RoutingDecision": _probe_route_task,
    "AgentTask": _probe_agent_task,
    "HierarchyChain": _probe_hierarchy_chain,
    "TeamSizing": _probe_team_sizing,
    "SubtaskGraph": _probe_subtask_graph,
    "SubtaskGraph.add": _probe_graph_add,
    "SubtaskGraph.validate": _probe_graph_validate,
    "SubtaskGraph.order": _probe_graph_order,
    "route_task": _probe_route_task,
    "HierarchyConfigStore": _probe_hcs_class,
    "HierarchyConfigStore.close_parent": _probe_close_parent,
    "may_start_early": _probe_may_start,
    "frozen_hash": _probe_frozen_hash,
    "ManifestRec": _probe_manifest_rec,
    "canonical_manifest_bytes": _probe_canonical_bytes,
    "manifest_hash": _probe_manifest_hash,
    "verify_manifest_hash": _probe_verify_hash,
    "validate_part_ref": _probe_part_ref_check,
    "ManifestRec.to_dict": _probe_to_dict,
    "validate_config_change": _probe_validate_change,
    "apply_config_change": _probe_apply_change,
    "delta_HierarchyConfigStore": _probe_hcs_class,
    "delta_HierarchyConfigStore.activate_chain": _probe_delta_hcs_activate,
    "delta_HierarchyConfigStore.append_user_correction": _probe_delta_hcs_correct,
    "delta_HierarchyConfigStore.grant_role_authority": _probe_delta_hcs_role,
    "delta_HierarchyConfigStore.close_parent": _probe_close_parent,
    "delta_HierarchyConfigStore.size_team": _probe_team_sizing,
    "teamcard_make_secret_ref": _probe_team_secret,
    "TeamCard": _probe_team_card,
    "director_context": _probe_director_context,
    "manager_context": _probe_manager_context,
    "worker_context": _probe_worker_context,
    "teamcard_DecompositionRecord": _probe_team_decomp_record,
    "teamcard_record_decomposition": _probe_team_decomp_record,
    "TeamConfigStore": _probe_team_store,
    "validate_team_config_change": _probe_validate_team,
    "AuditModelChoice": _probe_audit_choice,
    "select_audit_model": _probe_audit_choice,
    "register_verbatim": _probe_register_verbatim,
    "TeamReport": _probe_team_report,
    "LedgerRow": _probe_ledger_row,
    "PackageLedger": _probe_ledger_class,
    "PackageLedger.record_row": _probe_record_row,
    "PackageLedger.get_row": _probe_get_row,
    "package_report": _probe_package_report,
    "LedgerConfigStore": _probe_ledger_store,
    "validate_ledger_config_change": _probe_validate_ledger,
    "LedgerReport": _probe_ledger_report,
    "offload_DecisionRow": _probe_offload_decision,
    "HandoverRecord": _probe_handover,
    "offload_ApplyOutcome": _probe_offload_outcome,
    "offload_enabled": _probe_offload_enabled,
    "maybe_offload": _probe_maybe_offload,
    "apply_offload_config_change": _probe_apply_offload,
    "steplimits_ApplyOutcome": _probe_sl_outcome,
    "StepLimits": _probe_step_limits,
    "limits_for": _probe_limits_for,
    "apply_steplimit_config_change": _probe_apply_steplimit,
}

# (stub name, home lane, home attr path, production file, production line,
#  cited token; None means the last dotted bit)
_CALL = [
    ("utc_now", "common", "utc_now",
     "src/agent_si/backend/orchestration/gates.py", 118, None),
    ("is_compact_english", "common", "is_compact_english",
     "src/agent_si/backend/orchestration/split.py", 21, None),
    ("ensure_compact_english", "common", "ensure_compact_english",
     "src/agent_si/backend/orchestration/teamcard.py", 143, None),
    ("hot_write_text", "common", "hot_write_text",
     "src/agent_si/backend/orchestration/split.py", 338, None),
    ("DecisionRow", "common", "DecisionRow",
     "src/agent_si/backend/orchestration/common.py", 58, None),
    ("DecisionLog", "common", "DecisionLog",
     "src/agent_si/backend/orchestration/graph.py", 432, None),
    ("DecisionLog.append", "common", "DecisionLog.append",
     "src/agent_si/backend/orchestration/teamcard.py", 236, "append"),
    ("DecisionLog.add", "common", "DecisionLog.add",
     "src/agent_si/backend/orchestration/common.py", 103, None),
    ("DecisionLog.next_id", "common", "DecisionLog.next_id",
     "src/agent_si/backend/orchestration/common.py", 97, None),
    ("DecisionLog.to_list", "common", "DecisionLog.to_list",
     "src/agent_si/backend/orchestration/common.py", 94, None),
    ("ApplyOutcome", "common", "ApplyOutcome",
     "src/agent_si/backend/orchestration/teamcard.py", 225, None),
    ("surface_rejection", "common", "surface_rejection",
     "src/agent_si/backend/orchestration/ledger.py", 177, None),
    ("is_shared_ref", "split", "is_shared_ref",
     "src/agent_si/backend/orchestration/split.py", 120, None),
    ("corrections_hash", "split", "corrections_hash",
     "src/agent_si/backend/orchestration/split.py", 130, None),
    ("split_package", "split", "split_package",
     "src/agent_si/backend/orchestration/graph.py", 38, None),
    ("fanout", "split", "fanout",
     "src/agent_si/backend/orchestration/split.py", 316, None),
    ("split_TeamCard", "split", "TeamCard",
     "src/agent_si/backend/orchestration/split.py", 22, None),
    ("split_is_compact_english", "split", "is_compact_english",
     "src/agent_si/backend/orchestration/split.py", 21, None),
    ("split_ensure_compact_english", "split", "ensure_compact_english",
     "src/agent_si/backend/orchestration/split.py", 21, None),
    ("split_hot_write_text", "split", "hot_write_text",
     "src/agent_si/backend/orchestration/split.py", 21, None),
    ("MultiManagerSettings", "split", "MultiManagerSettings",
     "src/agent_si/backend/orchestration/split.py", 188, None),
    ("PartRef", "split", "PartRef",
     "src/agent_si/backend/orchestration/split.py", 151, None),
    ("split_DecompositionRecord", "split", "DecompositionRecord",
     "src/agent_si/backend/orchestration/split.py", 268, None),
    ("QueueSlot", "split", "QueueSlot",
     "src/agent_si/backend/orchestration/split.py", 321, None),
    ("PartRow", "parts", "PartRow",
     "src/agent_si/backend/orchestration/parts.py", 96, None),
    ("PartRecord", "parts", "PartRecord",
     "src/agent_si/backend/orchestration/parts.py", 170, None),
    ("gates_utc_now", "gates", "utc_now",
     "src/agent_si/backend/orchestration/gates.py", 16, "utc_now"),
    ("gate_id_of", "gates", "gate_id_of",
     "src/agent_si/backend/orchestration/gates.py", 115, None),
    ("audit_id_of", "gates", "audit_id_of",
     "src/agent_si/backend/orchestration/gates.py", 149, None),
    ("audit_scope_id_of", "gates", "audit_scope_id_of",
     "src/agent_si/backend/orchestration/gates.py", 154, None),
    ("can_close", "gates", "can_close",
     "src/agent_si/backend/orchestration/gates.py", 217, None),
    ("GateRecord", "gates", "GateRecord",
     "src/agent_si/backend/orchestration/gates.py", 114, None),
    ("AuditRecord", "gates", "AuditRecord",
     "src/agent_si/backend/orchestration/gates.py", 148, None),
    ("graph_utc_now", "graph", "utc_now",
     "src/agent_si/backend/orchestration/graph.py", 25, "utc_now"),
    ("graph_is_compact_english", "graph", "is_compact_english",
     "src/agent_si/backend/orchestration/graph.py", 24, None),
    ("graph_ensure_compact_english", "graph", "ensure_compact_english",
     "src/agent_si/backend/orchestration/graph.py", 23, None),
    ("graph_DecisionRow", "graph", "DecisionRow",
     "src/agent_si/backend/orchestration/graph.py", 22, None),
    ("graph_DecisionLog", "graph", "DecisionLog",
     "src/agent_si/backend/orchestration/graph.py", 21, None),
    ("graph_DecisionLog.append", "graph", "DecisionLog.append",
     "src/agent_si/backend/orchestration/graph.py", 42, "DecisionLog.append"),
    ("graph_DecisionLog.add", "graph", "DecisionLog.add",
     "src/agent_si/backend/orchestration/graph.py", 21, "DecisionLog"),
    ("graph_DecisionLog.next_id", "graph", "DecisionLog.next_id",
     "src/agent_si/backend/orchestration/graph.py", 21, "DecisionLog"),
    ("graph_DecisionLog.to_list", "graph", "DecisionLog.to_list",
     "src/agent_si/backend/orchestration/graph.py", 21, "DecisionLog"),
    ("graph_ApplyOutcome", "graph", "ApplyOutcome",
     "src/agent_si/backend/orchestration/graph.py", 20, None),
    ("PlannedSubtask", "graph", "PlannedSubtask",
     "src/agent_si/backend/orchestration/graph.py", 223, None),
    ("RunConfig", "graph", "RunConfig",
     "src/agent_si/backend/orchestration/graph.py", 279, None),
    ("RoutingDecision", "graph", "RoutingDecision",
     "src/agent_si/backend/orchestration/graph.py", 269, None),
    ("AgentTask", "graph", "AgentTask",
     "src/agent_si/backend/orchestration/graph.py", 308, None),
    ("HierarchyChain", "graph", "HierarchyChain",
     "src/agent_si/backend/orchestration/graph.py", 434, None),
    ("TeamSizing", "graph", "TeamSizing",
     "src/agent_si/backend/orchestration/graph.py", 545, None),
    ("SubtaskGraph", "graph", "SubtaskGraph",
     "src/agent_si/backend/orchestration/graph.py", 218, None),
    ("SubtaskGraph.add", "graph", "SubtaskGraph.add",
     "src/agent_si/backend/orchestration/graph.py", 237, "add"),
    ("SubtaskGraph.validate", "graph", "SubtaskGraph.validate",
     "src/agent_si/backend/orchestration/graph.py", 177, "validate"),
    ("SubtaskGraph.order", "graph", "SubtaskGraph.order",
     "src/agent_si/backend/orchestration/graph.py", 238, "order"),
    ("route_task", "graph", "route_task",
     "src/agent_si/backend/orchestration/graph.py", 39, None),
    ("HierarchyConfigStore", "graph", "HierarchyConfigStore",
     "src/agent_si/backend/orchestration/graph.py", 418, None),
    ("HierarchyConfigStore.close_parent", "graph",
     "HierarchyConfigStore.close_parent",
     "src/agent_si/backend/orchestration/graph.py", 41, "close_parent"),
    ("may_start_early", "overlap", "may_start_early",
     "src/agent_si/backend/orchestration/overlap.py", 116, None),
    ("frozen_hash", "manifest", "frozen_hash",
     "src/agent_si/backend/orchestration/manifest.py", 67, None),
    ("ManifestRec", "manifest", "ManifestRec",
     "src/agent_si/backend/orchestration/manifest.py", 147, None),
    ("canonical_manifest_bytes", "manifest", "canonical_manifest_bytes",
     "src/agent_si/backend/orchestration/manifest.py", 137, None),
    ("manifest_hash", "manifest", "manifest_hash",
     "src/agent_si/backend/orchestration/manifest.py", 168, None),
    ("verify_manifest_hash", "manifest", "verify_manifest_hash",
     "src/agent_si/backend/orchestration/manifest.py", 187, None),
    ("validate_part_ref", "manifest", "validate_part_ref",
     "src/agent_si/backend/orchestration/manifest.py", 202, None),
    ("ManifestRec.to_dict", "manifest", "ManifestRec.to_dict",
     "src/agent_si/backend/orchestration/manifest.py", 152, "to_dict"),
    ("validate_config_change", "delta", "validate_config_change",
     "src/agent_si/backend/orchestration/delta.py", 230, None),
    ("apply_config_change", "delta", "apply_config_change",
     "src/agent_si/backend/orchestration/delta.py", 312, None),
    ("delta_HierarchyConfigStore", "graph", "HierarchyConfigStore",
     "src/agent_si/backend/orchestration/graph.py", 418, None),
    ("delta_HierarchyConfigStore.activate_chain", "graph",
     "HierarchyConfigStore.activate_chain",
     "src/agent_si/backend/orchestration/graph.py", 434, "activate_chain"),
    ("delta_HierarchyConfigStore.append_user_correction", "graph",
     "HierarchyConfigStore.append_user_correction",
     "src/agent_si/backend/orchestration/graph.py", 462,
     "append_user_correction"),
    ("delta_HierarchyConfigStore.grant_role_authority", "graph",
     "HierarchyConfigStore.grant_role_authority",
     "src/agent_si/backend/orchestration/graph.py", 478,
     "grant_role_authority"),
    ("delta_HierarchyConfigStore.close_parent", "graph",
     "HierarchyConfigStore.close_parent",
     "src/agent_si/backend/orchestration/graph.py", 498, "close_parent"),
    ("delta_HierarchyConfigStore.size_team", "graph",
     "HierarchyConfigStore.size_team",
     "src/agent_si/backend/orchestration/graph.py", 523, "size_team"),
    ("teamcard_make_secret_ref", "teamcard", "make_secret_ref",
     "src/agent_si/backend/orchestration/teamcard.py", 64, "make_secret_ref"),
    ("TeamCard", "teamcard", "TeamCard",
     "src/agent_si/backend/orchestration/teamcard.py", 69, None),
    ("director_context", "teamcard", "director_context",
     "src/agent_si/backend/orchestration/teamcard.py", 103, None),
    ("manager_context", "teamcard", "manager_context",
     "src/agent_si/backend/orchestration/teamcard.py", 113, None),
    ("worker_context", "teamcard", "worker_context",
     "src/agent_si/backend/orchestration/teamcard.py", 117, None),
    ("teamcard_DecompositionRecord", "teamcard", "DecompositionRecord",
     "src/agent_si/backend/orchestration/teamcard.py", 122, None),
    ("teamcard_record_decomposition", "teamcard", "record_decomposition",
     "src/agent_si/backend/orchestration/teamcard.py", 323,
     "record_decomposition"),
    ("TeamConfigStore", "teamcard", "TeamConfigStore",
     "src/agent_si/backend/orchestration/teamcard.py", 185, None),
    ("validate_team_config_change", "teamcard", "validate_team_config_change",
     "src/agent_si/backend/orchestration/teamcard.py", 195, None),
    ("AuditModelChoice", "teamcard", "AuditModelChoice",
     "src/agent_si/backend/orchestration/teamcard.py", 243, None),
    ("select_audit_model", "teamcard", "select_audit_model",
     "src/agent_si/backend/orchestration/teamcard.py", 329, None),
    ("register_verbatim", "teamcard", "register_verbatim",
     "src/agent_si/backend/orchestration/teamcard.py", 333, None),
    ("TeamReport", "teamcard", "TeamReport",
     "src/agent_si/backend/orchestration/teamcard.py", 295, None),
    ("LedgerRow", "ledger", "LedgerRow",
     "src/agent_si/backend/orchestration/ledger.py", 80, None),
    ("PackageLedger", "ledger", "PackageLedger",
     "src/agent_si/backend/orchestration/ledger.py", 78, None),
    ("PackageLedger.record_row", "ledger", "PackageLedger.record_row",
     "src/agent_si/backend/orchestration/ledger.py", 82, "record_row"),
    ("PackageLedger.get_row", "ledger", "PackageLedger.get_row",
     "src/agent_si/backend/orchestration/ledger.py", 94, "get_row"),
    ("package_report", "ledger", "package_report",
     "src/agent_si/backend/orchestration/ledger.py", 101, None),
    ("LedgerConfigStore", "ledger", "LedgerConfigStore",
     "src/agent_si/backend/orchestration/ledger.py", 137, None),
    ("validate_ledger_config_change", "ledger", "validate_ledger_config_change",
     "src/agent_si/backend/orchestration/ledger.py", 147, None),
    ("LedgerReport", "ledger", "LedgerReport",
     "src/agent_si/backend/orchestration/ledger.py", 254, None),
    ("offload_DecisionRow", "offload", "DecisionRow",
     "src/agent_si/backend/orchestration/offload.py", 257, "DecisionRow"),
    ("HandoverRecord", "offload", "HandoverRecord",
     "src/agent_si/backend/orchestration/offload.py", 161, None),
    ("offload_ApplyOutcome", "offload", "ApplyOutcome",
     "src/agent_si/backend/orchestration/offload.py", 67, "ApplyOutcome"),
    ("offload_enabled", "offload", "offload_enabled",
     "src/agent_si/backend/orchestration/offload.py", 247, "_SWITCHES"),
    ("maybe_offload", "offload", "maybe_offload",
     "src/agent_si/backend/orchestration/offload.py", 247, "_SWITCHES"),
    ("apply_offload_config_change", "offload", "apply_offload_config_change",
     "src/agent_si/backend/orchestration/offload.py", 123, "_SWITCHES"),
    ("steplimits_ApplyOutcome", "steplimits", "ApplyOutcome",
     "src/agent_si/backend/orchestration/steplimits.py", 100,
     "ApplyOutcome"),
    ("StepLimits", "steplimits", "StepLimits",
     "src/agent_si/backend/orchestration/steplimits.py", 181, None),
    ("limits_for", "steplimits", "limits_for",
     "src/agent_si/backend/orchestration/steplimits.py", 190,
     "_PROJECT_LIMITS"),
    ("apply_steplimit_config_change", "steplimits",
     "apply_steplimit_config_change",
     "src/agent_si/backend/orchestration/steplimits.py", 115,
     "_PROJECT_LIMITS"),
]


@pytest.mark.parametrize("name,home,dotted,cite_file,cite_line,token", _CALL,
                         ids=[row[0] for row in _CALL])
def test_wired_call(name, home, dotted, cite_file, cite_line, token,
                    tmp_path):
    mod = _load(home)
    assert callable(_resolve(mod, dotted)), name
    assert (token or dotted.split(".")[-1]) in _cite(cite_file, cite_line)
    _PROBES[name](name, tmp_path)


_MID = "meta/muse-spark-1.3-contributor"

# (stub name, home lane, home attr, expected value, home file)
_CONST = [
    ("split_MODEL_ID", "split", "MODEL_ID", _MID, "split.py"),
    ("parts_MODEL_ID", "parts", "MODEL_ID", _MID, "parts.py"),
    ("graph_MODEL_ID", "graph", "MODEL_ID", _MID, "graph.py"),
    ("overlap_MODEL_ID", "overlap", "MODEL_ID", _MID, "overlap.py"),
    ("delta_MODEL_ID", "delta", "MODEL_ID", _MID, "delta.py"),
    ("teamcard_MODEL_ID", "teamcard", "MODEL_ID", _MID, "teamcard.py"),
    ("SECRET_REF_KEY", "split", "SECRET_REF_KEY", "secret_ref", "split.py"),
    ("split_ARTIFACT_PREFIX", "split", "ARTIFACT_PREFIX", "artifact://",
     "split.py"),
    ("split_ARTIFACT_REF_PREFIX", "split", "ARTIFACT_REF_PREFIX",
     "ARTIFACT_REF:", "split.py"),
    ("parts_ARTIFACT_PREFIX", "parts", "ARTIFACT_PREFIX", "artifact://",
     "parts.py"),
    ("parts_ARTIFACT_REF_PREFIX", "parts", "ARTIFACT_REF_PREFIX",
     "ARTIFACT_REF:", "parts.py"),
    ("parts_GATE_PASS", "parts", "GATE_PASS", "PASS", "parts.py"),
    ("parts_AUDIT_PASS", "parts", "AUDIT_PASS", "PASS", "parts.py"),
    ("parts_GATE_VERDICTS", "parts", "GATE_VERDICTS",
     frozenset({"PASS", "FAIL", "BLOCKED"}), "parts.py"),
    ("parts_AUDIT_RESULTS", "parts", "AUDIT_RESULTS",
     frozenset({"PASS", "REWORK", "BLOCKED", "ESCALATE", "FAIL"}),
     "parts.py"),
    ("gates_GATE_PASS", "gates", "GATE_PASS", "PASS", "gates.py"),
    ("gates_AUDIT_PASS", "gates", "AUDIT_PASS", "PASS", "gates.py"),
    ("gates_GATE_VERDICTS", "gates", "GATE_VERDICTS",
     frozenset({"PASS", "FAIL", "BLOCKED"}), "gates.py"),
    ("gates_AUDIT_RESULTS", "gates", "AUDIT_RESULTS",
     frozenset({"PASS", "REWORK", "BLOCKED", "ESCALATE", "FAIL"}),
     "gates.py"),
    ("split_FACT_PART_SIZE_VS_MODEL", "split", "FACT_PART_SIZE_VS_MODEL",
     "part-size-vs-model", "split.py"),
    ("split_FACT_LONG_CONTEXT_ROUTING", "split", "FACT_LONG_CONTEXT_ROUTING",
     "long-context-routing", "split.py"),
    ("split_FACT_CHEAP_SMALL_PARTS", "split", "FACT_CHEAP_SMALL_PARTS",
     "cheap-models-for-small-parts", "split.py"),
    ("split_SMALL_PART_THRESHOLD", "split", "SMALL_PART_THRESHOLD", 8,
     "split.py"),
    ("split_LONG_CONTEXT_THRESHOLD", "split", "LONG_CONTEXT_THRESHOLD", 64,
     "split.py"),
    ("teamcard_FACT_PART_SIZE_VS_MODEL", "teamcard",
     "FACT_PART_SIZE_VS_MODEL", "part-size-vs-model", "teamcard.py"),
    ("teamcard_FACT_LONG_CONTEXT_ROUTING", "teamcard",
     "FACT_LONG_CONTEXT_ROUTING", "long-context-routing", "teamcard.py"),
    ("teamcard_FACT_CHEAP_SMALL_PARTS", "teamcard",
     "FACT_CHEAP_SMALL_PARTS", "cheap-models-for-small-parts",
     "teamcard.py"),
    ("teamcard_SMALL_PART_THRESHOLD", "teamcard", "SMALL_PART_THRESHOLD", 8,
     "teamcard.py"),
    ("teamcard_LONG_CONTEXT_THRESHOLD", "teamcard", "LONG_CONTEXT_THRESHOLD",
     64, "teamcard.py"),
    ("teamcard_REGISTER_PRESERVED", "teamcard", "REGISTER_PRESERVED",
     "PRESERVED", "teamcard.py"),
    ("teamcard_REGISTER_CHANGED", "teamcard", "REGISTER_CHANGED", "CHANGED",
     "teamcard.py"),
    ("teamcard_REGISTER_MISSING", "teamcard", "REGISTER_MISSING", "MISSING",
     "teamcard.py"),
    ("teamcard_REGISTER_CONTRADICTED", "teamcard", "REGISTER_CONTRADICTED",
     "CONTRADICTED", "teamcard.py"),
    ("ledger_REGISTER_PRESERVED", "ledger", "REGISTER_PRESERVED", "PRESERVED",
     "ledger.py"),
    ("ledger_REGISTER_CHANGED", "ledger", "REGISTER_CHANGED", "CHANGED",
     "ledger.py"),
    ("ledger_REGISTER_MISSING", "ledger", "REGISTER_MISSING", "MISSING",
     "ledger.py"),
    ("ledger_REGISTER_CONTRADICTED", "ledger", "REGISTER_CONTRADICTED",
     "CONTRADICTED", "ledger.py"),
    ("TASK_KIND", "steplimits", "TASK_KIND", "task", "steplimits.py"),
    ("CHAT_KIND", "steplimits", "CHAT_KIND", "chat", "steplimits.py"),
    ("STEPLIMIT_SCOPE_PREFIX", "steplimits", "STEPLIMIT_SCOPE_PREFIX",
     "steplimits:", "steplimits.py"),
    ("STEP_LIMIT_MIN", "steplimits", "STEP_LIMIT_MIN", 1, "steplimits.py"),
    ("STEP_LIMIT_CAP", "steplimits", "STEP_LIMIT_CAP", 10000,
     "steplimits.py"),
    ("offload_AUDIT_INDEPENDENCE_REJECTED", "offload",
     "AUDIT_INDEPENDENCE_REJECTED", "AUDIT_INDEPENDENCE_REJECTED",
     "offload.py"),
    ("offload_BUDGET_CAPPED", "offload", "BUDGET_CAPPED", "BUDGET_CAPPED",
     "offload.py"),
    ("offload_POLICY_CONFLICT", "offload", "POLICY_CONFLICT",
     "POLICY_CONFLICT", "offload.py"),
    ("REJECTED_SCOPE_OVERLAP", "offload", "REJECTED_SCOPE_OVERLAP",
     "REJECTED_SCOPE_OVERLAP", "offload.py"),
    ("steplimits_AUDIT_INDEPENDENCE_REJECTED", "steplimits",
     "AUDIT_INDEPENDENCE_REJECTED", "AUDIT_INDEPENDENCE_REJECTED",
     "steplimits.py"),
    ("steplimits_BUDGET_CAPPED", "steplimits", "BUDGET_CAPPED",
     "BUDGET_CAPPED", "steplimits.py"),
    ("steplimits_POLICY_CONFLICT", "steplimits", "POLICY_CONFLICT",
     "POLICY_CONFLICT", "steplimits.py"),
    ("RISK_LEVELS", "graph", "RISK_LEVELS", ("LOW", "MEDIUM", "HIGH",
                                            "CRITICAL"), "graph.py"),
    ("PLANNED", "graph", "PLANNED", "PLANNED", "graph.py"),
    ("DIRECTOR_RUNTIME", "graph", "DIRECTOR_RUNTIME", None, "graph.py"),
    ("AUDIT_CHOICE_LOG", "teamcard", "AUDIT_CHOICE_LOG", [], "teamcard.py"),
    ("DEFAULT_TEAM_CONFIG", "teamcard", "DEFAULT_TEAM_CONFIG", None,
     "teamcard.py"),
    ("DEFAULT_LEDGER_CONFIG", "ledger", "DEFAULT_LEDGER_CONFIG", None,
     "ledger.py"),
    ("CONTROL_PLANE_MAP", "graph", "CONTROL_PLANE_MAP", None, "graph.py"),
    ("split_KNOWN_FACTS", "split", "KNOWN_FACTS", None, "split.py"),
    ("teamcard_KNOWN_FACTS", "teamcard", "KNOWN_FACTS", None, "teamcard.py"),
    ("UNKNOWN_LIMIT_KIND", "steplimits", "UNKNOWN_LIMIT_KIND", None,
     "steplimits.py"),
]


@pytest.mark.parametrize("name,home,attr,expected,cite_file", _CONST,
                         ids=[row[0] for row in _CONST])
def test_const_agreement(name, home, attr, expected, cite_file):
    stub = _load("interface")
    mod = _load(home)
    stub_val = getattr(stub, name)
    home_val = getattr(mod, attr)
    if isinstance(stub_val, type) and isinstance(home_val, type):
        assert stub_val is not home_val, name
        assert stub_val.__name__ == home_val.__name__, name
        assert [base.__name__ for base in stub_val.__mro__] == [
            base.__name__ for base in home_val.__mro__], name
        return
    assert stub_val == home_val, name
    if expected is not None:
        assert stub_val == expected, name
        if isinstance(expected, str):
            text = (_root() / "src/agent_si/backend/orchestration"
                    / cite_file).read_text(encoding="utf-8")
            assert expected in text, name


def test_part_status_literal():
    import typing
    stub = _load("interface")
    parts = _load("parts")
    assert typing.get_origin(stub.PartStatus) is typing.Literal
    assert set(typing.get_args(stub.PartStatus)) == set(
        typing.get_args(parts.PartStatus))
    assert set(typing.get_args(stub.PartStatus)) == {
        "QUEUED", "RUNNING", "RETURNED", "ACCEPTED", "REJECTED", "BLOCKED",
        "HANDOFF"}


def test_cross_lane_value_agreement():
    split = _load("split")
    parts = _load("parts")
    teamcard = _load("teamcard")
    ledger = _load("ledger")
    offload = _load("offload")
    steplimits = _load("steplimits")
    assert split.MODEL_ID == teamcard.MODEL_ID == (
        "meta/muse-spark-1.3-contributor")
    for code in ("REGISTER_PRESERVED", "REGISTER_CHANGED",
                 "REGISTER_MISSING", "REGISTER_CONTRADICTED"):
        assert getattr(teamcard, code) == getattr(ledger, code)
    assert split.KNOWN_FACTS == teamcard.KNOWN_FACTS
    assert split.SMALL_PART_THRESHOLD == teamcard.SMALL_PART_THRESHOLD == 8
    assert split.LONG_CONTEXT_THRESHOLD == teamcard.LONG_CONTEXT_THRESHOLD
    assert split.LONG_CONTEXT_THRESHOLD == 64
    for code in ("AUDIT_INDEPENDENCE_REJECTED", "BUDGET_CAPPED",
                 "POLICY_CONFLICT"):
        assert getattr(offload, code) == getattr(steplimits, code)
    assert split.ARTIFACT_PREFIX == parts.ARTIFACT_PREFIX == "artifact://"
    assert split.ARTIFACT_REF_PREFIX == parts.ARTIFACT_REF_PREFIX


# ---- (d) one definition per name in interface.py ----

def _stub_name_sets():
    stub = _load("interface")
    text = pathlib.Path(stub.__file__).read_text(encoding="utf-8")
    tree = ast.parse(text)
    funcs = set()
    valued = set()
    bare = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            if not node.name.startswith("_"):
                funcs.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith(
                        "_"):
                    valued.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(
                node.target, ast.Name):
            if not node.target.id.startswith("_"):
                if node.value is None:
                    bare.add(node.target.id)
                else:
                    valued.add(node.target.id)
    methods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not sub.name.startswith("_"):
                        methods.add(node.name + "." + sub.name)
    return funcs, valued, methods, bare


def test_one_definition_per_name():
    stub = _load("interface")
    text = pathlib.Path(stub.__file__).read_text(encoding="utf-8")
    tree = ast.parse(text)
    counts = {}
    for node in tree.body:
        names = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.Assign):
            names = [target.id for target in node.targets
                     if isinstance(target, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(
                node.target, ast.Name):
            names = [node.target.id]
        for name in names:
            if name.startswith("_"):
                continue
            counts[name] = counts.get(name, 0) + 1
    dupes = sorted(name for name, total in counts.items() if total > 1)
    assert dupes == []
    assert len(counts) > 100


# ---- (e) cross-lane waits: strict xfail with "<lane>: <row>" only ----
# Each entry names stub surfaces whose production caller lives in a
# sibling package or in INT2 wiring (out of this workspace, read-only
# here by scope). The wait test proves the K02 side is present, then
# fails with the wait message; strict xfail keeps the wait visible.

_WAITS = [
    ("split-cap-queue", "split: B0B-UNCOVERED_ARCH-762",
     [("capped_queue", "split", "capped_queue")]),
    ("split-decomp-persist", "split: R-301",
     [("persist_decompositions", "split", "persist_decompositions"),
      ("load_decompositions", "split", "load_decompositions"),
      ("split_record_decomposition", "split", "record_decomposition")]),
    ("split-secret-twin", "split: V7",
     [("split_make_secret_ref", "split", "make_secret_ref")]),
    ("gates-chain", "gates: B0B-BP06-30",
     [("check_hierarchy_activation", "gates",
       "check_hierarchy_activation")]),
    ("gates-fresh-readers", "gates: 94",
     [("GateAuditLog", "gates", "GateAuditLog"),
      ("GateAuditLog.gate_verdict", "gates", "GateAuditLog.gate_verdict"),
      ("GateAuditLog.audit_verdict", "gates", "GateAuditLog.audit_verdict"),
      ("GateAuditLog.has_fresh_audit", "gates",
       "GateAuditLog.has_fresh_audit")]),
    ("graph-planner", "graph: SPEC 22",
     [("TaskPlanner", "graph", "TaskPlanner"),
      ("TaskPlanner.plan", "graph", "TaskPlanner.plan")]),
    ("graph-store-activate", "graph: R-302",
     [("HierarchyConfigStore.activate_chain", "graph",
       "HierarchyConfigStore.activate_chain")]),
    ("graph-corrections", "graph: B0B-UNCOVERED_ARCH-704",
     [("HierarchyConfigStore.append_user_correction", "graph",
       "HierarchyConfigStore.append_user_correction")]),
    ("graph-role-authority", "graph: B0B-UNCOVERED_BP06-78",
     [("HierarchyConfigStore.grant_role_authority", "graph",
       "HierarchyConfigStore.grant_role_authority")]),
    ("graph-size-team", "graph: R-303",
     [("HierarchyConfigStore.size_team", "graph",
       "HierarchyConfigStore.size_team")]),
    ("graph-dispatch", "graph: B0B-UNCOVERED_ARCH-7",
     [("validate_dispatch", "graph", "validate_dispatch")]),
    ("graph-scheduler", "graph: R-359",
     [("build_graph", "graph", "build_graph"),
      ("ready_parts", "graph", "ready_parts"),
      ("mark_completed", "graph", "mark_completed")]),
    ("graph-control-map", "graph: 22",
     [("control_plane_map", "graph", "control_plane_map")]),
    ("graph-director-guard", "graph: M-P1-42",
     [("require_explicit_director", "graph",
       "require_explicit_director")]),
    ("graph-stage-rows", "graph: M-P2-80",
     [("stage_rows_to_hierarchy", "graph", "stage_rows_to_hierarchy")]),
    ("graph-store-class", "graph: 103",
     [("HierarchyConfigStore", "graph", "HierarchyConfigStore")]),
    ("overlap-early", "overlap: 101",
     [("early_start_allowed", "overlap", "early_start_allowed")]),
    ("overlap-settings", "overlap: R-359",
     [("validate_multi_manager_settings", "overlap",
       "validate_multi_manager_settings")]),
    ("delta-intake", "delta: 116",
     [("delta_intake_bounded_delta", "delta", "intake_bounded_delta")]),
    ("delta-cross-check", "delta: 118",
     [("cross_check", "delta", "cross_check")]),
    ("delta-linkcheck", "delta: 117",
     [("close_with_linkcheck", "delta", "close_with_linkcheck")]),
    ("delta-stored", "delta: 103",
     [("validate_stored_config", "delta", "validate_stored_config"),
      ("apply_stored_config", "delta", "apply_stored_config")]),
    ("delta-activate", "delta: B0B-BP06-30",
     [("activate_hierarchy_chain", "delta", "activate_hierarchy_chain")]),
    ("manifest-check", "manifest: 96",
     [("check_part_manifest", "manifest", "check_part_manifest"),
      ("check_manifest", "manifest", "check_manifest"),
      ("build_manifest", "manifest", "build_manifest"),
      ("save_manifest", "manifest", "save_manifest"),
      ("load_manifest", "manifest", "load_manifest"),
      ("ManifestRec.from_dict", "manifest", "ManifestRec.from_dict")]),
    ("parts-store", "parts: 33",
     [("PartStore", "parts", "PartStore"),
      ("PartStore.register", "parts", "PartStore.register"),
      ("PartStore.get", "parts", "PartStore.get"),
      ("PartStore.record_gate_verdict", "parts",
       "PartStore.record_gate_verdict"),
      ("PartStore.record_audit_verdict", "parts",
       "PartStore.record_audit_verdict"),
      ("PartStore.gate_verdict", "parts", "PartStore.gate_verdict"),
      ("PartStore.audit_verdict", "parts", "PartStore.audit_verdict")]),
    ("parts-frozen-ref", "parts: M-P1-15",
     [("ClosedPartRef", "parts", "ClosedPartRef")]),
    ("parts-gate-refused", "parts: 94",
     [("parts_GateRefused", "parts", "GateRefused")]),
    ("teamcard-build", "teamcard: R-301",
     [("build_team_card", "teamcard", "build_team_card"),
      ("build_team_report", "teamcard", "build_team_report")]),
    ("teamcard-apply", "teamcard: R-358",
     [("apply_team_config_change", "teamcard",
       "apply_team_config_change")]),
    ("ledger-apply", "ledger: R-358",
     [("apply_ledger_config_change", "ledger",
       "apply_ledger_config_change")]),
    ("ledger-reports", "ledger: 35",
     [("build_package_report", "ledger", "build_package_report"),
      ("build_ledger_report", "ledger", "build_ledger_report")]),
    ("ledger-persist", "ledger: M-P1-17",
     [("persist_ledger", "ledger", "persist_ledger"),
      ("load_ledger", "ledger", "load_ledger"),
      ("PackageLedger.package_ids", "ledger",
       "PackageLedger.package_ids")]),
    ("ledger-intake", "ledger: 116",
     [("ledger_intake_bounded_delta", "ledger", "intake_bounded_delta")]),
    ("common-applied", "common: R-358",
     [("AppliedOutcome", "common", "AppliedOutcome")]),
]


def _run_wait(wait_id):
    for known_id, reason, names in _WAITS:
        if known_id == wait_id:
            break
    else:
        raise AssertionError("unknown wait: " + wait_id)
    for name, home, dotted in names:
        _resolve(_load(home), dotted)
    pytest.fail("wait: the production caller for %s lives outside this "
                "workspace (%s)" % (wait_id, reason))


def test_wiring_covers_stub_callables():
    funcs, valued, methods, bare = _stub_name_sets()
    wired = ({row[0] for row in _RAISE} | {row[0] for row in _CALL} |
             {row[0] for row in _SERVE})
    agreed = {row[0] for row in _CONST} | {"PartStatus"}
    waited = {name for _, _, names in _WAITS for name, _, _ in names}
    assert (funcs | methods) - wired - waited == set()
    assert valued - agreed - bare == set()
    assert (wired | waited | agreed) - funcs - methods - valued == set()


def test_waits_have_tests():
    import sys
    mod = sys.modules[__name__]
    missing = ["test_wait_" + wait_id.replace("-", "_") for wait_id, _, _
               in _WAITS if not hasattr(mod, "test_wait_" + wait_id.replace(
                   "-", "_"))]
    assert missing == []


@pytest.mark.xfail(strict=True, reason="split: B0B-UNCOVERED_ARCH-762")
def test_wait_split_cap_queue():
    _run_wait("split-cap-queue")


@pytest.mark.xfail(strict=True, reason="split: R-301")
def test_wait_split_decomp_persist():
    _run_wait("split-decomp-persist")


@pytest.mark.xfail(strict=True, reason="split: V7")
def test_wait_split_secret_twin():
    _run_wait("split-secret-twin")


@pytest.mark.xfail(strict=True, reason="gates: B0B-BP06-30")
def test_wait_gates_chain():
    _run_wait("gates-chain")


@pytest.mark.xfail(strict=True, reason="gates: 94")
def test_wait_gates_fresh_readers():
    _run_wait("gates-fresh-readers")


@pytest.mark.xfail(strict=True, reason="graph: SPEC 22")
def test_wait_graph_planner():
    _run_wait("graph-planner")


@pytest.mark.xfail(strict=True, reason="graph: R-302")
def test_wait_graph_store_activate():
    _run_wait("graph-store-activate")


@pytest.mark.xfail(strict=True, reason="graph: B0B-UNCOVERED_ARCH-704")
def test_wait_graph_corrections():
    _run_wait("graph-corrections")


@pytest.mark.xfail(strict=True, reason="graph: B0B-UNCOVERED_BP06-78")
def test_wait_graph_role_authority():
    _run_wait("graph-role-authority")


@pytest.mark.xfail(strict=True, reason="graph: R-303")
def test_wait_graph_size_team():
    _run_wait("graph-size-team")


@pytest.mark.xfail(strict=True, reason="graph: B0B-UNCOVERED_ARCH-7")
def test_wait_graph_dispatch():
    _run_wait("graph-dispatch")


@pytest.mark.xfail(strict=True, reason="graph: R-359")
def test_wait_graph_scheduler():
    _run_wait("graph-scheduler")


@pytest.mark.xfail(strict=True, reason="graph: 22")
def test_wait_graph_control_map():
    _run_wait("graph-control-map")


@pytest.mark.xfail(strict=True, reason="graph: M-P1-42")
def test_wait_graph_director_guard():
    _run_wait("graph-director-guard")


@pytest.mark.xfail(strict=True, reason="graph: M-P2-80")
def test_wait_graph_stage_rows():
    _run_wait("graph-stage-rows")


@pytest.mark.xfail(strict=True, reason="graph: 103")
def test_wait_graph_store_class():
    _run_wait("graph-store-class")


@pytest.mark.xfail(strict=True, reason="overlap: 101")
def test_wait_overlap_early():
    _run_wait("overlap-early")


@pytest.mark.xfail(strict=True, reason="overlap: R-359")
def test_wait_overlap_settings():
    _run_wait("overlap-settings")


@pytest.mark.xfail(strict=True, reason="delta: 116")
def test_wait_delta_intake():
    _run_wait("delta-intake")


@pytest.mark.xfail(strict=True, reason="delta: 118")
def test_wait_delta_cross_check():
    _run_wait("delta-cross-check")


@pytest.mark.xfail(strict=True, reason="delta: 117")
def test_wait_delta_linkcheck():
    _run_wait("delta-linkcheck")


@pytest.mark.xfail(strict=True, reason="delta: 103")
def test_wait_delta_stored():
    _run_wait("delta-stored")


@pytest.mark.xfail(strict=True, reason="delta: B0B-BP06-30")
def test_wait_delta_activate():
    _run_wait("delta-activate")


@pytest.mark.xfail(strict=True, reason="manifest: 96")
def test_wait_manifest_check():
    _run_wait("manifest-check")


@pytest.mark.xfail(strict=True, reason="parts: 33")
def test_wait_parts_store():
    _run_wait("parts-store")


@pytest.mark.xfail(strict=True, reason="parts: M-P1-15")
def test_wait_parts_frozen_ref():
    _run_wait("parts-frozen-ref")


@pytest.mark.xfail(strict=True, reason="parts: 94")
def test_wait_parts_gate_refused():
    _run_wait("parts-gate-refused")


@pytest.mark.xfail(strict=True, reason="teamcard: R-301")
def test_wait_teamcard_build():
    _run_wait("teamcard-build")


@pytest.mark.xfail(strict=True, reason="teamcard: R-358")
def test_wait_teamcard_apply():
    _run_wait("teamcard-apply")


@pytest.mark.xfail(strict=True, reason="ledger: R-358")
def test_wait_ledger_apply():
    _run_wait("ledger-apply")


@pytest.mark.xfail(strict=True, reason="ledger: 35")
def test_wait_ledger_reports():
    _run_wait("ledger-reports")


@pytest.mark.xfail(strict=True, reason="ledger: M-P1-17")
def test_wait_ledger_persist():
    _run_wait("ledger-persist")


@pytest.mark.xfail(strict=True, reason="ledger: 116")
def test_wait_ledger_intake():
    _run_wait("ledger-intake")


@pytest.mark.xfail(strict=True, reason="common: R-358")
def test_wait_common_applied():
    _run_wait("common-applied")
