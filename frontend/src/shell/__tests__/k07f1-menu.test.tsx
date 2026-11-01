/** @vitest-environment jsdom */
// FXLAYOUT: the left nav holds exactly New task (chat empty composer),
// Projects, Results (current-project reports) and Settings; the single
// task entry points at the chat route. Owner redefinition quoted verbatim
// from kit BUILD_PLAN:850-852: "Layout on the Claude-desktop pattern: short
// left navigation (New task / Projects / Results / Settings), the
// conversation/task stream in the centre, compact cards on the right (Team
// now / Context / Results / Background work / Watcher)".
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { App } from "../../app/App";
import { resetLocaleForTests, setLocale } from "../../locale/index";

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  setLocale("en");
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

function renderAppAt(route: string): void {
  const router = createMemoryRouter([{ path: "*", element: <App /> }], {
    initialEntries: [route],
  });
  render(
    <ApiClientProvider client={new FakeApiClient({})}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

describe("sidebar menu hrefs with an active project", () => {
  it("points new task at the chat composer and results at reports", async () => {
    renderAppAt("/");
    await waitFor(() => {
      expect(screen.getByTestId("menu-new-task").getAttribute("href")).toBe(
        "/",
      );
    });
    expect(screen.queryByTestId("menu-tasks")).toBeNull();
    expect(screen.queryByTestId("menu-agents-live")).toBeNull();
    await waitFor(() => {
      expect(screen.getByTestId("menu-results").getAttribute("href")).toBe(
        "/projects/p-1/reports",
      );
    });
  });
});
