"""FXAUTO served: the Automations UI routes through the real app.

Through create_app + TestClient + memory store: templates order, rule
CRUD, Run now records a run + a checkpoint, global/per-project pause
refuse plainly, approvals pause for real, restart keeps the rule.
A fake lives only at the budget hook for the positive resume leg (the
default fail-closed refusal is asserted first with the real hook).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest  # noqa: E402
import fastapi.testclient  # noqa: E402

from agent_si.automation import (  # noqa: E402
    pause,
    runner,
    rules,
    scheduler,
    triggers,
)
from agent_si.backend.app import create_app  # noqa: E402

APP_TOKEN = "fxauto-app-token"
HEADERS = {"x-actor": "ui-probe", "x-ui-session-token": APP_TOKEN}
PROJECT = "proj-auto"


def _settings(tmp_path):
    return {"store_dir": str(tmp_path / "appdata"),
            "ui_session_token": APP_TOKEN,
            "secret_store": "memory"}


def _reset():
    for lane in (pause, runner, scheduler, triggers):
        lane.reset_state()
    rules.reset_state()


def _make_client(tmp_path):
    _reset()
    app = create_app(_settings(tmp_path))
    return fastapi.testclient.TestClient(app, raise_server_exceptions=False)


def _create_checkpoint_rule(client, **kw):
    body = {"project_id": PROJECT,
            "name": "half-hour checkpoint",
            "when_kind": "schedule",
            "when_detail": "every-30m",
            "do": "checkpoint"}
    body.update(kw)
    resp = client.post("/api/v1/automations/rules", json=body,
                       headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()["rule"]


def test_templates_plan_five_first_with_drafts(tmp_path):
    client = _make_client(tmp_path)
    resp = client.get("/api/v1/automations/templates")
    assert resp.status_code == 200, resp.text
    rows = resp.json()["templates"]
    assert [row["template_id"] for row in rows[:5]] == [
        "tpl-reread-3h",
        "tpl-checkpoint-30m",
        "tpl-resume-restart",
        "tpl-pause-90pct",
        "tpl-notify-audit-fail",
    ]
    assert len(rows) >= 11
    known = {row["template_id"] for row in rows}
    assert known >= {
        "tpl-reread-3h",
        "tpl-checkpoint-30m",
        "tpl-resume-restart",
        "tpl-pause-90pct",
        "tpl-notify-audit-fail",
        "tpl-nightly",
        "tpl-healthcheck",
        "tpl-container-audit",
        "tpl-usage-report",
        "tpl-watch-sweep",
        "tpl-outage-drill",
    }
    second = rows[1]
    assert second["draft"]["when_detail"] == "every-30m"
    assert second["draft"]["do"] == "checkpoint"
    assert second["trigger_key"] == "fxauto.chips.every30m"


def test_rule_create_list_run_now_records_checkpoint(tmp_path):
    client = _make_client(tmp_path)
    rule = _create_checkpoint_rule(client)
    assert rule["next_run_at"] is not None

    listed = client.get("/api/v1/automations/rules",
                        params={"project_id": PROJECT})
    assert listed.status_code == 200, listed.text
    assert [row["name"] for row in listed.json()["rules"]] == [
        "half-hour checkpoint"]

    fired = client.post(
        "/api/v1/automations/rules/%s/run" % rule["rule_id"],
        json={"project_id": PROJECT}, headers=HEADERS)
    assert fired.status_code == 200, fired.text
    payload = fired.json()
    assert payload["result"]["key"] == "fxauto.results.checkpoint"
    assert payload["run"]["state"] == "RUNNING"
    assert isinstance(payload["run"]["time"], str)

    runs = client.get("/api/v1/automations/runs",
                      params={"project_id": PROJECT})
    assert runs.status_code == 200, runs.text
    rows = runs.json()["runs"]
    assert len(rows) == 1
    assert rows[0]["rule"] == "half-hour checkpoint"
    assert rows[0]["result"]["key"] == "fxauto.results.checkpoint"

    ckpts = client.get("/api/v1/automations/checkpoints",
                       params={"project_id": PROJECT})
    assert ckpts.status_code == 200, ckpts.text
    stored = ckpts.json()
    assert len(stored["checkpoints"]) == 1
    assert stored["latest"]["digest"] != ""
    assert stored["latest"]["rule"] == "half-hour checkpoint"


def test_global_pause_refuses_run_now_plainly(tmp_path):
    client = _make_client(tmp_path)
    rule = _create_checkpoint_rule(client)
    paused = client.post("/api/v1/automations/pause",
                         json={"paused": True, "reason": "hd stop"},
                         headers=HEADERS)
    assert paused.status_code == 200, paused.text
    fired = client.post(
        "/api/v1/automations/rules/%s/run" % rule["rule_id"],
        json={"project_id": PROJECT}, headers=HEADERS)
    assert fired.status_code == 409, fired.text
    assert "paused" in fired.json()["detail"]["detail"]
    unpaused = client.post("/api/v1/automations/pause",
                           json={"paused": False, "reason": ""},
                           headers=HEADERS)
    assert unpaused.status_code == 200, unpaused.text
    fired = client.post(
        "/api/v1/automations/rules/%s/run" % rule["rule_id"],
        json={"project_id": PROJECT}, headers=HEADERS)
    assert fired.status_code == 200, fired.text


def test_per_project_switch_refuses_run_now(tmp_path):
    client = _make_client(tmp_path)
    rule = _create_checkpoint_rule(client)
    state = client.get("/api/v1/automations/pause/project",
                       params={"project_id": PROJECT})
    assert state.json() == {"project_id": PROJECT, "paused": False}
    set_resp = client.post("/api/v1/automations/pause/project",
                           json={"project_id": PROJECT, "paused": True},
                           headers=HEADERS)
    assert set_resp.json()["paused"] is True
    fired = client.post(
        "/api/v1/automations/rules/%s/run" % rule["rule_id"],
        json={"project_id": PROJECT}, headers=HEADERS)
    assert fired.status_code == 409, fired.text
    client.post("/api/v1/automations/pause/project",
                json={"project_id": PROJECT, "paused": False},
                headers=HEADERS)


def test_strong_action_approval_pauses_project(tmp_path):
    client = _make_client(tmp_path)
    rule = _create_checkpoint_rule(
        client, name="budget guard", when_kind="metric",
        when_detail="budget-90", do="pause-project")
    fired = client.post(
        "/api/v1/automations/rules/%s/run" % rule["rule_id"],
        json={"project_id": PROJECT}, headers=HEADERS)
    assert fired.status_code == 200, fired.text
    assert fired.json()["approval"] is not None

    pending = client.get("/api/v1/automations/approvals",
                         params={"project_id": PROJECT})
    assert len(pending.json()["approvals"]) == 1
    approval_id = pending.json()["approvals"][0]["approval_id"]

    decided = client.post(
        "/api/v1/automations/approvals/%s" % approval_id,
        json={"project_id": PROJECT, "approved": True}, headers=HEADERS)
    assert decided.status_code == 200, decided.text
    assert decided.json()["approval"]["state"] == "approved"
    state = client.get("/api/v1/automations/pause/project",
                       params={"project_id": PROJECT})
    assert state.json()["paused"] is True


def test_rule_off_refuses_run_now_and_skips_tick(tmp_path):
    client = _make_client(tmp_path)
    rule = _create_checkpoint_rule(client)
    off = client.put("/api/v1/automations/rules/%s" % rule["rule_id"],
                     json={"project_id": PROJECT, "enabled": False},
                     headers=HEADERS)
    assert off.json()["rule"]["enabled"] is False
    assert off.json()["rule"]["next_run_at"] is None
    fired = client.post(
        "/api/v1/automations/rules/%s/run" % rule["rule_id"],
        json={"project_id": PROJECT}, headers=HEADERS)
    assert fired.status_code == 409, fired.text
    assert "turned off" in fired.json()["detail"]["detail"]


def test_rule_validation_is_plain_400(tmp_path):
    client = _make_client(tmp_path)
    bad = client.post("/api/v1/automations/rules",
                      json={"project_id": PROJECT, "name": "",
                            "when_kind": "schedule",
                            "when_detail": "every-30m", "do": "notify"},
                      headers=HEADERS)
    assert bad.status_code == 400, bad.text
    assert bad.json()["detail"]["code"] == "INVALID_RULE"
    long_text = client.post(
        "/api/v1/automations/rules",
        json={"project_id": PROJECT, "name": "x", "when_kind": "schedule",
              "when_detail": "every-30m", "do": "notify",
              "if_text": "y" * 501},
        headers=HEADERS)
    assert long_text.status_code == 400, long_text.text


def test_restart_keeps_rule_listed_and_on(tmp_path):
    client = _make_client(tmp_path)
    rule = _create_checkpoint_rule(client)
    assert os.path.exists(
        os.path.join(str(tmp_path), "appdata", "automation", "rules.json"))
    _reset()
    client2 = _make_client(tmp_path)
    listed = client2.get("/api/v1/automations/rules",
                         params={"project_id": PROJECT})
    assert listed.status_code == 200, listed.text
    rows = listed.json()["rules"]
    assert [row["rule_id"] for row in rows] == [rule["rule_id"]]
    assert rows[0]["enabled"] is True


def test_checkpoint_resume_refused_without_budget_then_resumes(tmp_path):
    client = _make_client(tmp_path)
    rule = _create_checkpoint_rule(client)
    fired = client.post(
        "/api/v1/automations/rules/%s/run" % rule["rule_id"],
        json={"project_id": PROJECT}, headers=HEADERS)
    ckpts = client.get("/api/v1/automations/checkpoints",
                       params={"project_id": PROJECT}).json()
    checkpoint_id = ckpts["checkpoints"][0]["checkpoint_id"]

    refused = client.post(
        "/api/v1/automations/checkpoints/%s/resume" % checkpoint_id,
        json={"project_id": PROJECT}, headers=HEADERS)
    assert refused.status_code == 409, refused.text

    runner.set_budget_hook(lambda project_id: True)
    try:
        resumed = client.post(
            "/api/v1/automations/checkpoints/%s/resume" % checkpoint_id,
            json={"project_id": PROJECT}, headers=HEADERS)
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["run_id"] == fired.json()["run"]["run_id"]
    finally:
        runner.set_budget_hook(None)


def test_unknown_rule_is_plain_404(tmp_path):
    client = _make_client(tmp_path)
    fired = client.post("/api/v1/automations/rules/rule-9999/run",
                        json={"project_id": PROJECT}, headers=HEADERS)
    assert fired.status_code == 404, fired.text
