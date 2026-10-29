/** @vitest-environment jsdom */
// K07HTTP1 ARCH-643: readable reports over the REAL HttpApiClient (only
// global fetch stubbed; no FakeApiClient). Served rows follow
// ProjectRecordSchema (frontend/src/api/projectsApi.ts:50),
// TaskRecordSchema (:65), LedgerRowSchema (:78) and BudgetStateSchema
// (:152); the report export follows PackageReportSchema (:106).
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
import { ProjectView } from "../ProjectView";
import en from "../../locale/en.json";

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

interface SeenRequest {
  url: string;
  method: string;
}

const seen: SeenRequest[] = [];

function jsonBody(data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function stubBoundary(): void {
  seen.length = 0;
  vi.stubGlobal(
    "fetch",
    async (url: unknown, init?: { method?: string }) => {
      const path = String(url);
      const method = init?.method ?? "GET";
      seen.push({ url: path, method });
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
        return jsonBody({ project_id: "p-9", budget: BUDGET });
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

describe("k07http1 report readable over HttpApiClient", () => {
  it("proves readable reports with labelled rows and no raw braces outside the raw block", async () => {
    renderReports("en");
    const readable = await screen.findByTestId("project-report-readable");
    expect(readable.textContent).toContain("Alpha Nine");
    expect(readable.textContent).toContain(t("tasks.status.running"));
    expect(readable.textContent).toContain(t("tasks.status.queued"));
    expect(readable.textContent).toContain("10");
    expect(readable.textContent).toContain("5");
    expect(readable.textContent).toContain("100");
    expect(readable.textContent).toContain("u-9");
    expect(readable.textContent).not.toContain('{"');
    const raw = await screen.findByTestId("project-report-export");
    expect(raw.textContent).toContain('{"');
    expect(raw.textContent).toContain("agent-si-report/1");
    const derived = await screen.findByTestId("project-report-derived");
    expect(derived.textContent).toContain(en.projects.derived.label);
    expect(derived.textContent).toContain("packages=1 tasks=2");
    expect(derived.textContent).not.toContain('{"');
    const gets = seen.filter((request) => request.method === "GET");
    expect(
      gets.some((request) => request.url === "/api/v1/projects/p-9"),
    ).toBe(true);
    expect(
      gets.some(
        (request) => request.url === "/api/v1/runs/ledger?project_id=p-9",
      ),
    ).toBe(true);
    for (const request of seen) {
      expect(request.url).not.toContain("token");
    }
    expect(en.projects.derived.label.length).toBeGreaterThan(0);
  });
});
