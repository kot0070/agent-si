/** @vitest-environment jsdom */
// FXLOOK D3 RED: projects list — visible primary Open per row landing on
// chat, whole row opens too, create form folds behind New project once a
// project exists, Stop/Leave carry plain titles. Real ProjectsPage under
// a memory router; the ONLY fake is the FakeApiClient boundary.
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ReactElement } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  createMemoryRouter,
  RouterProvider,
  useParams,
} from "react-router-dom";
import {
  ApiClientProvider,
  useCurrentProject,
} from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProjectsPage } from "../ProjectsPage";
import { ProjectListProvider } from "../projectList";
import en from "../../locale/en.json";

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

const SEED = [
  {
    project_id: "p-1",
    name: "Crit3 Demo",
    created_at: "2026-11-02T21:34:00.000Z",
  },
];

function ChatProbe(): ReactElement {
  const { projectId } = useParams();
  const current = useCurrentProject();
  return (
    <div>
      <span data-testid="chat-route-id">{projectId ?? "none"}</span>
      <span data-testid="chat-selected-id">{current.projectId ?? "none"}</span>
    </div>
  );
}

function renderRealPage(client: FakeApiClient): void {
  const router = createMemoryRouter(
    [
      {
        path: "/projects",
        element: (
          <ProjectListProvider>
            <ProjectsPage />
          </ProjectListProvider>
        ),
      },
      { path: "/projects/:projectId/chat", element: <ChatProbe /> },
    ],
    { initialEntries: ["/projects"] },
  );
  render(
    <ApiClientProvider client={client}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

describe("FXLOOK D3 projects list", () => {
  it("folds the create form behind New project once a project exists", async () => {
    renderRealPage(new FakeApiClient({ projects: SEED }));
    await screen.findByTestId("project-row-p-1");
    expect(screen.queryByTestId("project-add-form")).toBeNull();
    const opener = await screen.findByTestId("project-add-open");
    expect(opener.textContent).toBe(en.projects.list.newProject);
    fireEvent.click(opener);
    expect(await screen.findByTestId("project-add-form")).toBeTruthy();
  });

  it("keeps the open form on the empty list", async () => {
    renderRealPage(new FakeApiClient({ projects: [] }));
    expect(await screen.findByTestId("project-add-form")).toBeTruthy();
    expect(screen.queryByTestId("project-add-open")).toBeNull();
  });

  it("primary Open lands on the project chat", async () => {
    renderRealPage(new FakeApiClient({ projects: SEED }));
    const open = await screen.findByTestId("project-open-primary-p-1");
    expect(open.textContent).toBe(en.projects.list.open);
    fireEvent.click(open);
    expect(await screen.findByTestId("chat-route-id")).toBeTruthy();
    expect((await screen.findByTestId("chat-route-id")).textContent).toBe(
      "p-1",
    );
  });

  it("the whole row opens the project chat", async () => {
    renderRealPage(new FakeApiClient({ projects: SEED }));
    const row = await screen.findByTestId("project-row-p-1");
    fireEvent.click(row);
    expect(await screen.findByTestId("chat-route-id")).toBeTruthy();
    expect((await screen.findByTestId("chat-route-id")).textContent).toBe(
      "p-1",
    );
  });

  it("Stop and Leave carry plain titles saying what they do", async () => {
    renderRealPage(new FakeApiClient({ projects: SEED }));
    const stop = await screen.findByTestId("project-pause-p-1");
    expect(stop.getAttribute("title")).toBe(en.projects.row.stopTitle);
    expect((stop.getAttribute("title") ?? "").length).toBeGreaterThan(10);
    const leave = await screen.findByTestId("project-archive-p-1");
    expect(leave.getAttribute("title")).toBe(en.projects.row.leaveTitle);
    expect((leave.getAttribute("title") ?? "").length).toBeGreaterThan(10);
  });

  it("inner Leave archives without opening the project", async () => {
    renderRealPage(new FakeApiClient({ projects: SEED }));
    const leave = await screen.findByTestId("project-archive-p-1");
    fireEvent.click(leave);
    // Still on the list (no chat navigation), the row is gone and the
    // empty list shows the open form again.
    await waitFor(() => {
      expect(screen.queryByTestId("chat-route-id")).toBeNull();
    });
    expect(await screen.findByTestId("project-add-form")).toBeTruthy();
  });
});
