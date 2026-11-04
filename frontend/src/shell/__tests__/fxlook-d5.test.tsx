/** @vitest-environment jsdom */
// FXLOOK D5 RED: small owner-found items on the real App (fetch is the
// only fake): Team Now summary reads human, watcher rail reads plain
// "not used yet", reports Tasks header carries the count with no
// duplicate Money spent and no engine rows under Calculated value, the
// nav guard names the live run.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import {
  createMemoryRouter,
  Link,
  RouterProvider,
  useLocation,
} from "react-router-dom";
import type { ReactElement } from "react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { ClosingGuard } from "../../shell/ClosingGuard";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { App } from "../../app/App";

const PROJECT = { project_id: "p-1", name: "n-1", created_at: "t-0" };

const LIVE_ROWS = [
  {
    agent: "director-plan",
    scope: "s",
    deliverable: "d-1",
    status: "RUNNING",
    role: "director",
    model: "muse-spark-1.3-contributor",
  },
];

const BUDGET = {
  project_id: "p-1",
  hard_limit: 100,
  spent: 30,
  reserved: 20,
  currency: "USD",
};

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubServed(taskCount: number): void {
  const tasks = Array.from({ length: taskCount }, (_, index) => ({
    task_id: `t-${index}`,
    project_id: "p-1",
    title: `task ${index}`,
    status: "RUNNING",
    created_at: "t-0",
  }));
  vi.stubGlobal("fetch", async (input: unknown) => {
    const url = String(input);
    if (url === "/api/v1/projects") {
      return jsonBody({ projects: [PROJECT] });
    }
    if (url === "/api/v1/projects/p-1") {
      return jsonBody({ project: PROJECT });
    }
    if (url === "/api/v1/agents/live") {
      return jsonBody({ agents: LIVE_ROWS });
    }
    if (url === "/api/v1/tasks?project_id=p-1") {
      return jsonBody({ tasks });
    }
    if (url === "/api/v1/runs/ledger?project_id=p-1") {
      return jsonBody({ rows: [], runs: [] });
    }
    if (url === "/api/v1/budget?project_id=p-1") {
      return jsonBody({ project_id: "p-1", budget: BUDGET });
    }
    if (url === "/api/v1/watcher/status?project_id=p-1") {
      // No answering model, no calls: the rail must read plain words.
      return jsonBody({
        project_id: "p-1",
        integrity_ok: true,
        journal_head: "jh-1",
        generated_at: "t-0",
        last_check_at: "2026-02-11T06:42:44Z",
        checks_done: 0,
        alerts_raised: 0,
      });
    }
    if (url === "/api/v1/watcher/journal?project_id=p-1") {
      return jsonBody([
        { entry_id: "e-1", timestamp: "t-1", hash: "h-1" },
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
    return jsonBody({ code: "FXLOOK_D5_UNEXPECTED" }, 404);
  });
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

function LocationProbe(): ReactElement {
  const location = useLocation();
  return <span data-testid="guard-location">{location.pathname}</span>;
}

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

describe("FXLOOK D5 team summary reads human", () => {
  it("shows role plus status, raw id and model only in tooltip/details", async () => {
    stubServed(0);
    renderAppAt("/");
    const line = await screen.findByTestId("team-line-director-plan");
    expect(line.textContent).toContain("Director");
    expect(line.textContent).toContain("Running");
    expect(line.textContent).not.toContain("director-plan");
    // FXFACTS F14: the line shows the short model name (this id has no prefix).
    expect(line.textContent).toContain("muse-spark-1.3-contributor");
    expect(line.getAttribute("title")).toBe("muse-spark-1.3-contributor");
    const detail = await screen.findByTestId("team-detail-director-plan");
    expect(detail.textContent).toContain("director-plan");
    expect(detail.textContent).toContain("muse-spark-1.3-contributor");
  });
});

describe("FXLOOK D5 watcher rail without a model", () => {
  it("reads plain not used yet, never UNAVAILABLE", async () => {
    stubServed(0);
    renderAppAt("/");
    // FXFACTS F10: the watcher card is collapsed by default; open it.
    fireEvent.click(await screen.findByTestId("rail-toggle-watcher"));
    const model = await screen.findByTestId("watcher-model");
    expect(model.textContent).toContain(t("watcher.tab.notUsedYet"));
    expect(model.textContent).not.toContain("UNAVAILABLE");
  });
});

describe("FXLOOK D5 reports without blanks or duplicates", () => {
  it("Tasks header carries the count; no duplicate spent, no engine rows", async () => {
    stubServed(2);
    renderAppAt("/projects/p-1/reports");
    const counts = await screen.findByTestId("report-task-counts");
    expect(counts.textContent).toContain("Tasks:");
    expect(counts.textContent).toContain("2");
    // The budget block keeps its spent; Calculated value drops the copy.
    expect(
      (await screen.findByTestId("report-budget-spent")).textContent,
    ).toContain("Money spent");
    const derived = await screen.findByTestId("project-report-derived");
    expect(derived.textContent).not.toContain("Money spent");
    expect(screen.queryByTestId("project-report-derived-split")).toBeNull();
  });

  it("empty tasks still read Tasks: 0", async () => {
    stubServed(0);
    renderAppAt("/projects/p-1/reports");
    const counts = await screen.findByTestId("report-task-counts");
    expect(counts.textContent).toContain("0");
  });
});

describe("FXLOOK D5 nav guard names the live run", () => {
  it("blocks with Run still working. Leave this page?", async () => {
    const router = createMemoryRouter(
      [
        {
          path: "*",
          element: (
            <>
              <ClosingGuard
                armed
                confirmKey="shell.closing.runWorking"
              >
                <span data-testid="guard-body">guarded</span>
              </ClosingGuard>
              <Link data-testid="guard-go" to="/guard-b">
                go
              </Link>
              <LocationProbe />
            </>
          ),
        },
      ],
      { initialEntries: ["/guard-a", "/guard-b"], initialIndex: 0 },
    );
    render(<RouterProvider router={router} />);
    expect(await screen.findByTestId("guard-body")).toBeTruthy();
    fireEvent.click(screen.getByTestId("guard-go"));
    expect(await screen.findByTestId("closing-confirm")).toBeTruthy();
    expect(
      screen.getByTestId("closing-confirm").textContent,
    ).toContain("Run still working. Leave this page?");
  });
});
