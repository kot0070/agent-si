/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import {
  resetLocaleForTests,
  setLocale,
  t,
} from "../../locale/index";
import { App } from "../App";

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

function renderApp(route: string, client?: FakeApiClient): void {
  const api = client ?? new FakeApiClient({});
  const router = createMemoryRouter([{ path: "*", element: <App /> }], {
    initialEntries: [route],
  });
  render(
    <ApiClientProvider client={api}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

function firstScreenWords(container: HTMLElement): string[] {
  const text = container.textContent ?? "";
  return text
    .split(/\s+/)
    .map((word) => word.trim())
    .filter((word) => word.length > 0);
}

describe("app default entry", () => {
  it("renders chat first with a short first screen and no graph canvas", async () => {
    const router = createMemoryRouter([{ path: "*", element: <App /> }], {
      initialEntries: ["/"],
    });
    const view = render(
      <ApiClientProvider client={new FakeApiClient({})}>
        <RouterProvider router={router} />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    expect(await screen.findByTestId("chat-send")).toBeTruthy();
    expect(screen.queryByTestId("graph-canvas")).toBeNull();
    expect(view.container.querySelector("canvas")).toBeNull();
    const words = firstScreenWords(view.container);
    expect(words.length).toBeGreaterThan(0);
    expect(words.length).toBeLessThanOrEqual(150);
    expect(screen.getByTestId("menu-new-task").textContent).toBe(
      t("tasks.creator.title"),
    );
    expect(screen.getByTestId("chat-send").textContent).toBe(
      t("chat.composer.send"),
    );
  });

  it("renders a safe message without a client provider", () => {
    const router = createMemoryRouter([{ path: "*", element: <App /> }], {
      initialEntries: ["/"],
    });
    const view = render(<RouterProvider router={router} />);
    expect(view.container.textContent).toContain(t("errors.generic"));
  });
});

describe("app journey", () => {
  it("navigates from chat to agents live to projects to a project report", async () => {
    renderApp("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    fireEvent.click(screen.getByTestId("team-open-agents"));
    const badges = await screen.findAllByTestId("agent-badge-LOCAL");
    expect(badges.length).toBeGreaterThanOrEqual(1);
    expect(await within(screen.getByTestId("app-main")).findByTestId("agents-live-rows")).toBeTruthy();
    fireEvent.click(screen.getByTestId("menu-new-task"));
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    fireEvent.click(screen.getByTestId("menu-projects"));
    expect(await screen.findByTestId("project-row-p-1")).toBeTruthy();
    fireEvent.click(screen.getByTestId("project-open-p-1"));
    fireEvent.click(screen.getByTestId("menu-results"));
    expect(
      (await screen.findByTestId("project-report-export")).textContent,
    ).toContain("pkg-1");
    expect(
      (await screen.findByTestId("project-report-derived")).textContent,
    ).toContain(t("projects.derived.label"));
  });

  it("renders the project overview from served records", async () => {
    renderApp("/projects/p-1/overview");
    expect((await screen.findByTestId("overview-name")).textContent).toContain(
      "n-1",
    );
    expect(
      (await screen.findByTestId("overview-task-count")).textContent,
    ).toContain("1");
    expect(
      (await screen.findByTestId("overview-wall-total")).textContent,
    ).toContain("60");
  });

  it("renders every project subview from the route table", async () => {
    const views = [
      "overview",
      "tasks",
      "runs",
      "time",
      "ai-usage",
      "tokens",
      "cost",
      "local-ai",
      "cloud-ai",
      "models",
      "routing-decisions",
      "audits",
      "errors",
      "reports",
    ];
    for (const view of views) {
      renderApp(`/projects/p-1/${view}`);
      expect(await screen.findByTestId("project-menu-overview")).toBeTruthy();
      const menus = document.querySelectorAll(
        '[data-testid^="project-menu-"]',
      );
      expect(menus.length).toBe(15);
      cleanup();
    }
  });

  it("mounts the team quick fix on the models route from served data", async () => {
    const client = new FakeApiClient({
      routingWhyByDecision: {
        "d-9": {
          decision: { decision_id: "d-9", policy_ref: "pol-9" },
          assignments: [
            {
              decision_id: "d-9",
              role: "manager",
              provider_id: "prov-9",
              model: "mod-9",
            },
          ],
          snapshot: {
            decision_id: "d-9",
            snapshot_ref: "snap-9",
            captured_at: "t-9",
          },
          reason: {
            task_class: "tc-9",
            fit_basis: "fb-9",
            price_basis: "KNOWN",
            quality_basis: "MEASURED",
            rejected: [],
          },
        },
      },
    });
    renderApp("/projects/p-1/models?decision=d-9", client);
    expect(await screen.findByTestId("team-quickfix")).toBeTruthy();
    expect(screen.getByTestId("quickfix-provider").textContent).toBe("prov-9");
    expect(screen.getByTestId("quickfix-model").textContent).toBe("mod-9");
  });
});

describe("app lane B routes", () => {
  it("mounts the settings index with every named section", async () => {
    renderApp("/settings");
    expect(await screen.findByTestId("settings-link-project")).toBeTruthy();
    expect(await screen.findByTestId("settings-link-localbench")).toBeTruthy();
    const links = document.querySelectorAll('[data-testid^="settings-link-"]');
    expect(links.length).toBe(10);
  });

  it("mounts the settings project section read-only", async () => {
    renderApp("/settings/project");
    expect(await screen.findByText(t("settings.roleProfile.title"))).toBeTruthy();
    expect(await screen.findByText(t("settings.risk.label"))).toBeTruthy();
  });

  it("mounts the first run flow", async () => {
    renderApp("/firstrun");
    expect(await screen.findByText(t("firstrun.title"))).toBeTruthy();
    expect(await screen.findByText(t("firstrun.next"))).toBeTruthy();
  });

  it("mounts about, migration and how-it-works read-only", async () => {
    renderApp("/about");
    expect(await screen.findByText("Agent SI")).toBeTruthy();
    cleanup();
    renderApp("/migration");
    expect(
      await screen.findByText(t("migration.keepsOldCopies")),
    ).toBeTruthy();
    cleanup();
    renderApp("/how-it-works");
    expect(await screen.findByText(t("howItWorks.runs.body"))).toBeTruthy();
  });
});
