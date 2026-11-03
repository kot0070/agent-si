/** @vitest-environment jsdom */
// FXKITUI guided first run + How-it-works diagram + settings need-it-now
// notes + labelled project form. Renders the REAL App; fakes ONLY at the
// network boundary (global fetch). No client or props doubles.
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
import { ApiClientProvider } from "../ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { App } from "../App";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";

interface ProjectRow {
  project_id: string;
  name: string;
  created_at: string;
}

const mockState = {
  projects: [] as ProjectRow[],
  providers: [] as string[],
};

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function installFetch(): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: { method?: string; body?: string }) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      let body: unknown = null;
      try {
        body = init?.body === undefined ? null : JSON.parse(init.body);
      } catch {
        body = null;
      }
      if (url === "/api/v1/projects" && method === "GET") {
        return json({ projects: mockState.projects });
      }
      if (url === "/api/v1/projects" && method === "POST") {
        const payload = body as { name: string; folder_ref: string };
        const row: ProjectRow = {
          project_id: `p-${mockState.projects.length + 1}`,
          name: payload.name,
          created_at: "2026-01-01T00:00:00Z",
        };
        mockState.projects.push(row);
        return json({ project: row });
      }
      const byId = url.match(/^\/api\/v1\/projects\/([^/?]+)$/);
      if (byId !== null && method === "GET") {
        const row = mockState.projects.find(
          (candidate) => candidate.project_id === byId[1],
        );
        if (row === undefined) {
          return json({ code: "CONTEXT_MISSING" }, 404);
        }
        return json({ project: row });
      }
      if (url === "/api/v1/providers" && method === "GET") {
        return json({
          providers: mockState.providers.map((provider_id) => ({
            provider_id,
          })),
        });
      }
      if (url === "/api/v1/providers/keys" && method === "POST") {
        const preset = (body as { preset_id: string }).preset_id;
        return new Response(
          JSON.stringify({ key_ref: { secret_id: preset, provider_id: preset } }),
          { status: 201, headers: { "content-type": "application/json" } },
        );
      }
      // FXR2E two-step check (416ddaa, merged 0661228): read-only preflight.
      if (url === "/api/v1/providers/keys/check" && method === "POST") {
        return json({});
      }
      if (url === "/api/v1/providers/connect" && method === "POST") {
        const preset = (body as { preset_id: string }).preset_id;
        if (!mockState.providers.includes(preset)) {
          mockState.providers.push(preset);
        }
        return json({ provider: { provider_id: preset } });
      }
      if (url.startsWith("/api/v1/tasks") && method === "POST") {
        const payload = body as { title: string; scope: string[] };
        const projectId =
          new URL(url, "http://localhost").searchParams.get("project_id") ??
          "p-1";
        return json({
          task: {
            task_id: "t-1",
            project_id: projectId,
            title: payload.title,
            status: "QUEUED",
            created_at: "2026-01-01T00:00:00Z",
          },
        });
      }
      if (url.startsWith("/api/v1/routing/role") && method === "PUT") {
        const payload = body as {
          project_id: string;
          role: string;
          mode: string;
        };
        return json({
          ok: true,
          profile: {
            role: payload.role,
            project_id: payload.project_id,
            mode: payload.mode,
            provider: null,
            model: null,
          },
        });
      }
      if (url === "/api/v1/agents/live" && method === "GET") {
        return json({ agents: [] });
      }
      return json({ code: "CONTEXT_MISSING" }, 404);
    },
  );
}

function renderApp(route: string): ReturnType<typeof createMemoryRouter> {
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
  window.localStorage.setItem("agentsi.locale", "en");
  setLocale("en");
  mockState.projects = [];
  mockState.providers = [];
  installFetch();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

const CHAIN = [
  "you write one task",
  "Director plans",
  "Managers",
  "agents write files",
  "app runs the checks",
  "fresh auditor",
  "honest result",
];

describe("fxkitui fresh profile opens the guided first run", () => {
  it("fresh answers (no provider, no project) land on /firstrun", async () => {
    const router = renderApp("/");
    expect(await screen.findByText(en.firstrun.title)).toBeTruthy();
    expect(router.state.location.pathname).toBe("/firstrun");
  });

  it("an existing profile with a project never sees the flow", async () => {
    window.localStorage.setItem("agentsi.firstrun.done", "true");
    mockState.projects = [
      { project_id: "p-1", name: "n-1", created_at: "2026-01-01T00:00:00Z" },
    ];
    const router = renderApp("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    expect(screen.queryByText(en.firstrun.title)).toBeNull();
    expect(router.state.location.pathname).toBe("/");
  });

  it("skip is always visible and remembered across remount", async () => {
    const router = renderApp("/");
    expect(await screen.findByText(en.firstrun.title)).toBeTruthy();
    expect(await screen.findByTestId("firstrun-skip")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: en.firstrun.next }));
    const skip = await screen.findByTestId("firstrun-skip");
    expect(skip.textContent).toContain(en.firstrun.skip);
    fireEvent.click(skip);
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/");
    cleanup();
    renderApp("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    expect(screen.queryByText(en.firstrun.title)).toBeNull();
  });

  it("finishing the flow lands in chat and is remembered", async () => {
    const router = renderApp("/");
    expect(await screen.findByText(en.firstrun.title)).toBeTruthy();
    const openaiRow = await screen.findByTestId("firstrun-provider-openai");
    fireEvent.click(
      within(openaiRow).getByRole("button", { name: "Connect OpenAI" }),
    );
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(
      within(dialog).getByLabelText(en.providers.connect.apiKey),
      { target: { value: "fx-fake-key" } },
    );
    // FXR2E two-step (416ddaa, merged 0661228): Check before Save.
    fireEvent.click(
      within(dialog).getByRole("button", { name: en.providers.connect.check }),
    );
    await within(dialog).findByText(en.providers.connect.checked);
    fireEvent.click(
      within(dialog).getByRole("button", { name: en.providers.connect.save }),
    );
    await waitFor(() => {
      expect(
        (screen.getByRole("button", { name: en.firstrun.next }) as HTMLButtonElement)
          .disabled,
      ).toBe(false);
    });
    fireEvent.click(screen.getByRole("button", { name: en.firstrun.next }));
    fireEvent.change(
      screen.getByRole("textbox", { name: en.shell.topbar.project }),
      { target: { value: "Team Alpha" } },
    );
    fireEvent.click(
      screen.getByRole("button", { name: en.settings.roleProfile.title }),
    );
    expect(await screen.findByTestId("firstrun-team-result")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: en.firstrun.next }));
    fireEvent.change(
      screen.getByRole("textbox", { name: en.firstrun.folder.label }),
      { target: { value: "alpha-folder" } },
    );
    fireEvent.click(
      screen.getByRole("button", { name: en.projects.list.create }),
    );
    expect(await screen.findByTestId("firstrun-project-result")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: en.firstrun.next }));
    fireEvent.change(
      screen.getByRole("textbox", { name: en.tasks.creator.title }),
      { target: { value: "My first task" } },
    );
    fireEvent.click(
      screen.getByRole("button", { name: en.tasks.creator.create }),
    );
    expect(await screen.findByTestId("firstrun-task-result")).toBeTruthy();
    fireEvent.click(
      screen.getByRole("button", { name: en.shell.sidebar.chat }),
    );
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/");
  });

  it("the first run links to how-it-works", async () => {
    renderApp("/firstrun");
    expect(await screen.findByText(en.firstrun.title)).toBeTruthy();
    const link = await screen.findByTestId("firstrun-how-it-works");
    expect(link.getAttribute("href")).toBe("/how-it-works");
  });
});

describe("fxkitui how-it-works diagram", () => {
  it("renders an inline SVG with six stage labels carrying the chain", async () => {
    renderApp("/how-it-works");
    const diagram = await screen.findByTestId("how-it-works-diagram");
    expect(diagram.tagName.toLowerCase()).toBe("svg");
    const stages = within(diagram as unknown as HTMLElement).getAllByTestId(
      /how-it-works-stage-/,
    );
    expect(stages).toHaveLength(6);
    const announced = stages
      .map((stage) => stage.getAttribute("aria-label") ?? "")
      .join(" -> ");
    let cursor = -1;
    for (const phrase of CHAIN) {
      const at = announced.indexOf(phrase, cursor + 1);
      expect(at).toBeGreaterThan(cursor);
      cursor = at;
    }
    expect(document.querySelectorAll("canvas").length).toBe(0);
  });

  it("explains runs, code tests and local tests in plain sentences", async () => {
    renderApp("/how-it-works");
    const concepts = await screen.findByTestId("how-it-works-concepts");
    expect(concepts.textContent).toContain(en.howItWorks.runs.body);
    expect(concepts.textContent).toContain(en.howItWorks.codeTests.body);
    expect(concepts.textContent).toContain(en.howItWorks.localTests.body);
  });

  it("is linked from the Settings General page", async () => {
    renderApp("/settings");
    const link = await screen.findByTestId("settings-how-it-works");
    expect(link.getAttribute("href")).toBe("/how-it-works");
  });
});

describe("fxkitui settings need-it-now notes", () => {
  const sections: Array<{ path: string; title: string }> = [
    { path: "appearance", title: en.settings.appearance.title },
    { path: "localAI", title: en.settings.localAi.title },
    { path: "models", title: en.settings.models.title },
    { path: "routing", title: en.settings.routing.title },
    { path: "optimization", title: en.settings.optimization.title },
    { path: "capabilityDB", title: en.settings.capabilityDb.title },
    { path: "project", title: en.settings.project.title },
    { path: "localbench", title: en.settings.localbench.title },
  ];
  const purposes: Record<string, string> = {
    appearance: en.settings.appearance.purpose,
    localAI: en.settings.localAi.purpose,
    models: en.settings.models.purpose,
    routing: en.settings.routing.purpose,
    optimization: en.settings.optimization.purpose,
    capabilityDB: en.settings.capabilityDb.purpose,
    project: en.settings.project.purpose,
    localbench: en.settings.localbench.purpose,
  };
  const needItNow: Record<string, string> = {
    appearance: en.settings.appearance.needItNow,
    localAI: en.settings.localAi.needItNow,
    models: en.settings.models.needItNow,
    routing: en.settings.routing.needItNow,
    optimization: en.settings.optimization.needItNow,
    capabilityDB: en.settings.capabilityDb.needItNow,
    project: en.settings.project.needItNow,
    localbench: en.settings.localbench.needItNow,
  };

  it("shows purpose plus need-it-now on every settings page", async () => {
    renderApp("/settings");
    expect(await screen.findByText(en.settings.general.purpose)).toBeTruthy();
    expect(
      await screen.findByText(en.settings.general.needItNow),
    ).toBeTruthy();
    cleanup();
    for (const section of sections) {
      renderApp(`/settings/${section.path}`);
      expect(
        (await screen.findAllByText(section.title)).length,
      ).toBeGreaterThan(0);
      expect(
        await screen.findByText(purposes[section.path] as string),
      ).toBeTruthy();
      expect(
        await screen.findByText(needItNow[section.path] as string),
      ).toBeTruthy();
      cleanup();
    }
    renderApp("/settings/diagnostics");
    expect(await screen.findByText(en.diagnostics.purpose)).toBeTruthy();
    expect(await screen.findByText(en.diagnostics.needItNow)).toBeTruthy();
  });
});

describe("fxkitui project form labels", () => {
  it("labels every input with a visible label and a placeholder example", async () => {
    renderApp("/projects");
    const nameInput = (await screen.findByLabelText(
      "Project name",
    )) as HTMLInputElement;
    const folderInput = (await screen.findByLabelText(
      "Project folder",
    )) as HTMLInputElement;
    expect(nameInput.placeholder.length).toBeGreaterThan(0);
    expect(folderInput.placeholder.length).toBeGreaterThan(0);
    expect(nameInput.value).not.toContain("project-add-name");
  });
});
