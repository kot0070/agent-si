/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import type {
  BudgetState,
  LedgerRow,
  ProjectRecord,
  TaskRecord,
} from "../../api/iface";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import {
  DERIVED_SPLIT_LABEL_KEY,
  buildDerivedSplit,
} from "../projectsApi";
import { ProjectView } from "../ProjectView";

const CREATED_AT = "2026-01-01T00:00:00.000Z";

const PROJECT: ProjectRecord = {
  project_id: "p-9",
  name: "Split Nine",
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
];

const LEDGER: LedgerRow[] = [
  { package_id: "pkg-a", agents: 3, peak_concurrency: 2, wall_time_s: 30 },
  { package_id: "pkg-b", agents: 1, peak_concurrency: 1, wall_time_s: 10 },
];

const BUDGET: BudgetState = {
  project_id: "p-9",
  hard_limit: 100,
  spent: 100,
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
        return jsonBody({ project_id: "p-9", budget: BUDGET });
      }
      if (path === "/api/v1/agents/live" && method === "GET") {
        return jsonBody({ agents: [] });
      }
      throw new Error(`unexpected fetch ${method} ${path}`);
    },
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

describe("ARCH-683 derived display split", () => {
  it("splits measured spent across packages by served wall time", () => {
    const split = buildDerivedSplit({ ledger: LEDGER, budget: BUDGET });
    expect(split).toHaveLength(2);
    expect(split[0]).toMatchObject({
      packageId: "pkg-a",
      wallTimeS: 30,
      currency: "u-9",
      labelKey: "projects.derived.label",
    });
    expect(split[0].derivedCost).toBeCloseTo(75, 9);
    expect(split[1].derivedCost).toBeCloseTo(25, 9);
    const total = split.reduce((sum, row) => sum + row.derivedCost, 0);
    expect(total).toBeCloseTo(BUDGET.spent, 9);
  });

  it("labels every row with the DERIVED key, never a measured key", () => {
    for (const row of buildDerivedSplit({ ledger: LEDGER, budget: BUDGET })) {
      expect(row.labelKey).toBe(DERIVED_SPLIT_LABEL_KEY);
      expect(row.labelKey).toBe("projects.derived.label");
    }
  });

  it("yields no rows for an empty ledger, never invented zeros", () => {
    expect(buildDerivedSplit({ ledger: [], budget: BUDGET })).toEqual([]);
  });

  it("yields zero allocations, still labeled derived, for a zero wall total", () => {
    const zeroWall: LedgerRow[] = [
      { package_id: "pkg-z", agents: 1, peak_concurrency: 1, wall_time_s: 0 },
    ];
    const split = buildDerivedSplit({ ledger: zeroWall, budget: BUDGET });
    expect(split).toHaveLength(1);
    expect(split[0].derivedCost).toBe(0);
    expect(split[0].labelKey).toBe("projects.derived.label");
  });

  it("no longer renders engine allocation rows under Calculated value", async () => {
    // FXLOOK D5: the derived-split rows are dropped from the reports
    // view (the pure builder keeps its own unit tests above).
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ProjectView projectId="p-9" view="reports" />
      </ApiClientProvider>,
    );
    await screen.findByTestId("project-report-derived");
    expect(screen.queryByTestId("project-report-derived-split")).toBeNull();
    expect(screen.queryByTestId("derived-split-pkg-a")).toBeNull();
  });
});
