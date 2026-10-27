// K03 STEP1 behaviour contract: runner view (rows 246, M-P4-155).
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
//   cmd /c "cd /d WS\_task\fe_run && node --preserve-symlinks-main node_modules\vitest\vitest.mjs run tests\runner_view.test.mjs 2>&1"
//
// Entry points: runner_view.js (STEP2 view contract; the real route module
// does not exist in STEP1 — views land in STEP2 — so the dynamic import
// inside each test below rejects = expected fail). All test data enters
// ONLY via the fetch/network boundary mock below; no hand-built run object
// is passed as a function argument.

import { beforeEach, describe, expect, it } from "vitest";

const runnerView = () => import("../src/teststage/runner_view.js");

// FAKE-OF: stage run payload served only through the fetch mock (test-only
// values mirroring the StageRun/TestResult stub shapes).
const FAKE_RUN_PAYLOAD = {
  run_id: "run-k03-stage1",
  results: [
    { test_id: "t-login", status: "PASS", output_ref: "out://t-login" },
    { test_id: "t-offline", status: "FAIL", output_ref: "out://t-offline" },
    { test_id: "t-perf", status: "BLOCKED", output_ref: null },
  ],
};

beforeEach(() => {
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => FAKE_RUN_PAYLOAD,
  });
});

describe("runner view: counters", () => {
  // laneB: 246 — flips when STEP2 lands runner_view.js.
  it.fails("shows active / passed / remaining counters", async () => {
    const view = await runnerView();
    expect(view.runnerCounters()).toEqual({
      active: 0,
      passed: 1,
      remaining: 2,
    });
  });
});

describe("runner view: per-test status plus openable outputs", () => {
  // laneB: 246 — flips when STEP2 lands runner_view.js.
  it.fails("lists one row per test with status", async () => {
    const view = await runnerView();
    expect(view.runnerTestRows().map((row) => row.test_id)).toEqual([
      "t-login",
      "t-offline",
      "t-perf",
    ]);
    expect(view.runnerTestRows().map((row) => row.status)).toEqual([
      "PASS",
      "FAIL",
      "BLOCKED",
    ]);
  });

  // laneB: M-P4-155 — flips when STEP2 lands runner_view.js.
  it.fails("opens each recorded output by ref", async () => {
    const view = await runnerView();
    const opened = view.openTestOutput("out://t-login");
    expect(opened.test_id).toBe("t-login");
    expect(opened.content_ref).toBe("out://t-login");
  });
});
