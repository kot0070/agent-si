// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WatcherRuleCards } from "./WatcherRuleCards";
import { isCardEnabled } from "./ruleOverrides";
import { resetLocaleForTests, setLocale } from "../locale/index";

const EVAL_BODY = {
  decision_id: "dec-0001",
  project_id: "proj-r",
  rule_id: "rule-guard",
  verdict: "BLOCK",
  journal_entry_id: "evt-0042",
  decided_at: "2026-10-27T00:01:00Z",
};

function fakeFetchOk(body: unknown, seen: Array<{ url: string; init: unknown }>) {
  return vi.fn().mockImplementation((url: unknown, init: unknown) => {
    seen.push({ url: String(url), init });
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(body),
    });
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("WatcherRuleCards (RED: component missing)", () => {
  it("renders every card with when, script, power, whom and an on switch", () => {
    render(<WatcherRuleCards projectId="proj-r" />);
    for (const cardId of ["card-hang", "card-guard", "card-tamper"]) {
      expect(screen.getByTestId(`watchcard-${cardId}`)).toBeTruthy();
      expect(screen.getByTestId(`watchcard-${cardId}-when`).textContent?.length).toBeGreaterThan(0);
      const toggle = screen.getByTestId(`watchcard-${cardId}-enabled`) as HTMLInputElement;
      expect(toggle.checked).toBe(true);
    }
    expect(screen.getByTestId("watchcard-card-hang-script").textContent).toContain("not known");
    expect(screen.getByTestId("watchcard-card-guard-script").textContent).toContain("guard");
  });

  it("turns a card off and the flag survives a reload", () => {
    const { unmount } = render(<WatcherRuleCards projectId="proj-r" />);
    fireEvent.click(screen.getByTestId("watchcard-card-guard-enabled"));
    expect(isCardEnabled("card-guard", "proj-r")).toBe(false);
    unmount();
    render(<WatcherRuleCards projectId="proj-r" />);
    expect(
      (screen.getByTestId("watchcard-card-guard-enabled") as HTMLInputElement).checked,
    ).toBe(false);
  });

  it("evaluates the guard card through its backend rule and shows the row", async () => {
    const seen: Array<{ url: string; init: unknown }> = [];
    vi.stubGlobal("fetch", fakeFetchOk(EVAL_BODY, seen));
    render(<WatcherRuleCards projectId="proj-r" />);
    fireEvent.click(screen.getByTestId("watchcard-card-guard-evaluate"));
    expect(await screen.findByTestId("watchcard-card-guard-result")).toBeTruthy();
    expect(screen.getByTestId("watchcard-card-guard-result").textContent).toContain("evt-0042");
    await waitFor(() => {
      expect(seen.some((call) => call.url === "/api/v1/watcher/rules/rule-guard/evaluate")).toBe(true);
    });
  });

  it("PLANB X3: a resting verdict with no journal row never reads Blocked or Journal row", async () => {
    const seen: Array<{ url: string; init: unknown }> = [];
    vi.stubGlobal(
      "fetch",
      fakeFetchOk({ ...EVAL_BODY, verdict: "BLOCK", journal_entry_id: "" }, seen),
    );
    render(<WatcherRuleCards projectId="proj-r" />);
    fireEvent.click(screen.getByTestId("watchcard-card-guard-evaluate"));
    const line = await screen.findByTestId("watchcard-card-guard-result");
    expect(line.textContent).toContain("Checked: nothing needs attention");
    expect(line.textContent).not.toMatch(/Blocked|Journal row/);
  });

  it("gives the hang card no evaluate control, only the read-only note", () => {
    render(<WatcherRuleCards projectId="proj-r" />);
    expect(screen.queryByTestId("watchcard-card-hang-evaluate")).toBeNull();
    expect(screen.getByTestId("watchcard-card-hang-no-backend")).toBeTruthy();
  });

  it("gates a strong power behind a one-shot approval", async () => {
    const seen: Array<{ url: string; init: unknown }> = [];
    vi.stubGlobal("fetch", fakeFetchOk(EVAL_BODY, seen));
    render(<WatcherRuleCards projectId="proj-r" />);
    fireEvent.change(screen.getByTestId("watchcard-card-guard-power"), {
      target: { value: "stop" },
    });
    const button = screen.getByTestId("watchcard-card-guard-evaluate") as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(screen.getByTestId("watchcard-card-guard-approve"));
    expect((screen.getByTestId("watchcard-card-guard-evaluate") as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(screen.getByTestId("watchcard-card-guard-evaluate"));
    expect(await screen.findByTestId("watchcard-card-guard-result")).toBeTruthy();
    await waitFor(() => {
      expect(seen.length).toBeGreaterThan(0);
    });
  });
});
