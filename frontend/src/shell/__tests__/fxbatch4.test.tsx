/** @vitest-environment jsdom */
// FXBATCH4 P19/P21: stop-all posts a project body only when a project is
// selected (else {}), and the TopBar select shows names with the id only
// in the title. The REAL App is mounted; only global fetch is faked and
// the posted stop-all body is asserted.
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
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import {
  resetLocaleForTests,
  setLocale,
  t,
} from "../../locale/index";
import { App } from "../../app/App";

const HEX_ID = "9f8e7d6c5b4a39281706f5e4d3c2b1a0";
const HEX_RE = /[0-9a-f]{32}/;
const PROJECT_NAME = "Field Notes";

const SEEN: Array<{ url: string; method: string; body: string }> = [];

function stopReceipt(projectId: string): unknown {
  return {
    project_id: projectId,
    accepted: true,
    reason: "stop supervised by user",
    stopped_count: 0,
    journal_entry_id: "evt-fxb4",
    stopped_at: "2026-11-01T00:00:00Z",
  };
}

function stubFetch(): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: { method?: string; body?: unknown }) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      let body = "";
      try {
        body =
          typeof init?.body === "string"
            ? (init.body as string)
            : JSON.stringify(init?.body ?? "");
      } catch {
        body = "";
      }
      SEEN.push({ url, method, body });
      if (url === "/api/v1/stop-all" && method === "POST") {
        let projectId = "";
        try {
          projectId = String(JSON.parse(body).project_id ?? "");
        } catch {
          projectId = "";
        }
        return new Response(JSON.stringify(stopReceipt(projectId)), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      return new Response(JSON.stringify({}), {
        status: 404,
        headers: { "content-type": "application/json" },
      });
    },
  );
}

function renderApp(client: FakeApiClient): void {
  const router = createMemoryRouter([{ path: "*", element: <App /> }], {
    initialEntries: ["/"],
  });
  render(
    <ApiClientProvider client={client}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

function stopPosts(): Array<{ url: string; method: string; body: string }> {
  return SEEN.filter(
    (entry) => entry.url === "/api/v1/stop-all" && entry.method === "POST",
  );
}

async function armAndConfirmStopAll(): Promise<void> {
  // FXFACTS F12: one click stops at once, no confirmation dialog.
  fireEvent.click(await screen.findByTestId("topbar-stop-all"));
  expect(await screen.findByTestId("stop-all-result")).toBeTruthy();
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem("agentsi.firstrun.done", "true");
  setLocale("en");
  SEEN.length = 0;
  stubFetch();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("fxbatch4 stop-all request body over the real App", () => {
  it("posts {project_id} when a project is selected", async () => {
    renderApp(
      new FakeApiClient({
        projects: [
          { project_id: HEX_ID, name: PROJECT_NAME, created_at: "t-0" },
        ],
      }),
    );
    // D6B: the Sidebar project list shows the same name as visible text,
    // so the wait scopes to the TopBar select option (the surface this
    // test then asserts). Same asserted property: the name renders.
    const projectSelect = await screen.findByTestId("topbar-project");
    expect(
      await within(projectSelect as HTMLElement).findByText(PROJECT_NAME),
    ).toBeTruthy();
    await waitFor(() => {
      expect(
        (screen.getByTestId("topbar-project") as HTMLSelectElement).value,
      ).toBe(HEX_ID);
    });
    await armAndConfirmStopAll();
    // FXFACTS F12/F15: one quiet locale status line (unit included).
    expect(screen.getByTestId("stop-all-result").textContent).toContain(
      "Stopped 0",
    );
    expect(stopPosts()).toHaveLength(1);
    expect(JSON.parse(stopPosts()[0]?.body ?? "")).toEqual({
      project_id: HEX_ID,
      actor: "user",
    });
  });

  it("posts {} when no project is selected", async () => {
    renderApp(new FakeApiClient({ projects: [] }));
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    await armAndConfirmStopAll();
    // FXFACTS F12/F15: one quiet locale status line (unit included).
    expect(screen.getByTestId("stop-all-result").textContent).toContain(
      "Stopped 0",
    );
    expect(stopPosts()).toHaveLength(1);
    expect(JSON.parse(stopPosts()[0]?.body ?? "")).toEqual({
      actor: "user",
    });
  });
});

describe("fxbatch4 project select shows names, id only in the title", () => {
  it("shows the project name with no 32-hex string in the select", async () => {
    renderApp(
      new FakeApiClient({
        projects: [
          { project_id: HEX_ID, name: PROJECT_NAME, created_at: "t-0" },
        ],
      }),
    );
    const select = (await screen.findByTestId(
      "topbar-project",
    )) as HTMLSelectElement;
    // D6B: scoped to the select (see above): the Sidebar project list
    // renders the same name as visible text.
    expect(await within(select as HTMLElement).findByText(PROJECT_NAME)).toBeTruthy();
    expect(select.textContent).toContain(PROJECT_NAME);
    expect(HEX_RE.test(select.textContent ?? "")).toBe(false);
    const options = Array.from(select.querySelectorAll("option"));
    expect(options.length).toBeGreaterThan(0);
    expect(
      options.some((option) => option.textContent === PROJECT_NAME),
    ).toBe(true);
    for (const option of options) {
      if (option.value !== "") {
        expect(option.getAttribute("title")).toBe(option.value);
      }
    }
  });
});
