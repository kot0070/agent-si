// PLANB V2f: the verdict line lists the planned files (the plan line no
// longer carries "[files: ...]" for files that do not exist yet).
import { describe, expect, it } from "vitest";
import { engineVerdictLine, summarizeEngineTurn } from "../index";

const LOG = [
  "Working folder: ws",
  "Team: director, manager, worker, auditor on ollama/muse-glimmer:30b (Pinned)",
  "Director: plan of 2 parts",
  "Part p1: Create package.json, add.js and add.test.js (planned: package.json, add.js, add.test.js)",
  "Part p2: Run tests until green using project's test script [files: ]",
  "Auditor for p1: PASS (ok)",
  "Part p1: PASS (checks green, auditor PASS)",
  "Part p2: PASS (checks green, auditor PASS)",
  "Total: 10 input + 5 output = 15 tokens; cost not known (no price)",
  "run success: all 2 parts PASS",
].join("\n");

describe("engine verdict files", () => {
  it("names the planned files when no [files:] marker exists", () => {
    const summary = summarizeEngineTurn(LOG, "ok", null);
    expect(summary.files).toEqual(["package.json", "add.js", "add.test.js"]);
    expect(engineVerdictLine(summary, "")).toContain(
      "files: package.json, add.js, add.test.js",
    );
  });
  it("still says none listed when nothing was planned or marked", () => {
    const text = LOG.replace(" (planned: package.json, add.js, add.test.js)", "");
    expect(engineVerdictLine(summarizeEngineTurn(text, "ok", null), "")).toContain(
      "files: none listed",
    );
  });
});
