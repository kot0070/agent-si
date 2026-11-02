/** @vitest-environment jsdom */
// FXTABS RED-first: project tabs + tables fixes T1-T11, (b)(c)(d), J7.
// Real App render, fetch stubbed at network only.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { App } from "../../app/App";
import { dedupeLiveRows } from "../viewsApi";

const PROJECT = {
  project_id: "p9",
  name: "P9",
  created_at: "2026-01-01T00:00:00.000Z",
};

const RUN_ID = "3829831f3546456baaa49e3c4d932851";

const RUN = {
  run_id: RUN_ID,
  start: "2026-11-02T10:14:00.000Z",
  end: "2026-11-02T10:15:11.000Z",
  parts: [
    { part_id: "p1", verdict: "PASS", attempts: 1, reason: "checks green" },
    { part_id: "p2", verdict: null, attempts: 0 },
    { part_id: "p3", verdict: null, attempts: 0 },
  ],
  verdicts: { p1: "PASS" },
  tokens: 11464,
  cost: "UNKNOWN",
  files: ["wordcount.py"],
  success: false,
  summary: "interrupted: stop requested",
};

const LIVE = [
  { agent: "director-plan", status: "RUNNING", scope: "s", deliverable: "d-1", role: "director", model: "muse-spark-1.3-contributor", tokens: { input: 100, output: 50 } },
  { agent: "director-plan", status: "BLOCKED", scope: "s", deliverable: "d-1", role: "director", model: "muse-spark-1.3-contributor", tokens: { input: 60, output: 40 } },
  { agent: "manager-plan", status: "RUNNING", scope: "s", deliverable: "d-2", role: "manager", model: "muse-spark-1.3-contributor", tokens: { input: 70, output: 30 } },
  { agent: "manager-plan", status: "BLOCKED", scope: "s", deliverable: "d-2", role: "manager", model: "muse-spark-1.3-contributor", tokens: { input: 20, output: 10 } },
  { agent: "worker-p1", status: "BLOCKED", scope: "s", deliverable: "d-3", role: "worker", model: "muse-spark-1.3-contributor", tokens: { input: 10, output: 5 } },
  { agent: "worker-p1", status: "RUNNING", scope: "s", deliverable: "d-3", role: "worker", model: "muse-spark-1.3-contributor" },
  { agent: "worker-p1", status: "RUNNING", scope: "s", deliverable: "d-3", role: "worker", model: "muse-spark-1.3-contributor" },
];

const BUDGET = {
  project_id: "p9",
  hard_limit: 5,
  spent: 0,
  reserved: 0,
  currency: "USD",
};

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
        return jsonBody({ rows: [], runs: [RUN] });
      }
      if (method === "GET" && url === "/api/v1/budget?project_id=p9") {
        return jsonBody({ project_id: "p9", budget: BUDGET });
      }
      if (method === "GET" && url === "/api/v1/agents/live") {
        return jsonBody({ agents: LIVE });
      }
      if (method === "GET" && url === "/api/v1/providers") {
        return jsonBody({ providers: [] });
      }
      if (method === "GET" && url === "/api/v1/chat/models?project_id=p9") {
        return jsonBody({ project_id: "p9", models: [] });
      }
      if (method === "GET" && url === "/api/v1/apps/card?project_id=p9") {
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
      return jsonBody({ code: "FXTABS_UNEXPECTED_API" }, 404);
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
  stubFetch();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("fxtabs tabs", () => {
  it("T2 active tab is marked with aria-selected", async () => {
    renderAppAt("/projects/p9/runs");
    await screen.findByTestId("devrun-card-" + RUN_ID);
    const active = await screen.findByTestId("project-menu-runs");
    expect(active.getAttribute("aria-selected")).toBe("true");
  });

  it("T3 run id shows first 8 chars with copy and full id in title", async () => {
    renderAppAt("/projects/p9/runs");
    const card = await screen.findByTestId("devrun-card-" + RUN_ID);
    const short = card.querySelector('[data-testid="run-id-short"]');
    expect(short).toBeTruthy();
    expect(short?.textContent).toBe(RUN_ID.slice(0, 8));
    expect(short?.getAttribute("title")).toContain(RUN_ID);
    expect(
      card.querySelector('[data-testid="run-id-copy"]'),
    ).toBeTruthy();
    expect(card.textContent).not.toContain(RUN_ID.slice(8));
  });

  it("T4 glued label and value read separated", async () => {
    renderAppAt("/projects/p9/reports");
    const name = await screen.findByTestId("report-project-name");
    const cells = name.querySelectorAll(":scope > span");
    expect(cells.length).toBe(2);
    expect(cells[0]?.textContent).toMatch(/:$/);
  });

  it("T5 no zero guesses: unknown wall and unknown agents, run rows say Run", async () => {
    renderAppAt("/projects/p9/overview");
    const wall = await screen.findByTestId("overview-wall-total");
    // Real run value (71 s served), never a 0 guess.
    expect(wall.textContent).toMatch(/1 min 11 s/);
    const agents = await screen.findByTestId("overview-agents-total");
    expect(agents.textContent).toMatch(/Unknown/);
    renderAppAt("/projects/p9/time");
    const row = await screen.findByTestId("time-run-" + RUN_ID);
    expect(row.textContent).toMatch(/^Run/);
    expect(row.textContent).toMatch(/1 min 11 s/);
  });

  it("T6 one row per agent, nothing stays Running, pending reads not run", async () => {
    renderAppAt("/projects/p9/runs");
    await screen.findByTestId("devrun-card-" + RUN_ID);
    const team = document.querySelectorAll('[data-testid^="runhistory-part-"]');
    const agents = new Set(
      [...team].map((el) => el.getAttribute("data-testid")),
    );
    expect(agents.size).toBeLessThanOrEqual(3);
    for (const el of [...team]) {
      expect(el.textContent).not.toMatch(/Running/);
    }
    const card = screen.getByTestId("devrun-card-" + RUN_ID);
    expect(card.textContent).toMatch(/not run/);
    expect(card.textContent).toMatch(/interrupted: stop requested/);
  });

  it("T7 errors tab shows the run record reason, never served/guard/row", async () => {
    renderAppAt("/projects/p9/errors");
    const panel = await screen.findByTestId("kit-card-project-errors");
    expect(panel.textContent).toMatch(/checks green/);
    expect(panel.textContent).not.toMatch(/served|guard|row waits/);
  });

  it("T8 routing tab has per-role model content after a run", async () => {
    renderAppAt("/projects/p9/routing-decisions");
    const panel = await screen.findByTestId("kit-card-project-routing-decisions");
    expect(panel.textContent).not.toMatch(/Nothing to show yet/);
    expect(panel.textContent).toMatch(/muse-spark-1\.3-contributor/);
  });

  it("T11 uk names: language options and theme words", async () => {
    window.localStorage.setItem("agentsi.locale", "uk");
    const { setLocale } = await import("../../locale/index");
    setLocale("uk");
    renderAppAt("/projects/p9/overview");
    const select = (await screen.findByTestId(
      "topbar-language",
    )) as HTMLSelectElement;
    const labels = [...select.options].map((option) => option.text);
    expect(labels).toContain("Українська");
    expect(labels).toContain("English");
    expect(labels).not.toContain("uk");
    const toggle = await screen.findByTestId("theme-toggle");
    expect(toggle.textContent).toMatch(/темна|світла/);
  });

  it("T10 stop-all is quiet when idle and clickable", async () => {
    renderAppAt("/projects/p9/overview");
    const stop = await screen.findByTestId("topbar-stop-all");
    expect((stop as HTMLButtonElement).disabled).toBe(false);
    expect(stop.className).not.toMatch(/danger/);
  });

  it("T5-D1 no glued Queued2 after runs ended, and tokens tab counts", async () => {
    renderAppAt("/projects/p9/reports");
    const counts = await screen.findByTestId("report-task-counts");
    expect(counts.textContent).not.toMatch(/Queued\d/);
    renderAppAt("/projects/p9/tokens");
    const total = await screen.findByTestId("tokens-spent");
    expect(total.textContent).not.toMatch(/not known yet/);
    expect(total.textContent).toMatch(/395/);
  });
});

describe("fxtabs dedupe", () => {
  it("folds one agent into one row with its last status", () => {
    const rows = dedupeLiveRows(LIVE as never);
    const agents = rows.map((row) => row.agent).sort();
    expect(agents).toEqual(["director-plan", "manager-plan", "worker-p1"]);
  });
});
