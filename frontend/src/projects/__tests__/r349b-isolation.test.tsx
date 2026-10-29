/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { LocaleProvider } from "../../locale/index";
import { ProjectView } from "../ProjectView";

// R349C: the merged project view must survive a failing limits request.
// Budget uses the strict served shape ({project_id, budget}, string amounts,
// mirrors frontend/src/api/wire/budget-state.json); step-limits answers 500;
// everything else is served through the real HttpApiClient. No legacy {state}
// envelope, no browser-rebuilt export: reports use only the served export.
const PROJECT = {
  project_id: "p-9",
  name: "Alpha Nine",
  created_at: "2026-01-01T00:00:00.000Z",
};

const TASKS = [
  {
    task_id: "t-9",
    project_id: "p-9",
    title: "running nine",
    status: "RUNNING",
    created_at: "2026-01-01T00:00:00.000Z",
  },
];

const LEDGER = [
  { package_id: "pkg-9", agents: 3, peak_concurrency: 2, wall_time_s: 90 },
];

const SERVED_BUDGET = {
  project_id: "p-9",
  hard_limit: "100",
  spent: "10",
  reserved: "5",
  currency: "u-9",
};

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubViewWithFailingLimits(): void {
  vi.stubGlobal(
    "fetch",
    async (url: unknown, init?: { method?: string }) => {
      const path = String(url);
      const method = init?.method ?? "GET";
      if (path === "/api/v1/projects/p-9" && method === "GET") {
        return jsonBody({ project: PROJECT });
      }
      if (path === "/api/v1/tasks?project_id=p-9" && method === "GET") {
        return jsonBody({ tasks: TASKS });
      }
      if (path === "/api/v1/runs/ledger?project_id=p-9" && method === "GET") {
        return jsonBody({ rows: LEDGER });
      }
      if (path === "/api/v1/budget?project_id=p-9" && method === "GET") {
        return jsonBody({ project_id: "p-9", budget: SERVED_BUDGET });
      }
      if (path === "/api/v1/agents/live" && method === "GET") {
        return jsonBody({ agents: [] });
      }
      if (path === "/api/v1/projects/p-9/step-limits") {
        return jsonBody({ detail: "STEP_LIMITS_DOWN" }, 500);
      }
      throw new Error(`unexpected fetch ${method} ${path}`);
    },
  );
}

function renderView(view: "overview" | "reports" | "tasks"): void {
  setLocale("en");
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <LocaleProvider initialLocale="en">
        <ProjectView projectId="p-9" view={view} />
      </LocaleProvider>
    </ApiClientProvider>,
  );
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  stubViewWithFailingLimits();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("R349C limits isolation", () => {
  it("still renders the report when the limits request fails", async () => {
    renderView("reports");
    const readable = await screen.findByTestId("project-report-readable");
    expect(readable.textContent).toContain("Alpha Nine");
    expect(readable.textContent).toContain("10");
    expect(readable.textContent).toContain("100");
    const raw = await screen.findByTestId("project-report-export");
    expect(raw.textContent).toContain("agent-si-report/1");
  });

  it("still renders the tasks when the limits request fails", async () => {
    renderView("tasks");
    const row = await screen.findByTestId("task-row-t-9");
    expect(row.textContent).toContain("running nine");
  });

  it("keeps the overview content and shows the limits error on its own", async () => {
    renderView("overview");
    const name = await screen.findByTestId("overview-name");
    expect(name.textContent).toContain("Alpha Nine");
    const error = await screen.findByTestId("project-limits-error");
    expect(error.textContent?.length).toBeGreaterThan(0);
  });
});
