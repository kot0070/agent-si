// FXCLASS RED-first frontend proofs (real page, fake only at network).
// P1 shared word, P5 polling helper.
import { describe, expect, it } from "vitest";
import { backoffForFailures, isHiddenTick } from "../../api/polling";
import { runStatusWord } from "../../projects/viewsApi";

describe("FXCLASS CB-1/CB-2/CB-3/CB-6 shared run word", () => {
  it("a run with one FAIL part says failed even when success is true", () => {
    expect(
      runStatusWord({
        success: true,
        parts: [
          { part_id: "p1", verdict: "PASS" },
          { part_id: "p2", verdict: "FAIL", reason: "boom" },
        ],
        verdicts: { p1: "PASS", p2: "FAIL" },
      }),
    ).toBe("failed");
  });
  it("an all-PASS run says done", () => {
    expect(
      runStatusWord({
        success: true,
        parts: [{ part_id: "p1", verdict: "PASS" }],
        verdicts: { p1: "PASS" },
      }),
    ).toBe("done");
  });
  it("a plain answer with no parts keeps done (CB-7 by design)", () => {
    expect(runStatusWord({ success: true, parts: [], verdicts: {} })).toBe(
      "done",
    );
  });
});

describe("FXCLASS P5 polling helper", () => {
  it("backs off 3-6-12-30 s and caps", () => {
    expect(backoffForFailures(0)).toBe(3000);
    expect(backoffForFailures(1)).toBe(6000);
    expect(backoffForFailures(2)).toBe(12000);
    expect(backoffForFailures(3)).toBe(30000);
    expect(backoffForFailures(99)).toBe(30000);
  });
  it("does not treat a missing document as hidden", () => {
    expect(isHiddenTick()).toBe(false);
  });
});
