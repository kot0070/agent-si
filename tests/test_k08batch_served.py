"""K08BATCH served proofs: 10 K08 rows via create_app + TestClient.

Row order (easiest first): 186 watcher preset seeded | R-321 workspace
escape alert+block | R-322 watcher untouchable restart | R-323 one-click
Stop all | R-324 watcher alerts never stops | R-326 stop hierarchy stops
everything | R-327 temp cleanup script | R-335 timers/launchers | 249
named apps card + closing prompt | 181 outage stop-and-report.

Every test drives the served app (create_app + HTTP client, loopback TEST
data only). Lane setup (template/trigger registration, child attach,
temp planting) uses real product APIs; facts are verified over served
reads plus the owned lane stores. No doubles, no skip/xfail.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.append(str(SRC))

from fastapi.testclient import TestClient  # noqa: E402

import agent_si.automation.interface as auto_iface  # noqa: E402
from agent_si.automation import launcher as _launcher  # noqa: E402
from agent_si.automation import pause as _pause  # noqa: E402
from agent_si.automation import runner as _runner  # noqa: E402
from agent_si.automation import scheduler as _sched  # noqa: E402
from agent_si.automation import service_status as _services  # noqa: E402
from agent_si.automation import service_watch as _watch  # noqa: E402
from agent_si.automation import templates as _templates  # noqa: E402
from agent_si.automation import triggers as _triggers  # noqa: E402
from agent_si.backend import stop_all as _stop_all  # noqa: E402
from agent_si.backend.app import create_app  # noqa: E402
from agent_si.watcher import engine as _engine  # noqa: E402
from agent_si.watcher import guard as _guard  # noqa: E402
from agent_si.watcher import integrity as _integrity  # noqa: E402
from agent_si.watcher import journal as _journal  # noqa: E402
from agent_si.watcher import outage as _watch_outage  # noqa: E402
from agent_si.watcher import presets as _presets  # noqa: E402
from agent_si.watcher import rules as _rules  # noqa: E402
from agent_si.watcher import status as _status  # noqa: E402
from agent_si.watcher.journal import WatcherError  # noqa: E402

TESTID = "k08batch-served"
TOKEN = "k08batch-token"


def _settings():
    return {"testing": True, "ui_session_token": TOKEN}


def _auth():
    return {"x-ui-session-token": TOKEN}


def _client():
    return TestClient(create_app(_settings()))


@pytest.fixture(autouse=True)
def _lane():
    """Reset every touched lane store; no doubles, real backends only."""
    _pause.reset_state()
    _runner.reset_state()
    _templates._IMPORTS.clear()
    _triggers.reset_state()
    _sched.reset_state()
    _launcher.set_journal_hook(None)
    _launcher.set_guard_hook(None)
    _journal.reset_state()
    _integrity.reset_state()
    _rules.reset_state()
    _engine.reset_state()
    _presets.reset_state()
    _status.reset_state()
    _services.reset_state()
    _watch.reset_baseline()
    _stop_all.reset_state()
    yield
    _stop_all.reset_state()
    _journal.reset_state()
    _integrity.reset_state()
    _rules.reset_state()
    _engine.reset_state()
    _presets.reset_state()
    _status.reset_state()
    _pause.reset_state()
    _runner.set_run_temp_base(None)


def _spawn_sleeper():
    """One real endless child process for stop tests (portable)."""
    return subprocess.Popen(
        [sys.executable, "-c", "import time\nwhile True: time.sleep(0.05)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _reap(proc):
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()
                proc.wait(timeout=10)
    except Exception:
        pass


def _served_journal(client, project_id, kind):
    resp = client.get("/api/v1/watcher/journal",
                      params={"project_id": project_id, "kind": kind})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_186_preset_seeded_on_first_served_evaluate():
    """Row 186 [k08batch-served]: first served evaluate seeds standard."""
    assert TESTID == "k08batch-served"
    client = _client()
    pid = "k08batch-186-p1"
    assert _presets.installed_cards(pid) == ()
    resp = client.post("/api/v1/watcher/rules/rule-tamper/evaluate",
                       json={"project_id": pid}, headers=_auth())
    assert resp.status_code == 200, resp.text
    assert _presets.installed_cards(pid) == ("card-hang", "card-guard")
    seeds = _journal.stored_rows(pid, "SERVICE_STATE")
    assert any("seed standard preset" in row.summary for row in seeds)
    assert any(
        row["entry_id"] == seeds[0].entry_id
        for row in _served_journal(client, pid, "SERVICE_STATE")
    )
    again = client.post("/api/v1/watcher/rules/rule-tamper/evaluate",
                        json={"project_id": pid}, headers=_auth())
    assert again.status_code == 200, again.text
    assert len(_journal.stored_rows(pid, "SERVICE_STATE")) == len(seeds)


def test_r321_escape_from_facts_alerts_and_blocks():
    """Row R-321 [k08batch-served]: escape from facts alerts + blocks."""
    assert TESTID == "k08batch-served"
    client = _client()
    pid = "k08batch-r321-p1"
    _journal.append_event(pid, "agent-x", "TAMPER_ATTEMPT",
                          "write outside workspace", ("/outside/evil.txt",))
    resp = client.post("/api/v1/watcher/rules/rule-tamper/evaluate",
                       json={"project_id": pid}, headers=_auth())
    assert resp.status_code == 200, resp.text
    assert resp.json()["verdict"] == "BLOCK"
    assert len(_served_journal(client, pid, "WATCH_DECISION")) == 1
    blocked = _guard.check_escape(pid, "/outside/evil.txt", "/ws/proj")
    assert blocked.allowed is False
    assert blocked.reason != ""
    calm = _guard.check_escape(pid, "/ws/proj/notes.txt", "/ws/proj")
    assert calm.allowed is True


def test_r322_watcher_untouchable_restart_across_stop():
    """Row R-322 [k08batch-served]: stop-all never stops the watcher."""
    assert TESTID == "k08batch-served"
    client = _client()
    pid = "k08batch-r322-p1"
    proc = _spawn_sleeper()
    try:
        _stop_all.attach_child(pid, "run-k08batch-r322-1", proc)
        stopped = client.post("/api/v1/stop-all",
                              json={"actor": "user", "project_id": pid},
                              headers=_auth())
        assert stopped.status_code == 200, stopped.text
        assert stopped.json()["accepted"] is True
        assert proc.poll() is not None
        status = client.get("/api/v1/watcher/status",
                            params={"project_id": pid})
        assert status.status_code == 200, status.text
        evaluated = client.post(
            "/api/v1/watcher/rules/rule-tamper/evaluate",
            json={"project_id": pid}, headers=_auth())
        assert evaluated.status_code == 200, evaluated.text
    finally:
        _reap(proc)
    receipt = _engine.supervised_restart(pid, "supervisor-batch")
    assert receipt.accepted is True
    assert receipt.journal_entry_id != ""
    with pytest.raises(WatcherError) as excinfo:
        _engine.supervised_restart(pid, "")
    assert excinfo.value.code == "STOP_REASON_MISSING"


def test_r323_one_click_stop_all_served():
    """Row R-323 [k08batch-served]: one user stop-all stops the run."""
    assert TESTID == "k08batch-served"
    client = _client()
    pid = "k08batch-r323-p1"
    proc = _spawn_sleeper()
    try:
        _stop_all.attach_child(pid, "run-k08batch-r323-1", proc)
        resp = client.post("/api/v1/stop-all",
                           json={"actor": "user", "project_id": pid},
                           headers=_auth())
        assert resp.status_code == 200, resp.text
        assert resp.json()["accepted"] is True
        assert resp.json()["stopped_count"] >= 1
        assert proc.poll() is not None
        assert _stop_all.attached(pid) == ()
    finally:
        _reap(proc)
    rows = _served_journal(client, pid, "STOP_ALL")
    assert len(rows) == 1
    assert rows[0]["entry_id"] == resp.json()["journal_entry_id"]
    assert any("stop-all by user" in row.summary for row in
               _journal.stored_rows(pid, "STOP_ALL"))


def test_r324_watcher_alerts_but_never_stops():
    """Row R-324 [k08batch-served]: alerts are read-only, agents untouched."""
    assert TESTID == "k08batch-served"
    client = _client()
    pid = "k08batch-r324-p1"
    proc = _spawn_sleeper()
    try:
        _stop_all.attach_child(pid, "run-k08batch-r324-1", proc)
        before = len(_journal.stored_rows(pid))
        alerts = client.get("/api/v1/watcher/alerts",
                            params={"project_id": pid})
        assert alerts.status_code == 200, alerts.text
        rows = alerts.json()["alerts"]
        assert len(rows) == len(_engine.DUE_CARDS)
        assert proc.poll() is None
        assert _stop_all.attached(pid) != ()
        assert len(_journal.stored_rows(pid)) == before
        kinds = [row.kind for row in _journal.stored_rows(pid)]
        assert "STOP_ALL" not in kinds
    finally:
        _reap(proc)


def test_r326_stop_hierarchy_stops_everything():
    """Row R-326 [k08batch-served]: one stop-all stops the hierarchy."""
    assert TESTID == "k08batch-served"
    client = _client()
    pid = "k08batch-r326-p1"
    parent = _spawn_sleeper()
    child = _spawn_sleeper()
    try:
        _stop_all.attach_child(pid, "run-k08batch-r326-parent", parent)
        _stop_all.attach_child(pid, "run-k08batch-r326-child", child)
        assert len(_stop_all.attached(pid)) == 2
        resp = client.post("/api/v1/stop-all",
                           json={"actor": "user", "project_id": pid},
                           headers=_auth())
        assert resp.status_code == 200, resp.text
        assert resp.json()["accepted"] is True
        assert resp.json()["stopped_count"] >= 2
        assert parent.poll() is not None
        assert child.poll() is not None
        assert _stop_all.attached(pid) == ()
    finally:
        _reap(parent)
        _reap(child)


def test_r327_temp_cleanup_script_served_journal():
    """Row R-327 [k08batch-served]: janitor cleans one run temp, journaled."""
    assert TESTID == "k08batch-served"
    client = _client()
    pid = "k08batch-r327-p1"
    run_id = "run-k08batch-r327"
    with tempfile.TemporaryDirectory(prefix="k08batch-327-") as base:
        from agent_si.automation import cleanup as _cleanup

        target = Path(_cleanup.run_dir_for(base, run_id))
        (target / "nested").mkdir(parents=True)
        (target / "out.log").write_text("log bytes", encoding="utf-8")
        (target / "nested" / "deep.tmp").write_text("deep",
                                                    encoding="utf-8")
        result = _engine.run_script(pid, "temp-file-janitor", (run_id,),
                                    run_temp_base=base)
        assert result.outcome == "cleaned"
        assert "removed=2" in result.detail
        assert target.is_dir()
        assert list(target.iterdir()) == []
    served = _served_journal(client, pid, "SERVICE_STATE")
    assert any(row["entry_id"] == result.journal_entry_id
               for row in served)
    assert any("temp-file-janitor" in row.summary for row in
               _journal.stored_rows(pid, "SERVICE_STATE"))


def test_r335_timers_launchers_served():
    """Row R-335 [k08batch-served]: watcher timers + trigger launch served."""
    assert TESTID == "k08batch-served"
    client = _client()
    pid = "k08batch-r335-p1"
    fired = client.post("/api/v1/watcher/timers/tm-k08batch/fire",
                        json={"project_id": pid}, headers=_auth())
    assert fired.status_code == 200, fired.text
    assert fired.json()["event"] == "TIMER_FIRED"
    assert fired.json()["action_mode"] == "local_ai_default"
    rows = _served_journal(client, pid, "AUTOMATION_RUN")
    assert any(row["entry_id"] == fired.json()["journal_entry_id"]
               for row in rows)
    assert any("TIMER_FIRED" in row.summary for row in
               _journal.stored_rows(pid, "AUTOMATION_RUN"))
    paused = client.post("/api/v1/watcher/timers/tm-k08batch/pause",
                         json={"project_id": pid, "paused": True,
                               "reason": "k08batch drill"},
                         headers=_auth())
    assert paused.status_code == 200, paused.text
    refused = client.post("/api/v1/watcher/timers/tm-k08batch/fire",
                          json={"project_id": pid}, headers=_auth())
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "AUTOMATION_PAUSED"
    resumed = client.post("/api/v1/watcher/timers/tm-k08batch/pause",
                          json={"project_id": pid, "paused": False,
                                "reason": ""},
                          headers=_auth())
    assert resumed.status_code == 200, resumed.text
    _runner.register_template("tpl-k08batch-335", pid, "batch 335")
    _triggers.register_trigger("trg-k08batch-335", pid, kind="TIMER",
                               schedule_ref="tm-k08batch")
    launched = client.post(
        "/api/v1/automations/triggers/trg-k08batch-335/fire",
        json={"project_id": pid}, headers=_auth())
    assert launched.status_code == 200, launched.text
    assert launched.json()["state"] == "RUNNING"


def test_249_apps_card_closing_prompt_served():
    """Row 249 [k08batch-served]: card serves facts, pause mirrors close."""
    assert TESTID == "k08batch-served"
    client = _client()
    proj = "proj-b"
    _runner.register_template("tpl-k08batch-249", proj, "batch card")
    started = client.post("/api/v1/automations/runs",
                          json={"project_id": proj,
                                "template_id": "tpl-k08batch-249"},
                          headers=_auth())
    assert started.status_code == 200, started.text
    assert started.json()["state"] == "RUNNING"
    card = client.get("/api/v1/apps/card", params={"project_id": proj})
    assert card.status_code == 200, card.text
    payload = card.json()
    assert payload["project_id"] == proj
    assert "svc-loopback" in payload["service_ids"]
    assert payload["paused"] is False
    assert payload["generated_at"] != ""
    paused = client.post("/api/v1/automations/pause",
                         json={"paused": True, "reason": "k08batch 249"},
                         headers=_auth())
    assert paused.status_code == 200, paused.text
    closed = client.get("/api/v1/apps/card", params={"project_id": proj})
    assert closed.json()["paused"] is True
    opened = client.post("/api/v1/automations/pause",
                         json={"paused": False, "reason": ""},
                         headers=_auth())
    assert opened.status_code == 200, opened.text
    assert client.get(
        "/api/v1/apps/card",
        params={"project_id": proj}).json()["paused"] is False


def test_181_outage_stop_and_report_never_double():
    """Row 181 [k08batch-served]: one outage stops once + one report row."""
    assert TESTID == "k08batch-served"
    client = _client()
    pid = "k08batch-181-p1"
    proc = _spawn_sleeper()
    try:
        _stop_all.attach_child(pid, "run-k08batch-181-1", proc)
        first = _watch_outage.signal_outage(pid, "svc-a",
                                            "outage svc-a down")
        assert first.stopped is True
        assert proc.poll() is not None
    finally:
        _reap(proc)
    assert len(_served_journal(client, pid, "STOP_ALL")) == 1
    outage_rows = _served_journal(client, pid, "OUTAGE_SIGNAL")
    assert len(outage_rows) == 1
    stored = _journal.stored_rows(pid, "OUTAGE_SIGNAL")
    assert len(stored) == 1
    assert "STOP_AND_REPORT" in stored[0].summary
    second = _watch_outage.signal_outage(pid, "svc-a",
                                         "outage svc-a down")
    assert second.stopped is False
    assert len(_served_journal(client, pid, "STOP_ALL")) == 1
    assert len(_served_journal(client, pid, "OUTAGE_SIGNAL")) == 1


def _served_start_run(client, project_id, template_id):
    """Start one run over the served runs route (real template row)."""
    _runner.register_template(template_id, project_id,
                              "batch %s" % template_id)
    resp = client.post("/api/v1/automations/runs",
                       json={"project_id": project_id,
                             "template_id": template_id},
                       headers=_auth())
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "RUNNING"
    return resp.json()["run_id"]


def _served_cancel(client, project_id, run_id, reason, mode=None):
    """Cancel one run over the served run-cancel route."""
    body = {"project_id": project_id, "reason": reason}
    if mode is not None:
        body["mode"] = mode
    return client.post("/api/v1/automations/runs/%s/cancel" % run_id,
                       json=body, headers=_auth())


def test_mp3_112_builtin_or_import_only_served():
    """Row M-P3-112 [k08batch-served]: builtin or import only, served."""
    assert TESTID == "k08batch-served"
    client = _client()
    pid = "k08batch-mp3-112-p1"
    resp = client.post(
        "/api/v1/automations/templates/tpl-nightly/instantiate",
        json={"project_id": pid}, headers=_auth())
    assert resp.status_code == 200, resp.text
    assert resp.json()["template_id"] == "tpl-nightly"
    plan = _templates.materialize(pid, "tpl-nightly")
    assert plan["model"] == "meta/muse-spark-1.3-contributor"
    assert plan["project_id"] == pid
    for step in plan["steps"]:
        assert step["action"] in _templates.ACTION_CATALOG
        assert step["outputs"] != []
    missing = client.post(
        "/api/v1/automations/templates/tpl-scripted/instantiate",
        json={"project_id": pid}, headers=_auth())
    assert missing.status_code == 404, missing.text
    assert missing.json()["detail"]["code"] == "TEMPLATE_NOT_FOUND"
    spec = {"name": "k08batch-import", "version": 1, "steps": [
        {"action": "service.check",
         "with": {"service_id": "svc-api"},
         "outputs": ["service_id", "state", "checked_at"]}]}
    assert _templates.import_template(
        "tpl-k08batch-112", spec) == "tpl-k08batch-112"
    imported = client.post(
        "/api/v1/automations/templates/tpl-k08batch-112/instantiate",
        json={"project_id": pid}, headers=_auth())
    assert imported.status_code == 200, imported.text
    assert imported.json()["template_id"] == "tpl-k08batch-112"
    bad = {"name": "bad", "version": 1, "steps": [
        {"action": "service.stop", "with": {}, "outputs": ["ok"]}]}
    with pytest.raises(ValueError):
        _templates.import_template("tpl-k08batch-112-bad", bad)


def test_mp4_160_checkpoint_benchmark_served():
    """Row M-P4-160 [k08batch-served]: save-restore benchmark served."""
    assert TESTID == "k08batch-served"
    client = _client()
    pid = "k08batch-mp4-160-p1"
    resp = client.post(
        "/api/v1/watcher/checkpoints/benchmark",
        json={"project_id": pid, "task_id": "task-1", "run_id": "run-1",
              "contract_hash": "hash-a", "context_refs": ["ref-a"],
              "sourced_refs": ["ref-a"]},
        headers=_auth())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["restored_ok"] is True
    assert body["saved_refs"] == ["ref-a"]
    assert body["restored_refs"] == ["ref-a"]
    assert body["markers"] == [["ref-a", "SOURCED"]]
    assert body["sourced_count"] == 1
    assert body["unknown_count"] == 0
    ghost = client.post(
        "/api/v1/watcher/checkpoints/benchmark",
        json={"project_id": pid, "task_id": "task-1", "run_id": "run-1",
              "contract_hash": "hash-a",
              "context_refs": ["ref-a", "ref-ghost"],
              "sourced_refs": ["ref-a"]},
        headers=_auth())
    assert ghost.status_code == 200, ghost.text
    assert ghost.json()["restored_ok"] is True
    assert ghost.json()["markers"] == [["ref-a", "SOURCED"],
                                       ["ref-ghost", "UNKNOWN"]]
    assert ghost.json()["sourced_count"] == 1
    assert ghost.json()["unknown_count"] == 1


def test_b0b_sdk_94_cancel_modes_served():
    """Row B0B-SDK-94 [k08batch-served]: immediate default + after-turn."""
    import inspect

    assert TESTID == "k08batch-served"
    assert inspect.signature(_runner.cancel_run).parameters[
        "mode"].default == "immediate"
    client = _client()
    pid = "k08batch-sdk94-p1"
    run_id = _served_start_run(client, pid, "tpl-k08batch-94")
    immediate = _served_cancel(client, pid, run_id, "sdk-94")
    assert immediate.status_code == 200, immediate.text
    assert immediate.json()["state"] == "CANCELLED"
    other = _served_start_run(client, pid, "tpl-k08batch-94")
    _runner.begin_turn(pid, other)
    flagged = _served_cancel(client, pid, other, "sdk-94b",
                             mode="after-turn")
    assert flagged.status_code == 200, flagged.text
    assert flagged.json()["state"] == "RUNNING"
    done = _runner.complete_turn(pid, other)
    assert done["state"] == "CANCELLED"
    third = _served_start_run(client, pid, "tpl-k08batch-94")
    bad = _served_cancel(client, pid, third, "sdk-94c", mode="nope")
    assert bad.status_code == 400, bad.text
    assert bad.json()["detail"]["code"] == "CANCEL_MODE_UNKNOWN"
    unknown = _served_cancel(client, pid, "run-absent-94", "sdk-94d")
    assert unknown.status_code == 404, unknown.text
    assert unknown.json()["detail"]["code"] == "AUTOMATION_RUN_NOT_FOUND"


def test_b0b_sdk_95_immediate_stops_at_once_served():
    """Row B0B-SDK-95 [k08batch-served]: immediate stops at once, done."""
    assert TESTID == "k08batch-served"
    client = _client()
    pid = "k08batch-sdk95-p1"
    run_id = _served_start_run(client, pid, "tpl-k08batch-95")
    stopped = _served_cancel(client, pid, run_id, "sdk-95")
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["state"] == "CANCELLED"
    final = _runner.get_finalization(pid, run_id)
    assert final == {"reason": "sdk-95", "finalized": True}
    history = _runner.get_history(pid, run_id)
    assert history[0]["event"] == "created"
    assert history[-1]["event"] == "cancelled:sdk-95"


def test_b0b_sdk_96_turn_left_uncompleted_served():
    """Row B0B-SDK-96 [k08batch-served]: immediate leaves turn open."""
    assert TESTID == "k08batch-served"
    client = _client()
    pid = "k08batch-sdk96-p1"
    run_id = _served_start_run(client, pid, "tpl-k08batch-96")
    opened = _runner.begin_turn(pid, run_id)
    stopped = _served_cancel(client, pid, run_id, "sdk-96")
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["state"] == "CANCELLED"
    events = [entry["event"]
              for entry in _runner.get_history(pid, run_id)]
    assert "turn-started:%d" % opened["turn"] in events
    assert "turn-completed:%d" % opened["turn"] not in events


def test_b0b_sdk_99_after_turn_finishes_served():
    """Row B0B-SDK-99 [k08batch-served]: after-turn waits for the turn."""
    assert TESTID == "k08batch-served"
    client = _client()
    pid = "k08batch-sdk99-p1"
    run_id = _served_start_run(client, pid, "tpl-k08batch-99")
    opened = _runner.begin_turn(pid, run_id)
    flagged = _served_cancel(client, pid, run_id, "sdk-99",
                             mode="after-turn")
    assert flagged.status_code == 200, flagged.text
    assert flagged.json()["state"] == "RUNNING"
    done = _runner.complete_turn(pid, run_id)
    assert done["turn"] == opened["turn"]
    assert done["state"] == "CANCELLED"
    events = [entry["event"]
              for entry in _runner.get_history(pid, run_id)]
    assert "turn-completed:%d" % opened["turn"] in events
    assert events[-1] == "cancelled:sdk-99"


def _finalize_body(pid, finalization_id="fin-k08batch-1",
                   run_id="run-k08batch-fin-1",
                   ver_id="v-k08batch-fin-1", ver_hash="h-k08batch-fin-1",
                   aud_id="aud-k08batch-fin-1",
                   aud_hash="h-k08batch-fin-1"):
    """Record-bound finalize-write body over the served finalize route."""
    return {
        "finalization_id": finalization_id,
        "project_id": pid,
        "task_id": "task-1",
        "run_id": run_id,
        "task_state": "COMPLETED",
        "verification_ref": ver_id,
        "verification": {"verification_id": ver_id,
                         "contract_hash": ver_hash},
        "audit": {"audit_id": aud_id, "contract_hash": aud_hash,
                  "result": "PASS"},
        "output_refs": ["art-k08batch-fin-1"],
        "accounting_complete": True,
        "budget_settled": True,
        "resources_released": True,
    }


def test_641_finalize_binds_verification_served():
    """Row 641 [k08batch-served]: finalize binds the verification record."""
    assert TESTID == "k08batch-served"
    client = _client()
    pid = "k08batch-641-p1"
    ok = client.post("/api/v1/core/finalizations", json=_finalize_body(pid),
                     headers=_auth())
    assert ok.status_code == 200, ok.text
    assert ok.json()["verification_ref"] == "v-k08batch-fin-1"
    assert ok.json()["completion_disposition"] == "VERIFIED_PASS"
    absent = _finalize_body(pid, finalization_id="fin-k08batch-absent")
    del absent["verification"]
    refused = client.post("/api/v1/core/finalizations", json=absent,
                          headers=_auth())
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"]["code"] == "FINALIZATION_REFUSED"
    mismatch = _finalize_body(pid, finalization_id="fin-k08batch-mismatch")
    mismatch["verification_ref"] = "v-some-other-id"
    denied = client.post("/api/v1/core/finalizations", json=mismatch,
                         headers=_auth())
    assert denied.status_code == 400, denied.text
    assert denied.json()["detail"]["code"] == "FINALIZATION_REFUSED"


def test_642_finalize_binds_audit_served():
    """Row 642 [k08batch-served]: finalize binds the exact audit record."""
    assert TESTID == "k08batch-served"
    client = _client()
    pid = "k08batch-642-p1"
    ok = client.post("/api/v1/core/finalizations", json=_finalize_body(pid),
                     headers=_auth())
    assert ok.status_code == 200, ok.text
    assert ok.json()["audit_result"] == "PASS"
    assert ok.json()["audit_ref"]["audit_id"] == "aud-k08batch-fin-1"
    assert ok.json()["audit_ref"]["result"] == ok.json()["audit_result"]
    absent = _finalize_body(pid, finalization_id="fin-k08batch-642-absent")
    del absent["audit"]
    refused = client.post("/api/v1/core/finalizations", json=absent,
                          headers=_auth())
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"]["code"] == "FINALIZATION_REFUSED"
    mismatch = _finalize_body(pid,
                              finalization_id="fin-k08batch-642-mismatch")
    mismatch["audit"] = dict(mismatch["audit"])
    mismatch["audit"]["contract_hash"] = "h-other-hash"
    denied = client.post("/api/v1/core/finalizations", json=mismatch,
                         headers=_auth())
    assert denied.status_code == 400, denied.text
    assert denied.json()["detail"]["code"] == "FINALIZATION_REFUSED"
