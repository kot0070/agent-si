/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/client";
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
  it("points task entries at the project tasks view and results at reports", async () => {
    renderAppAt("/");
    await waitFor(() => {
      expect(screen.getByTestId("menu-tasks").getAttribute("href")).toBe(
        "/projects/p-1/tasks",
      );
    });
    expect(screen.getByTestId("menu-new-task").getAttribute("href")).toBe(
      "/projects/p-1/tasks",
    );
    expect(screen.getByTestId("menu-results").getAttribute("href")).toBe(
      "/projects/p-1/reports",
    );
  });
});
