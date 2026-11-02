/** @vitest-environment jsdom */
// FXVIEWS V7 RED-first: (1) project tabs stay ONE scrollable row with a
// selected state, never wrapped into several rows; (2) merged run verdict
// text verification: runStatusText "done"/"failed" plus served per-part
// verdicts verbatim (no "All parts passed" string anywhere in frontend).
// Network only (fetch stubbed, real HttpApiClient over the real App).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
// @ts-ignore: node types unavailable offline
import { readFileSync } from "node:fs";
import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { App } from "../../app/App";
import { PROJECT_VIEWS, projectMenuTestId } from "../projectsApi";
import { runStatusText } from "../viewsApi";
import type { DevrunRun } from "../viewsApi";

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

// All parts pass: merged verdict line must read the served verdicts.
const RUN = {
  run_id: "r-1",
  start: "2026-05-01T10:00:00.000Z",
  end: "2026-05-01T10:01:30.000Z",
  parts: [
    { part_id: "p1", verdict: "PASS", attempts: 1, reason: "checks green" },
    { part_id: "p2", verdict: "PASS", attempts: 1, reason: "checks green" },
  ],
  verdicts: { p1: "PASS", p2: "PASS" },
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
      return jsonBody({ code: "FXVIEWSV7_UNEXPECTED_API" }, 404);
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

describe("fxviewsv7 quiet wrapping tab row", () => {
  it("wraps tabs to more lines with the selected tab marked in ink", async () => {
    renderAppAt("/projects/p9/overview");
    const nav = await screen.findByRole("navigation", {
      name: "Project sections",
    });
    expect(nav.classList.contains("fxpv-tabs")).toBe(true);
    // U1: quiet text tabs wrap to more lines — no boxed scroll row, no
    // thick scrollbar, no solid repaint. (jsdom applies no stylesheet
    // here — SHEETS 0 probed — so the rule text itself is the guard,
    // same readFileSync precedent as fxrc1fix/fxfirstrun2; the DOM half
    // below proves every tab lives in that row with the ink selected
    // state intact.)
    // Tests run from frontend/, so this is src/projects/projectview.css.
    const tabsCss = readFileSync("src/projects/projectview.css", "utf8");
    const tabsBlock = /\.fxpv-tabs\s*\{([^}]*)\}/.exec(tabsCss)?.[1] ?? "";
    expect(tabsBlock).toMatch(/flex-wrap\s*:\s*wrap/);
    expect(tabsBlock).toMatch(/overflow-x\s*:\s*visible/);
    expect(tabsBlock).not.toMatch(/flex-wrap\s*:\s*nowrap/);
    // Every tab (chat + all project views) lives in that row.
    expect(nav.querySelector('[data-testid="project-chat-tab"]')).not.toBeNull();
    for (const view of PROJECT_VIEWS) {
      expect(
        nav.querySelector(`[data-testid="${projectMenuTestId(view)}"]`),
      ).not.toBeNull();
    }
    // Selected state survives the wrap rework.
    const selected = await screen.findByTestId("project-menu-overview");
    expect(selected.getAttribute("aria-current")).toBe("true");
    expect(selected.className).toContain("fxpv-tab-selected");
    const idle = screen.getByTestId("project-menu-cost");
    expect(idle.getAttribute("aria-current")).toBeNull();
    expect(idle.className).not.toContain("fxpv-tab-selected");
  });
});

describe("fxviewsv7 merged run verdict text (verify, no replace)", () => {
  it("reads done plus the served per-part verdicts on an all-pass run", async () => {
    renderAppAt("/projects/p9/runs");
    const card = await screen.findByTestId("devrun-card-r-1");
    const text = card.textContent ?? "";
    expect(text).toContain("done");
    expect(text).toContain("p1: PASS");
    expect(text).toContain("p2: PASS");
  });

  it("runStatusText merges success to done, failure to failed", () => {
    expect(runStatusText(RUN as DevrunRun)).toBe("done");
    expect(runStatusText({ ...RUN, success: false } as DevrunRun)).toBe(
      "failed",
    );
  });
});
