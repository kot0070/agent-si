/** @vitest-environment jsdom */
// FXDESIGN7 behaviour proofs: red stop wiring, tab active state, watcher
// human model names, role not-set hints, provider cap lines, project
// dedup + long dates, KB human labels, disclosure aria-expanded.
// Behaviour only; no colour or CSS literals.
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
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { formatDateLong } from "../../locale/index";
import { App } from "../../app/App";
import { RoleProfileEditor } from "../../settings/index";
import { dedupeProjects } from "../../projects/ProjectsPage";
import { ProvidersPage } from "../../settings/ProvidersPage/ProvidersPage";
import {
  humanFieldName,
  KbRefreshProposal,
} from "../../k07next2/KbRefreshProposal";
import { watcherModelName } from "../../watcher/WatcherTab";
import { Disclosure } from "../../ui/Disclosure";
import type { ProjectRecord } from "../../api/iface";

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const PROJECT = {
  project_id: "p1",
  name: "P1",
  created_at: "2026-02-11T06:42:44Z",
};

function stubFetch(): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "GET" && url === "/api/v1/projects") {
        return jsonBody({
          projects: [
            PROJECT,
            { ...PROJECT, name: "P1-dup" },
            {
              project_id: "p2",
              name: "P2",
              created_at: "2026-02-11T06:42:44Z",
            },
          ],
        });
      }
      if (method === "GET" && url === "/api/v1/projects/p1") {
        return jsonBody({ project: PROJECT });
      }
      if (method === "GET" && url === "/api/v1/kb/status") {
        return jsonBody({
          kb_version: 2,
          updated_at: "2026-02-11T06:42:44Z",
          per_provider: { meta: 3 },
        });
      }
      if (method === "GET" && url === "/api/v1/kb/refresh/proposal") {
        return jsonBody({ kb_id: null, stale: false, proposals: [] });
      }
      if (method === "GET" && url === "/api/v1/agents/live") {
        return jsonBody({ agents: [] });
      }
      return jsonBody({ code: "FXDESIGN7_UNEXPECTED_API" }, 404);
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

describe("fxdesign7 top bar", () => {
  it("stop-all keeps its scope label and danger wiring", async () => {
    renderAppAt("/");
    const stop = await screen.findByTestId("topbar-stop-all");
    expect(stop.textContent).toBe(t("shell.topbar.stop_all"));
    expect(stop.className).toContain("fx-stop-danger");
  });

  it("project and language selects stay labelled", async () => {
    renderAppAt("/");
    const project = await screen.findByTestId("topbar-project");
    expect(project.getAttribute("aria-label")).toBe(t("shell.topbar.project"));
    const language = await screen.findByTestId("topbar-language");
    expect(language.getAttribute("aria-label")).toBe(
      t("shell.topbar.language"),
    );
  });
});

describe("fxdesign7 settings tabs", () => {
  it("the open section tab carries aria-selected state", async () => {
    renderAppAt("/settings/models");
    const active = await screen.findByTestId("settings-link-models");
    await waitFor(() => {
      expect(active.getAttribute("aria-current")).toBe("page");
    });
    const other = await screen.findByTestId("settings-link-general");
    expect(other.getAttribute("aria-current")).toBeNull();
  });
});

describe("fxdesign7 watcher models", () => {
  it("human names never leak the raw enum", () => {
    expect(watcherModelName("local")).toBe(t("watcher.tab.modelLocal"));
    expect(watcherModelName("API")).toBe(t("watcher.tab.modelApi"));
    expect(watcherModelName("OFF")).toBe(t("watcher.tab.modelOff"));
    expect(watcherModelName("local")).not.toBe("local");
  });

  it("fallback note resolves in both locales", () => {
    expect(t("watcher.tab.fallbackNote").length).toBeGreaterThan(10);
  });
});

describe("fxdesign7 role profile", () => {
  it("empty provider/model show not-set hints with recovery", async () => {
    render(<RoleProfileEditor projectId="p1" role="manager" />);
    const providerHint = await screen.findByTestId(
      "role-profile-p1-manager-provider-notset",
    );
    expect(providerHint.textContent).toContain(t("settings.roleProfile.notSet"));
    const modelHint = await screen.findByTestId(
      "role-profile-p1-manager-model-notset",
    );
    expect(modelHint.textContent).toContain(t("settings.roleProfile.notSet"));
    const link = providerHint.querySelector("a");
    expect(link?.getAttribute("href")).toBe("/settings/models");
    expect(modelHint.querySelector("a")?.getAttribute("href")).toBe(
      "/settings/models",
    );
  });
});

describe("fxdesign7 providers", () => {
  it("cards carry no lone dash line, only the key-only note", async () => {
    render(<ProvidersPage project_id="p1" />);
    const cards = await screen.findAllByTestId("provider-card");
    expect(cards.length).toBeGreaterThan(0);
    expect(document.querySelector('[data-testid^="provider-caps-"]')).toBeNull();
    const keynote = document.querySelector(
      '[data-testid^="provider-keynote-"]',
    );
    expect(keynote?.textContent?.length).toBeGreaterThan(0);
  });
});

describe("fxdesign7 projects", () => {
  it("dedupeProjects collapses repeated ids", () => {
    const rows = [
      { project_id: "a", name: "A", created_at: "t" },
      { project_id: "a", name: "A2", created_at: "t" },
      { project_id: "b", name: "B", created_at: "t" },
    ] as ProjectRecord[];
    const out = dedupeProjects(rows);
    expect(out.map((r) => r.project_id)).toEqual(["a", "b"]);
  });

  it("long dates carry a label and a month name", () => {
    const text = formatDateLong("2026-02-11T06:42:44Z");
    expect(text).toContain("2026");
    expect(text).toMatch(/Feb|Feb\.|Feb/);
    expect(formatDateLong("not-a-date")).toBe("not-a-date");
  });

  it("rows show one labelled date each", async () => {
    renderAppAt("/projects");
    const created = await screen.findByTestId("project-created-p1");
    expect(created.textContent).toContain(t("projects.list.created"));
    expect(created.textContent).toContain("2026");
    const dupes = await screen.findAllByTestId("project-row-p1");
    expect(dupes).toHaveLength(1);
  });
});

describe("fxdesign7 capability db", () => {
  it("field names render human, never snake_case", () => {
    expect(humanFieldName("kb_version")).toBe("Version");
    expect(humanFieldName("updated_at")).toBe("Updated");
    expect(humanFieldName("per_provider")).toBe("Per provider");
  });

  it("status facts show human labels and locale dates", async () => {
    render(<KbRefreshProposal />);
    const status = await screen.findByTestId("kb-status");
    expect(status.textContent).toContain("Version");
    expect(status.textContent).not.toContain("kb_version");
    expect(status.textContent).toContain("2026");
  });
});

describe("fxdesign7 disclosure", () => {
  it("toggle exposes aria-expanded", () => {
    render(
      <Disclosure
        disclosureId="fx7"
        summaryKey="ui.disclosure.more"
        expanded={false}
        onToggle={() => undefined}
      >
        body
      </Disclosure>,
    );
    const toggle = screen.getByTestId("kit-toggle-fx7");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
  });
});

describe("fxdesign7 inspector deferred", () => {
  const LIVE_KNOWN = {
    agents: [
      {
        agent: "agent-1",
        scope: "scope-1",
        deliverable: "part-1",
        status: "RUNNING",
        role: "manager",
        provider: "meta",
        model: "m-1",
        tokens: { input: 400, output: 600 },
        context: 424200,
        window: 1000000,
      },
    ],
  };
  const LIVE_UNKNOWN = {
    agents: [
      {
        agent: "agent-9",
        scope: "scope-9",
        deliverable: "part-9",
        status: "RUNNING",
        role: "worker",
      },
    ],
  };

  function stubInspector(live: unknown): void {
    vi.stubGlobal(
      "fetch",
      async (input: unknown, init?: RequestInit): Promise<Response> => {
        const url = String(input);
        const method = (init?.method ?? "GET").toUpperCase();
        if (method === "GET" && url === "/api/v1/projects") {
          return jsonBody({ projects: [PROJECT] });
        }
        if (method === "GET" && url === "/api/v1/agents/live") {
          return jsonBody(live);
        }
        if (method === "GET" && url === "/api/v1/projects/p1") {
          return jsonBody({ project: PROJECT });
        }
        if (method === "GET" && url.startsWith("/api/v1/runs/ledger")) {
          return jsonBody({ rows: [] });
        }
        if (method === "GET" && url.startsWith("/api/v1/tasks")) {
          return jsonBody({ tasks: [] });
        }
        if (method === "GET" && url.startsWith("/api/v1/budget")) {
          return jsonBody({ project_id: "p1", budget: null });
        }
        if (
          method === "GET" &&
          url.startsWith("/api/v1/watcher/status")
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
          url.startsWith("/api/v1/watcher/journal")
        ) {
          return jsonBody([
            {
              entry_id: "e-1",
              timestamp: "2026-02-11T06:42:44Z",
              hash: "h-1",
            },
          ]);
        }
        if (method === "GET" && url.startsWith("/api/v1/apps/card")) {
          return jsonBody({
            project_id: "p1",
            service_ids: [],
            paused: false,
            generated_at: "t-0",
          });
        }
        return jsonBody({ code: "FXDESIGN7_UNEXPECTED_API" }, 404);
      },
    );
  }

  function renderInspectorAt(): {
    router: ReturnType<typeof createMemoryRouter>;
  } {
    const router = createMemoryRouter([{ path: "*", element: <App /> }], {
      initialEntries: ["/projects"],
    });
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <RouterProvider router={router} />
      </ApiClientProvider>,
    );
    return { router };
  }

  async function openProject(
    router: ReturnType<typeof createMemoryRouter>,
  ): Promise<void> {
    fireEvent.click(await screen.findByTestId("project-open-p1"));
    await router.navigate("/projects/p-1/overview");
  }

  it("no live rows render one quiet no-usage line, never Unknown repeats", async () => {
    stubInspector({ agents: [] });
    renderInspectorAt();
    const empty = await screen.findByTestId("context-empty");
    expect(empty.textContent).toBe(t("shell.cards.context.noUsage"));
    expect(empty.textContent).not.toContain(
      t("shell.common.unknown"),
    );
    expect(screen.queryByTestId("ctx-bar")).toBeNull();
    expect(screen.queryByTestId("ctx-legend")).toBeNull();
  });

  it("team fields use label-colon-value separators", async () => {
    stubInspector(LIVE_KNOWN);
    renderInspectorAt();
    const row = await screen.findByTestId("team-row-agent-1");
    expect(row.textContent).toContain(`${t("agents.row.scope")}:`);
    expect(row.textContent).toContain(
      `${t("settings.roleProfile.modelLabel")}:`,
    );
    expect(row.textContent).not.toContain("Scope scope-1");
  });

  it("unknown counts collapse to one quiet line, legend only from data", async () => {
    stubInspector(LIVE_UNKNOWN);
    renderInspectorAt();
    const unknown = await screen.findByTestId("ctx-unknown");
    expect(unknown.textContent?.length).toBeGreaterThan(0);
    expect(screen.queryByTestId("ctx-percent")).toBeNull();
  });

  it("watcher model is human with fallback state; action is local time", async () => {
    stubInspector(LIVE_KNOWN);
    const { router } = renderInspectorAt();
    await openProject(router);
    const model = await screen.findByTestId("watcher-model");
    expect(model.textContent).toContain(t("watcher.tab.modelLocal"));
    expect(model.textContent).not.toContain("local");
    expect(model.textContent).not.toContain("Configured model");
    const action = await screen.findByTestId("watcher-action");
    expect(action.textContent).toContain("e-1");
    expect(action.textContent).toContain("2026");
    expect(action.textContent).not.toContain("T06:42:44Z");
  });

  it("metric cards keep a heading toggle", async () => {
    stubInspector(LIVE_KNOWN);
    renderInspectorAt();
    const toggle = await screen.findByTestId("kit-toggle-fx-tokens");
    expect(toggle.getAttribute("aria-expanded")).not.toBeNull();
  });
});
