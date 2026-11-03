/** @vitest-environment jsdom */
// FXFACTS F2/F2b/F3/F4 RED: trial-4 tabs say otherwise than the run.
// Four runs (three failed key-missing + one passed). Tabs show the LATEST
// run only; the passing reason never reads as an error. Real App render,
// fetch stubbed at network only.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { App } from "../../app/App";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";

const PROJECT = {
  project_id: "p9",
  name: "P9",
  created_at: "2026-01-01T00:00:00.000Z",
};

function oldRun(id: string) {
  return {
    run_id: id,
    start: "2026-11-02T09:00:00.000Z",
    end: "2026-11-02T09:01:00.000Z",
    parts: [{ part_id: "p1", verdict: "FAIL", attempts: 1, reason: "key missing" }],
    verdicts: { p1: "FAIL" },
    tokens: "UNKNOWN",
    cost: "UNAVAILABLE",
    files: [],
    success: false,
    summary: "The key for 'meta' is not available. Connect it again.",
  };
}

const NEW_RUN = {
  run_id: "r-new",
  start: "2026-11-02T10:14:00.000Z",
  end: "2026-11-02T10:15:00.000Z",
  parts: [{ part_id: "p1", verdict: "PASS", attempts: 1, reason: "checks green" }],
  verdicts: { p1: "PASS" },
  tokens: 150,
  cost: "0.000023",
  files: ["ok.py"],
  success: true,
  summary: "run success: all 1 parts PASS",
};

function oldRow(agent: string, id: string) {
  return {
    agent,
    scope: "s",
    deliverable: `artifact://run/${id}/output`,
    context: `artifact:run/${id}/input`,
    status: "BLOCKED",
    role: "director",
    provider: "meta",
    model: "muse-spark-1.3-contributor",
    placement: "CLOUD",
    tokens: { input: 10, output: 5 },
    cost: "UNAVAILABLE",
    errors: ["The key for 'meta' is not available. Connect it again."],
    waits: [],
  };
}

const LIVE = [
  {
    agent: "director-plan",
    scope: "s",
    deliverable: "artifact://run/r-new/output",
    context: "artifact:run/r-new/input",
    status: "RETURNED",
    role: "director",
    provider: "meta",
    model: "muse-spark-1.3-contributor",
    placement: "CLOUD",
    tokens: { input: 100, output: 50 },
    cost: "0.000023",
    errors: [],
    waits: [],
  },
  oldRow("director-plan", "r-old-1"),
  oldRow("director-plan", "r-old-2"),
  oldRow("director-plan", "r-old-3"),
];

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubFetch(): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "GET" && url === "/api/v1/projects") {
        return jsonBody({ projects: [PROJECT] });
      }
      if (method === "GET" && url === "/api/v1/projects/p9") {
        return jsonBody({ project: PROJECT });
      }
      if (method === "GET" && url === "/api/v1/tasks?project_id=p9") {
        return jsonBody({ tasks: [] });
      }
      if (method === "GET" && url === "/api/v1/runs/ledger?project_id=p9") {
        return jsonBody({
          rows: [],
          runs: [NEW_RUN, oldRun("r-old-3"), oldRun("r-old-2"), oldRun("r-old-1")],
        });
      }
      if (method === "GET" && url === "/api/v1/budget?project_id=p9") {
        return jsonBody({
          project_id: "p9",
          budget: {
            project_id: "p9",
            hard_limit: 5,
            spent: 0,
            reserved: 0,
            currency: "USD",
          },
        });
      }
      if (method === "GET" && url === "/api/v1/agents/live") {
        return jsonBody({ agents: LIVE });
      }
      if (method === "GET" && url.startsWith("/api/v1/analytics/telemetry")) {
        return jsonBody({
          models: [],
          roles: [
            { role: "director", model: "muse-spark-1.3-contributor", calls: 1, tokens: 150, cost: "UNAVAILABLE" },
          ],
        });
      }
      return jsonBody({ code: "FXFACTS2_UNEXPECTED_API" }, 404);
    },
  );
}

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

describe("fxfacts2 latest run owns the tabs", () => {
  it("cloud tab shows the latest run only, no blocked note", async () => {
    stubFetch();
    renderAppAt("/projects/p9/cloud-ai");
    const card = await screen.findByTestId("place-row-director-plan");
    expect(card.textContent).not.toContain("BLOCKED");
    expect(screen.queryByTestId("live-blocked-note")).toBeNull();
    expect(card.textContent).toContain("Finished");
    expect(card.textContent).not.toContain("4 attempts");
  });

  it("errors tab lists no passing reason as an error", async () => {
    stubFetch();
    renderAppAt("/projects/p9/errors");
    // The latest run passed: no blocked rows from stale runs, and the
    // passing reason never renders as an error.
    const active = await screen.findByTestId("project-menu-errors");
    expect(active.getAttribute("aria-selected")).toBe("true");
    await screen.findByTestId("inspector-card-team");
    expect(screen.queryByTestId("error-blocked-0")).toBeNull();
    expect(document.body.textContent).not.toContain("checks green");
  });

  it("models tab third cell is a served number with a translated role", async () => {
    stubFetch();
    renderAppAt("/projects/p9/models");
    const row = await screen.findByTestId("model-live-0");
    expect(row.textContent).toContain("150");
    expect(row.textContent).toContain(t("providers.role.director"));
    expect(row.textContent).not.toContain("director muse-spark");
  });

  it("time tab totals the listed run walls when the ledger is empty", async () => {
    stubFetch();
    renderAppAt("/projects/p9/time");
    // 60 + 60 + 60 + 60 s of listed walls.
    const total = await screen.findByTestId("time-wall-total");
    expect(total.textContent).toContain("4 min");
    expect(total.textContent).not.toContain("Unknown");
  });
});
