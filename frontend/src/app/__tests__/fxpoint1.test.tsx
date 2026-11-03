/** @vitest-environment jsdom */
// FXPOINT1 dry-run rows R1-R7 over the REAL App.
// Fakes ONLY at the network boundary (global fetch); every component,
// route, label and locale lookup under test is the real product code.
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
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { App } from "../App";
import en from "../../locale/en.json";

interface ProjectRow {
  project_id: string;
  name: string;
  created_at: string;
}

interface TaskRow {
  task_id: string;
  project_id: string;
  title: string;
  status: string;
  created_at: string;
}

const mockState = {
  projects: [] as ProjectRow[],
  providers: [] as string[],
  tasks: [] as TaskRow[],
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
      if (url === "/api/v1/providers/keys" && method === "POST") {        const preset = (body as { preset_id: string }).preset_id;
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
        const row: TaskRow = {
          task_id: `t-${mockState.tasks.length + 1}`,
          project_id: projectId,
          title: payload.title,
          status: "QUEUED",
          created_at: "2026-01-01T00:00:00Z",
        };
        mockState.tasks.push(row);
        return json({ task: row });
      }
      if (url.startsWith("/api/v1/tasks") && method === "GET") {
        return json({ tasks: mockState.tasks });
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
      if (url.startsWith("/api/v1/routing/role") && method === "GET") {
        return json({ code: "CONTEXT_MISSING" }, 404);
      }
      if (url === "/api/v1/agents/live" && method === "GET") {
        return json({ agents: [] });
      }
      if (url.startsWith("/api/v1/chat/models") && method === "GET") {
        return json({ project_id: "p-1", models: [] });
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

function seedProject(): void {
  mockState.projects = [
    { project_id: "p-1", name: "n-1", created_at: "2026-01-01T00:00:00Z" },
  ];
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem("agentsi.locale", "en");
  setLocale("en");
  mockState.projects = [];
  mockState.providers = [];
  mockState.tasks = [];
  installFetch();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("fxpoint1 R1 settings project role pickers", () => {
  it("selects Mode by label and fills Role by label", async () => {
    seedProject();
    renderApp("/settings/project");
    const mode = (await screen.findByLabelText(
      en.settings.roleProfile.modeLabel,
    )) as HTMLSelectElement;
    expect(mode.tagName.toLowerCase()).toBe("select");
    fireEvent.change(mode, { target: { value: "pool" } });
    expect(mode.value).toBe("pool");
    const role = (await screen.findByLabelText(
      en.settings.roleProfile.roleLabel,
    )) as HTMLInputElement;
    expect(role.tagName.toLowerCase()).toBe("input");
    fireEvent.change(role, { target: { value: "manager" } });
    expect(role.value).toBe("manager");
  });

  it("resolves with no project selected", async () => {
    renderApp("/settings/project");
    const mode = (await screen.findByLabelText(
      en.settings.roleProfile.modeLabel,
    )) as HTMLSelectElement;
    expect(mode.tagName.toLowerCase()).toBe("select");
    const role = (await screen.findByLabelText(
      en.settings.roleProfile.roleLabel,
    )) as HTMLInputElement;
    expect(role.tagName.toLowerCase()).toBe("input");
  });
});

describe("fxpoint1 R2 sidebar tab purposes", () => {
  it("carries a one-sentence purpose per tab", async () => {
    seedProject();
    renderApp("/");
    const rows: Array<[string, string]> = [
      ["menu-new-task", en.tasks.creator.subtitle],
      ["menu-projects", en.projects.list.subtitle],
      ["menu-results", en.projects.reports.subtitle],
      ["menu-settings", en.settings.index.subtitle],
    ];
    for (const [id, purpose] of rows) {
      const tab = await screen.findByTestId(id);
      expect(tab).toBeTruthy();
      const note = await screen.findByTestId(`${id}-purpose`);
      expect(note.textContent).toBe(purpose);
      expect(tab.nextElementSibling).toBe(note);
    }
  });
});

describe("fxpoint1 R3 settings need-it-now note placement", () => {
  it("shows the need-it-now note on routing, never on project", async () => {
    seedProject();
    renderApp("/settings/routing");
    expect(
      (await screen.findByTestId("settings-need-it-now")).textContent,
    ).toContain(en.settings.routing.needItNow);
    cleanup();
    seedProject();
    renderApp("/settings/project");
    await screen.findByTestId("kit-card-needitnow-project");
    expect(screen.queryByTestId("settings-need-it-now")).toBeNull();
  });
});

describe("fxpoint1 R4 first chat screen label", () => {
  it("carries the composer label", async () => {
    seedProject();
    renderApp("/");
    expect(await screen.findByText(en.chat.composer.prompt)).toBeTruthy();
  });
});

describe("fxpoint1 R5 top bar brand plus pairing gap", () => {
  it("leads with the Agent SI brand and keeps the pairing spans apart", async () => {
    seedProject();
    renderApp("/");
    const topbar = await screen.findByTestId("topbar");
    const brand = await screen.findByTestId("topbar-brand");
    expect(brand.textContent).toContain("Agent SI");
    expect(topbar.firstElementChild).toBe(brand);
    const strip = screen.getByTestId("pairing-strip");
    const label = screen.getByTestId("pairing-label");
    const badge = screen.getByTestId("pairing-badge");
    expect(strip.firstElementChild).toBe(label);
    expect(label.nextElementSibling).toBe(badge);
    expect(strip.textContent).toContain(`${en.shell.topbar.watcher} `);
  });
});

describe("fxpoint1 R6 first-run prefill", () => {
  it("lands the first task text in the chat composer", async () => {
    const router = renderApp("/");
    expect(await screen.findByText(en.firstrun.title)).toBeTruthy();
    expect(router.state.location.pathname).toBe("/firstrun");
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
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/");
    });
    expect(
      (await screen.findByTestId("chat-prompt") as HTMLInputElement).value,
    ).toBe("My first task");
  });
});
