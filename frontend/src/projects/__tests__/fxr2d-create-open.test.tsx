/** @vitest-environment jsdom
 *
 * U13 (RC5 acceptance drive): first project submit kept "No projects yet"
 * on screen although the project WAS created; a retry made a second
 * project with the same name. After create the page refreshes the list
 * AND opens the new project at once; a duplicate name is refused in
 * place with a plain line; submit is disabled while saving.
 * Real-page test: the real ProjectsPage under a memory router.
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
import type { ProjectCreate, ProjectRecord } from "../../api/iface";
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

function renderRealPage(client: FakeApiClient, initial = "/projects"): void {
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
      {
        path: "/projects/:projectId/chat",
        element: <ChatProbe />,
      },
    ],
    { initialEntries: [initial] },
  );
  render(
    <ApiClientProvider client={client}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
  return void router;
}

async function fillAndSubmit(name: string, folder: string): Promise<void> {
  fireEvent.change(await screen.findByTestId("project-add-name"), {
    target: { value: name },
  });
  fireEvent.change(await screen.findByTestId("project-add-folder"), {
    target: { value: folder },
  });
  fireEvent.click(await screen.findByTestId("project-add-submit"));
}

describe("U13 create opens the new project at once", () => {
  it("first submit leaves the empty state and lands on the new chat", async () => {
    const client = new FakeApiClient({ projects: [] });
    renderRealPage(client);
    expect(await screen.findByTestId("project-add-form")).toBeTruthy();
    expect(screen.queryByTestId("project-add-duplicate")).toBeNull();

    await fillAndSubmit("alpha", "alpha-folder");

    // Opened at once: the new chat route renders with the created id,
    // and the selection follows it (no stuck "No projects yet").
    expect(await screen.findByTestId("chat-route-id")).toBeTruthy();
    expect((await screen.findByTestId("chat-route-id")).textContent).not.toBe(
      "none",
    );
    const selected = (await screen.findByTestId("chat-selected-id"))
      .textContent;
    expect(selected).not.toBe("none");
    expect((await screen.findByTestId("chat-route-id")).textContent).toBe(
      selected,
    );
  });

  it("refuses a duplicate name in place with a plain line", async () => {
    const client = new FakeApiClient({ projects: [] });
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
    await fillAndSubmit("alpha", "alpha-folder");
    await screen.findByTestId("chat-route-id");
    // Only one project was created by the first submit.
    expect((await client.listProjects()).length).toBe(1);

    // Back on the list: the new row is there after the shared refresh.
    await router.navigate("/projects");
    await waitFor(() => {
      expect(
        document.querySelector('[data-testid^="project-row-"]'),
      ).toBeTruthy();
    });
    expect(
      document.querySelectorAll('[data-testid^="project-row-"]').length,
    ).toBe(1);

    // Retry with the same name: refused in place, no second project.
    // FXLOOK D3: the form folded behind New project once the first row
    // exists, so the retry opens it first.
    fireEvent.click(await screen.findByTestId("project-add-open"));
    await fillAndSubmit("alpha", "other-folder");
    expect(await screen.findByTestId("project-add-duplicate")).toBeTruthy();
    expect((await screen.findByTestId("project-add-duplicate")).textContent).toBe(
      en.projects.list.duplicate,
    );
    expect((await client.listProjects()).length).toBe(1);
    expect(
      document.querySelectorAll('[data-testid^="project-row-"]').length,
    ).toBe(1);

    // A corrected name submits again (duplicate line clears).
    await fillAndSubmit("beta", "beta-folder");
    await waitFor(async () => {
      expect((await client.listProjects()).length).toBe(2);
    });
  });

  it("disables submit while saving so a double click makes one project", async () => {
    let release!: (row: ProjectRecord) => void;
    let calls = 0;
    class DeferredCreateClient extends FakeApiClient {
      override createProject(body: ProjectCreate): Promise<ProjectRecord> {
        calls += 1;
        return new Promise<ProjectRecord>((resolve) => {
          release = resolve;
        }).then(() => super.createProject(body));
      }
    }
    const client = new DeferredCreateClient({ projects: [] });
    renderRealPage(client);
    fireEvent.change(await screen.findByTestId("project-add-name"), {
      target: { value: "solo" },
    });
    fireEvent.change(await screen.findByTestId("project-add-folder"), {
      target: { value: "solo-folder" },
    });
    const submit = await screen.findByTestId("project-add-submit");
    fireEvent.click(submit);
    // Saving: the submit is disabled, so a second click cannot re-fire.
    await waitFor(() => {
      expect(
        (screen.getByTestId("project-add-submit") as HTMLButtonElement)
          .disabled,
      ).toBe(true);
    });
    fireEvent.click(screen.getByTestId("project-add-submit"));
    expect(calls).toBe(1);
    release({ project_id: "unused", name: "unused", created_at: "t-0" });
    await screen.findByTestId("chat-route-id");
    expect(calls).toBe(1);
    expect((await client.listProjects()).length).toBe(1);
  });
});
