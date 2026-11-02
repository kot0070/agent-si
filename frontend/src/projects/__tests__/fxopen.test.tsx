/** @vitest-environment jsdom */
// FXOPEN O6: SH-01/SH-04/SH-05 page proofs on the real components.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { useEffect } from "react";
import type { ReactElement } from "react";
import {
  createMemoryRouter,
  RouterProvider,
} from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { useCurrentProject } from "../../app/ApiClientProvider";
import { ApiError } from "../../api/errors";
import type { ProjectCreate, ProjectRecord } from "../../api/iface";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import {
  resetLocaleForTests,
  setLocale,
} from "../../locale/index";
import { ProjectsPage } from "../ProjectsPage";
import { ProjectView } from "../ProjectView";

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

function SelectedProbe(): ReactElement {
  const current = useCurrentProject();
  return (
    <span data-testid="selected-project">{current.projectId ?? "none"}</span>
  );
}

function Preselect(props: { projectId: string }): ReactElement {
  const current = useCurrentProject();
  useEffect(() => {
    current.select(props.projectId);
  }, []);
  return <SelectedProbe />;
}

describe("FXOPEN O6 SH-01: the same folder twice refuses", () => {
  it("a 409 names the plain folder line, no second row", async () => {
    class DuplicateFolderClient extends FakeApiClient {
      override createProject(_body: ProjectCreate): Promise<ProjectRecord> {
        return Promise.reject(
          new ApiError("PROJECT_FOLDER_IN_USE", 409),
        );
      }
    }
    const client = new DuplicateFolderClient({ projects: [] });
    render(
      <ApiClientProvider client={client}>
        <ProjectsPage />
      </ApiClientProvider>,
    );
    fireEvent.change(await screen.findByTestId("project-add-name"), {
      target: { value: "B" },
    });
    fireEvent.change(screen.getByTestId("project-add-folder"), {
      target: { value: "D:\\shared" },
    });
    fireEvent.click(screen.getByTestId("project-add-submit"));
    const panel = await screen.findByTestId("kit-error-panel");
    expect(panel.textContent).toContain("already used");
    expect(panel.textContent).toContain("PROJECT_FOLDER_IN_USE");
    expect(screen.queryByTestId("project-row-p-2")).toBeNull();
  });
});

describe("FXOPEN O6 SH-04: archived selection leaves no ghost", () => {
  it("a 404 read clears the selection and lands on the list", async () => {
    const client = new FakeApiClient({ projects: [] });
    const router = createMemoryRouter(
      [
        {
          path: "/projects/:projectId/*",
          element: (
            <>
              <Preselect projectId="p-old" />
              <ProjectView projectId="p-old" view="overview" />
            </>
          ),
        },
        {
          path: "/projects",
          element: (
            <>
              <span data-testid="projects-list">list</span>
              <SelectedProbe />
            </>
          ),
        },
      ],
      { initialEntries: ["/projects/p-old/overview"] },
    );
    render(
      <ApiClientProvider client={client}>
        <RouterProvider router={router} />
      </ApiClientProvider>,
    );
    await screen.findByTestId("projects-list");
    expect(screen.getByTestId("selected-project").textContent).toBe("none");
  });
});

describe("FXOPEN O6 SH-05: a deleted folder shows one plain banner", () => {
  function renderOverview(project: {
    project_id: string;
    name: string;
    created_at: string;
    folder_ok?: boolean;
    folder_path?: string;
  }): void {
    const client = new FakeApiClient({ projects: [project] });
    const router = createMemoryRouter(
      [
        {
          path: "*",
          element: <ProjectView projectId="p-9" view="overview" />,
        },
      ],
      { initialEntries: ["/projects/p-9/overview"] },
    );
    render(
      <ApiClientProvider client={client}>
        <RouterProvider router={router} />
      </ApiClientProvider>,
    );
  }

  it("names the missing folder, never green facts alone", async () => {
    renderOverview({
      project_id: "p-9",
      name: "n-9",
      created_at: "2026-01-01T00:00:00.000Z",
      folder_ok: false,
      folder_path: "D:\\gone",
    });
    const banner = await screen.findByTestId("project-folder-banner");
    expect(banner.textContent).toContain("not found");
    expect(banner.textContent).toContain("D:\\gone");
  });

  it("no banner when the folder is healthy", async () => {
    renderOverview({
      project_id: "p-9",
      name: "n-9",
      created_at: "2026-01-01T00:00:00.000Z",
      folder_ok: true,
      folder_path: "D:\\kept",
    });
    await screen.findByTestId("overview-name");
    expect(screen.queryByTestId("project-folder-banner")).toBeNull();
  });
});
