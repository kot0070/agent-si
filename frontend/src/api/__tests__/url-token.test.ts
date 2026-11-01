/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("URL query token at module load", () => {
  it("token abc with extra param x gives getUiToken abc, address keeps x without token", async () => {
    vi.resetModules();
    window.localStorage.clear();
    window.sessionStorage.clear();
    delete (window as unknown as Record<string, unknown>)[
      "__AGENT_SI_UI_TOKEN"
    ];
    window.history.replaceState(null, "", "/?token=abc&x=1");
    const errors = await import("../errors");
    expect(errors.getUiToken()).toBe("abc");
    expect(window.location.search).toContain("x=1");
    expect(window.location.search).not.toContain("token");
    expect(window.localStorage.getItem("agent-si.ui-token")).toBe("abc");
  });
});
