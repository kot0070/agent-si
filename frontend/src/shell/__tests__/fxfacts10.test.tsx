/** @vitest-environment jsdom */
// FXFACTS F10 RED: rail cards collapse to one line. Closed cards show no
// subtitle and no details; the whole title row toggles; Team now, Results,
// Background and Watcher all expose a header toggle whose state follows
// aria-expanded. The ONLY fake is the fetch boundary (served schemas); the
// App, Inspector and MetricCard are real.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { App } from "../../app/App";

const PROJECT = { project_id: "p-1", name: "n-1", created_at: "t-0" };

const LIVE_ROWS = [
  {
    agent: "agent-1",
    scope: "scope-1",
    deliverable: "artifact://run/r-9/output",
    status: "RUNNING",
    role: "manager",
    model: "m-1",
    step: 2,
    tokens: { input: 400, output: 600 },
    waits: [],
  },
];

const TASKS = [
  {
    task_id: "t-9",
    project_id: "p-1",
    title: "running nine",
    status: "RUNNING",
    created_at: "t-0",
  },
];

const RUNS = [
  {
    run_id: "r-9",
    folder: "f-1",
    start: "2026-11-02T10:00:00Z",
    end: "2026-11-02T10:01:00Z",
    title: "nine",
    parts: [{ part_id: "p1", verdict: "PASS", attempts: 1 }],
    verdicts: { p1: "PASS" },
    tokens: 1000,
    cost: "0.000105",
    files: [],
    success: true,
    summary: "run success: all 1 parts PASS",
  },
];

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubServed(): void {
  vi.stubGlobal("fetch", async (input: unknown) => {
    const url = String(input);
    if (url === "/api/v1/projects") {
      return jsonBody({ projects: [PROJECT] });
    }
    if (url === "/api/v1/agents/live") {
      return jsonBody({ agents: LIVE_ROWS });
    }
    if (url === "/api/v1/tasks?project_id=p-1") {
      return jsonBody({ tasks: TASKS });
    }
    if (url === "/api/v1/runs/ledger?project_id=p-1") {
      return jsonBody({ rows: [], runs: RUNS });
    }
    if (url === "/api/v1/reports/next-package-nudge?package_id=pkg-2") {
      return jsonBody({ code: "NONE" }, 404);
    }
    if (url === "/api/v1/budget?project_id=p-1") {
      return jsonBody({
        project_id: "p-1",
        budget: {
          project_id: "p-1",
          hard_limit: 5,
          spent: 0,
          reserved: 0,
          currency: "USD",
        },
      });
    }
    if (url === "/api/v1/watcher/status?project_id=p-1") {
      return jsonBody({
        project_id: "p-1",
        integrity_ok: true,
        journal_head: "jh-1",
        generated_at: "t-0",
      });
    }
    if (url === "/api/v1/watcher/journal?project_id=p-1") {
      return jsonBody([
        {
          entry_id: "evt-1",
          timestamp: "2026-11-02T10:00:00Z",
          hash: "h1",
          kind: "SERVICE_STATE",
          source: "watcher",
          summary: "boot",
          refs: [],
        },
        {
          entry_id: "evt-2",
          timestamp: "2026-11-02T10:01:00Z",
          hash: "h2",
          kind: "DEVRUN_END",
          source: "runner",
          summary: "run success: all 1 parts PASS",
          refs: ["r-9"],
        },
        {
          entry_id: "evt-3",
          timestamp: "2026-11-02T10:02:00Z",
          hash: "h3",
          kind: "WATCH_DECISION",
          source: "watcher",
          summary: "rule-tamper ESCALATE no watcher model: default action",
          refs: ["rule-tamper"],
        },
        {
          entry_id: "evt-4",
          timestamp: "2026-11-02T10:03:00Z",
          hash: "h4",
          kind: "DEVRUN_END",
          source: "runner",
          summary: "run success: all 1 parts PASS",
          refs: ["r-9"],
        },
      ]);
    }
    if (url === "/api/v1/apps/card?project_id=p-1") {
      return jsonBody({
        project_id: "p-1",
        service_ids: [],
        paused: false,
        generated_at: "t-0",
      });
    }
    if (url === "/api/v1/providers") {
      return jsonBody({ providers: [{ provider_id: "meta" }] });
    }
    if (url.startsWith("/api/v1/teststage/")) {
      return jsonBody({ code: "NONE" }, 404);
    }
    if (url === "/api/v1/local/models") {
      return jsonBody([]);
    }
    return jsonBody({ code: "FXFACTS10_UNEXPECTED_API" }, 404);
  });
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem("agentsi.firstrun.done", "true");
  setLocale("en");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

function renderAppAt(route: string): void {
  const router = createMemoryRouter([{ path: "*", element: <App /> }], {
    initialEntries: [route],
  });
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

describe("fxfacts10 rail one-line cards", () => {
  it("closed metric cards show no subtitle and no details", async () => {
    stubServed();
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    expect(await screen.findByTestId("inspector-card-team")).toBeTruthy();
    fireEvent.click(await screen.findByTestId("rail-more-toggle"));
    const tokens = await screen.findByTestId("kit-metric-fx-tokens");
    expect(
      tokens.querySelector('[data-testid="kit-sub-fx-tokens"]'),
    ).toBeNull();
    expect(
      tokens.querySelector('[data-testid="kit-expanded-bar"]'),
    ).toBeNull();
    const budget = await screen.findByTestId("kit-metric-fx-budget");
    expect(
      budget.querySelector('[data-testid="kit-sub-fx-budget"]'),
    ).toBeNull();
  });

  it("toggling a metric card shows then hides its details", async () => {
    stubServed();
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    fireEvent.click(await screen.findByTestId("rail-more-toggle"));
    const toggle = await screen.findByTestId("kit-toggle-fx-tokens");
    fireEvent.click(toggle);
    const open = await screen.findByTestId("kit-metric-fx-tokens");
    expect(
      open.querySelector('[data-testid="kit-expanded-bar"]'),
    ).not.toBeNull();
    expect(
      open.querySelector('[data-testid="kit-sub-fx-tokens"]'),
    ).not.toBeNull();
    fireEvent.click(await screen.findByTestId("kit-toggle-fx-tokens"));
    const closed = await screen.findByTestId("kit-metric-fx-tokens");
    expect(
      closed.querySelector('[data-testid="kit-expanded-bar"]'),
    ).toBeNull();
    expect(
      closed.querySelector('[data-testid="kit-sub-fx-tokens"]'),
    ).toBeNull();
  });

  it("rail watcher card reads online with model, minutes and journal rows", async () => {
    stubServed();
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    await screen.findByTestId("inspector-card-watcher");
    // Closed line names the served state.
    expect(
      screen.getByTestId("inspector-card-watcher").textContent,
    ).toContain("Online");
    fireEvent.click(await screen.findByTestId("rail-toggle-watcher"));
    // Model with a link to where it is set.
    const model = await screen.findByTestId("watcher-model");
    expect(model.textContent).toContain("not known");
    expect(screen.getByTestId("watcher-model-settings").getAttribute("href")).toBe(
      "/watcher",
    );
    // Check minutes from the stored settings.
    expect(
      screen.getByTestId("rail-watcher-minutes-card-hang").textContent,
    ).toContain("20");
    // Last three journal rows in the plain form; the oldest stays out.
    expect(await screen.findByTestId("journal-row-evt-4")).toBeTruthy();
    expect(screen.getByTestId("journal-row-evt-2")).toBeTruthy();
    expect(screen.queryByTestId("journal-row-evt-1")).toBeNull();
    expect(screen.getByTestId("watcher-open").getAttribute("href")).toBe(
      "/watcher",
    );
    expect(screen.getByTestId("watcher-open").textContent).toBe("Open journal");
  });

  it("closed rail shows every card header with data served", async () => {
    // FXFACTS F14, part 1 (presence): the closed rail names every card.
    // Part 2 (no scroll at 1366x768) is measured on the real exe in
    // HD-CHECK, where layout exists.
    stubServed();
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    await screen.findByTestId("inspector-card-team");
    for (const toggle of [
      "rail-toggle-team",
      "rail-toggle-context",
      "rail-toggle-results",
      "rail-toggle-background",
      "rail-toggle-watcher",
      "kit-toggle-fx-budget",
      "rail-more-toggle",
    ]) {
      expect(await screen.findByTestId(toggle)).toBeTruthy();
    }
    // One-line team row: role, short model, status, no agent pill row.
    const line = await screen.findByTestId("team-line-agent-1");
    expect(line.textContent).toContain("Manager");
    expect(line.textContent).toContain("m-1");
  });

  it("team, results, background and watcher cards toggle their content", async () => {
    stubServed();
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    await screen.findByTestId("inspector-card-team");
    // Team now is open with a project; the others start closed.
    // A live run keeps Team now open: the toggle stores the choice but
    // the card stays open.
    expect(
      (await screen.findByTestId("rail-toggle-team")).getAttribute(
        "aria-expanded",
      ),
    ).toBe("true");
    expect(await screen.findByTestId("team-rows")).toBeTruthy();
    fireEvent.click(await screen.findByTestId("rail-toggle-team"));
    expect(await screen.findByTestId("team-rows")).toBeTruthy();
    expect(
      (await screen.findByTestId("rail-toggle-team")).getAttribute(
        "aria-expanded",
      ),
    ).toBe("true");
    const pairs: Array<[string, string]> = [
      ["rail-toggle-results", "result-last"],
      ["rail-toggle-background", "bg-row-t-9"],
      ["rail-toggle-watcher", "watcher-state"],
    ];
    for (const [toggleId, contentId] of pairs) {
      const toggle = await screen.findByTestId(toggleId);
      expect(toggle.getAttribute("aria-expanded")).toBe("false");
      expect(screen.queryByTestId(contentId)).toBeNull();
      fireEvent.click(toggle);
      expect(await screen.findByTestId(contentId)).toBeTruthy();
      expect(
        (await screen.findByTestId(toggleId)).getAttribute("aria-expanded"),
      ).toBe("true");
      fireEvent.click(await screen.findByTestId(toggleId));
      expect(screen.queryByTestId(contentId)).toBeNull();
      expect(
        (await screen.findByTestId(toggleId)).getAttribute("aria-expanded"),
      ).toBe("false");
    }
  });
});
