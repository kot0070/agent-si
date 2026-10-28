/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import type {
  BudgetState,
  LedgerRow,
  ProjectRecord,
  TaskRecord,
} from "../../api/iface";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { LocaleProvider } from "../../locale/index";
import type { SupportedLocale } from "../../locale/index";
import {
  ProjectView,
  ReportReadable,
  parseReportExport,
} from "../ProjectView";

const CREATED_AT = "2026-01-01T00:00:00.000Z";

const PROJECT: ProjectRecord = {
  project_id: "p-9",
  name: "Alpha Nine",
  created_at: CREATED_AT,
};

const TASKS: TaskRecord[] = [
  {
    task_id: "t-9",
    project_id: "p-9",
    title: "running nine",
    status: "RUNNING",
    created_at: CREATED_AT,
  },
  {
    task_id: "t-10",
    project_id: "p-9",
    title: "queued nine",
    status: "QUEUED",
    created_at: CREATED_AT,
  },
  {
    task_id: "t-11",
    project_id: "p-9",
    title: "created nine",
    status: "CREATED",
    created_at: "2026-02-03T04:05:06.000Z",
  },
];

const LEDGER: LedgerRow[] = [
  { package_id: "pkg-9", agents: 3, peak_concurrency: 2, wall_time_s: 90 },
];

const BUDGET: BudgetState = {
  project_id: "p-9",
  hard_limit: 100,
  spent: 10,
  reserved: 5,
  currency: "u-9",
};

function jsonBody(data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function stubBoundary(): void {
  vi.stubGlobal(
    "fetch",
    async (url: unknown, init?: { method?: string; body?: string }) => {
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
        return jsonBody({ state: BUDGET });
      }
      if (path === "/api/v1/agents/live" && method === "GET") {
        return jsonBody({ agents: [] });
      }
      throw new Error(`unexpected fetch ${method} ${path}`);
    },
  );
}

function renderReports(locale: SupportedLocale): void {
  setLocale(locale);
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <LocaleProvider initialLocale={locale}>
        <ProjectView projectId="p-9" view="reports" />
      </LocaleProvider>
    </ApiClientProvider>,
  );
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  stubBoundary();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("uifix1 report readable", () => {
  it("shows the report as labelled rows in en without raw braces outside the raw block", async () => {
    renderReports("en");
    const readable = await screen.findByTestId("project-report-readable");
    expect(readable.textContent).toContain("Alpha Nine");
    expect(readable.textContent).toContain(t("tasks.status.running"));
    expect(readable.textContent).toContain(t("tasks.status.queued"));
    expect(readable.textContent).toContain(t("tasks.status.queued"));
    expect(readable.textContent).toContain("10");
    expect(readable.textContent).toContain("5");
    expect(readable.textContent).toContain("100");
    expect(readable.textContent).toContain("u-9");
    expect(readable.textContent).not.toContain('{"');
    const raw = await screen.findByTestId("project-report-export");
    expect(raw.textContent).toContain('{"');
    expect(raw.textContent).toContain("agent-si-report/1");
  });

  it("labels the same rows in uk with different text", async () => {
    setLocale("en");
    const enRunning = t("tasks.status.running");
    const enCreated = t("tasks.status.queued");
    renderReports("uk");
    const readable = await screen.findByTestId("project-report-readable");
    expect(readable.textContent).toContain("Alpha Nine");
    expect(readable.textContent).toContain(t("tasks.status.running"));
    expect(readable.textContent).toContain(t("tasks.status.queued"));
    expect(t("tasks.status.running")).not.toBe(enRunning);
    expect(t("tasks.status.queued")).not.toBe(enCreated);
    expect(readable.textContent).not.toContain('{"');
  });

  it("keeps the raw export collapsed behind an explicit control with the original text", async () => {
    renderReports("en");
    const raw = await screen.findByTestId("project-report-export");
    const details = await screen.findByTestId("project-report-raw");
    expect(details.tagName).toBe("DETAILS");
    expect((details as HTMLDetailsElement).open).toBe(false);
    const parsed: unknown = JSON.parse(raw.textContent ?? "");
    expect(parsed).toMatchObject({
      format: "agent-si-report/1",
      project: { name: "Alpha Nine" },
    });
  });

  it("shows non-JSON export text as plain text without throwing", () => {
    setLocale("en");
    expect(parseReportExport("not json{{")).toBeNull();
    expect(
      parseReportExport(
        '{"format":"agent-si-report/1","project":{},"ledger":[],"budget":{}}',
      ),
    ).not.toBeNull();
    render(
      <LocaleProvider initialLocale="en">
        <ReportReadable
          project={PROJECT}
          tasks={TASKS}
          budget={BUDGET}
          report="not json{{"
        />
      </LocaleProvider>,
    );
    expect(screen.getByTestId("project-report-readable").textContent).toContain(
      "not json{{",
    );
  });
});
