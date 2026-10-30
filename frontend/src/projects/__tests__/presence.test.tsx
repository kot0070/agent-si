/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
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
  PROJECT_VIEWS,
  buildDerivedSplit,
  projectMenuTestId,
  projectViewTitleKey,
} from "../projectsApi";
import type { ProjectViewName } from "../projectsApi";
import { ProjectView } from "../ProjectView";
import { Sidebar } from "../../shell/Sidebar";
import { NAMED_MENU_TEST_IDS, checkPresenceBreach } from "../scope";

const CREATED_AT = "2026-01-01T00:00:00.000Z";

const PROJECT: ProjectRecord = {
  project_id: "p-9",
  name: "Presence Nine",
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
        return jsonBody({ project_id: "p-9", budget: BUDGET });
      }
      if (path === "/api/v1/agents/live" && method === "GET") {
        return jsonBody({ agents: [] });
      }
      throw new Error(`unexpected fetch ${method} ${path}`);
    },
  );
}

function renderedTestIds(container: HTMLElement): string[] {
  return [...container.querySelectorAll("[data-testid]")]
    .map((node) => node.getAttribute("data-testid") ?? "")
    .filter((id) => id.length > 0);
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

describe("ARCH-679 named menus", () => {
  it("renders every named menu on the real Sidebar", async () => {
    const view = render(
      <ApiClientProvider client={new HttpApiClient()}>
        <MemoryRouter initialEntries={["/"]}>
          <Sidebar projectId={null} />
        </MemoryRouter>
      </ApiClientProvider>,
    );
    for (const menuId of NAMED_MENU_TEST_IDS) {
      expect(
        await screen.findByTestId(menuId),
        `named menu ${menuId} is rendered`,
      ).toBeTruthy();
    }
    const breaches = checkPresenceBreach({
      must: [...NAMED_MENU_TEST_IDS],
      present: renderedTestIds(view.container),
    });
    expect(breaches).toEqual([]);
    view.unmount();
  });
});

describe.each(PROJECT_VIEWS)("ARCH-679 named view %s", (viewName) => {
  it("renders on the real ProjectView with its locale title", async () => {
    const view = render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ProjectView
          projectId="p-9"
          view={viewName as ProjectViewName}
        />
      </ApiClientProvider>,
    );
    const menuId = projectMenuTestId(viewName as ProjectViewName);
    expect(
      await screen.findByTestId(menuId),
      `project menu ${menuId} is rendered`,
    ).toBeTruthy();
    const title = t(projectViewTitleKey(viewName as ProjectViewName));
    expect(view.container.textContent).toContain(title);
    const breaches = checkPresenceBreach({
      must: PROJECT_VIEWS.map((name) => projectMenuTestId(name)),
      present: renderedTestIds(view.container),
    });
    expect(breaches).toEqual([]);
    view.unmount();
  });
});

describe("ARCH-686 presence guard", () => {
  it("reports a MUST_PRESENCE_BREACH for a missing named menu", () => {
    expect(
      checkPresenceBreach({
        must: [...NAMED_MENU_TEST_IDS],
        present: [...NAMED_MENU_TEST_IDS].filter(
          (id) => id !== "menu-settings",
        ),
      }),
    ).toEqual([{ kind: "MUST_PRESENCE_BREACH", name: "menu-settings" }]);
  });

  it("reports a SHOULD_AS_MUST_BREACH when a MUST render needs a SHOULD breakdown", () => {
    expect(
      checkPresenceBreach({
        must: [...NAMED_MENU_TEST_IDS],
        present: [...NAMED_MENU_TEST_IDS],
        gatedByShould: ["menu-settings"],
      }),
    ).toEqual([{ kind: "SHOULD_AS_MUST_BREACH", name: "menu-settings" }]);
  });

  it("stays silent when every MUST name renders without SHOULD gating", () => {
    expect(
      checkPresenceBreach({
        must: [...NAMED_MENU_TEST_IDS],
        present: [...NAMED_MENU_TEST_IDS, "project-report-derived-split"],
      }),
    ).toEqual([]);
    expect(buildDerivedSplit({ ledger: LEDGER, budget: BUDGET })).toHaveLength(
      1,
    );
  });
});
