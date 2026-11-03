/** @vitest-environment jsdom */
// FXDENYLINE: after Deny the verdict line reads the REAL end state in
// plain words (Stopped), never a stale Waiting line. The deny epilogue
// lands on text that still holds the earlier hold line, so denied wins
// over held. en + uk.
import { describe, expect, it, beforeEach, afterEach } from "vitest";
import {
  resetLocaleForTests,
  setLocale,
} from "../../locale/index";
import {
  engineVerdictLine,
  summarizeEngineTurn,
} from "../index";

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
});

afterEach(() => {
  resetLocaleForTests();
});

const DENY_AFTER_HOLD =
  "run held: waiting for your permission to run npm install --save\n" +
  "Part p1: FAILED (install permission denied for npm install is-number --save)";

describe("FXDENYLINE deny reads the real end state", () => {
  it("deny after hold renders Stopped, no stale Waiting, en", () => {
    const summary = summarizeEngineTurn(DENY_AFTER_HOLD, "failed");
    expect(summary.done).toBe(false);
    const line = engineVerdictLine(summary);
    expect(line).toBe(
      "Stopped: you denied npm install. Nothing was installed.",
    );
    expect(line).not.toContain("Waiting");
    expect(line).not.toContain("Done");
  });

  it("deny after hold renders Stopped, no stale Waiting, uk", () => {
    setLocale("uk");
    const summary = summarizeEngineTurn(DENY_AFTER_HOLD, "failed");
    expect(summary.done).toBe(false);
    const line = engineVerdictLine(summary);
    expect(line).toContain("Зупинено");
    expect(line).not.toContain("Очікування");
    expect(line).not.toContain("Done");
  });

  it("hold alone still renders Waiting, en", () => {
    const summary = summarizeEngineTurn(
      "Waiting for your permission to run npm install --save.",
      "ok",
    );
    expect(summary.done).toBe(false);
    expect(engineVerdictLine(summary)).toBe(
      "Waiting for your permission to run npm install --save.",
    );
  });
});
