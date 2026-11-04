/** @vitest-environment jsdom */
// K07OPEN10 strip: two PARTIAL shell rows over the served shell path.
// kit BUILD_PLAN:1479 M-R-UX-1 one top bar; pairing as top strip, never overlay chrome
// kit BUILD_PLAN:1480 M-R-UX-2 one H2 plus explainer; jargon carries a Why chip
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { App } from "../../app/App";
import { SETTINGS_ROUTES } from "../../settings/index";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";

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

// kit BUILD_PLAN:1479 M-R-UX-1 one top bar; pairing as top strip, never overlay chrome
async function expectSingleTopBarWithStrip(): Promise<void> {
  const topbar = await screen.findByTestId("topbar");
  expect(topbar.tagName.toLowerCase()).toBe("header");
  expect(document.querySelectorAll('[data-testid="topbar"]').length).toBe(1);
  const strip = screen.getByTestId("pairing-strip");
  expect(strip.tagName.toLowerCase()).toBe("div");
  expect(topbar.contains(strip)).toBe(true);
  // FXFACTS F15: the top bar carries no watcher word; the strip holds
  // the placement badge only.
  expect(screen.queryByTestId("topbar-watcher")).toBeNull();
  expect(screen.queryByTestId("pairing-label")).toBeNull();
  const badge = strip.textContent ?? "";
  const badgeEl = screen.getByTestId("pairing-badge");
  expect(
    badge.includes(t("agents.badge.local")) ||
      badge.includes(t("agents.badge.cloud")) ||
      badge.includes(t("agents.badge.split")) ||
      badgeEl.hasAttribute("hidden"),
  ).toBe(true);
  const position = window.getComputedStyle(strip).position;
  expect(["fixed", "absolute"]).not.toContain(position);
  const marker = screen.getByTestId("k07open10-shell");
  expect(topbar.contains(marker)).toBe(true);
}

describe("k07open10 shell strip M-R-UX-1", () => {
  it("serves one topbar with the pairing strip inside it, never overlay chrome", async () => {
    renderAppAt("/");
    await expectSingleTopBarWithStrip();
  });
});

describe.each([
  // FXROLEPICK R6: /settings is the grouped index with its own title.
  { path: "/settings", titleKey: "settings.index.title" },
  ...SETTINGS_ROUTES.map((route) => ({
    path: `/settings/${route.path}`,
    titleKey: route.titleKey,
  })),
])(
  // kit BUILD_PLAN:1480 M-R-UX-2 one H2 plus explainer; jargon carries a Why chip
  "k07open10 settings page $path keeps one H2 plus explainer and a Why chip button",
  ({ path, titleKey }) => {
    it("renders the served SettingsLayout shape on the production call path", async () => {
      renderAppAt(path);
      await expectSingleTopBarWithStrip();
      const chip = await screen.findByTestId("settings-why-chip");
      expect(chip.tagName.toLowerCase()).toBe("button");
      expect(chip.getAttribute("type")).toBe("button");
      expect(chip.textContent).toBe(t("projects.why_this_model.title"));
      const section = chip.closest("section");
      expect(section).not.toBeNull();
      const topLevelH2 = Array.from(section?.children ?? []).filter(
        (node) => node.tagName.toLowerCase() === "h2",
      );
      expect(topLevelH2.length).toBe(1);
      expect(topLevelH2[0]?.textContent).toBe(t(titleKey));
      const explainer = Array.from(section?.querySelectorAll("p") ?? []).filter(
        (node) => (node.textContent ?? "").trim().length > 0,
      );
      expect(explainer.length).toBeGreaterThanOrEqual(1);
      expect(screen.getByTestId("k07open10-shell")).toBeTruthy();
    });
  },
);
