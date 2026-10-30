/** @vitest-environment node */
import { beforeEach, describe, expect, it, vi } from "vitest";

async function freshView() {
  vi.resetModules();
  return import("../teststage/stage_view.js");
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe("M-P4-154 global default ON", () => {
  it("missing payload reads True", async () => {
    vi.stubGlobal("fetch", async () => ({ json: async () => null }));
    const view = await freshView();
    expect(await view.localTestsEnabled()).toBe(true);
  });

  it("missing flag reads True", async () => {
    vi.stubGlobal("fetch", async () => ({ json: async () => ({}) }));
    const view = await freshView();
    expect(await view.localTestsEnabled()).toBe(true);
  });

  it("per-project override wins then fetch resumes", async () => {
    vi.stubGlobal("fetch", async () => ({
      json: async () => ({ local_tests: false }),
    }));
    const view = await freshView();
    expect(await view.localTestsEnabled()).toBe(false);
    expect(await view.setLocalTestsEnabled(true)).toBe(true);
    expect(await view.localTestsEnabled()).toBe(true);
    expect(await view.setLocalTestsEnabled(false)).toBe(false);
    expect(await view.localTestsEnabled()).toBe(false);
  });

  it("Tests tab carries no settings controls", async () => {
    const view = await freshView();
    expect(view.testsTabDescriptor().settings_controls).toEqual([]);
  });
});
