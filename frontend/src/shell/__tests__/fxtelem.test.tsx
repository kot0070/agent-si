/** @vitest-environment jsdom */
// FXTELEM RED first: two runs in one project (chat Totals 5142 + 13938).
// The rail names each number: "Last run 13,938" and "This project 19,080";
// per-model rows add up to the project total, never a global sum.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import type { ReactElement } from "react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { Inspector } from "../Inspector";
import { ProjectView } from "../../projects/ProjectView";

const PROJECT = {
  project_id: "p-1",
  name: "P1",
  created_at: "2026-02-11T06:42:44Z",
};

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const RUNS_LEDGER_TWO_RUNS = {
  rows: [
    { package_id: "pkg-1", agents: 2, peak_concurrency: 2, wall_time_s: 60 },
    { package_id: "pkg-2", agents: 2, peak_concurrency: 2, wall_time_s: 61 },
  ],
  runs: [
    {
      run_id: "run-1",
      start: "2026-02-11T06:40:00Z",
      end: "2026-02-11T06:41:00Z",
      parts: [],
      verdicts: {},
      tokens: 5142,
      cost: "UNKNOWN",
      files: ["a.txt"],
      success: true,
      summary: "first",
    },
    {
      run_id: "run-2",
      start: "2026-02-11T06:42:00Z",
      end: "2026-02-11T06:43:00Z",
      parts: [],
      verdicts: {},
      tokens: 13938,
      cost: "UNKNOWN",
      files: ["b.txt"],
      success: true,
      summary: "second",
    },
  ],
};

const TELEMETRY_PROJECT = {
  metric_records: 6,
  telemetry_events: 2,
  totals: { tokens_total: 33180, cloud_calls: 2 },
  tasks: ["t-1", "t-2"],
  models: [
    { model: "muse-spark-1.3-contributor", calls: 2, tokens: 33180, cost: "UNAVAILABLE" },
  ],
  providers: [{ provider: "meta", calls: 2, tokens: 33180, cost: "UNAVAILABLE" }],
};

function stubTwoRuns(): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "GET" && url === "/api/v1/projects") {
        return jsonBody({ projects: [PROJECT] });
      }
      if (method === "GET" && url === "/api/v1/projects/p-1") {
        return jsonBody({ project: PROJECT });
      }
      if (method === "GET" && url === "/api/v1/agents/live") {
        return jsonBody({ agents: [] });
      }
      if (method === "GET" && url.startsWith("/api/v1/runs/ledger")) {
        return jsonBody(RUNS_LEDGER_TWO_RUNS);
      }
      if (method === "GET" && url.startsWith("/api/v1/tasks")) {
        return jsonBody({ tasks: [] });
      }
      if (method === "GET" && url.startsWith("/api/v1/budget")) {
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
      if (method === "GET" && url.startsWith("/api/v1/watcher/status")) {
        return jsonBody({
          project_id: "p-1",
          integrity_ok: true,
          journal_head: "evt-1",
          generated_at: "2026-02-11T06:42:44Z",
        });
      }
      if (method === "GET" && url.startsWith("/api/v1/watcher/journal")) {
        return jsonBody([]);
      }
      if (method === "GET" && url.startsWith("/api/v1/apps/card")) {
        return jsonBody({
          project_id: "p-1",
          service_ids: [],
          paused: false,
          generated_at: "t-0",
        });
      }
      if (method === "GET" && url.startsWith("/api/v1/analytics/telemetry")) {
        return jsonBody(TELEMETRY_PROJECT);
      }
      if (method === "GET" && url === "/api/v1/providers") {
        return jsonBody({
          providers: [{ provider_id: "meta", health: "ok", evidenced: true }],
        });
      }
      if (method === "GET" && url.startsWith("/api/v1/teststage/plans/latest")) {
        return jsonBody({ code: "NO_PLAN" }, 404);
      }
      if (method === "GET" && url.startsWith("/api/v1/teststage/runs/latest")) {
        return jsonBody({ code: "NO_RUN" }, 404);
      }
      if (method === "GET" && url.startsWith("/api/v1/local/status")) {
        return jsonBody({ code: "NO_LOCAL" }, 404);
      }
      if (method === "GET" && url.startsWith("/api/v1/local/models")) {
        return jsonBody({ code: "NO_LOCAL" }, 404);
      }
      return jsonBody({ code: "FXTELEM_UNEXPECTED_API" }, 404);
    },
  );
}

function renderInspector(): void {
  const router = createMemoryRouter(
    [{ path: "*", element: <Inspector projectId="p-1" live={<span>live</span>} /> }],
    { initialEntries: ["/"] },
  );
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem("agentsi.locale", "en");
  setLocale("en");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("fxtelem two-run truth", () => {
  it("names last run and project totals, never an unlabeled global", async () => {
    stubTwoRuns();
    renderInspector();
    const lastRun = await screen.findByTestId("tokens-last-run");
    expect(lastRun.textContent).toContain("13,938");
    expect(lastRun.textContent).toContain("Last run");
    // Rail "This project" is the project-scoped telemetry total: the same
    // number the project Tokens tab shows, and the per-model rows add up
    // to it.
    const project = await screen.findByTestId("tokens-project");
    expect(project.textContent).toContain("33,180");
    expect(project.textContent).toContain("This project");
    const ctxProject = await screen.findByTestId("ctx-used");
    expect(ctxProject.textContent).toContain("33,180");
    expect(ctxProject.textContent).toContain("This project");
    const chatLine = await screen.findByTestId("tokens-chat");
    expect(chatLine.textContent).toContain("19,080");
    expect(chatLine.textContent).toContain("In chat answers");
    const ctxChat = await screen.findByTestId("ctx-chat");
    expect(ctxChat.textContent).toContain("19,080");
    // Per-model rows add up to the rail number.
    const kindRows = await screen.findAllByTestId(/^tokens-kind-/);
    let kindSum = 0;
    for (const row of kindRows) {
      const tail = (row.textContent ?? "").match(/([\d,]+)\s*$/);
      kindSum += Number((tail?.[1] ?? "0").replace(/,/g, ""));
    }
    expect(kindSum).toBe(33180);
  });

  it("rail number equals the project Tokens tab number", async () => {
    stubTwoRuns();
    const router = createMemoryRouter(
      [{ path: "*", element: <ProjectView projectId="p-1" view="tokens" /> }],
      { initialEntries: ["/"] },
    );
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <RouterProvider router={router} />
      </ApiClientProvider>,
    );
    const spent = await screen.findByTestId("tokens-spent");
    expect(spent.textContent).toContain("33,180");
    cleanup();
    renderInspector();
    const project = await screen.findByTestId("tokens-project");
    expect(project.textContent).toContain("33,180");
  });

  it("never renders spent 0 when the price is unknown", async () => {
    stubTwoRuns();
    renderInspector();
    const budget = await screen.findByTestId("kit-metric-fx-budget");
    expect(budget.textContent).not.toMatch(/Spent 0([^.]|$)/);
    expect(budget.textContent).toContain("not known, no price yet");
  });

  it("names connected providers instead of Unknown", async () => {
    stubTwoRuns();
    renderInspector();
    const providers = await screen.findByTestId("kit-metric-fx-providers");
    expect(providers.textContent).toContain("meta");
    expect(providers.textContent).not.toContain("Unknown");
  });
});
