// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WatcherAlerts } from "./WatcherAlerts";
import { resetLocaleForTests, setLocale } from "../locale/index";

const ALERTS_BODY = {
  alerts: [
    {
      alert_id: "alert-rule-guard",
      project_id: "proj-a",
      rule_id: "rule-guard",
      verdict: "BLOCK",
      detail: "rule-guard BLOCK over 3 stored rows",
    },
    {
      alert_id: "alert-rule-tamper",
      project_id: "proj-a",
      rule_id: "rule-tamper",
      verdict: "ALLOW",
      detail: "rule-tamper ALLOW over 3 stored rows",
    },
  ],
};

const INTEGRITY_BODY = {
  project_id: "proj-a",
  ok: true,
  checked_at: "2026-10-27T00:02:00Z",
  mismatched_refs: [],
};

const FIRE_BODY = {
  timer_id: "t-1",
  project_id: "proj-a",
  event: "TIMER_FIRED",
  action_mode: "local_ai_default",
  journal_entry_id: "evt-0099",
  fired_at: "2026-10-27T00:03:00Z",
};

function fakeFetch(
  seen: Array<{ url: string; method: string; body: unknown }>,
) {
  return vi.fn().mockImplementation((url: unknown, init?: unknown) => {
    const request = (init ?? {}) as { method?: string; body?: string };
    const method = request.method ?? "GET";
    let body: unknown = undefined;
    try {
      body = request.body === undefined ? undefined : JSON.parse(request.body);
    } catch {
      body = request.body;
    }
    seen.push({ url: String(url), method, body });
    const text = String(url);
    const payload = text.includes("/api/v1/watcher/alerts")
      ? ALERTS_BODY
      : text.includes("/api/v1/watcher/integrity-check")
        ? INTEGRITY_BODY
        : FIRE_BODY;
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(payload),
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

describe("WatcherAlerts (RED: component missing)", () => {
  it("loads nothing on mount and shows the served alerts on demand", async () => {
    const seen: Array<{ url: string; method: string; body: unknown }> = [];
    vi.stubGlobal("fetch", fakeFetch(seen));
    render(<WatcherAlerts projectId="proj-a" />);
    expect(seen).toHaveLength(0);
    expect(screen.queryByTestId("watcher-alert-rule-guard")).toBeNull();
    fireEvent.click(screen.getByTestId("watcher-alerts-show"));
    expect(await screen.findByTestId("watcher-alert-rule-guard")).toBeTruthy();
    expect(screen.getByTestId("watcher-alert-rule-guard").textContent).toContain("Blocked a problem");
    expect(screen.getByTestId("watcher-alert-rule-tamper").textContent).toContain("Checked, all quiet");
  });

  it("runs the integrity check and shows the plain result", async () => {
    const seen: Array<{ url: string; method: string; body: unknown }> = [];
    vi.stubGlobal("fetch", fakeFetch(seen));
    render(<WatcherAlerts projectId="proj-a" />);
    fireEvent.click(screen.getByTestId("watcher-integrity-check"));
    expect(await screen.findByTestId("watcher-integrity-result")).toBeTruthy();
    expect(screen.getByTestId("watcher-integrity-result").textContent).toContain("Integrity OK");
    await waitFor(() => {
      expect(
        seen.some(
          (call) =>
            call.url === "/api/v1/watcher/integrity-check" &&
            call.method === "POST",
        ),
      ).toBe(true);
    });
  });

  it("fires a timer by id and shows the served receipt", async () => {
    const seen: Array<{ url: string; method: string; body: unknown }> = [];
    vi.stubGlobal("fetch", fakeFetch(seen));
    render(<WatcherAlerts projectId="proj-a" />);
    fireEvent.change(screen.getByTestId("watcher-timer-id"), {
      target: { value: "t-1" },
    });
    fireEvent.click(screen.getByTestId("watcher-timer-fire"));
    expect(await screen.findByTestId("watcher-timer-result")).toBeTruthy();
    expect(screen.getByTestId("watcher-timer-result").textContent).toContain("TIMER_FIRED");
    await waitFor(() => {
      expect(
        seen.some(
          (call) =>
            call.url === "/api/v1/watcher/timers/t-1/fire" &&
            call.method === "POST",
        ),
      ).toBe(true);
    });
  });
});
