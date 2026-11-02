/** @vitest-environment jsdom */
// FXLANGEN: clean-install default UI language is English; a stored locale wins.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { App } from "../../app/App";
import { TopBar } from "../../shell/TopBar";
import {
  DEFAULT_LOCALE,
  LOCALE_STORAGE_KEY,
  resetLocaleForTests,
  t,
} from "../index";
import en from "../en.json";
import uk from "../uk.json";

beforeEach(() => {
  resetLocaleForTests();
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

function renderApp(): void {
  const router = createMemoryRouter([{ path: "*", element: <App /> }], {
    initialEntries: ["/"],
  });
  render(
    <ApiClientProvider client={new FakeApiClient({})}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

function renderTopBar(): void {
  const router = createMemoryRouter(
    [{ path: "/", element: <TopBar projectId="p-1" /> }],
    { initialEntries: ["/"] },
  );
  render(
    <ApiClientProvider client={new FakeApiClient({})}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

function languageSelect(): HTMLSelectElement {
  return screen.getByTestId("topbar-language") as HTMLSelectElement;
}

describe("fxlangen default English", () => {
  it("clean storage renders English chrome and the language select reads en", async () => {
    expect(DEFAULT_LOCALE).toBe("en");
    expect(t("tasks.creator.title")).toBe(en.tasks.creator.title);
    renderApp();
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    expect(languageSelect().value).toBe("en");
    expect(screen.getByTestId("menu-new-task").textContent).toBe(
      en.tasks.creator.title,
    );
    expect(screen.queryByText(uk.tasks.creator.title)).toBeNull();
  });

  it("a stored uk locale wins over the default", async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "uk");
    renderTopBar();
    expect(await screen.findByTestId("topbar-language")).toBeTruthy();
    expect(languageSelect().value).toBe("uk");
    expect(t("shell.topbar.language")).toBe(uk.shell.topbar.language);
    expect(t("tasks.creator.title")).toBe(uk.tasks.creator.title);
  });

  it("names the languages in words, never raw codes", async () => {
    renderTopBar();
    const select = await screen.findByTestId("topbar-language");
    const options = Array.from(
      (select as HTMLSelectElement).options,
    );
    expect(options.map((option) => option.value)).toEqual(["en", "uk"]);
    const labels = options.map((option) => option.text);
    expect(labels).toContain("English");
    expect(labels).toContain("Українська");
    expect(labels).not.toContain("en");
    expect(labels).not.toContain("uk");
  });

  it("uk locale names both languages in words", async () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "uk");
    renderTopBar();
    const select = await screen.findByTestId("topbar-language");
    const labels = Array.from(
      (select as HTMLSelectElement).options,
    ).map((option) => option.text);
    expect(labels).toContain("English");
    expect(labels).toContain("Українська");
    expect(labels).not.toContain("en");
    expect(labels).not.toContain("uk");
  });
});
