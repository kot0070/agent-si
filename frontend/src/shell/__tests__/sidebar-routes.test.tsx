/** @vitest-environment jsdom
 *
 * FXLOCALE1 durable test: the REAL Sidebar never renders the same route
 * twice. A section title plus a link to one route is allowed; two links
 * to one route are not.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { Sidebar } from "../Sidebar";

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

function renderSidebar(projectId: string): void {
  const router = createMemoryRouter([{ path: "/", element: <Sidebar projectId={projectId} /> }], {
    initialEntries: ["/"],
  });
  render(
    <ApiClientProvider client={new FakeApiClient({})}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

describe("sidebar routes", () => {
  it("renders no route twice", () => {
    renderSidebar("p-1");
    const sidebar = document.querySelector('[data-testid="sidebar"]') as HTMLElement;
    expect(sidebar).toBeTruthy();
    const hrefs = Array.from(sidebar.querySelectorAll("a"))
      .map((link) => link.getAttribute("href") ?? "")
      .filter((href) => href.length > 0);
    expect(hrefs.length).toBeGreaterThan(0);
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });
});
