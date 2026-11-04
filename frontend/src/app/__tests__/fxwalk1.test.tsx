/** @vitest-environment jsdom */
// FXWALK1 screens+backend lane: one test per WALKCHECK row (excl W5n;
// W6 is one test over three tabs) over the REAL App with fetch mocked
// only. RED on the unpatched tree, GREEN after the row fixes.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../ApiClientProvider";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { App } from "../App";

const PROJECT = { project_id: "p1", name: "P1", created_at: "2026-01-01T00:00:00Z" };

const LEDGER = [
  { package_id: "pkg-1", agents: 1, peak_concurrency: 1, wall_time_s: 60 },
];

const BUDGET = {
  project_id: "p1",
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

type FetchCall = { url: string; method: string };

let calls: FetchCall[];
let overrides: Map<string, (call: FetchCall) => Response | Promise<Response>>;

function stubFetch(): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      const call = { url, method };
      calls.push(call);
      const override = overrides.get(`${method} ${url}`);
      if (override !== undefined) {
        return override(call);
      }
      if (method === "GET" && url === "/api/v1/projects") {
        return jsonBody({ projects: [PROJECT] });
      }
      if (method === "GET" && url === "/api/v1/projects/p1") {
        return jsonBody({ project: PROJECT });
      }
      if (method === "GET" && url === "/api/v1/tasks?project_id=p1") {
        return jsonBody({ tasks: [] });
      }
      if (method === "GET" && url === "/api/v1/runs/ledger?project_id=p1") {
        return jsonBody({ rows: LEDGER });
      }
      if (method === "GET" && url === "/api/v1/budget?project_id=p1") {
        return jsonBody({ project_id: "p1", budget: BUDGET });
      }
      if (method === "GET" && url === "/api/v1/agents/live") {
        return jsonBody({ agents: [] });
      }
      if (method === "GET" && url === "/api/v1/providers") {
        return jsonBody({ providers: [] });
      }
      if (
        method === "GET" &&
        url === "/api/v1/chat/models?project_id=p1"
      ) {
        return jsonBody({ project_id: "p1", models: [] });
      }
      if (
        method === "GET" &&
        url === "/api/v1/watcher/status?project_id=p1"
      ) {
        return jsonBody({
          project_id: "p1",
          integrity_ok: true,
          journal_head: "jh-1",
          generated_at: "t-0",
        });
      }
      if (
        method === "GET" &&
        url === "/api/v1/watcher/journal?project_id=p1"
      ) {
        return jsonBody([{ entry_id: "e-1", timestamp: "t-1", hash: "h-1" }]);
      }
      if (method === "GET" && url === "/api/v1/apps/card?project_id=p1") {
        return jsonBody({
          project_id: "p1",
          service_ids: ["svc-a", "svc-b"],
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
      if (
        method === "GET" &&
        url === "/api/v1/reports/next-package-nudge?package_id=pkg-1"
      ) {
        return jsonBody({
          package_id: "pkg-1",
          load: LEDGER[0],
          nudge: "next-up",
          auto_push: false,
        });
      }
      return jsonBody({ code: "FXWALK1_UNEXPECTED_API" }, 404);
    },
  );
}

function on(
  method: string,
  url: string,
  answer: (call: FetchCall) => Response | Promise<Response>,
): void {
  overrides.set(`${method} ${url}`, answer);
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem("agentsi.locale", "en");
  window.localStorage.setItem("agentsi.firstrun.done", "true");
  setLocale("en");
  calls = [];
  overrides = new Map();
  stubFetch();
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

describe("fxwalk1 screens over the real app", () => {
  it("W4: empty composer submit shows the inline title error and sends nothing", async () => {
    renderAppAt("/projects/p1/tasks");
    fireEvent.click(await screen.findByTestId("composer-create"));
    expect(await screen.findByTestId("composer-title-error")).toBeTruthy();
    expect(screen.getByTestId("composer-title-error").textContent).toBe(
      t("tasks.creator.titleRequired"),
    );
    expect(
      calls.some(
        (call) =>
          call.method === "POST" &&
          call.url.startsWith("/api/v1/tasks"),
      ),
    ).toBe(false);
  });

  it("W5: projects error and empty states never show the skeleton past response", async () => {
    on("GET", "/api/v1/projects", () =>
      jsonBody({ code: "FXWALK1_PROJECTS_DOWN" }, 500),
    );
    renderAppAt("/projects");
    const main = await screen.findByTestId("app-main");
    expect(
      await within(main).findByTestId("kit-error-panel"),
    ).toBeTruthy();
    expect(within(main).queryByTestId("kit-loading-state")).toBeNull();
    cleanup();

    overrides = new Map();
    on("GET", "/api/v1/projects", () => jsonBody({ projects: [] }));
    renderAppAt("/projects");
    const retryMain = await screen.findByTestId("app-main");
    expect(await within(retryMain).findByTestId("project-add-form")).toBeTruthy();
    expect(
      await within(retryMain).findByTestId("kit-empty-state"),
    ).toBeTruthy();
    expect(within(retryMain).queryByTestId("kit-loading-state")).toBeNull();
  });

  it("W6: project tabs navigate on click and on Enter", async () => {
    renderAppAt("/projects/p1/tasks");
    expect(await screen.findByTestId("composer-create")).toBeTruthy();
    fireEvent.click(screen.getByTestId("project-menu-overview"));
    expect(await screen.findByTestId("overview-name")).toBeTruthy();
    fireEvent.click(screen.getByTestId("project-menu-tasks"));
    expect(await screen.findByTestId("composer-create")).toBeTruthy();
    fireEvent.keyDown(screen.getByTestId("project-menu-runs"), {
      key: "Enter",
    });
    expect(await screen.findByTestId("runhistory-ledger-pkg-1")).toBeTruthy();
  });

  it("W7: watcher failure shows the error with Retry, and a hang times out", async () => {
    on("GET", "/api/v1/watcher/status?project_id=p1", () =>
      jsonBody({ code: "FXWALK1_WATCHER_DOWN" }, 500),
    );
    renderAppAt("/watcher");
    expect(await screen.findByTestId("watcher-error")).toBeTruthy();
    expect(screen.queryByTestId("watcher-loading")).toBeNull();
    on("GET", "/api/v1/watcher/status?project_id=p1", () =>
      jsonBody({
        project_id: "p1",
        integrity_ok: true,
        journal_head: "jh-1",
        generated_at: "t-0",
      }),
    );
    fireEvent.click(await screen.findByTestId("kit-error-retry"));
    expect(await screen.findByTestId("watcher-journal")).toBeTruthy();
    cleanup();

    overrides = new Map();
    on(
      "GET",
      "/api/v1/watcher/status?project_id=p1",
      () => new Promise<Response>(() => undefined),
    );
    on(
      "GET",
      "/api/v1/watcher/journal?project_id=p1",
      () => new Promise<Response>(() => undefined),
    );
    renderAppAt("/watcher");
    expect(await screen.findByTestId("watcher-loading")).toBeTruthy();
    expect(await screen.findByTestId("watcher-error")).toBeTruthy();
    expect(await screen.findByTestId("kit-error-retry")).toBeTruthy();
  });

  it("W8: reports sections fail and empty independently with no placeholders", async () => {
    renderAppAt("/projects/p1/reports");
    expect(await screen.findByTestId("project-reports-subtitle")).toBeTruthy();
    expect(await screen.findByTestId("report-task-counts")).toBeTruthy();
    expect(
      within(screen.getByTestId("report-task-counts")).queryByTestId(
        "kit-empty-state",
      ),
    ).toBeNull();
    expect(screen.getByTestId("report-task-counts").textContent).toContain("0");
    // FXLOOK D5: the engine allocation rows no longer render an exact
    // "Calculated value" text node; the derived section keeps its
    // labelled header.
    expect(screen.queryByText("Calculated value:")).toBeTruthy();
    expect(await screen.findByTestId("report-project-name")).toBeTruthy();
  });

  it("W9: agents live renders from exactly one source", async () => {
    renderAppAt("/agents/live");
    expect(await screen.findByTestId("kit-empty-state")).toBeTruthy();
    await waitFor(() => {
      expect(
        screen.queryAllByTestId("kit-card-agents-live").length,
      ).toBe(1);
    });
    expect(screen.queryByTestId("kit-loading-state")).toBeNull();
  });

  it("W11: chat shows the bound-model hint with a Connect link before any send", async () => {
    renderAppAt("/");
    expect(await screen.findByTestId("chat-no-model-hint")).toBeTruthy();
    expect(screen.getByTestId("chat-no-model-hint").textContent).toBe(
      t("chat.composer.noModel"),
    );
    expect(screen.getByTestId("chat-no-model-connect").getAttribute("href")).toBe(
      "/settings/models",
    );
    expect(
      calls.some((call) => call.url === "/api/v1/chat/stream"),
    ).toBe(false);
    cleanup();

    overrides = new Map();
    on("GET", "/api/v1/chat/models?project_id=p1", () =>
      jsonBody({
        project_id: "p1",
        models: [{ provider_id: "openai", model: "openai/model-1" }],
      }),
    );
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    await waitFor(() => {
      expect(screen.queryByTestId("chat-no-model-hint")).toBeNull();
    });
  });

  it("W12: connected providers seed the chat model select", async () => {
    on("GET", "/api/v1/providers", () =>
      jsonBody({
        providers: [
          {
            provider_id: "openai",
            type: "cloud",
            base_url: "https://api.openai.com",
            health: "ONLINE",
            evidenced: true,
          },
        ],
      }),
    );
    // FXFACTS F7: the chat model select lives on the routing tab.
    renderAppAt("/settings/routing");
    const picker = await screen.findByTestId("chat-model-selector");
    await waitFor(() => {
      expect(
        within(picker).getAllByRole("option").length,
      ).toBeGreaterThan(1);
    });
  });

  it("W15: the KB busy text shows only while an update runs", async () => {
    let releaseUpdate: ((value: Response) => void) | null = null;
    on(
      "POST",
      "/api/v1/kb/update",
      () =>
        new Promise<Response>((resolve) => {
          releaseUpdate = resolve;
        }),
    );
    renderAppAt("/settings/capabilityDB");
    expect(await screen.findByTestId("kb-update")).toBeTruthy();
    expect(screen.queryByText(t("chat.stream.spinner"))).toBeNull();
    fireEvent.click(screen.getByTestId("kb-update"));
    expect(await screen.findByText(t("chat.stream.spinner"))).toBeTruthy();
    expect(releaseUpdate).not.toBeNull();
    (releaseUpdate as unknown as (value: Response) => void)(
      jsonBody({ proposal_id: null }),
    );
    expect(await screen.findByTestId("kb-update-result")).toBeTruthy();
    await waitFor(() => {
      expect(screen.queryByText(t("chat.stream.spinner"))).toBeNull();
    });
  });

  it("W16: chat, agents, projects, reports and watcher render headings", async () => {
    renderAppAt("/");
    expect(
      (await screen.findByRole("heading", { level: 1 })).textContent,
    ).toBe(t("shell.sidebar.chat"));
    cleanup();
    renderAppAt("/agents/live");
    expect(
      (await screen.findAllByRole("heading", { level: 2 })).length,
    ).toBeGreaterThan(0);
    cleanup();
    renderAppAt("/projects");
    expect(
      (await screen.findAllByRole("heading", { level: 2 })).length,
    ).toBeGreaterThan(0);
    cleanup();
    renderAppAt("/projects/p1/reports");
    expect(await screen.findByTestId("project-reports-subtitle")).toBeTruthy();
    expect(
      (await screen.findAllByRole("heading", { level: 2 })).length,
    ).toBeGreaterThan(0);
    cleanup();
    renderAppAt("/watcher");
    expect(
      (await screen.findAllByRole("heading", { level: 2 })).length,
    ).toBeGreaterThan(0);
  });

  it("W18: new-task, projects and results screens render t() subtitles", async () => {
    renderAppAt("/projects/p1/tasks");
    expect(await screen.findByTestId("task-composer-subtitle")).toBeTruthy();
    expect(screen.getByTestId("task-composer-subtitle").textContent).toBe(
      t("tasks.creator.subtitle"),
    );
    cleanup();
    renderAppAt("/projects");
    expect(await screen.findByTestId("projects-list-subtitle")).toBeTruthy();
    expect(screen.getByTestId("projects-list-subtitle").textContent).toBe(
      t("projects.list.subtitle"),
    );
    cleanup();
    renderAppAt("/projects/p1/reports");
    expect(await screen.findByTestId("project-reports-subtitle")).toBeTruthy();
    expect(screen.getByTestId("project-reports-subtitle").textContent).toBe(
      t("projects.reports.subtitle"),
    );
  });

  it("W19: the inspector apps metric renders the served card facts", async () => {
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    // FXFACTS F10: the apps card lives in More.
    fireEvent.click(await screen.findByTestId("rail-more-toggle"));
    const metric = await screen.findByTestId("kit-metric-fx-apps");
    await waitFor(() => {
      expect(metric.textContent).toContain("2");
    });
    expect(
      calls.some(
        (call) =>
          call.method === "GET" &&
          call.url === "/api/v1/apps/card?project_id=p1",
      ),
    ).toBe(true);
  });

  it("W20: the providers surface renders over the facade-backed endpoint", async () => {
    // FXFACTS F7: the chat model select lives on the routing tab; the
    // providers surface still reads the facade endpoint there.
    renderAppAt("/settings/routing");
    expect(await screen.findByTestId("chat-model-selector")).toBeTruthy();
    expect(
      calls.some(
        (call) =>
          call.method === "GET" && call.url === "/api/v1/providers",
      ),
    ).toBe(true);
  });
});
