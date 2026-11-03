// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { WatcherPresets } from "./WatcherPresets";
import { isCardEnabled } from "./ruleOverrides";
import { loadWatcherPreset } from "./watcherPresetStore";
import { resetLocaleForTests, setLocale } from "../locale/index";

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("WatcherPresets (RED: component missing)", () => {
  it("marks standard current on a fresh project", () => {
    render(<WatcherPresets projectId="proj-p" />);
    expect(
      screen.getByTestId("watcher-preset-standard"),
    ).toHaveProperty("disabled", false);
    expect(
      screen.getByTestId("watcher-preset-standard").getAttribute("aria-pressed"),
    ).toBe("true");
    expect(screen.getByTestId("watcher-preset-strict")).toHaveProperty(
      "disabled",
      false,
    );
  });

  it("marks strict and survives a reload, switching card flags to match", () => {
    const { unmount } = render(<WatcherPresets projectId="proj-p" />);
    fireEvent.click(screen.getByTestId("watcher-preset-strict"));
    expect(loadWatcherPreset("proj-p")).toBe("strict");
    expect(
      screen.getByTestId("watcher-preset-strict").getAttribute("aria-pressed"),
    ).toBe("true");
    expect(isCardEnabled("card-tamper", "proj-p")).toBe(true);
    unmount();
    render(<WatcherPresets projectId="proj-p" />);
    expect(
      screen.getByTestId("watcher-preset-strict").getAttribute("aria-pressed"),
    ).toBe("true");
  });

  it("switching to cautious turns the guard and tamper cards off", () => {
    render(<WatcherPresets projectId="proj-p" />);
    fireEvent.click(screen.getByTestId("watcher-preset-strict"));
    fireEvent.click(screen.getByTestId("watcher-preset-cautious"));
    expect(loadWatcherPreset("proj-p")).toBe("cautious");
    expect(isCardEnabled("card-hang", "proj-p")).toBe(true);
    expect(isCardEnabled("card-guard", "proj-p")).toBe(false);
    expect(isCardEnabled("card-tamper", "proj-p")).toBe(false);
  });
});
