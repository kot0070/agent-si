/** @vitest-environment jsdom */
// FXRC1FIX P4: after a first-message project the select refetches instead
// of showing "Select a project"; the fresh options show the project name.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  render,
  screen,
} from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import type { ApiClient } from "../../api/iface";
import type { ProjectRecord } from "../../api/iface";
import {
  resetLocaleForTests,
  setLocale,
  t,
} from "../../locale/index";
import { TopBar } from "../TopBar";

const NEW_ID = "p-new-project-1";
const NEW_NAME = "Fresh From First Message";

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

describe("fxrc1fix P4 first-message project refetch", () => {
  it("shows the new project name instead of the placeholder", async () => {
    const lists: ProjectRecord[][] = [
      [],
      [{ project_id: NEW_ID, name: NEW_NAME, created_at: "t-0" }],
    ];
    let calls = 0;
    const stub = {
      listProjects: async (): Promise<ProjectRecord[]> =>
        lists[Math.min(calls++, lists.length - 1)] ?? [],
      listAgentsLive: async () => [],
    } as unknown as ApiClient;
    const router = createMemoryRouter(
      [{ path: "/", element: <TopBar projectId={NEW_ID} /> }],
      { initialEntries: ["/"] },
    );
    render(
      <ApiClientProvider client={stub}>
        <RouterProvider router={router} />
      </ApiClientProvider>,
    );
    expect(await screen.findByText(NEW_NAME)).toBeTruthy();
    const select = screen.getByTestId("topbar-project") as HTMLSelectElement;
    expect(select.value).toBe(NEW_ID);
    expect(select.textContent).toContain(NEW_NAME);
    expect(select.textContent).not.toContain(
      t("shell.topbar.projectPlaceholder"),
    );
    expect(calls).toBeGreaterThan(1);
  });
});
