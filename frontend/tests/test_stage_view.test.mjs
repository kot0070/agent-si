// K03 STEP1 behaviour contract: TEST stage view (rows R-347, M-P4-155).
// Strict-expected-fail suite: every `it.fails` below waits for STEP2
// behaviour and carries its row reason in the title; the frozen suite runs
// green-with-fail and each marker flips when STEP2 lands. Run ONLY under
// vitest from an _task/fe_run copy; never against workspace
// frontend/node_modules.
//
// _task/fe_run setup + run (exact commands, WS =
// D:\AI_PROJECTS\AGENT_SI_BUILD\WT\K03):
//   robocopy WS\frontend\src\teststage WS\_task\fe_run\src\teststage ask_buttons.jsx
//   robocopy WS\frontend\tests WS\_task\fe_run\tests test_stage_view.test.mjs runner_view.test.mjs
//   cmd /c "cd /d WS\_task\fe_run && node --preserve-symlinks-main node_modules\vitest\vitest.mjs run tests\test_stage_view.test.mjs 2>&1"
//
// Entry points: stage_view.js (STEP2 view contract; the real route module
// does not exist in STEP1 — views land in STEP2 — so the dynamic import
// inside each test below rejects = expected fail) and the real stub symbols
// AskButtons/askDecisions from ../src/teststage/ask_buttons.jsx (shells
// throw = expected fail). All stage-view test data enters ONLY via the
// fetch/network boundary mock below; no hand-built run object is passed as
// a view argument.

import { beforeEach, describe, expect, it } from "vitest";
import { AskButtons, askDecisions } from "../src/teststage/ask_buttons.jsx";

const stageView = () => import("../src/teststage/stage_view.js");

// FAKE-OF: project settings payload served only through the fetch mock
// (test-only values mirroring the stub shapes).
const FAKE_SETTINGS_PAYLOAD = {
  project_id: "proj-k03-stage1",
  local_tests: false,
  unrelated_flag: true,
};

beforeEach(() => {
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => FAKE_SETTINGS_PAYLOAD,
  });
});

describe("local tests: one switch in project settings", () => {
  // laneB: M-P4-155 — flips when STEP2 lands stage_view.js.
  it.fails("the switch alone turns local tests on and off", async () => {
    const view = await stageView();
    expect(await view.localTestsEnabled()).toBe(false);
    expect(await view.setLocalTestsEnabled(true)).toBe(true);
    expect(await view.setLocalTestsEnabled(false)).toBe(false);
  });
});

describe("Tests tab is informational", () => {
  // laneB: R-347 — flips when STEP2 lands stage_view.js.
  it.fails("holds no settings controls", async () => {
    const view = await stageView();
    expect(view.testsTabDescriptor().settings_controls).toEqual([]);
  });

  // laneB: M-P4-155 — STEP2 implements ask_buttons.jsx shells.
  it("asks the three ASK decisions through buttons only", () => {
    expect(askDecisions().map((choice) => choice.id)).toEqual([
      "allow_once",
      "allow_project",
      "deny",
    ]);
    expect(askDecisions().map((choice) => choice.label)).toEqual([
      "Allow once",
      "For this project",
      "Deny",
    ]);
  });

  // laneB: M-P4-155 — STEP2 implements ask_buttons.jsx shells.
  it("each button click forwards its exact decision id", () => {
    const seen = [];
    // FAKE-OF: ask-button probe props (test-only run id + decision sink).
    const buttons = AskButtons({
      runId: "run-k03-stage1",
      onDecision: (id) => seen.push(id),
    });
    expect(buttons.map((button) => button.id)).toEqual([
      "allow_once",
      "allow_project",
      "deny",
    ]);
    buttons.forEach((button) => button.select());
    expect(seen).toEqual(["allow_once", "allow_project", "deny"]);
  });
});
