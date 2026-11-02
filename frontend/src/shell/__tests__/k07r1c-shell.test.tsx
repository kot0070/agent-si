/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  Link,
  RouterProvider,
  createMemoryRouter,
  useLocation,
} from "react-router-dom";
import type { ReactElement } from "react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { App } from "../../app/App";
import { ClosingGuard } from "../ClosingGuard";

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

function stubScheme(dark: boolean): void {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: 375,
  });
  const matchMedia = (query: string) => ({
    matches: query === "(prefers-color-scheme: dark)" && dark,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: matchMedia,
  });
}

function renderAppAt(path: string): void {
  const router = createMemoryRouter([{ path: "*", element: <App /> }], {
    initialEntries: [path],
  });
  render(
    <ApiClientProvider client={new FakeApiClient({})}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

function LocationProbe(): ReactElement {
  const location = useLocation();
  return <span data-testid="guard-location">{location.pathname}</span>;
}

describe.each([false, true])("k07r1c shell rows (dark=%s)", (dark) => {
  it("D1 pairing strip lives inside the single top bar on the real home page", async () => {
    stubScheme(dark);
    renderAppAt("/");
    const topbar = await screen.findByTestId("topbar");
    expect(topbar.tagName.toLowerCase()).toBe("header");
    expect(document.querySelectorAll('[data-testid="topbar"]').length).toBe(1);
    const strip = await screen.findByTestId("pairing-strip");
    expect(topbar.contains(strip)).toBe(true);
    expect(strip.textContent).toContain(t("shell.topbar.watcher"));
    const badge = strip.textContent ?? "";
    const badgeEl = screen.getByTestId("pairing-badge");
    expect(
      badge.includes(t("agents.badge.local")) ||
        badge.includes(t("agents.badge.cloud")) ||
        badge.includes(t("agents.badge.split")) ||
        badgeEl.hasAttribute("hidden"),
    ).toBe(true);
  });

  it("D2 settings page keeps one H2 plus a Why chip", async () => {
    stubScheme(dark);
    renderAppAt("/settings/general");
    const chip = await screen.findByTestId("settings-why-chip");
    expect(chip.textContent).toBe(t("projects.why_this_model.title"));
    const section = chip.closest("section");
    expect(section).not.toBeNull();
    expect(section?.querySelectorAll("h2").length).toBe(1);
  });

  it("D3 destructive Leave is primary and undo restores the guarded location", async () => {
    stubScheme(dark);
    const router = createMemoryRouter(
      [
        {
          path: "*",
          element: (
            <>
              <ClosingGuard armed confirmKey="shell.closing.confirm">
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
    expect(await screen.findByTestId("guard-body")).toBeTruthy();
    fireEvent.click(screen.getByTestId("guard-go"));
    expect(await screen.findByTestId("closing-confirm")).toBeTruthy();
    expect(screen.getByTestId("closing-leave").textContent).toBe(
      t("shell.closing.leave"),
    );
    expect(screen.getByTestId("closing-stay").textContent).toBe(
      t("shell.closing.stay"),
    );
    expect(document.activeElement).toBe(screen.getByTestId("closing-leave"));
    fireEvent.click(screen.getByTestId("closing-leave"));
    await waitFor(() => {
      expect(screen.getByTestId("guard-location").textContent).toBe("/guard-b");
    });
    expect(screen.queryByTestId("closing-confirm")).toBeNull();
    const undo = await screen.findByTestId("closing-undo");
    expect(undo.textContent).toBe(t("ui.error.retry"));
    fireEvent.click(undo);
    await waitFor(() => {
      expect(screen.getByTestId("guard-location").textContent).toBe("/guard-a");
    });
    expect(screen.queryByTestId("closing-undo")).toBeNull();
    fireEvent.click(screen.getByTestId("guard-go"));
    expect(await screen.findByTestId("closing-confirm")).toBeTruthy();
  });
});
