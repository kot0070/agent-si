/** @vitest-environment jsdom */
// L0C-01: one failing read must never hide the sibling panels of the real
// ProjectView. Budget uses the strict served shape ({project_id, budget},
// string amounts, mirrors frontend/src/api/wire/budget-state.json); tasks,
// ledger and project use their served envelopes ({tasks}, {rows},
// {project}); live uses {agents}. Fakes only at the network boundary via the
// real HttpApiClient. No legacy envelope fallback, no browser-rebuilt data.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { LocaleProvider } from "../../locale/index";
import { ProjectView } from "../ProjectView";

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

const STEP_LIMITS = {
  project_id: "p-9",
  task_max_steps: 8,
  chat_max_steps: 8,
};

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubView(options: { failBudget: boolean; failTasks: boolean }): void {
  vi.stubGlobal(
    "fetch",
    async (url: unknown, init?: { method?: string }) => {
      const path = String(url);
      const method = init?.method ?? "GET";
      if (path === "/api/v1/projects/p-9" && method === "GET") {
        return jsonBody({ project: PROJECT });
      }
      if (path === "/api/v1/tasks?project_id=p-9" && method === "GET") {
        if (options.failTasks) {
          return jsonBody({ code: "CONTEXT_MISSING" }, 500);
        }
        return jsonBody({ tasks: TASKS });
      }
      if (path === "/api/v1/runs/ledger?project_id=p-9" && method === "GET") {
        return jsonBody({ rows: LEDGER });
      }
      if (path === "/api/v1/budget?project_id=p-9" && method === "GET") {
        if (options.failBudget) {
          return jsonBody({ code: "BUDGET_CAPPED" }, 500);
        }
        return jsonBody({ project_id: "p-9", budget: SERVED_BUDGET });
      }
      if (path === "/api/v1/agents/live" && method === "GET") {
        return jsonBody({ agents: [] });
      }
      if (path === "/api/v1/projects/p-9/step-limits") {
        return jsonBody(STEP_LIMITS);
      }
      throw new Error(`unexpected fetch ${method} ${path}`);
    },
  );
}

function renderView(view: "tasks" | "reports" | "cost" | "overview"): void {
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
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("L0C-01 panel isolation", () => {
  it("still renders tasks and reports when the budget read fails", async () => {
    stubView({ failBudget: true, failTasks: false });

    renderView("tasks");
    const taskRow = await screen.findByTestId("task-row-t-9");
    expect(taskRow.textContent).toContain("running nine");
    cleanup();

    renderView("reports");
    const readable = await screen.findByTestId("project-report-readable");
    expect(readable.textContent).toContain("Alpha Nine");
    expect(readable.textContent).toContain("1");
    const panels = await screen.findAllByTestId("kit-error-panel");
    expect(panels.length).toBeGreaterThanOrEqual(1);
    expect(
      await screen.findAllByTestId("kit-error-retry"),
    ).not.toHaveLength(0);
    cleanup();

    renderView("overview");
    const name = await screen.findByTestId("overview-name");
    expect(name.textContent).toContain("Alpha Nine");
    expect(
      (await screen.findByTestId("overview-task-count")).textContent,
    ).toContain("1");
    expect(await screen.findAllByTestId("kit-error-panel")).not.toHaveLength(
      0,
    );
  });

  it("still renders budget and reports when the tasks read fails", async () => {
    stubView({ failBudget: false, failTasks: true });

    renderView("cost");
    const limit = await screen.findByTestId("cost-limit");
    expect(limit.textContent).toContain("100");
    cleanup();

    renderView("reports");
    const spent = await screen.findByTestId("report-budget-spent");
    expect(spent.textContent).toContain("10");
    const raw = await screen.findByTestId("project-report-export");
    expect(raw.textContent).toContain("agent-si-report/1");
    expect(raw.textContent).toContain("pkg-9");
    expect(await screen.findAllByTestId("kit-error-panel")).not.toHaveLength(
      0,
    );
  });
});
