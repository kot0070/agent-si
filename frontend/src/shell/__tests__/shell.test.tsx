/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { Link, RouterProvider, createMemoryRouter, useLocation } from "react-router-dom";
import type { ReactElement } from "react";
import { ApiClientProvider, useCurrentProject } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import {
  LOCALE_STORAGE_KEY,
  resetLocaleForTests,
  setLocale,
  t,
} from "../../locale/index";
import { App } from "../../app/App";
import { TOPBAR_STOP_EVENT } from "../TopBar";
import { TopBar } from "../TopBar";
import { Sidebar } from "../Sidebar";
import { Inspector } from "../Inspector";
import { ClosingGuard } from "../ClosingGuard";

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  setLocale("en");
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

function renderShell(node: ReactElement, client?: FakeApiClient): void {
  const api = client ?? new FakeApiClient({});
  const router = createMemoryRouter([{ path: "/", element: node }], {
    initialEntries: ["/"],
  });
  render(
    <ApiClientProvider client={api}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

describe("top bar", () => {
  it("renders the switcher, watcher chip, stop-all and language switch", async () => {
    const client = new FakeApiClient({
      projects: [
        { project_id: "p-1", name: "n-1", created_at: "t-0" },
        { project_id: "p-2", name: "n-2", created_at: "t-0" },
      ],
    });
    const router = createMemoryRouter(
      [
        {
          path: "/",
          element: (
            <>
              <TopBar projectId="p-1" />
              <SelectedProbe />
            </>
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
    expect(await screen.findByTestId("topbar-project")).toBeTruthy();
    // FXFACTS F15: the top bar carries no watcher word; the placement
    // badge stays.
    expect(screen.queryByTestId("topbar-watcher")).toBeNull();
    expect(screen.getByTestId("pairing-badge")).toBeTruthy();
    expect(screen.getByTestId("topbar-stop-all").textContent).toBe(
      t("shell.topbar.stop_all"),
    );
    expect(screen.getByTestId("topbar-language")).toBeTruthy();
    fireEvent.change(screen.getByTestId("topbar-project"), {
      target: { value: "p-2" },
    });
    expect(screen.getByTestId("selected-project").textContent).toBe("p-2");
  });

  it("signals stop-all without touching served state", async () => {
    let stopped = 0;
    window.addEventListener(TOPBAR_STOP_EVENT, () => {
      stopped += 1;
    });
    renderShell(<TopBar projectId="p-1" />);
    fireEvent.click(await screen.findByTestId("topbar-stop-all"));
    expect(stopped).toBe(1);
  });

  it("re-renders screens through the locale surface and persists", async () => {
    const localeRouter = createMemoryRouter(
      [{ path: "*", element: <App /> }],
      { initialEntries: ["/"] },
    );
    render(
      <ApiClientProvider client={new FakeApiClient({})}>
        <RouterProvider router={localeRouter} />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    const before = screen.getByTestId("menu-new-task").textContent;
    fireEvent.change(screen.getByTestId("topbar-language"), {
      target: { value: "uk" },
    });
    await waitFor(() => {
      expect(screen.getByTestId("menu-new-task").textContent).not.toBe(before);
    });
    expect(screen.getByTestId("menu-new-task").textContent).toBe(
      t("tasks.creator.title"),
    );
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("uk");
  });
});

describe("sidebar", () => {
  it("shows exactly the four Claude-desktop entries with locale labels", async () => {
    renderShell(<Sidebar projectId="p-1" />);
    const sidebar = screen.getByTestId("sidebar");
    const anchors = Array.from(sidebar.querySelectorAll("a"));
    expect(
      anchors.map((anchor) => anchor.getAttribute("data-testid")).sort(),
    ).toEqual(
      ["menu-new-task", "menu-projects", "menu-results", "menu-settings"].sort(),
    );
    const menus: Array<[string, string]> = [
      ["menu-new-task", "tasks.creator.title"],
      ["menu-projects", "shell.sidebar.projects"],
      ["menu-results", "projects.reports.title"],
      ["menu-settings", "shell.sidebar.settings"],
    ];
    for (const [testId, key] of menus) {
      expect((await screen.findByTestId(testId)).textContent).toBe(t(key));
    }
  });

  it("hints at the project list when no project is selected", async () => {
    renderShell(<Sidebar projectId={null} />);
    expect(await screen.findByTestId("menu-results-hint")).toBeTruthy();
    expect(screen.getByTestId("menu-results").getAttribute("href")).toBe(
      "/projects",
    );
  });

  it("routes results to the current project reports view", async () => {
    const resultsRouter = createMemoryRouter(
      [{ path: "*", element: <App /> }],
      { initialEntries: ["/"] },
    );
    render(
      <ApiClientProvider client={new FakeApiClient({})}>
        <RouterProvider router={resultsRouter} />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    fireEvent.click(screen.getByTestId("menu-results"));
    expect(
      (await screen.findByTestId("project-report-export")).textContent,
    ).toContain("pkg-1");
  });
});

describe("inspector", () => {
  it("renders five live cards plus six collapsed cards with the team content", async () => {
    renderShell(
      <Inspector
        projectId="p-1"
        live={<span data-testid="live-probe">live content</span>}
      />,
    );
    for (const card of [
      "inspector-card-team",
      "inspector-card-context",
      "inspector-card-results",
      "inspector-card-background",
      "inspector-card-watcher",
    ]) {
      expect(await screen.findByTestId(card)).toBeTruthy();
    }
    expect(await screen.findByTestId("live-probe")).toBeTruthy();
    // FXFACTS F10: Tokens, Tests, Providers, Local AI and Apps live in
    // the More disclosure; Budget stays a direct card.
    fireEvent.click(await screen.findByTestId("rail-more-toggle"));
    for (const card of [
      "fx-tokens",
      "fx-tests",
      "fx-budget",
      "fx-providers",
      "fx-localai",
      "fx-apps",
    ]) {
      expect(await screen.findByTestId(`kit-metric-${card}`)).toBeTruthy();
    }
    const scroll = screen.getByTestId("inspector-scroll");
    expect(scroll.style.overflowY).toBe("auto");
  });

  it("mounts live agents on the agents-live route beside the inspector team card", async () => {
    const inspectorRouter = createMemoryRouter(
      [{ path: "*", element: <App /> }],
      { initialEntries: ["/agents/live"] },
    );
    render(
      <ApiClientProvider client={new FakeApiClient({})}>
        <RouterProvider router={inspectorRouter} />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("inspector-card-team")).toBeTruthy();
    const main = await screen.findByTestId("app-main");
    expect(
      await within(main).findByTestId("agents-live-rows"),
    ).toBeTruthy();
    const badges = await within(main).findAllByTestId("agent-badge-LOCAL");
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });
});

function LocationProbe(): ReactElement {
  const location = useLocation();
  return <span data-testid="guard-location">{location.pathname}</span>;
}

function renderGuard(armed: boolean): void {
  const router = createMemoryRouter(
    [
      {
        path: "*",
        element: (
          <>
            <ClosingGuard armed={armed} confirmKey="shell.closing.confirm">
              <span data-testid="guard-body">guarded</span>
            </ClosingGuard>
            <Link data-testid="guard-go" to="/guard-b">
              go
            </Link>
            <LocationProbe />
          </>
        ),
      },
    ],
    { initialEntries: ["/guard-a", "/guard-b"], initialIndex: 0 },
  );
  render(<RouterProvider router={router} />);
}

describe("closing guard", () => {
  it("renders children and stays quiet while unarmed", async () => {
    renderGuard(false);
    expect(await screen.findByTestId("guard-body")).toBeTruthy();
    fireEvent.click(screen.getByTestId("guard-go"));
    expect((await screen.findByTestId("guard-location")).textContent).toBe(
      "/guard-b",
    );
    expect(screen.queryByTestId("closing-confirm")).toBeNull();
  });

  it("blocks navigation while armed until stay or leave", async () => {
    renderGuard(true);
    expect(await screen.findByTestId("guard-body")).toBeTruthy();
    fireEvent.click(screen.getByTestId("guard-go"));
    expect(await screen.findByTestId("closing-confirm")).toBeTruthy();
    expect(
      screen.getByTestId("closing-confirm").textContent,
    ).toContain(t("shell.closing.confirm"));
    fireEvent.click(screen.getByTestId("closing-stay"));
    await waitFor(() => {
      expect(screen.queryByTestId("closing-confirm")).toBeNull();
    });
    expect(screen.getByTestId("guard-location").textContent).toBe("/guard-a");
    fireEvent.click(screen.getByTestId("guard-go"));
    expect(await screen.findByTestId("closing-confirm")).toBeTruthy();
    fireEvent.click(screen.getByTestId("closing-leave"));
    await waitFor(() => {
      expect(screen.getByTestId("guard-location").textContent).toBe(
        "/guard-b",
      );
    });
    expect(screen.queryByTestId("closing-confirm")).toBeNull();
  });
});

describe("composer guard", () => {
  it("keeps a user-edited value through a late status load", async () => {
    const composerRouter = createMemoryRouter(
      [{ path: "*", element: <App /> }],
      { initialEntries: ["/projects/p-1/tasks?initialTask=t-1"] },
    );
    render(
      <ApiClientProvider client={new FakeApiClient({})}>
        <RouterProvider router={composerRouter} />
      </ApiClientProvider>,
    );
    const title = (await screen.findByTestId(
      "composer-title",
    )) as HTMLInputElement;
    fireEvent.change(title, { target: { value: "user edit" } });
    expect(await screen.findByDisplayValue("user edit")).toBeTruthy();
  });

  it("shows every named project menu on a project view", async () => {
    const menusRouter = createMemoryRouter(
      [{ path: "*", element: <App /> }],
      { initialEntries: ["/projects/p-1/overview"] },
    );
    render(
      <ApiClientProvider client={new FakeApiClient({})}>
        <RouterProvider router={menusRouter} />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("overview-name")).toBeTruthy();
    const menus = document.querySelectorAll('[data-testid^="project-menu-"]');
    expect(menus.length).toBe(15);
    menus.forEach((node) => {
      expect((node.textContent ?? "").trim().length).toBeGreaterThan(0);
    });
  });
});
