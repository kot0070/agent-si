/** @vitest-environment jsdom */
// FXVIEWS3 RED-first: the Runs ledger "runs" key reaches the tabs.
// Network only (fetch stubbed, real HttpApiClient over the real App);
// asserts the served devrun row renders instead of the empty state.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { App } from "../../app/App";
import { readRuns, runWallS } from "../viewsApi";

const PROJECT = {
  project_id: "p9",
  name: "P9",
  created_at: "2026-01-01T00:00:00.000Z",
};

const TASK = {
  task_id: "t-9",
  project_id: "p9",
  title: "build it",
  status: "done",
  created_at: "2026-05-01T10:00:00.000Z",
};

const RUN = {
  run_id: "r-1",
  start: "2026-05-01T10:00:00.000Z",
  end: "2026-05-01T10:01:30.000Z",
  parts: [
    { part_id: "p1", verdict: "PASS", attempts: 1, reason: "checks green" },
  ],
  verdicts: { p1: "PASS" },
  tokens: 42,
  cost: "UNKNOWN",
  files: ["test_p1.py"],
  success: true,
  summary: "built it",
};

const BUDGET = {
  project_id: "p9",
  hard_limit: 100,
  spent: 10,
  reserved: 5,
  currency: "u-9",
};

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

type FetchCall = { url: string; method: string };

let calls: FetchCall[];

function stubFetch(): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      calls.push({ url, method });
      if (method === "GET" && url === "/api/v1/projects") {
        return jsonBody({ projects: [PROJECT] });
      }
      if (method === "GET" && url === "/api/v1/projects/p9") {
        return jsonBody({ project: PROJECT });
      }
      if (method === "GET" && url === "/api/v1/tasks?project_id=p9") {
        return jsonBody({ tasks: [TASK] });
      }
      if (method === "GET" && url === "/api/v1/runs/ledger?project_id=p9") {
        return jsonBody({ rows: [], runs: [RUN] });
      }
      if (method === "GET" && url === "/api/v1/budget?project_id=p9") {
        return jsonBody({ project_id: "p9", budget: BUDGET });
      }
      if (method === "GET" && url === "/api/v1/agents/live") {
        return jsonBody({ agents: [] });
      }
      if (method === "GET" && url === "/api/v1/providers") {
        return jsonBody({ providers: [] });
      }
      if (
        method === "GET" &&
        url === "/api/v1/chat/models?project_id=p9"
      ) {
        return jsonBody({ project_id: "p9", models: [] });
      }
      if (
        method === "GET" &&
        url === "/api/v1/apps/card?project_id=p9"
      ) {
        return jsonBody({
          project_id: "p9",
          service_ids: [],
          paused: false,
          generated_at: "t-0",
        });
      }
      if (method === "GET" && url === "/api/v1/kb/status") {
        return jsonBody({ kb_id: null });
      }
      if (method === "GET" && url === "/api/v1/kb/refresh/proposal") {
        return jsonBody({ kb_id: null, stale: false, proposals: [] });
      }
      return jsonBody({ code: "FXVIEWS3_UNEXPECTED_API" }, 404);
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
  calls = [];
  stubFetch();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("fxviews3 runs over the real app", () => {
  it("runs tab lists the served run as one card, never the empty state", async () => {
    renderAppAt("/projects/p9/runs");
    const row = await screen.findByTestId("devrun-card-r-1");
    const text = row.textContent ?? "";
    expect(text).toContain("done");
    expect(text).toContain("2026");
    expect(text).toContain("p1: PASS");
    expect(text).toContain("42");
    expect(text).toContain("not known");
    expect(text).toContain("test_p1.py");
    expect(text).toContain("built it");
    expect(text).toContain("r-1");
    const card = await screen.findByTestId("kit-card-project-runs");
    expect(
      within(card).queryByTestId("kit-empty-state"),
    ).toBeNull();
  });

  it("overview counts the served runs in one line", async () => {
    renderAppAt("/projects/p9/overview");
    const count = await screen.findByTestId("overview-package-count");
    expect(count.textContent).toContain("Runs");
    expect(count.textContent).toContain("1");
    const wall = await screen.findByTestId("overview-wall-total");
    expect(wall.textContent).toContain("1 min 30 s");
  });

  it("tasks tab shows the served task status text", async () => {
    renderAppAt("/projects/p9/tasks");
    const row = await screen.findByTestId("task-row-t-9");
    expect(row.textContent).toContain("build it");
    expect(row.textContent).toContain("done");
  });
});

describe("fxviews3 viewsApi runs helpers", () => {
  it("reads the runs key off the same ledger route", async () => {
    const runs = await readRuns("p9");
    expect(runs).toHaveLength(1);
    expect(runs[0]?.run_id).toBe("r-1");
    expect(runWallS(runs[0]!)).toBe(90);
    expect(
      calls.some(
        (call) =>
          call.method === "GET" &&
          call.url === "/api/v1/runs/ledger?project_id=p9",
      ),
    ).toBe(true);
  });
});
