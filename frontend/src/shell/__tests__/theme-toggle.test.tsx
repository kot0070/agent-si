/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { THEME_STORAGE_KEY, applyTheme, readTheme } from "../theme";
import { ThemeToggle } from "../ThemeToggle";

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

describe("theme state", () => {
  it("defaults to dark and applies it to the document root", () => {
    expect(readTheme()).toBe("dark");
    applyTheme(readTheme());
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("persists the chosen theme and reads it back", () => {
    applyTheme("light");
    expect(readTheme()).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });

  it("ignores unknown stored values and keeps the dark default", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "neon");
    expect(readTheme()).toBe("dark");
  });
});

describe("ThemeToggle", () => {
  it("toggles the root theme and persists the choice", () => {
    render(<ThemeToggle />);
    const button = screen.getByTestId("theme-toggle");
    expect(button.getAttribute("data-theme-value")).toBe("dark");
    fireEvent.click(button);
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(button.getAttribute("data-theme-value")).toBe("light");
    fireEvent.click(button);
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
  });

  it("labels itself with the appearance locale keys in both languages", () => {
    setLocale("en");
    const view = render(<ThemeToggle />);
    const button = screen.getByTestId("theme-toggle");
    expect(button.textContent).toContain(t("settings.appearance.title"));
    expect(button.getAttribute("title")).toBe(
      t("settings.appearance.needItNow"),
    );
    view.unmount();
    cleanup();
    setLocale("uk");
    render(<ThemeToggle />);
    const ukButton = screen.getByTestId("theme-toggle");
    expect(ukButton.textContent).toContain(t("settings.appearance.title"));
    expect(ukButton.textContent).not.toContain("Appearance");
  });

  it("names the theme in words, never a raw token", () => {
    setLocale("en");
    const view = render(<ThemeToggle />);
    expect(screen.getByTestId("theme-toggle").textContent).toContain(
      t("settings.appearance.dark"),
    );
    view.unmount();
    cleanup();
    setLocale("uk");
    render(<ThemeToggle />);
    const ukButton = screen.getByTestId("theme-toggle");
    expect(ukButton.textContent).toContain("темна");
    expect(ukButton.textContent).not.toContain(": dark");
    expect(ukButton.textContent).not.toContain(": light");
  });
});
