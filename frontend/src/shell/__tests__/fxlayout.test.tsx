/** @vitest-environment jsdom */
// FXLAYOUT lane proof: the REAL App renders the Claude-desktop shell —
// exactly four nav entries, five live cards from served route answers and
// six collapsed-by-default metric cards with persisted toggles. The ONLY
// fake is the fetch boundary below (quoting the served schemas); the shell,
// router, sidebar labels, inspector cards and metric cards are all real.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import {
  formatNumber,
  resetLocaleForTests,
  setLocale,
  t,
} from "../../locale/index";
import type { SupportedLocale } from "../../locale/index";
import { App } from "../../app/App";

const PROJECT = { project_id: "p-1", name: "n-1", created_at: "t-0" };

const LIVE_ROWS = [
  {
    agent: "agent-1",
    scope: "scope-1",
    deliverable: "part-1",
    status: "RUNNING",
    role: "manager",
    model: "m-1",
    step: 2,
    file: "f-1.ts",
    tokens: { input: 400, output: 600 },
    context: "ctx-1",
    errors: ["boom-1"],
    waits: ["agent-2"],
  },
  {
    agent: "agent-2",
    scope: "scope-2",
    deliverable: "part-2",
    status: "QUEUED",
  },
];

const TASKS = [
  {
    task_id: "t-9",
    project_id: "p-1",
    title: "running nine",
    status: "RUNNING",
    created_at: "t-0",
  },
  {
    task_id: "t-10",
    project_id: "p-1",
    title: "queued ten",
    status: "QUEUED",
    created_at: "t-0",
  },
  {
    task_id: "t-11",
    project_id: "p-1",
    title: "done eleven",
    status: "RETURNED",
    created_at: "t-0",
  },
];

const LEDGER = [
  { package_id: "pkg-1", agents: 2, peak_concurrency: 2, wall_time_s: 60 },
  { package_id: "pkg-2", agents: 1, peak_concurrency: 1, wall_time_s: 30 },
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

function stubServed(): void {
  vi.stubGlobal("fetch", async (input: unknown) => {
    const url = String(input);
    if (url === "/api/v1/projects") {
      return jsonBody({ projects: [PROJECT] });
    }
    if (url === "/api/v1/agents/live") {
      return jsonBody({ agents: LIVE_ROWS });
    }
    if (url === "/api/v1/tasks?project_id=p-1") {
      return jsonBody({ tasks: TASKS });
    }
    if (url === "/api/v1/runs/ledger?project_id=p-1") {
      return jsonBody({ rows: LEDGER });
    }
    if (url === "/api/v1/reports/next-package-nudge?package_id=pkg-2") {
      return jsonBody({
        package_id: "pkg-2",
        load: LEDGER[1],
        nudge: "next-up",
        auto_push: false,
      });
    }
    if (url === "/api/v1/budget?project_id=p-1") {
      return jsonBody({ project_id: "p-1", budget: BUDGET });
    }
    if (url === "/api/v1/watcher/status?project_id=p-1") {
      return jsonBody({
        project_id: "p-1",
        integrity_ok: true,
        journal_head: "jh-1",
        generated_at: "t-0",
        last_action:
          "rule-tamper BLOCK model=fx-local-1 action=scripts/tamper_check.py",
        last_check_at: "2026-02-11T06:42:44Z",
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
        service_ids: ["svc-a", "svc-b"],
        paused: false,
        generated_at: "t-0",
      });
    }
    return jsonBody({ code: "FXLAYOUT_UNEXPECTED_API" }, 404);
  });
}

function stubEmpty(): void {
  vi.stubGlobal("fetch", async (input: unknown) => {
    const url = String(input);
    if (url === "/api/v1/projects") {
      return jsonBody({ projects: [] });
    }
    if (url === "/api/v1/agents/live") {
      return jsonBody({ agents: [] });
    }
    return jsonBody({ code: "FXLAYOUT_UNEXPECTED_API" }, 404);
  });
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem("agentsi.firstrun.done", "true");
  setLocale("en");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

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

const NAV_IDS = [
  "menu-new-task",
  "menu-projects",
  "menu-results",
  "menu-settings",
];

const METRIC_IDS = [
  "fx-tokens",
  "fx-tests",
  "fx-budget",
  "fx-providers",
  "fx-localai",
  "fx-apps",
];

describe("fxlayout shell over the real app", () => {
  it("holds exactly four nav entries in English", async () => {
    stubServed();
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    const sidebar = screen.getByTestId("sidebar");
    const anchors = Array.from(sidebar.querySelectorAll("a"));
    expect(
      anchors.map((anchor) => anchor.getAttribute("data-testid")).sort(),
    ).toEqual([...NAV_IDS].sort());
    expect(screen.getByTestId("menu-new-task").textContent).toBe(
      t("tasks.creator.title"),
    );
    await waitFor(() => {
      expect(screen.queryByTestId("menu-results-hint")).toBeNull();
    });
  });

  it("renders the same four nav entries in Ukrainian with differing labels", async () => {
    stubServed();
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    const english = NAV_IDS.map(
      (id) => screen.getByTestId(id).textContent ?? "",
    );
    cleanup();
    const locale: SupportedLocale = "uk";
    setLocale(locale);
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    const sidebar = screen.getByTestId("sidebar");
    const anchors = Array.from(sidebar.querySelectorAll("a"));
    expect(
      anchors.map((anchor) => anchor.getAttribute("data-testid")).sort(),
    ).toEqual([...NAV_IDS].sort());
    const ukrainian = NAV_IDS.map(
      (id) => screen.getByTestId(id).textContent ?? "",
    );
    expect(ukrainian.every((label) => label.length > 0)).toBe(true);
    expect(ukrainian).not.toEqual(english);
    expect(screen.getByTestId("menu-new-task").textContent).toBe(
      t("tasks.creator.title"),
    );
  });

  it("renders the five live cards from served route answers", async () => {
    stubServed();
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();

    const team = await screen.findByTestId("inspector-card-team");
    expect(team.textContent).toContain("agent-1");
    expect(team.textContent).toContain(t("providers.role.manager"));
    expect(team.textContent).toContain("m-1");
    expect(screen.getByTestId("team-warnings").textContent).toContain("boom-1");
    expect(screen.getByTestId("team-row-agent-1").textContent).toContain(
      "agent-2",
    );
    expect(screen.getByTestId("team-open-agents").getAttribute("href")).toBe(
      "/agents/live",
    );

    // FXTABS T9: with no window served the rail shows just the used
    // count, never "Unknown / Unknown" and no percent off thin air.
    expect(screen.queryByTestId("ctx-percent")).toBeNull();
    const ctxWindow = screen.getByTestId("ctx-window");
    expect(ctxWindow.textContent).toContain(t("shell.common.unknown"));
    expect(ctxWindow.textContent).not.toContain("/");
    expect(screen.getByTestId("ctx-source").textContent).toContain(
      t("shell.cards.context.sourceLive"),
    );
    const inputBar = screen.getByTestId("ctx-bar-input");
    expect(inputBar.style.width).toBe("40%");
    expect(screen.getByTestId("ctx-legend").textContent).toContain(
      formatNumber(400),
    );

    expect(await screen.findByTestId("result-row-pkg-2")).toBeTruthy();
    expect(screen.getByTestId("result-nudge").textContent).toContain("next-up");
    expect(screen.getByTestId("result-open-pkg-2").getAttribute("href")).toBe(
      "/projects/p-1/reports",
    );

    expect(await screen.findByTestId("bg-row-t-9")).toBeTruthy();
    expect(screen.getByTestId("bg-row-t-9").textContent).toContain(
      t("tasks.status.running"),
    );
    expect(screen.getByTestId("bg-row-t-10").textContent).toContain(
      t("tasks.status.queued"),
    );
    expect(screen.queryByTestId("bg-row-t-11")).toBeNull();

    expect(await screen.findByTestId("watcher-state")).toBeTruthy();
    expect(screen.getByTestId("watcher-state").textContent).toContain(
      t("shell.cards.watcher.ok"),
    );
    expect(screen.getByTestId("watcher-model").textContent).toContain(
      // FXLOOK D5: with no answering model the rail reads plain
      // "not used yet", never UNAVAILABLE.
      t("watcher.tab.notUsedYet"),
    );
    const action = screen.getByTestId("watcher-action");
    expect(action.textContent).toContain(
      t("watcher.tab.actionBlocked"),
    );
    expect(action.textContent).not.toContain("e-1");
    expect(action.getAttribute("title")).toBe("e-1");
    expect(screen.getByTestId("watcher-open").getAttribute("href")).toBe(
      "/watcher",
    );
  });

  it("keeps six metric cards collapsed with persisted toggles", async () => {
    stubServed();
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    for (const card of METRIC_IDS) {
      expect(await screen.findByTestId(`kit-metric-${card}`)).toBeTruthy();
    }
    for (const card of METRIC_IDS) {
      const metric = screen.getByTestId(`kit-metric-${card}`);
      expect(metric.querySelector('[data-testid="kit-expanded-bar"]')).toBeNull();
    }
    expect(
      screen.getByTestId("kit-metric-fx-tokens").textContent,
    ).toContain(formatNumber(1000));

    fireEvent.click(screen.getByTestId("kit-toggle-fx-tokens"));
    expect(
      (await screen.findByTestId("kit-metric-fx-tokens")).querySelector(
        '[data-testid="kit-expanded-bar"]',
      ),
    ).toBeTruthy();
    expect(
      screen
        .getByTestId("kit-metric-fx-tokens")
        .querySelector('[data-testid="kit-expanded-legend"]')?.textContent,
    ).toContain(formatNumber(400));
    await waitFor(() => {
      expect(window.localStorage.getItem("agent-si.collapsed.fx-tokens")).toBe(
        "false",
      );
    });

    cleanup();
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    const revived = await screen.findByTestId("kit-metric-fx-tokens");
    await waitFor(() => {
      expect(
        revived.querySelector('[data-testid="kit-expanded-bar"]'),
      ).toBeTruthy();
    });
    expect(
      screen
        .getByTestId("kit-metric-fx-tests")
        .querySelector('[data-testid="kit-expanded-bar"]'),
    ).toBeNull();
  });

  it("shows empty lines and UNKNOWN with no records, never invented numbers", async () => {
    stubEmpty();
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    expect(await screen.findByTestId("inspector-card-team")).toBeTruthy();
    expect(screen.getByTestId("team-empty").textContent).toBe(
      t("agents.live.empty"),
    );
    expect(screen.getByTestId("results-empty").textContent).toBe(
      t("empty.generic"),
    );
    expect(screen.getByTestId("background-empty").textContent).toBe(
      t("empty.generic"),
    );
    expect(screen.getByTestId("watcher-empty").textContent).toBe(
      t("empty.generic"),
    );
    expect(
      screen.getByTestId("kit-metric-fx-budget").textContent,
    ).toContain(t("shell.common.unknown"));
    expect(screen.queryByTestId("watcher-state")).toBeNull();
    expect(screen.getByTestId("menu-results-hint")).toBeTruthy();
  });
});
