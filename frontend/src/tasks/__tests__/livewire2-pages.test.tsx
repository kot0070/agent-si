/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import {
  resetLocaleForTests,
  setLocale,
} from "../../locale/index";
import { ProjectView } from "../../projects/ProjectView";
import { RunHistory } from "../../projects/RunHistory";

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

const SERVED_BUDGET = {
  project_id: "p-1",
  budget: {
    project_id: "p-1",
    currency: "k",
    budget_limit: "5.00",
    soft_limit: "4.00",
    hard_limit: "5.00",
    spent: "1.25",
    reserved: "0.50",
    updated_at: "t-0",
    provider_spend_caps: {},
  },
};

const SERVED_NUDGE = {
  package_id: "pkg-9",
  load: { package_id: "pkg-9", agents: 3, peak_concurrency: 2, wall_time_s: 90 },
  nudge: "review package pkg-9 load before starting the next package",
  auto_push: false,
};

function stubPages(): void {
  vi.stubGlobal("fetch", async (input: unknown) => {
    const url = String(input);
    if (url.includes("/api/v1/budget")) {
      return Response.json(SERVED_BUDGET);
    }
    if (url.includes("/api/v1/tasks")) {
      return Response.json({
        tasks: [
          {
            task_id: "t-1",
            project_id: "p-1",
            title: "task one",
            status: "QUEUED",
            created_at: "t-0",
          },
        ],
      });
    }
    if (url.includes("/api/v1/runs/ledger")) {
      return Response.json({
        rows: [
          { package_id: "pkg-1", agents: 2, peak_concurrency: 2, wall_time_s: 60 },
        ],
      });
    }
    if (url.includes("/api/v1/agents/live")) {
      return Response.json({ agents: [] });
    }
    if (url.includes("/api/v1/reports/next-package-nudge")) {
      return Response.json(SERVED_NUDGE);
    }
    if (url.includes("/api/v1/projects/")) {
      return Response.json({
        project: { project_id: "p-1", name: "n-1", created_at: "t-0" },
      });
    }
    throw new Error(`unexpected fetch to ${url}`);
  });
}

describe("Tasks and Reports load on a real budget response", () => {
  it("renders the tasks view on a 200 budget with string amounts", async () => {
    stubPages();
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-1" view="tasks" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("task-row-t-1")).toBeTruthy();
    expect(screen.queryByTestId("kit-error-panel")).toBeNull();
  });

  it("renders the reports view with derived numbers from the served budget", async () => {
    stubPages();
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-1" view="reports" />
      </ApiClientProvider>,
    );
    const exported = await screen.findByTestId("project-report-export");
    expect(exported.textContent).toContain("pkg-1");
    expect(exported.textContent).toContain("1.25");
    const derived = await screen.findByTestId("project-report-derived");
    expect(derived.textContent).toContain("remaining=3.25");
    expect(screen.queryByTestId("kit-error-panel")).toBeNull();
  });

  it("renders the served budget through the cost view and health leg", async () => {
    stubPages();
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-1" view="cost" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("context-remaining")).toBeTruthy();
    expect(screen.getByTestId("context-remaining").textContent).toBe("3.25");
    expect(screen.getByTestId("context-total").textContent).toBe("5");
    expect(screen.getByTestId("health-spent").textContent).toBe("1.25");
    expect(screen.getByTestId("health-remaining").textContent).toBe("3.25");
    expect(screen.queryByTestId("kit-error-panel")).toBeNull();
  });

  it("renders the reports leg from the served load shape", async () => {
    vi.stubGlobal("fetch", async (input: unknown) => {
      const url = String(input);
      if (url.includes("/api/v1/runs/ledger")) {
        return Response.json({
          rows: [
            { package_id: "pkg-9", agents: 3, peak_concurrency: 2, wall_time_s: 90 },
          ],
        });
      }
      if (url.includes("/api/v1/agents/live")) {
        return Response.json({ agents: [] });
      }
      if (url.includes("/api/v1/reports/next-package-nudge")) {
        return Response.json(SERVED_NUDGE);
      }
      throw new Error(`unexpected fetch to ${url}`);
    });
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <RunHistory projectId="p-9" packageId="pkg-9" />
      </ApiClientProvider>,
    );
    const install = await screen.findByTestId("runhistory-install");
    expect(install.textContent).toContain("pkg-9");
    expect(install.textContent).toContain("90");
    expect(await screen.findByTestId("runhistory-ledger-pkg-9")).toBeTruthy();
    expect(screen.queryByTestId("kit-error-panel")).toBeNull();
  });
});
