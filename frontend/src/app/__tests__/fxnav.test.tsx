/** @vitest-environment jsdom */
// FXNAV RED-first: first-run rail clicks release the gate for the session
// (W03 dead click), kit purpose captions on the rail, need-it-now card on
// the Settings Project page, one purpose sentence per project tab.
// Real App + real pages; the ONLY fake is the fetch boundary below.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import {
  resetLocaleForTests,
  setLocale,
} from "../../locale/index";
import en from "../../locale/en.json";
import uk from "../../locale/uk.json";
import { App } from "../../app/App";
import { ProjectView } from "../../projects/ProjectView";
import type { ProjectViewName } from "../../projects/projectsApi";
import { PROJECT_VIEWS } from "../../projects/projectsApi";
import { resetFirstRunGateForTests } from "../../app/firstrun/gateRelease";

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function installFetch(): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown) => {
      const url = String(input);
      if (url === "/api/v1/providers") {
        return json({ providers: [] });
      }
      if (url === "/api/v1/projects") {
        return json({ projects: [] });
      }
      if (url === "/api/v1/agents/live") {
        return json({ agents: [] });
      }
      return json({ code: "CONTEXT_MISSING" }, 404);
    },
  );
}

function renderAppAt(route: string): ReturnType<typeof createMemoryRouter> {
  const router = createMemoryRouter([{ path: "*", element: <App /> }], {
    initialEntries: [route],
  });
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
  return router;
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  setLocale("en");
  resetFirstRunGateForTests();
  installFetch();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  resetFirstRunGateForTests();
});

describe("FXNAV W03 first-run rail click releases the gate", () => {
  it("menu-new-task lands on / with the composer; run not done, flow resumable", async () => {
    const router = renderAppAt("/firstrun");
    expect(await screen.findByTestId("firstrun")).toBeTruthy();
    fireEvent.click(screen.getByTestId("menu-new-task"));
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/");
    expect(screen.getByTestId("chat-send").textContent).toBe("Send");
    expect(
      window.localStorage.getItem("agentsi.firstrun.done"),
    ).toBeNull();
    router.navigate("/firstrun");
    expect(await screen.findByTestId("firstrun")).toBeTruthy();
  });

  it("menu-projects lands on the projects page in the same session", async () => {
    const router = renderAppAt("/firstrun");
    expect(await screen.findByTestId("firstrun")).toBeTruthy();
    fireEvent.click(screen.getByTestId("menu-projects"));
    expect(await screen.findByTestId("projects-list-subtitle")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/projects");
    expect(
      window.localStorage.getItem("agentsi.firstrun.done"),
    ).toBeNull();
  });
});

describe("FXNAV P16-purpose rail captions", () => {
  it("carries all four kit purpose notes with the one-sentence copy", async () => {
    renderAppAt("/");
    const rows: Array<[string, string]> = [
      ["kit-tab-purpose-new-task", en.tasks.creator.subtitle],
      ["kit-tab-purpose-projects", en.projects.list.subtitle],
      ["kit-tab-purpose-results", en.projects.reports.subtitle],
      ["kit-tab-purpose-settings", en.settings.index.subtitle],
    ];
    for (const [id, purpose] of rows) {
      const note = await screen.findByTestId(id);
      expect(note.textContent).toBe(purpose);
    }
  });

  it("renders the Ukrainian captions in uk locale", async () => {
    setLocale("uk");
    renderAppAt("/");
    expect(await screen.findByTestId("kit-tab-purpose-new-task")).toBeTruthy();
    expect(
      (await screen.findByTestId("kit-tab-purpose-new-task")).textContent,
    ).toBe(uk.tasks.creator.subtitle);
    expect(
      (await screen.findByTestId("kit-tab-purpose-settings")).textContent,
    ).toBe(uk.settings.index.subtitle);
  });
});

describe("FXNAV P16-needitnow project settings card", () => {
  it("shows purpose in the kit project card, need-it-now only on models and routing", async () => {
    renderAppAt("/settings/project");
    const card = await screen.findByTestId("kit-card-needitnow-project");
    expect(card.textContent).toContain(en.settings.project.purpose);
    expect(card.textContent).not.toContain(en.settings.project.needItNow);
  });
});

describe("FXNAV one purpose sentence per project tab", () => {
  function projectClient(): FakeApiClient {
    return new FakeApiClient({
      projects: [
        {
          project_id: "p-9",
          name: "n-9",
          created_at: "2026-01-01T00:00:00.000Z",
        },
      ],
    });
  }

  it("shows a purpose line on every ProjectView panel", async () => {
    const expected: Record<ProjectViewName, string> = {
      overview: en.projectView.purpose.overview,
      tasks: en.projectView.purpose.tasks,
      runs: en.projectView.purpose.runs,
      time: en.projectView.purpose.time,
      "ai-usage": en.projectView.purpose.aiUsage,
      tokens: en.projectView.purpose.tokens,
      cost: en.projectView.purpose.cost,
      "local-ai": en.projectView.purpose.localAi,
      "cloud-ai": en.projectView.purpose.cloudAi,
      models: en.projectView.purpose.models,
      "routing-decisions": en.projectView.purpose.routing,
      audits: en.projectView.purpose.audits,
      errors: en.projectView.purpose.errors,
      reports: en.projectView.purpose.reports,
      tests: en.projectView.purpose.tests,
    };
    expect(PROJECT_VIEWS).toHaveLength(15);
    for (const view of PROJECT_VIEWS) {
      const shown = render(
        <ApiClientProvider client={projectClient()}>
          <ProjectView projectId="p-9" view={view} />
        </ApiClientProvider>,
      );
      const purpose = await screen.findByTestId("tab-purpose");
      expect(purpose.textContent).toBe(expected[view]);
      expect(purpose.textContent?.length).toBeGreaterThan(10);
      shown.unmount();
      cleanup();
    }
  });

  it("chat route carries no strip: head line opens Overview (FXLOOK D8)", async () => {
    // FXLOOK D8 supersedes the chat purpose line: the chat route is a
    // separate surface, so it shows the project head, never tab-purpose.
    vi.stubGlobal(
      "fetch",
      async (input: unknown) => {
        const url = String(input);
        if (url === "/api/v1/projects") {
          return json({
            projects: [
              {
                project_id: "p-9",
                name: "n-9",
                folder_ref: "n-9",
                created_at: "2026-01-01T00:00:00.000Z",
              },
            ],
          });
        }
        if (url === "/api/v1/projects/p-9") {
          return json({
            project: {
              project_id: "p-9",
              name: "n-9",
              folder_ref: "n-9",
              created_at: "2026-01-01T00:00:00.000Z",
            },
          });
        }
        if (url === "/api/v1/agents/live") {
          return json({ agents: [] });
        }
        return json({ code: "CONTEXT_MISSING" }, 404);
      },
    );
    const router = renderAppAt("/projects/p-9/chat");
    const head = await screen.findByTestId("chat-route-head");
    const named = await within(head).findByText("n-9");
    expect(named.getAttribute("data-testid")).toBe("chat-route-project");
    expect(
      screen.getByTestId("project-details-open").textContent,
    ).toBe(en.projects.details.open);
    expect(screen.queryByTestId("tab-purpose")).toBeNull();
    expect(screen.queryByTestId("project-tabs")).toBeNull();
    fireEvent.click(screen.getByTestId("project-details-open"));
    expect(await screen.findByTestId("project-tabs")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/projects/p-9/overview");
  });
});
