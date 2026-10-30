/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../app/ApiClientProvider";
import { HttpApiClient } from "../api/client";
import { App, ROUTES } from "../app/App";
import { AGENT_SI_NAME, LICENCE_LINE } from "../app/About";
import { resetLocaleForTests, setLocale } from "../locale/index";
import en from "../locale/en.json";

function stubFetch(): void {
  vi.stubGlobal("fetch", async (input: unknown) => {
    const target = String(input);
    if (target.includes("/api/v1/projects")) {
      return new Response(JSON.stringify({ projects: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }
    if (target.includes("/api/v1/agents/live")) {
      return new Response(JSON.stringify({ agents: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }
    return new Response(JSON.stringify({ projects: [] }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  });
}

function renderAppAt(route: string): void {
  const router = createMemoryRouter([{ path: "*", element: <App /> }], {
    initialEntries: [route],
  });
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  stubFetch();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("untest3 ui rows over the real App route with fetch-boundary fake", () => {
  it("R-372 About route shows name plus licence line plus third-party MIT text", async () => {
    renderAppAt("/about");
    expect(await screen.findByText(AGENT_SI_NAME)).toBeTruthy();
    expect(await screen.findByText(LICENCE_LINE)).toBeTruthy();
    const about = await screen.findByText(AGENT_SI_NAME);
    const section = about.closest("section");
    expect(section).toBeTruthy();
    expect(section?.textContent).toContain(en.about.licence.line);
    expect(section?.textContent).toContain("MIT License");
    expect(section?.textContent).toContain(en.about.licence.mitText.slice(0, 24));
    expect(ROUTES.chat).toBe("/");
  });

  it("ARCH-679 every named menu and view is wired on the real shell", async () => {
    renderAppAt("/");
    expect(await screen.findByTestId("sidebar")).toBeTruthy();
    for (const id of [
      "menu-chat",
      "menu-agents-live",
      "menu-new-task",
      "menu-projects",
      "menu-tasks",
      "menu-results",
      "menu-settings",
    ]) {
      expect(await screen.findByTestId(id)).toBeTruthy();
    }
    expect(ROUTES.agentsLive).toBe("/agents/live");
    expect(ROUTES.projects).toBe("/projects");
    expect(ROUTES.projectReports).toBe("/projects/:projectId/reports");
  });
});
