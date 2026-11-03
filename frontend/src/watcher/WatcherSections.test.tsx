// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WatcherSections } from "./WatcherSections";
import { resetLocaleForTests, setLocale } from "../locale/index";

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("WatcherSections (RED: aggregator missing)", () => {
  it("mounts all four sections and fetches nothing", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<WatcherSections projectId="proj-s" />);
    expect(screen.getByTestId("watcher-fxrules")).toBeTruthy();
    expect(screen.getByTestId("watcher-presets")).toBeTruthy();
    expect(screen.getByTestId("watcher-alerts-section")).toBeTruthy();
    expect(screen.getByTestId("watcher-apps")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("renders the uk copy with no raw English section titles", () => {
    setLocale("uk");
    render(<WatcherSections projectId="proj-s" />);
    expect(screen.getByTestId("watcher-fxrules-title").textContent).toBe(
      "Картки правил",
    );
    expect(screen.getByTestId("watcher-presets-title").textContent).toBe(
      "Пресети",
    );
    expect(screen.getByTestId("watcher-alerts-title").textContent).toBe(
      "Сповіщення, таймери і цілісність",
    );
    expect(screen.getByTestId("watcher-apps-title").textContent).toBe(
      "Застосунки і служби",
    );
  });
});
