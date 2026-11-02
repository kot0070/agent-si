/** @vitest-environment jsdom
 *
 * FXPROJ J1: one shared project list with refetch on create + delete +
 * route change. Loading is not empty, failure is not empty. After a chat
 * run creates the project (ChatStartBox path), the left list and the
 * Projects page show it without a remount.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ReactElement } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { createMemoryRouter, Outlet, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import type { ProjectRecord } from "../../api/iface";
import { ApiError } from "../../api/errors";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { Sidebar } from "../../shell/Sidebar";
import { ProjectsPage } from "../ProjectsPage";
import { ProjectListProvider } from "../projectList";

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

const CREATED_AT = "2026-01-01T00:00:00.000Z";

function shell(routes: { path: string; element: ReactElement }[], initial: string): void {
  // ProjectListProvider reads the route, so it mounts inside the router.
  const wrapped = routes.map((route) => ({
    path: route.path,
    element: <ProjectListProvider>{route.element}</ProjectListProvider>,
  }));
  const router = createMemoryRouter(wrapped, { initialEntries: [initial] });
  const client = new FakeApiClient({ projects: [] });
  render(
    <ApiClientProvider client={client}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

describe("fxproj shared project list", () => {
  it("sidebar refetches on route change so a chat-created project appears", async () => {
    const client = new FakeApiClient({ projects: [] });
    // Persistent shell: the Sidebar stays mounted across route changes,
    // exactly like AppShell. The chat run creates the project later
    // (ChatStartBox path); the mounted Sidebar must pick it up on route
    // change, no remount.
    const router = createMemoryRouter(
      [
        {
          path: "/",
          element: (
            <ProjectListProvider>
              <Sidebar projectId={null} />
              <Outlet />
            </ProjectListProvider>
          ),
          children: [
            {
              index: true,
              element: (
                <button
                  type="button"
                  data-testid="go-projects"
                  onClick={() => {
                    void router.navigate("/projects");
                  }}
                >
                  go
                </button>
              ),
            },
            { path: "projects", element: <span data-testid="here" /> },
          ],
        },
      ],
      { initialEntries: ["/"] },
    );
    render(
      <ApiClientProvider client={client}>
        <RouterProvider router={router} />
      </ApiClientProvider>,
    );
    // Mount settles on the empty list.
    await waitFor(() => {
      expect(
        document.querySelector('[data-testid="sidebar-projects"]'),
      ).toBeTruthy();
    });
    // The chat run creates the project; the still-mounted Sidebar must
    // show it after the route change (shared list refetch), no remount.
    await client.createProject({ name: "seven", folder_ref: "seven" });
    fireEvent.click(screen.getByTestId("go-projects"));
    await waitFor(() => {
      expect(
        document.querySelector('[data-testid="sidebar-project-p-1"]'),
      ).toBeTruthy();
    });
  });

  it("projects page add shows the new row from the shared list", async () => {
    // U13: creating a project opens it at once, so the harness needs
    // the chat route the new behavior navigates to.
    shell(
      [
        { path: "/projects", element: <ProjectsPage /> },
        {
          path: "/projects/:projectId/chat",
          element: <span data-testid="chat-here" />,
        },
      ],
      "/projects",
    );
    await waitFor(() => {
      expect(screen.getByTestId("project-add-form")).toBeTruthy();
    });
    fireEvent.change(screen.getByTestId("project-add-name"), {
      target: { value: "added" },
    });
    fireEvent.change(screen.getByTestId("project-add-folder"), {
      target: { value: "added" },
    });
    fireEvent.click(screen.getByTestId("project-add-submit"));
    // U13: the new project opens at once (no stuck empty state).
    await waitFor(() => {
      expect(screen.getByTestId("chat-here")).toBeTruthy();
    });
  });
});

class DeferredProjectsClient extends FakeApiClient {
  resolveList: ((rows: ProjectRecord[]) => void) | null = null;

  override listProjects(): Promise<ProjectRecord[]> {
    return new Promise<ProjectRecord[]>((resolve) => {
      this.resolveList = resolve;
    });
  }
}

class FlakyProjectsClient extends FakeApiClient {
  fail = true;

  override listProjects(): Promise<ProjectRecord[]> {
    if (this.fail) {
      return Promise.reject(new ApiError("CONTEXT_MISSING", 404));
    }
    return super.listProjects();
  }
}

function renderSidebarWith(client: FakeApiClient): void {
  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: (
          <ProjectListProvider>
            <Sidebar projectId={null} />
          </ProjectListProvider>
        ),
      },
    ],
    { initialEntries: ["/"] },
  );
  render(
    <ApiClientProvider client={client}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

describe("fxproj sidebar list states", () => {
  it("loading is not an empty list", async () => {
    const client = new DeferredProjectsClient({ projects: [] });
    renderSidebarWith(client);
    await waitFor(() => {
      expect(screen.getByTestId("kit-loading-state")).toBeTruthy();
    });
    expect(
      document.querySelector('[data-testid^="sidebar-project-"]'),
    ).toBeNull();
    client.resolveList?.([]);
    await waitFor(() => {
      expect(screen.queryByTestId("kit-loading-state")).toBeNull();
    });
  });

  it("failure is not an empty list and retry recovers", async () => {
    const client = new FlakyProjectsClient({});
    renderSidebarWith(client);
    await waitFor(() => {
      expect(screen.getByTestId("kit-error-panel")).toBeTruthy();
    });
    expect(
      document.querySelector('[data-testid^="sidebar-project-"]'),
    ).toBeNull();
    client.fail = false;
    fireEvent.click(screen.getByTestId("kit-error-retry"));
    await waitFor(() => {
      expect(
        document.querySelector('[data-testid="sidebar-project-p-1"]'),
      ).toBeTruthy();
    });
  });
});
